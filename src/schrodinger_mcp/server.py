"""FastMCP server entry point.

Creates the MCP app, registers every tool group and the resources, and runs over
stdio. Tool groups live in ``schrodinger_mcp.tools.*`` and each exposes a
``register(mcp)`` function.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from . import installation
from .tools import docking, foundation, jobs_api, prep, properties, qm, viz

mcp = FastMCP(
    "schrodinger",
    instructions=(
        "Drive Schrödinger Suites 2026 computational-chemistry workflows: structure "
        "prep, Glide docking, ADMET/site analysis, and QM/MM-GBSA. Fast operations "
        "(format conversion, structure info, SMILES→3D) return inline. Long jobs "
        "(ligprep, docking, MM-GBSA, QM) return a job_id immediately — poll with "
        "get_job_status and fetch with get_job_results. Every tool writes output files "
        "to a job directory AND returns a structured summary. Desmond MD and FEP+ are "
        "unavailable (no NVIDIA GPU)."
    ),
)

# Register tool groups.
foundation.register(mcp)
prep.register(mcp)
docking.register(mcp)
properties.register(mcp)
qm.register(mcp)
viz.register(mcp)
jobs_api.register(mcp)


@mcp.resource("schrodinger://installation")
def installation_resource() -> str:
    """Schrödinger installation summary: root, version, licensed products, hosts, GPU."""
    try:
        return json.dumps(installation.describe(), indent=2)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)}, indent=2)


@mcp.resource("schrodinger://jobs")
def jobs_resource() -> str:
    """Listing of all known async jobs and their states."""
    from . import jobs

    return json.dumps(jobs.list_jobs(), indent=2, default=str)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
