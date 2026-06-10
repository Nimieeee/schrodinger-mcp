"""Helper for tools that submit long-running Schrödinger jobs."""

from __future__ import annotations

from typing import Optional

from .. import config, jobs


def submit_async(
    workflow: str,
    argv: list[str],
    *,
    label: Optional[str] = None,
    stage_files: Optional[dict] = None,
    stage_copy: Optional[list[str]] = None,
    extra: Optional[dict] = None,
) -> dict:
    """Submit a job and return a caller-friendly dict with polling guidance."""
    res = jobs.submit(
        workflow, argv, label=label or workflow, stage_files=stage_files, stage_copy=stage_copy
    )
    res["next_steps"] = (
        f"Poll get_job_status('{res['job_id']}'); when state is 'completed' call "
        f"get_job_results('{res['job_id']}')."
    )
    if extra:
        res.update(extra)
    return res


def njobs(requested: Optional[int] = None) -> int:
    """Clamp subjob parallelism to keep the laptop responsive."""
    if requested is None:
        return config.DEFAULT_NJOBS
    return max(1, min(int(requested), config.CPU_COUNT - 1))
