"""Validate the remaining untested tools: fetch_pdb (network), epik, confgen.
Run with the project venv: python tests/manual_remaining.py
"""

import time
from pathlib import Path

from schrodinger_mcp import jobs
from schrodinger_mcp.tools import foundation, prep


def poll(job_id, timeout=600, label=""):
    last = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = jobs.status(job_id)
        if st["state"] != last:
            print(f"   {label}: {st['state']} (elapsed={st['elapsed_s']})", flush=True)
            last = st["state"]
        if st["state"] in ("completed", "failed", "canceled"):
            return st
        time.sleep(4)
    return jobs.status(job_id)


def main():
    out = {}

    print("[fetch_pdb 1HSG]", flush=True)
    try:
        r = foundation.fetch_pdb("1HSG")
        info = foundation.structure_info(r["path"])
        print("   ->", Path(r["path"]).name, "atoms:", info["total_atoms"], flush=True)
        out["fetch_pdb"] = "completed"
    except Exception as e:
        print("   FETCH FAILED:", e, flush=True)
        out["fetch_pdb"] = f"failed: {e}"

    # Use a prepared single ligand from the docking fixture for epik / confgen.
    ligand = sorted(Path("data/fixtures/split").glob("0002_*.mae"))[0]

    print("\n[epik]", flush=True)
    j = prep.epik(str(ligand), max_states=4)
    st = poll(j["job_id"], label="epik")
    res = jobs.results(j["job_id"])
    print("   ->", st["state"], [Path(o).name for o in res["outputs"]][:5], flush=True)
    if st["state"] != "completed":
        print("   log:", st.get("log_tail", "")[-700:], flush=True)
    out["epik"] = st["state"]

    print("\n[confgen]", flush=True)
    j = prep.confgen(str(ligand), max_conformers=10)
    st = poll(j["job_id"], label="confgen")
    res = jobs.results(j["job_id"])
    print("   ->", st["state"], [Path(o).name for o in res["outputs"]][:5], flush=True)
    if st["state"] != "completed":
        print("   log:", st.get("log_tail", "")[-700:], flush=True)
    out["confgen"] = st["state"]

    print("\n==== REMAINING SUMMARY ====", flush=True)
    for k, v in out.items():
        flag = "OK " if v == "completed" else "XX "
        print(f"  {flag}{k}: {v}", flush=True)


if __name__ == "__main__":
    main()
