"""Runtime configuration: working directories and resource limits.

Working directories live OUTSIDE the install and outside the repo. Everything the
server writes (job dirs, scratch, the job registry) is rooted at ``SCHRODINGER_MCP_HOME``.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Default root for everything this server writes. Override with $SCHRODINGER_MCP_HOME.
_DEFAULT_HOME = Path.home() / ".local" / "share" / "schrodinger-mcp"


def home() -> Path:
    """Root directory for all server-managed state (jobs, scratch, registry)."""
    root = Path(os.environ.get("SCHRODINGER_MCP_HOME", _DEFAULT_HOME)).expanduser()
    return root


def jobs_dir() -> Path:
    """Directory holding per-job working directories (``jobs/<job_id>/``)."""
    return home() / "jobs"


def scratch_dir() -> Path:
    """Scratch directory for transient files (e.g. worker payload JSON)."""
    return home() / "scratch"


def registry_path() -> Path:
    """Path to the persisted job registry."""
    return home() / "jobs.json"


def ensure_dirs() -> None:
    """Create the home/jobs/scratch directories if they do not exist."""
    for d in (home(), jobs_dir(), scratch_dir()):
        d.mkdir(parents=True, exist_ok=True)


# --- Resource limits (tuned for an 8-core laptop) -----------------------------

#: Total logical cores reported by the machine, with a sane floor.
CPU_COUNT = os.cpu_count() or 4

#: Max simultaneous heavy (async) jobs. Keep small so docking can't swamp a laptop.
MAX_CONCURRENT_JOBS = int(os.environ.get("SCHRODINGER_MCP_MAX_JOBS", "2"))

#: Default subjob parallelism handed to Schrödinger launchers (-NJOBS / -PROCESSORS).
DEFAULT_NJOBS = max(1, min(CPU_COUNT - 2, 4))

#: Timeout (seconds) for synchronous tool calls before suggesting async submission.
SYNC_TIMEOUT = int(os.environ.get("SCHRODINGER_MCP_SYNC_TIMEOUT", "120"))

#: Per-workflow async wall-clock caps (seconds) after which a job is auto-cancelled.
JOB_WALLCLOCK_CAPS = {
    "ligprep": 3 * 3600,
    "prepwizard": 2 * 3600,
    "epik": 2 * 3600,
    "confgen": 2 * 3600,
    "glide_grid": 1 * 3600,
    "glide_dock": 4 * 3600,
    "qikprop": 1 * 3600,
    "sitemap": 1 * 3600,
    "shape_screen": 4 * 3600,
    "prime_mmgbsa": 6 * 3600,
    "jaguar": 8 * 3600,
}
DEFAULT_WALLCLOCK_CAP = 4 * 3600
