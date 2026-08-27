from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

ALLOWED_MT5_METHODS = frozenset(
    {
        "account_info",
        "copy_rates_from_pos",
        "copy_rates_range",
        "history_deals_get",
        "history_orders_get",
        "initialize",
        "last_error",
        "orders_get",
        "positions_get",
        "shutdown",
        "symbol_info",
        "symbol_info_tick",
        "symbols_get",
        "terminal_info",
        "version",
    }
)
FORBIDDEN_METHODS = frozenset(
    {
        "login",
        "market_book_add",
        "market_book_release",
        "order_calc_margin",
        "order_calc_profit",
        "order_check",
        "order_send",
        "symbol_select",
    }
)
NATIVE_ADAPTER_NAME = "native_mt5.py"


def _is_mt5_receiver(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return "mt5" in node.id.lower()
    if isinstance(node, ast.Attribute):
        return "mt5" in node.attr.lower() or node.attr in {"_module", "module"}
    return False


def scan_source(source: str, reference: str) -> list[dict[str, object]]:
    try:
        tree = ast.parse(source, filename=reference)
    except SyntaxError:
        return [
            {"reference": reference, "line": 1, "category": "invalid Python syntax"}
        ]

    findings: list[dict[str, object]] = []
    native_file = Path(reference).name == NATIVE_ADAPTER_NAME
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            module = node.module if isinstance(node, ast.ImportFrom) else None
            if module:
                names.append(module)
            if any(name == "MetaTrader5" for name in names) and not native_file:
                findings.append(
                    {
                        "reference": reference,
                        "line": node.lineno,
                        "category": "MetaTrader5 import outside native adapter",
                    }
                )
        if not isinstance(node, ast.Call):
            continue
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "setattr"}
            and (not node.args or _is_mt5_receiver(node.args[0]))
        ):
            findings.append(
                {
                    "reference": reference,
                    "line": node.lineno,
                    "category": "forbidden dynamic MT5 dispatch",
                }
            )
        if isinstance(node.func, ast.Attribute):
            method = node.func.attr
            if method in FORBIDDEN_METHODS:
                findings.append(
                    {
                        "reference": reference,
                        "line": node.lineno,
                        "category": f"forbidden MT5 call: {method}",
                    }
                )
            if (
                native_file
                and _is_mt5_receiver(node.func.value)
                and method not in ALLOWED_MT5_METHODS
            ):
                findings.append(
                    {
                        "reference": reference,
                        "line": node.lineno,
                        "category": f"MT5 call outside allowlist: {method}",
                    }
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    findings: list[dict[str, object]] = []
    for file_name in args.files:
        path = Path(file_name)
        findings.extend(scan_source(path.read_text(encoding="utf-8"), file_name))
    print(json.dumps(findings, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
