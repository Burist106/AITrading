from __future__ import annotations

import http.client
import json
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import NamedTuple

import pytest
from pydantic import SecretStr

from aurum_worker.adapters.worker_http import (
    HttpsWorkerRpcClient,
    WorkerRpcErrorCode,
    WorkerRpcTransportError,
)


class Received(NamedTuple):
    path: str
    body: bytes
    authorization: str | None
    api_key: str | None


@contextmanager
def endpoint(
    *,
    status: int = 200,
    body: bytes = b'{"ok":true}',
    headers: dict[str, str] | None = None,
) -> Iterator[tuple[str, list[Received]]]:
    requests: list[Received] = []
    additions = headers or {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            requests.append(
                Received(
                    self.path,
                    self.rfile.read(int(self.headers["Content-Length"])),
                    self.headers.get("Authorization"),
                    self.headers.get("apikey"),
                )
            )
            self.send_response(status)
            self.send_header(
                "Content-Type", additions.get("Content-Type", "application/json")
            )
            self.send_header(
                "Content-Length", additions.get("Content-Length", str(len(body)))
            )
            for key, value in additions.items():
                if key not in ("Content-Type", "Content-Length"):
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_concrete_transport_sends_one_authenticated_post_with_exact_payload() -> None:
    with endpoint() as (origin, requests):
        client = HttpsWorkerRpcClient(
            origin,
            SecretStr("fictional-worker-test-token"),
            api_key=SecretStr("fictional-api-test-key"),
            allow_loopback_http=True,
        )
        result = client.call(
            "worker_read_shadow_context", {"p_trading_account_id": "test-id"}
        )
        assert result == {"ok": True}
        assert len(requests) == 1
        request = requests[0]
        assert request.path == "/rest/v1/rpc/worker_read_shadow_context"
        assert json.loads(request.body) == {"p_trading_account_id": "test-id"}
        assert request.authorization == "Bearer fictional-worker-test-token"
        assert request.api_key == "fictional-api-test-key"
        assert "fictional" not in repr(client)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "http://127.0.0.1",
        "ftp://example.com",
        "https://user@example.com",
        "https://example.com/path",
        "https://example.com?query=x",
        "https://example.com#fragment",
        "https://example.com:99999",
        "https://example.com\r\nHeader:value",
    ],
)
def test_invalid_or_plaintext_service_origins_are_rejected(url: str) -> None:
    with pytest.raises(WorkerRpcTransportError) as raised:
        HttpsWorkerRpcClient(url, SecretStr("fictional-token"))
    assert raised.value.code is WorkerRpcErrorCode.CONFIGURATION_INVALID
    assert url not in str(raised.value)


@pytest.mark.parametrize(
    "url", ["http://example.com", "http://localhost", "http://192.0.2.1"]
)
def test_loopback_opt_in_does_not_allow_remote_or_name_resolved_plaintext(
    url: str,
) -> None:
    with pytest.raises(WorkerRpcTransportError):
        HttpsWorkerRpcClient(
            url, SecretStr("fictional-token"), allow_loopback_http=True
        )


@pytest.mark.parametrize("timeout", [0, -1, 31, float("nan"), float("inf"), True])
def test_transport_timeout_must_be_finite_and_bounded(timeout: float) -> None:
    with pytest.raises(WorkerRpcTransportError):
        HttpsWorkerRpcClient(
            "https://worker.example",
            SecretStr("fictional-token"),
            timeout_seconds=timeout,
        )


@pytest.mark.parametrize(
    "token", ["", "bad\nheader", "bad\rheader", "bad token", "x" * 8193]
)
def test_injected_header_credentials_are_validated_without_disclosure(
    token: str,
) -> None:
    with pytest.raises(WorkerRpcTransportError) as raised:
        HttpsWorkerRpcClient("https://worker.example", SecretStr(token))
    assert str(raised.value) == "RPC_CONFIGURATION_INVALID"


