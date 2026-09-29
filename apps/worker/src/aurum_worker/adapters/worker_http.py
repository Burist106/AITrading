"""Bounded authenticated Worker RPC transport with no credential discovery."""

from __future__ import annotations

import http.client
import ipaddress
import json
import math
from enum import StrEnum
from time import monotonic
from urllib.parse import urlsplit

from pydantic import SecretStr

_FUNCTIONS = frozenset(
    {
        "worker_record_mt5_account_observation",
        "worker_record_mt5_symbol_observation",
        "worker_upsert_mt5_latest_tick",
        "worker_read_mt5_reconciliation_state",
        "worker_begin_reconciliation",
        "worker_record_reconciliation_mismatch",
        "worker_complete_reconciliation",
        "worker_record_heartbeat",
        "worker_record_incident",
        "worker_read_shadow_context",
        "worker_read_shadow_cycles",
        "worker_record_shadow_cycle",
        "worker_append_shadow_outcome",
    }
)
_MAX_REQUEST_BYTES = 262_144
_MAX_RESPONSE_BYTES = 4_194_304


class WorkerRpcErrorCode(StrEnum):
    CONFIGURATION_INVALID = "RPC_CONFIGURATION_INVALID"
    FUNCTION_NOT_ALLOWED = "RPC_FUNCTION_NOT_ALLOWED"
    REQUEST_INVALID = "RPC_REQUEST_INVALID"
    REQUEST_TOO_LARGE = "RPC_REQUEST_TOO_LARGE"
    AUTH_REJECTED = "RPC_AUTH_REJECTED"
    REDIRECT_REJECTED = "RPC_REDIRECT_REJECTED"
    HTTP_ERROR = "RPC_HTTP_ERROR"
    RESPONSE_TOO_LARGE = "RPC_RESPONSE_TOO_LARGE"
    RESPONSE_INVALID = "RPC_RESPONSE_INVALID"
    TRANSPORT_UNAVAILABLE = "RPC_TRANSPORT_UNAVAILABLE"


