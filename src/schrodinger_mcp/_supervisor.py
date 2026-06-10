"""Detached job supervisor.

Runs in OUR venv (normal Python), spawned detached by ``jobs.submit``. It owns the
lifecycle of one Schrödinger launcher invocation so that job state survives even if
the MCP server process is restarted.

Invoked as::

    python -m schrodinger_mcp._supervisor <job_dir>

Reads ``<job_dir>/command.json`` = {"argv": [...], "env": {...}, "wallclock_cap": int},
runs the command with cwd=<job_dir>, tees output to ``run.log``, and writes the
authoritative ``status.json`` as state changes. ``status.json`` is the single source
of truth that the server reads back in ``jobs.status``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Import the platform helpers without importing the whole package (the supervisor is
# launched as ``python -m schrodinger_mcp._supervisor`` so the package is importable).
from . import platformutil


def _write_status(job_dir: Path, status: dict) -> None:
    tmp = job_dir / "status.json.tmp"
    tmp.write_text(json.dumps(status))
    tmp.replace(job_dir / "status.json")


def _list_outputs(job_dir: Path) -> list[str]:
    """All files produced in the job dir except our own bookkeeping."""
    skip = {"command.json", "status.json", "status.json.tmp", "run.log"}
    out = []
    for p in sorted(job_dir.iterdir()):
        if p.is_file() and p.name not in skip:
            out.append(str(p))
    return out


def run(job_dir: Path) -> int:
    spec = json.loads((job_dir / "command.json").read_text())
    argv = spec["argv"]
    env = dict(os.environ)
    env.update(spec.get("env") or {})
    cap = spec.get("wallclock_cap")

    started = time.time()
    base = {
        "job_dir": str(job_dir),
        "argv": argv,
        "started_at": started,
        "pid": os.getpid(),
    }
    _write_status(job_dir, {**base, "state": "running"})

    log = open(job_dir / "run.log", "w")
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(job_dir),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            # New session/process group so cancel can kill the whole subjob tree.
            **platformutil.detached_popen_kwargs(),
        )
        # Record the child pid (and, on POSIX, its process-group id) for cancellation.
        running = {**base, "state": "running", "child_pid": proc.pid}
        if not platformutil.IS_WINDOWS:
            try:
                running["pgid"] = os.getpgid(proc.pid)
            except OSError:
                pass
        _write_status(job_dir, running)
        try:
            rc = proc.wait(timeout=cap)
        except subprocess.TimeoutExpired:
            platformutil.kill_tree(proc.pid)
            rc = proc.wait()
            _finish(job_dir, base, "failed", rc, error="wall-clock cap exceeded")
            return rc
    finally:
        log.close()

    state = "completed" if rc == 0 else "failed"
    _finish(job_dir, base, state, rc)
    return rc


def _finish(job_dir: Path, base: dict, state: str, rc: int, error: str | None = None) -> None:
    status = {
        **base,
        "state": state,
        "returncode": rc,
        "finished_at": time.time(),
        "elapsed": time.time() - base["started_at"],
        "outputs": _list_outputs(job_dir),
    }
    if error:
        status["error"] = error
    elif state == "failed":
        status["error"] = _log_tail(job_dir)
    _write_status(job_dir, status)


def _log_tail(job_dir: Path, limit: int = 2000) -> str:
    try:
        text = (job_dir / "run.log").read_text(errors="replace")
    except OSError:
        return ""
    return text.strip()[-limit:]


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m schrodinger_mcp._supervisor <job_dir>", file=sys.stderr)
        sys.exit(2)
    job_dir = Path(sys.argv[1])
    sys.exit(run(job_dir))


if __name__ == "__main__":
    main()
