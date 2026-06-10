"""Worker-side I/O contract.

Workers run under ``$SCHRODINGER/run python3`` (Schrödinger's bundled Python 3.11),
so this module may ONLY import the stdlib and ``schrodinger`` — never the
``schrodinger_mcp`` package (different interpreter / dependency set).

A worker is invoked as::

    $SCHRODINGER/run python3 <worker>.py <payload.json>

It reads the JSON payload, does its work, and prints exactly one result line:

    __SMCP_RESULT__{"ok": true, "data": {...}}

Schrödinger libraries are chatty on stdout/stderr; the sentinel prefix lets the
parent reliably find the result among the noise.
"""

import json
import sys
import traceback

RESULT_SENTINEL = "__SMCP_RESULT__"


def read_payload() -> dict:
    if len(sys.argv) < 2:
        return {}
    with open(sys.argv[1]) as fh:
        return json.load(fh)


def emit(data: dict) -> None:
    sys.stdout.write(RESULT_SENTINEL + json.dumps({"ok": True, "data": data}) + "\n")
    sys.stdout.flush()


def emit_error(message: str, etype: str = "WorkerError", **extra) -> None:
    payload = {"ok": False, "error": str(message), "type": etype}
    payload.update(extra)
    sys.stdout.write(RESULT_SENTINEL + json.dumps(payload) + "\n")
    sys.stdout.flush()


def main(fn) -> None:
    """Run ``fn(payload) -> dict`` with uniform error handling."""
    try:
        data = fn(read_payload())
        emit(data if data is not None else {})
    except Exception as exc:  # noqa: BLE001 - report everything cleanly to the parent
        emit_error(str(exc), etype=type(exc).__name__, traceback=traceback.format_exc())
        sys.exit(1)
