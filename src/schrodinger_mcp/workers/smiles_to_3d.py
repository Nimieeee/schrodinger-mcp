"""Worker: generate 3D structures from SMILES and write them to one file.

Payload: {"smiles": [str,...] | str, "titles": [str,...]?, "output_path": str,
          "require_stereo": bool}
Returns: per-molecule results + the output file path.

Uses ``schrodinger.adapter.smiles_to_3d_structure`` (RDKit-backed embed + H placement).
This is a quick single-conformer 3D build; use the ligprep tool for full ligand prep
(ionization, tautomers, ring conformers).
"""

import _wio
from schrodinger import structure


def run(payload):
    smiles = payload["smiles"]
    if isinstance(smiles, str):
        smiles = [smiles]
    titles = payload.get("titles") or []
    output_path = payload["output_path"]
    require_stereo = bool(payload.get("require_stereo", False))

    molecules = []
    written = 0
    with structure.StructureWriter(output_path) as writer:
        for i, smi in enumerate(smiles):
            entry = {"smiles": smi}
            try:
                st = _wio.smiles_to_3d(smi, require_stereo=require_stereo)
                title = titles[i] if i < len(titles) else smi
                st.title = title
                entry.update(
                    {
                        "title": title,
                        "num_atoms": st.atom_total,
                        "formal_charge": st.formal_charge,
                        "ok": True,
                    }
                )
                writer.append(st)
                written += 1
            except Exception as exc:  # one bad SMILES shouldn't fail the whole batch
                entry.update({"ok": False, "error": str(exc)})
            molecules.append(entry)

    return {
        "output_path": output_path,
        "num_input": len(smiles),
        "num_written": written,
        "molecules": molecules,
    }


if __name__ == "__main__":
    _wio.main(run)
