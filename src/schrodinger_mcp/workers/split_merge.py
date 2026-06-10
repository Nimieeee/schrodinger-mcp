"""Worker: split a multi-structure file into singles, or merge several into one.

Payload (split): {"mode": "split", "path": str, "output_dir": str, "format": str}
Payload (merge): {"mode": "merge", "paths": [str,...], "output_path": str}
"""

import os

import _wio
from schrodinger import structure


def _safe_stem(title, index):
    base = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (title or "").strip())
    base = base.strip("_.") or f"structure_{index}"
    return f"{index:04d}_{base}"[:80]


def _split(payload):
    path = payload["path"]
    out_dir = payload["output_dir"]
    fmt = payload.get("format", "mae").lstrip(".")
    os.makedirs(out_dir, exist_ok=True)
    written = []
    with structure.StructureReader(path) as reader:
        for i, st in enumerate(reader, start=1):
            stem = _safe_stem(st.title, i)
            out = os.path.join(out_dir, f"{stem}.{fmt}")
            st.write(out)
            written.append({"index": i, "title": st.title, "path": out, "num_atoms": st.atom_total})
    return {"mode": "split", "source": path, "output_dir": out_dir, "count": len(written), "files": written}


def _merge(payload):
    paths = payload["paths"]
    output_path = payload["output_path"]
    count = 0
    with structure.StructureWriter(output_path) as writer:
        for p in paths:
            with structure.StructureReader(p) as reader:
                for st in reader:
                    writer.append(st)
                    count += 1
    return {"mode": "merge", "inputs": paths, "output_path": output_path, "num_structures": count}


def run(payload):
    if payload.get("mode") == "merge":
        return _merge(payload)
    return _split(payload)


if __name__ == "__main__":
    _wio.main(run)
