"""Manual end-to-end docking test using bundled Glide tutorial data (no network).

Builds a receptor + ligand fixture from $SCHRODINGER/tutorials/glide.zip
(factorXa_sp_pv.maegz), generates a Glide grid, docks the ligand back (SP, 1 pose),
and summarizes the poses. Exercises generate_glide_grid -> glide_dock -> summarize_docking
plus the whole async job path. Run with the project venv:

    python tests/manual_docking_e2e.py
"""

import time
import zipfile
from pathlib import Path

from schrodinger_mcp import installation, jobs
from schrodinger_mcp.tools import docking, foundation


def poll(job_id, timeout=600, label=""):
    last = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = jobs.status(job_id)
        if st["state"] != last:
            print(f"   {label} state={st['state']} elapsed={st['elapsed_s']}")
            last = st["state"]
        if st["state"] in ("completed", "failed", "canceled"):
            return st
        time.sleep(4)
    return jobs.status(job_id)


def main():
    fixtures = Path(__file__).parent.parent / "data" / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    pv = fixtures / "factorXa_sp_pv.maegz"
    if not pv.exists():
        with zipfile.ZipFile(installation.find_root() / "tutorials" / "glide.zip") as z:
            with z.open("factorXa_sp_pv.maegz") as src, open(pv, "wb") as dst:
                dst.write(src.read())
    print("fixture:", pv)

    info = foundation.structure_info(str(pv), max_structures=3)
    print("pv structures:", info["num_structures"], "(entry1=receptor, entry2+=poses)")

    # Split: entry 1 = receptor, entry 2 = a ligand pose.
    sp = foundation.split_structures(str(pv), output_dir=str(fixtures / "split"), output_format="mae")
    files = sorted(sp["outputs"])
    receptor = files[0]
    ligand = files[1]
    print("receptor:", Path(receptor).name, "| ligand:", Path(ligand).name)

    print("\n[1/3] generate_glide_grid (center from ligand)")
    g = docking.generate_glide_grid(receptor, ligand_ref=ligand, inner_box=10, outer_box=20)
    gst = poll(g["job_id"], label="grid")
    gres = jobs.results(g["job_id"])
    grid_zip = next((o for o in gres["outputs"] if o.endswith(".zip")), None)
    print("grid result:", gst["state"], "grid:", grid_zip and Path(grid_zip).name)
    assert gst["state"] == "completed" and grid_zip, f"grid failed: {gst.get('error','')[:800]}"

    print("\n[2/3] glide_dock (SP, 1 pose)")
    d = docking.glide_dock(grid_zip, ligand, precision="SP", poses_per_ligand=1)
    dst = poll(d["job_id"], label="dock")
    dres = jobs.results(d["job_id"])
    pv_out = next((o for o in dres["outputs"] if o.endswith("_pv.maegz")), None)
    print("dock result:", dst["state"], "pv:", pv_out and Path(pv_out).name)
    if dst["state"] != "completed":
        print("dock log tail:\n", dst.get("log_tail", "")[-1500:])
    assert dst["state"] == "completed" and pv_out, f"dock failed: {dst.get('error','')[:800]}"

    print("\n[3/3] summarize_docking")
    summ = docking.summarize_docking(pv_out)
    print("num_poses:", summ["num_poses"], "best:", summ["best"])
    assert summ["num_poses"] >= 1 and summ["best"].get("docking_score") is not None
    print("\nDOCKING END-TO-END PASSED  (GlideScore =", summ["best"]["docking_score"], ")")


if __name__ == "__main__":
    main()
