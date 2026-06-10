"""Manual validation of Wave-5 tools: qikprop, prime_mmgbsa, sitemap, shape_screen,
jaguar_qm. Uses small inputs derived from the docking fixture + a tiny molecule.
Run with the project venv: python tests/manual_wave5.py
"""

import time
from pathlib import Path

from schrodinger_mcp import jobs
from schrodinger_mcp.tools import foundation, properties, qm


def poll(job_id, timeout=900, label=""):
    last = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = jobs.status(job_id)
        if st["state"] != last:
            print(f"   {label}: {st['state']} (elapsed={st['elapsed_s']})", flush=True)
            last = st["state"]
        if st["state"] in ("completed", "failed", "canceled"):
            return st
        time.sleep(5)
    return jobs.status(job_id)


def main():
    fix = Path("data/fixtures/split")
    ligs = sorted(fix.glob("00*_*.mae"))
    receptor = str(ligs[0])
    ligand = str(ligs[1])
    print("receptor:", Path(receptor).name, "ligand:", Path(ligand).name, flush=True)

    results = {}

    # 1. qikprop (fast) on a single ligand
    print("\n[qikprop -fast]", flush=True)
    j = properties.qikprop(ligand, fast=True)
    st = poll(j["job_id"], label="qikprop")
    res = jobs.results(j["job_id"])
    csv = [o for o in res["outputs"] if o.endswith(".CSV")]
    results["qikprop"] = (st["state"], [Path(o).name for o in res["outputs"]][:6])
    print("   ->", st["state"], "csv:", [Path(c).name for c in csv], flush=True)

    # 2. compute a small complex (receptor + 1 ligand) and run MM-GBSA (ENERGY, fast)
    print("\n[prime_mmgbsa ENERGY on receptor+ligand]", flush=True)
    complex_mae = str(Path("data/fixtures") / "complex_pv.mae")
    foundation.merge_structures([receptor, ligand], complex_mae)
    j = qm.prime_mmgbsa(complex_mae, minimize=False)
    st = poll(j["job_id"], label="mmgbsa")
    res = jobs.results(j["job_id"])
    results["prime_mmgbsa"] = (st["state"], [Path(o).name for o in res["outputs"]][:6])
    print("   ->", st["state"], "outputs:", [Path(o).name for o in res["outputs"]][:6], flush=True)
    if st["state"] != "completed":
        print("   log:", st.get("log_tail", "")[-700:], flush=True)

    # 3. sitemap on the receptor
    print("\n[sitemap]", flush=True)
    j = properties.sitemap(receptor, num_sites=3)
    st = poll(j["job_id"], label="sitemap")
    res = jobs.results(j["job_id"])
    results["sitemap"] = (st["state"], [Path(o).name for o in res["outputs"]][:6])
    print("   ->", st["state"], "outputs:", [Path(o).name for o in res["outputs"]][:6], flush=True)
    if st["state"] != "completed":
        print("   log:", st.get("log_tail", "")[-700:], flush=True)

    # 4. shape_screen: query vs a small screen db of a few ligand poses
    print("\n[shape_screen]", flush=True)
    screen_db = str(Path("data/fixtures") / "screen_db.mae")
    foundation.merge_structures([str(p) for p in ligs[2:6]], screen_db)
    j = properties.shape_screen(ligand, screen_db)
    st = poll(j["job_id"], label="shape")
    res = jobs.results(j["job_id"])
    results["shape_screen"] = (st["state"], [Path(o).name for o in res["outputs"]][:6])
    print("   ->", st["state"], "outputs:", [Path(o).name for o in res["outputs"]][:6], flush=True)
    if st["state"] != "completed":
        print("   log:", st.get("log_tail", "")[-700:], flush=True)

    # 5. jaguar_qm energy on ethanol
    print("\n[jaguar_qm energy on ethanol]", flush=True)
    eth = foundation.smiles_to_3d(["CCO"], output_format="mae", titles=["ethanol"])["output_path"]
    j = qm.jaguar_qm(eth, calculation="energy")
    st = poll(j["job_id"], label="jaguar")
    res = jobs.results(j["job_id"])
    results["jaguar_qm"] = (st["state"], [Path(o).name for o in res["outputs"]][:6])
    print("   ->", st["state"], "outputs:", [Path(o).name for o in res["outputs"]][:6], flush=True)
    if st["state"] != "completed":
        print("   log:", st.get("log_tail", "")[-900:], flush=True)

    print("\n==== WAVE 5 SUMMARY ====", flush=True)
    for k, (state, outs) in results.items():
        flag = "OK " if state == "completed" else "XX "
        print(f"  {flag}{k}: {state} {outs}", flush=True)


if __name__ == "__main__":
    main()
