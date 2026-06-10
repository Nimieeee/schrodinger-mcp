"""Worker-side I/O contract and version-compatibility shims.

Workers run under ``$SCHRODINGER/run python3`` (whatever Python the installed Suite
ships), so this module may ONLY import the stdlib and ``schrodinger`` — never the
``schrodinger_mcp`` package (different interpreter / dependency set).

A worker is invoked as::

    $SCHRODINGER/run python3 <worker>.py <payload.json>

It reads the JSON payload, does its work, and prints exactly one result line:

    __SMCP_RESULT__{"ok": true, "data": {...}}

Schrödinger libraries are chatty on stdout/stderr; the sentinel prefix lets the
parent reliably find the result among the noise.

The ``compat`` helpers below wrap a few Schrödinger Python-API calls that have moved
or been renamed across releases, so workers keep working across many Suite versions.
"""

import json
import os
import sys
import tempfile
import traceback

RESULT_SENTINEL = "__SMCP_RESULT__"


# --- Version-compatibility shims (work across many Schrödinger releases) ----------

def smiles_to_3d(smiles: str, require_stereo: bool = False):
    """SMILES -> a 3D ``schrodinger.Structure``.

    Prefers ``adapter.smiles_to_3d_structure`` (modern Suites). Falls back to an RDKit
    embed routed through an SD file, which works on older releases lacking that helper.
    """
    import schrodinger.adapter as adapter

    if hasattr(adapter, "smiles_to_3d_structure"):
        return adapter.smiles_to_3d_structure(smiles, require_stereo=require_stereo)

    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"invalid SMILES: {smiles}")
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, AllChem.ETKDGv3()) != 0:
        AllChem.EmbedMolecule(mol, useRandomCoords=True)
    try:
        AllChem.MMFFOptimizeMolecule(mol)
    except Exception:
        pass
    return _rdkit_to_structure(mol)


def to_rdkit(st):
    """``schrodinger.Structure`` -> RDKit mol, across releases."""
    import schrodinger.adapter as adapter

    if hasattr(adapter, "to_rdkit"):
        return adapter.to_rdkit(st)
    return _structure_via_sdf(st)


def to_smiles(st) -> str:
    """``schrodinger.Structure`` -> SMILES, across releases."""
    import schrodinger.adapter as adapter

    if hasattr(adapter, "to_smiles"):
        return adapter.to_smiles(st)
    from rdkit import Chem

    return Chem.MolToSmiles(to_rdkit(st))


def _structure_via_sdf(st):
    from rdkit import Chem

    tmp = tempfile.mktemp(suffix=".sdf")
    try:
        st.write(tmp)
        mol = next(iter(Chem.SDMolSupplier(tmp, removeHs=False)), None)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    if mol is None:
        raise ValueError("could not convert structure to RDKit via SD")
    return mol


def _rdkit_to_structure(mol):
    from rdkit import Chem
    from schrodinger import structure

    tmp = tempfile.mktemp(suffix=".sdf")
    try:
        writer = Chem.SDWriter(tmp)
        writer.write(mol)
        writer.close()
        return structure.StructureReader.read(tmp)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def read_payload() -> dict:
    if len(sys.argv) < 2:
        return {}
    with open(sys.argv[1]) as fh:
        return json.load(fh)


def emit(data: dict) -> None:
    sys.stdout.write(RESULT_SENTINEL + json.dumps({"ok": True, "data": data}) + "\n")
    sys.stdout.flush()


def emit_error(message: str, etype: str = "WorkerError", **extra) -> None:
    payload = {"ok": False, "error": str(message), "type": etype}
    payload.update(extra)
    sys.stdout.write(RESULT_SENTINEL + json.dumps(payload) + "\n")
    sys.stdout.flush()


def main(fn) -> None:
    """Run ``fn(payload) -> dict`` with uniform error handling."""
    try:
        data = fn(read_payload())
        emit(data if data is not None else {})
    except Exception as exc:  # noqa: BLE001 - report everything cleanly to the parent
        emit_error(str(exc), etype=type(exc).__name__, traceback=traceback.format_exc())
        sys.exit(1)
