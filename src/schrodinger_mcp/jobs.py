"""Async job registry.

A job is one detached Schrödinger launcher invocation supervised by
``schrodinger_mcp._supervisor``. The registry maps our stable ``job_id`` (a UUID,
the key Claude uses) to the supervisor PID and the job directory. State is read back
from each job's authoritative ``status.json``; the registry file only holds metadata
needed to find and reconcile jobs after a server restart.

This deliberately avoids depending on Schrödinger's job-server database or any
reconnect-by-jobid API (which does not exist in this build): the supervisor process
plus ``status.json`` are the source of truth.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from filelock import FileLock

from . import config, installation, platformutil
from .errors import InvalidInput, JobNotFound

_VALID_ID = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def _lock() -> FileLock:
    config.ensure_dirs()
    return FileLock(str(config.registry_path()) + ".lock")


def _read_registry() -> dict:
    path = config.registry_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_registry(reg: dict) -> None:
    path = config.registry_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(reg, indent=2))
    tmp.replace(path)


def _validate_id(job_id: str) -> str:
    if not job_id or any(c not in _VALID_ID for c in job_id):
        raise InvalidInput("invalid job_id", job_id=job_id)
    return job_id


def _pid_alive(pid: Optional[int]) -> bool:
    return platformutil.pid_alive(pid)


def _count_active(reg: dict) -> int:
    n = 0
    for rec in reg.values():
        st = _status_from_disk(rec)
        if st.get("state") in ("submitted", "running"):
            n += 1
    return n


def submit(
    workflow: str,
    argv: list[str],
    *,
    label: Optional[str] = None,
    env_extra: Optional[dict] = None,
    stage_files: Optional[dict] = None,
    stage_copy: Optional[list[str]] = None,
) -> dict:
    """Launch ``argv`` under a detached supervisor and register the job.

    Returns {job_id, job_dir, workflow, state}. ``argv[0]`` is typically an absolute
    Schrödinger launcher path; cwd will be the job dir. ``stage_files`` maps filename ->
    text content; ``stage_copy`` is a list of existing files to copy into the job dir.
    Both let argv reference inputs by bare name (some tools require inputs in the cwd).
    """
    import shutil

    job_id = uuid.uuid4().hex
    job_dir = config.jobs_dir() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    for fname, content in (stage_files or {}).items():
        (job_dir / fname).write_text(content)
    for src in stage_copy or []:
        shutil.copy2(src, job_dir / Path(src).name)

    cap = config.JOB_WALLCLOCK_CAPS.get(workflow, config.DEFAULT_WALLCLOCK_CAP)
    command = {
        "argv": argv,
        "env": installation.child_env(env_extra),
        "wallclock_cap": cap,
        "workflow": workflow,
    }
    (job_dir / "command.json").write_text(json.dumps(command))

    with _lock():
        reg = _read_registry()
        active = _count_active(reg)
        if active >= config.MAX_CONCURRENT_JOBS:
            # Don't refuse outright; queueing is out of scope. Surface a clear note so
            # the caller can decide. The job still launches (the OS schedules it).
            note = (
                f"{active} job(s) already active (limit {config.MAX_CONCURRENT_JOBS}); "
                "this job will compete for CPU."
            )
        else:
            note = None

        proc = subprocess.Popen(
            [sys.executable, "-m", "schrodinger_mcp._supervisor", str(job_dir)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(job_dir),
            **platformutil.detached_popen_kwargs(),
        )
        rec = {
            "job_id": job_id,
            "workflow": workflow,
            "label": label or workflow,
            "job_dir": str(job_dir),
            "supervisor_pid": proc.pid,
            "submitted_at": time.time(),
            "argv": argv,
        }
        reg[job_id] = rec
        _write_registry(reg)

    result = {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "workflow": workflow,
        "state": "submitted",
    }
    if note:
        result["note"] = note
    return result


def _status_from_disk(rec: dict) -> dict:
    """Reconcile a registry record against its status.json and PID liveness."""
    job_dir = Path(rec["job_dir"])
    status_file = job_dir / "status.json"
    if status_file.exists():
        try:
            st = json.loads(status_file.read_text())
        except (json.JSONDecodeError, OSError):
            st = {}
        state = st.get("state", "unknown")
        # If status says running but the supervisor is gone, it died uncleanly.
        if state in ("running", "submitted") and not _pid_alive(rec.get("supervisor_pid")):
            st["state"] = "failed"
            st["error"] = st.get("error") or "supervisor process exited unexpectedly"
        return st
    # No status yet: supervisor may be starting, or died before writing.
    if _pid_alive(rec.get("supervisor_pid")):
        return {"state": "submitted"}
    return {"state": "failed", "error": "supervisor did not start"}


def _get_record(job_id: str) -> dict:
    job_id = _validate_id(job_id)
    reg = _read_registry()
    if job_id not in reg:
        raise JobNotFound(f"no such job: {job_id}", job_id=job_id)
    return reg[job_id]


def status(job_id: str) -> dict:
    rec = _get_record(job_id)
    st = _status_from_disk(rec)
    elapsed = st.get("elapsed")
    if elapsed is None and st.get("started_at"):
        elapsed = time.time() - st["started_at"]
    return {
        "job_id": job_id,
        "workflow": rec.get("workflow"),
        "label": rec.get("label"),
        "state": st.get("state", "unknown"),
        "elapsed_s": round(elapsed, 1) if elapsed else None,
        "returncode": st.get("returncode"),
        "job_dir": rec["job_dir"],
        "error": st.get("error"),
        "log_tail": _log_tail(Path(rec["job_dir"])),
    }


def results(job_id: str) -> dict:
    rec = _get_record(job_id)
    st = _status_from_disk(rec)
    state = st.get("state", "unknown")
    return {
        "job_id": job_id,
        "workflow": rec.get("workflow"),
        "state": state,
        "returncode": st.get("returncode"),
        "outputs": st.get("outputs", _scan_outputs(Path(rec["job_dir"]))),
        "job_dir": rec["job_dir"],
        "error": st.get("error"),
    }


def cancel(job_id: str) -> dict:
    rec = _get_record(job_id)
    st = _status_from_disk(rec)
    killed = False
    # Kill the child launcher tree first (covers subjobs), then the supervisor.
    for target in (st.get("child_pid"), rec.get("supervisor_pid")):
        if target and platformutil.kill_tree(target):
            killed = True
    # Mark cancelled in the job's status.json so future polls report it.
    job_dir = Path(rec["job_dir"])
    cur = {}
    sf = job_dir / "status.json"
    if sf.exists():
        try:
            cur = json.loads(sf.read_text())
        except (json.JSONDecodeError, OSError):
            cur = {}
    cur["state"] = "canceled"
    (job_dir / "status.json").write_text(json.dumps(cur))
    return {"job_id": job_id, "state": "canceled", "signal_sent": killed}


def list_jobs(state_filter: Optional[str] = None) -> list[dict]:
    reg = _read_registry()
    out = []
    for job_id, rec in sorted(reg.items(), key=lambda kv: kv[1].get("submitted_at", 0), reverse=True):
        st = _status_from_disk(rec)
        if state_filter and st.get("state") != state_filter:
            continue
        out.append(
            {
                "job_id": job_id,
                "workflow": rec.get("workflow"),
                "label": rec.get("label"),
                "state": st.get("state", "unknown"),
                "submitted_at": rec.get("submitted_at"),
            }
        )
    return out


def _scan_outputs(job_dir: Path) -> list[str]:
    skip = {"command.json", "status.json", "status.json.tmp", "run.log"}
    if not job_dir.is_dir():
        return []
    return [str(p) for p in sorted(job_dir.iterdir()) if p.is_file() and p.name not in skip]


def _log_tail(job_dir: Path, limit: int = 1200) -> str:
    f = job_dir / "run.log"
    if not f.exists():
        return ""
    try:
        return f.read_text(errors="replace").strip()[-limit:]
    except OSError:
        return ""
