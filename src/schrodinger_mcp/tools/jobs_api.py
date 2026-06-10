"""Generic async-job tools, shared by every long-running workflow.

Long workflows (ligprep, docking, MM-GBSA, QM, ...) return a ``job_id`` immediately.
Use these tools to poll and collect results.
"""

from __future__ import annotations

from typing import Optional

from .. import jobs


def get_job_status(job_id: str) -> dict:
    """Check a submitted job. Returns state (submitted/running/completed/failed/
    canceled), elapsed time, exit code, and a tail of the job log. Poll this after
    submitting any long-running workflow."""
    return jobs.status(job_id)


def get_job_results(job_id: str) -> dict:
    """Fetch a finished job's outputs: the list of produced files (poses, prepped
    structures, logs) and its final state. For docking jobs, follow up with
    summarize_docking on the produced pose-viewer (*_pv.maegz) file for a ranked table."""
    return jobs.results(job_id)


def cancel_job(job_id: str) -> dict:
    """Stop a running job. Terminates the job's process group; the job directory and
    any partial outputs are left in place."""
    return jobs.cancel(job_id)


def list_jobs(state: Optional[str] = None) -> dict:
    """List known async jobs, most recent first. Optionally filter by state
    (submitted/running/completed/failed/canceled)."""
    return {"jobs": jobs.list_jobs(state_filter=state)}


def register(mcp) -> None:
    for fn in (get_job_status, get_job_results, cancel_job, list_jobs):
        mcp.tool()(fn)