@pytest.mark.parametrize(
    "function",
    ["worker_claim_command", "order_send", "../unexpected", "worker_apply_command"],
)
def test_transport_has_no_command_consumption_or_arbitrary_rpc_capability(
    function: str,
) -> None:
    client = HttpsWorkerRpcClient(
        "https://worker.example", SecretStr("fictional-token")
    )
    with pytest.raises(WorkerRpcTransportError) as raised:
        client.call(function, {})
    assert raised.value.code is WorkerRpcErrorCode.FUNCTION_NOT_ALLOWED


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (301, WorkerRpcErrorCode.REDIRECT_REJECTED),
        (307, WorkerRpcErrorCode.REDIRECT_REJECTED),
        (401, WorkerRpcErrorCode.AUTH_REJECTED),
        (403, WorkerRpcErrorCode.AUTH_REJECTED),
        (429, WorkerRpcErrorCode.HTTP_ERROR),
        (500, WorkerRpcErrorCode.HTTP_ERROR),
    ],
)
def test_http_failures_never_retry_follow_redirect_or_expose_response(
    status: int, code: WorkerRpcErrorCode
) -> None:
    with endpoint(
        status=status,
        body=b'"private remote detail"',
        headers={"Location": "https://other.example"},
    ) as (origin, requests):
        client = HttpsWorkerRpcClient(
            origin, SecretStr("fictional-token"), allow_loopback_http=True
        )
        with pytest.raises(WorkerRpcTransportError) as raised:
            client.call("worker_read_shadow_cycles", {})
        assert raised.value.code is code
        assert "private" not in str(raised.value)
        assert len(requests) == 1


@pytest.mark.parametrize(
    "body", [b"[]", b"null", b"{", b'{"a":1,"a":2}', b'{"x":NaN}', b"\xff"]
)
def test_malformed_json_or_non_object_response_is_rejected(body: bytes) -> None:
    with endpoint(body=body) as (origin, _requests):
        client = HttpsWorkerRpcClient(
            origin, SecretStr("fictional-token"), allow_loopback_http=True
        )
        with pytest.raises(WorkerRpcTransportError) as raised:
            client.call("worker_read_shadow_cycles", {})
        assert raised.value.code is WorkerRpcErrorCode.RESPONSE_INVALID


@pytest.mark.parametrize(
    ("headers", "code"),
    [
        ({"Content-Length": "4194305"}, WorkerRpcErrorCode.RESPONSE_TOO_LARGE),
        ({"Content-Encoding": "gzip"}, WorkerRpcErrorCode.RESPONSE_INVALID),
        ({"Content-Type": "text/html"}, WorkerRpcErrorCode.RESPONSE_INVALID),
        ({"Content-Length": "-1"}, WorkerRpcErrorCode.RESPONSE_INVALID),
    ],
)
def test_response_metadata_is_bounded(
    headers: dict[str, str], code: WorkerRpcErrorCode
) -> None:
    with endpoint(headers=headers) as (origin, _requests):
        client = HttpsWorkerRpcClient(
            origin, SecretStr("fictional-token"), allow_loopback_http=True
        )
        with pytest.raises(WorkerRpcTransportError) as raised:
            client.call("worker_read_shadow_cycles", {})
        assert raised.value.code is code


def test_https_connection_failure_is_sanitized_without_credential_or_provider_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenConnection(http.client.HTTPSConnection):
        def connect(self) -> None:
            raise OSError("remote internal detail")

    monkeypatch.setattr(http.client, "HTTPSConnection", BrokenConnection)
    client = HttpsWorkerRpcClient(
        "https://worker.example", SecretStr("fictional-token")
    )
    with pytest.raises(WorkerRpcTransportError) as raised:
        client.call("worker_read_shadow_cycles", {})
    assert str(raised.value) == "RPC_TRANSPORT_UNAVAILABLE"
    assert raised.value.__cause__ is None


def test_invalid_and_oversized_requests_are_rejected_before_transport() -> None:
    client = HttpsWorkerRpcClient(
        "https://worker.example", SecretStr("fictional-token")
    )
    with pytest.raises(WorkerRpcTransportError) as raised:
        client.call("worker_record_shadow_cycle", {"p_cycle": "x" * 262144})
    assert raised.value.code is WorkerRpcErrorCode.REQUEST_TOO_LARGE
    with pytest.raises(WorkerRpcTransportError) as raised:
        client.call("worker_record_shadow_cycle", {"p_cycle": float("nan")})
    assert raised.value.code is WorkerRpcErrorCode.REQUEST_INVALID