class WorkerRpcTransportError(RuntimeError):
    def __init__(self, code: WorkerRpcErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


def _header_secret(value: SecretStr) -> bool:
    raw = value.get_secret_value()
    return 1 <= len(raw) <= 8192 and all(32 < ord(char) < 127 for char in raw)


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("nonfinite JSON value")


class HttpsWorkerRpcClient:
    """No redirects, implicit proxy, retries, auth issuance, or secret logging.

    The caller supplies credentials and the intended service origin. Socket waits
    are bounded; body reads additionally share a monotonic response deadline.
    Plain HTTP is accepted only for an explicitly opted-in literal loopback host.
    """

    def __init__(
        self,
        base_url: str,
        bearer_token: SecretStr,
        *,
        api_key: SecretStr | None = None,
        allow_loopback_http: bool = False,
        timeout_seconds: float = 5.0,
    ) -> None:
        try:
            if not isinstance(base_url, str) or not isinstance(bearer_token, SecretStr):
                raise ValueError
            if api_key is not None and not isinstance(api_key, SecretStr):
                raise ValueError
            if type(allow_loopback_http) is not bool:
                raise ValueError
            if (
                type(timeout_seconds) not in (int, float)
                or not math.isfinite(timeout_seconds)
                or not 0 < timeout_seconds <= 30
            ):
                raise ValueError
            parsed = urlsplit(base_url)
            host = parsed.hostname
            if (
                host is None
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or parsed.path not in ("", "/")
                or any(ord(char) <= 32 or ord(char) >= 127 for char in base_url)
            ):
                raise ValueError
            if parsed.scheme == "http":
                if (
                    not allow_loopback_http
                    or not ipaddress.ip_address(host).is_loopback
                ):
                    raise ValueError
            elif parsed.scheme != "https":
                raise ValueError
            port = parsed.port
            if port is not None and not 1 <= port <= 65535:
                raise ValueError
            if not _header_secret(bearer_token) or (
                api_key is not None and not _header_secret(api_key)
            ):
                raise ValueError
        except Exception:
            raise WorkerRpcTransportError(
                WorkerRpcErrorCode.CONFIGURATION_INVALID
            ) from None
        self._host = host
        self._port = port
        self._https = parsed.scheme == "https"
        self._token = bearer_token
        self._api_key = api_key
        self._timeout = float(timeout_seconds)

    def call(self, function: str, parameters: dict[str, object]) -> dict[str, object]:
        if not isinstance(function, str) or function not in _FUNCTIONS:
            raise WorkerRpcTransportError(WorkerRpcErrorCode.FUNCTION_NOT_ALLOWED)
        try:
            if not isinstance(parameters, dict) or not all(
                isinstance(key, str) for key in parameters
            ):
                raise ValueError
            body = json.dumps(
                parameters, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
        except Exception:
            raise WorkerRpcTransportError(WorkerRpcErrorCode.REQUEST_INVALID) from None
        if len(body) > _MAX_REQUEST_BYTES:
            raise WorkerRpcTransportError(WorkerRpcErrorCode.REQUEST_TOO_LARGE)
        connection: http.client.HTTPConnection | None = None
        try:
            connection_type = (
                http.client.HTTPSConnection
                if self._https
                else http.client.HTTPConnection
            )
            connection = connection_type(self._host, self._port, timeout=self._timeout)
            headers = {
                "Authorization": "Bearer " + self._token.get_secret_value(),
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            }
            if self._api_key is not None:
                headers["apikey"] = self._api_key.get_secret_value()
            connection.request(
                "POST", "/rest/v1/rpc/" + function, body=body, headers=headers
            )
            response = connection.getresponse()
            if 300 <= response.status < 400:
                raise WorkerRpcTransportError(WorkerRpcErrorCode.REDIRECT_REJECTED)
            if response.status in (401, 403):
                raise WorkerRpcTransportError(WorkerRpcErrorCode.AUTH_REJECTED)
            if response.status != 200:
                raise WorkerRpcTransportError(WorkerRpcErrorCode.HTTP_ERROR)
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise WorkerRpcTransportError(WorkerRpcErrorCode.RESPONSE_INVALID)
            if response.getheader("Content-Type", "").split(";", 1)[0].strip() != (
                "application/json"
            ):
                raise WorkerRpcTransportError(WorkerRpcErrorCode.RESPONSE_INVALID)
            declared = response.getheader("Content-Length")
            if declared is not None:
                if not declared.isdecimal():
                    raise WorkerRpcTransportError(WorkerRpcErrorCode.RESPONSE_INVALID)
                if int(declared) > _MAX_RESPONSE_BYTES:
                    raise WorkerRpcTransportError(WorkerRpcErrorCode.RESPONSE_TOO_LARGE)
            deadline = monotonic() + self._timeout
            raw = bytearray()
            while True:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(min(65536, _MAX_RESPONSE_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > _MAX_RESPONSE_BYTES:
                    raise WorkerRpcTransportError(WorkerRpcErrorCode.RESPONSE_TOO_LARGE)
            if declared is not None and len(raw) != int(declared):
                raise WorkerRpcTransportError(WorkerRpcErrorCode.RESPONSE_INVALID)
            try:
                result: object = json.loads(
                    raw.decode("utf-8"),
                    object_pairs_hook=_json_object,
                    parse_constant=_invalid_constant,
                )
                if not isinstance(result, dict):
                    raise ValueError
            except Exception:
                raise WorkerRpcTransportError(
                    WorkerRpcErrorCode.RESPONSE_INVALID
                ) from None
            return result
        except WorkerRpcTransportError:
            raise
        except Exception:
            raise WorkerRpcTransportError(
                WorkerRpcErrorCode.TRANSPORT_UNAVAILABLE
            ) from None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
