"""Worker: summarize a Glide pose-viewer file into a ranked score table.

A pose-viewer (*_pv.mae[gz]) file starts with the receptor structure, followed by one
structure per docked pose. Poses carry Glide score properties:
  r_i_docking_score  - GlideScore (primary; lower is better)
  r_i_glide_gscore   - GlideScore components total
  r_i_glide_emodel   - Emodel
  r_i_glide_lipo / _hbond / _evdw / _ecoul - term breakdown

Payload: {"path": str, "top_n": int}
"""

import _wio
from schrodinger import structure

_SCORE_KEYS = {
    "docking_score": "r_i_docking_score",
    "glide_gscore": "r_i_glide_gscore",
    "emodel": "r_i_glide_emodel",
    "lipophilic": "r_i_glide_lipo",
    "hbond": "r_i_glide_hbond",
    "evdw": "r_i_glide_evdw",
    "ecoul": "r_i_glide_ecoul",
}


def _has_score(st):
    return any(k in st.property for k in ("r_i_docking_score", "r_i_glide_gscore"))


def run(payload):
    path = payload["path"]
    top_n = int(payload.get("top_n", 50))
    poses = []
    with structure.StructureReader(path) as reader:
        for i, st in enumerate(reader, start=1):
            if i == 1 and not _has_score(st):
                # first entry is the receptor
                continue
            if not _has_score(st):
                continue
            row = {"title": st.title, "index": i}
            for label, key in _SCORE_KEYS.items():
                if key in st.property:
                    row[label] = round(float(st.property[key]), 4)
            poses.append(row)

    poses.sort(key=lambda r: r.get("docking_score", r.get("glide_gscore", 1e9)))
    best = poses[0] if poses else None
    return {
        "path": path,
        "num_poses": len(poses),
        "best": best,
        "poses": poses[:top_n],
        "truncated": len(poses) > top_n,
    }


if __name__ == "__main__":
    _wio.main(run)
