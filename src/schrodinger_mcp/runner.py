"""The subprocess boundary between our (normal-venv) MCP layer and Schrödinger's
bundled Python / launchers.

Two entry points:
- ``run_worker``: execute one of our worker scripts under ``$SCHRODINGER/run python3``.
  Workers import ``schrodinger`` and emit a single sentinel-tagged JSON line.
- ``run_launcher``: execute a Schrödinger launcher binary directly (e.g. structconvert)
  and return the completed process.

Everything is argv-list based (never a shell string), so spaces in paths are safe.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from typing import Optional, Sequence

from . import config, installation
from .errors import LicenseError, Timeout, WorkerError, looks_like_license_error

#: Workers print their result on a line prefixed with this sentinel.
RESULT_SENTINEL = "__SMCP_RESULT__"

WORKERS_DIR = Path(__file__).parent / "workers"


def _worker_path(name: str) -> Path:
    p = WORKERS_DIR / f"{name}.py"
    if not p.exists():
        raise WorkerError(f"worker script not found: {name}", path=str(p))
    return p


def _extract_result(stdout: str) -> Optional[dict]:
    """Find the last sentinel-tagged JSON line in stdout."""
    result = None
    for line in stdout.splitlines():
        if line.startswith(RESULT_SENTINEL):
            payload = line[len(RESULT_SENTINEL):]
            try:
                result = json.loads(payload)
            except json.JSONDecodeError:
                continue
    return result


def run_worker(
    name: str,
    payload: dict,
    timeout: Optional[int] = None,
) -> dict:
    """Run worker ``name`` with ``payload`` (serialized to a temp JSON file).

    Returns the worker's ``data`` dict on success. Raises WorkerError / LicenseError /
    Timeout on failure.
    """
    timeout = timeout or config.SYNC_TIMEOUT
    config.ensure_dirs()
    payload_file = config.scratch_dir() / f"payload_{uuid.uuid4().hex}.json"
    payload_file.write_text(json.dumps(payload))
    cmd = [
        str(installation.run_path()),
        "python3",
        str(_worker_path(name)),
        str(payload_file),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=installation.child_env(),
        )
    except subprocess.TimeoutExpired:
        raise Timeout(
            f"worker '{name}' exceeded {timeout}s; consider an async submission for large inputs",
            worker=name,
        )
    finally:
        payload_file.unlink(missing_ok=True)

    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if looks_like_license_error(combined):
        raise LicenseError(
            f"license checkout failed while running '{name}'",
            detail=_tail(proc.stderr or combined),
        )

    result = _extract_result(proc.stdout or "")
    if result is None:
        raise WorkerError(
            f"worker '{name}' produced no parseable result (exit {proc.returncode})",
            stderr=_tail(proc.stderr),
        )
    if not result.get("ok"):
        raise WorkerError(
            result.get("error", f"worker '{name}' failed"),
            type=result.get("type"),
            traceback=_tail(result.get("traceback")),
        )
    return result.get("data", {})


def run_launcher(
    argv: Sequence[str],
    cwd: Optional[Path] = None,
    timeout: Optional[int] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run a Schrödinger launcher binary directly (argv[0] is an absolute tool path).

    Used for fast utilities like structconvert/structcat/getpdb that aren't worth a
    full job-control submission. Raises WorkerError on non-zero exit when ``check``.
    """
    timeout = timeout or config.SYNC_TIMEOUT
    try:
        proc = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            env=installation.child_env(),
        )
    except subprocess.TimeoutExpired:
        raise Timeout(f"command exceeded {timeout}s: {Path(argv[0]).name}")

    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if looks_like_license_error(combined):
        raise LicenseError(
            f"license checkout failed: {Path(argv[0]).name}",
            detail=_tail(proc.stderr or combined),
        )
    if check and proc.returncode != 0:
        raise WorkerError(
            f"{Path(argv[0]).name} exited {proc.returncode}",
            stderr=_tail(proc.stderr) or _tail(proc.stdout),
        )
    return proc


def _tail(text: Optional[str], limit: int = 1500) -> str:
    if not text:
        return ""
    text = text.strip()
    return text[-limit:]
