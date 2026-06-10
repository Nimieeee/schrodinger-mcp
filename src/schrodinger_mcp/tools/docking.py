"""Glide docking tools: grid generation, docking (SP/XP), and pose summarization.

Grid and docking jobs are driven by Glide ``.in`` keyword files, which we generate
and stage into the job directory. summarize_docking is synchronous (parses poses).
"""

from __future__ import annotations

from typing import Optional

from .. import runner
from ..errors import InvalidInput
from . import _async, _common


def generate_glide_grid(
    receptor_path: str,
    center: Optional[list[float]] = None,
    ligand_ref: Optional[str] = None,
    inner_box: float = 10.0,
    outer_box: float = 20.0,
    grid_name: str = "grid.zip",
) -> dict:
    """Build a Glide docking grid from a prepared receptor. Specify the binding-site
    center either explicitly via `center` [x,y,z] or by giving `ligand_ref` (a file
    containing a bound ligand whose centroid defines the site). Long-running — returns
    a job_id; the grid (<grid_name>) lands in the job dir and is the input to glide_dock."""
    receptor = _common.validate_input_path(receptor_path)

    if center is None and ligand_ref is None:
        raise InvalidInput("provide either center=[x,y,z] or ligand_ref=<file with bound ligand>")
    if center is None:
        ref = _common.validate_input_path(ligand_ref)
        cres = runner.run_worker("centroid", {"path": str(ref)})
        center = cres["centroid"]
    if len(center) != 3:
        raise InvalidInput("center must be [x, y, z]")

    jobname = grid_name[:-4] if grid_name.endswith(".zip") else grid_name
    argv = [
        _common.utility("generate_glide_grids"),
        "-rec_file", receptor.name,
        "-cent_coor", f"{center[0]:.4f},{center[1]:.4f},{center[2]:.4f}",
        "-inner_box", str(int(inner_box)),
        "-outer_box", str(int(outer_box)),
        "-j", jobname,
        "-HOST", "localhost", "-WAIT",
    ]
    return _async.submit_async(
        "glide_grid",
        argv,
        label=f"grid:{receptor.name}",
        stage_copy=[str(receptor)],
        extra={"grid_center": center, "grid_file": f"{jobname}.zip"},
    )


def glide_dock(
    grid_path: str,
    ligands_path: str,
    precision: str = "SP",
    poses_per_ligand: int = 1,
    njobs: Optional[int] = None,
) -> dict:
    """Dock prepared ligands into a Glide grid and score them. `precision` is 'SP'
    (standard, default) or 'XP' (extra-precision, slower). `ligands_path` should be a
    LigPrep-prepared file. Long-running — returns a job_id. When complete, run
    summarize_docking on the produced *_pv.maegz for a ranked GlideScore table."""
    grid = _common.validate_input_path(grid_path)
    ligands = _common.validate_input_path(ligands_path)
    precision = precision.upper()
    if precision not in ("SP", "XP", "HTVS"):
        raise InvalidInput("precision must be SP, XP, or HTVS")

    dock_in = (
        f"GRIDFILE {grid}\n"
        f"LIGANDFILE {ligands}\n"
        f"PRECISION {precision}\n"
        f"POSES_PER_LIG {int(poses_per_ligand)}\n"
        f"POSE_OUTTYPE poseviewer\n"
    )
    argv = [
        _common.launcher("glide"),
        "dock.in",
        "-HOST",
        "localhost",
        "-NJOBS",
        str(_async.njobs(njobs)),
        "-WAIT",
    ]
    return _async.submit_async(
        "glide_dock",
        argv,
        label=f"dock:{ligands.name}→{grid.name}",
        stage_files={"dock.in": dock_in},
        extra={"precision": precision},
    )


def summarize_docking(pose_file: str, top_n: int = 50) -> dict:
    """Parse a Glide pose-viewer file (*_pv.maegz) into a ranked table of GlideScores
    and key terms per ligand. Returns the best poses sorted by score (lower is better)."""
    pv = _common.validate_input_path(pose_file)
    return runner.run_worker("summarize_docking", {"path": str(pv), "top_n": int(top_n)})


def register(mcp) -> None:
    for fn in (generate_glide_grid, glide_dock, summarize_docking):
        mcp.tool()(fn)
