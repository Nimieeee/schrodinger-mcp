"""Worker: build a self-contained Jaguar input (.in) from a structure file.

Payload: {"path", "calculation", "basis", "functional", "charge", "multiplicity"}
Returns: {"input_text": str}  (the .in file contents, with geometry embedded)
"""

import os
import tempfile

import _wio
from schrodinger import structure
from schrodinger.application.jaguar import input as jaguar_input


def run(payload):
    st = structure.StructureReader.read(payload["path"])
    if payload.get("charge") is not None:
        st.property["i_m_Molecular_charge"] = int(payload["charge"])

    ji = jaguar_input.JaguarInput(structure=st)

    keys = {
        "basis": payload.get("basis", "6-31G**"),
        "dftname": payload.get("functional", "B3LYP"),
        "multip": str(int(payload.get("multiplicity", 1))),
    }
    calc = payload.get("calculation", "optimization")
    if calc == "optimization":
        keys["igeopt"] = "1"
    elif calc == "frequency":
        keys["ifreq"] = "1"
    else:
        keys["igeopt"] = "0"
    if payload.get("charge") is not None:
        keys["molchg"] = str(int(payload["charge"]))
    ji.setValues(keys)

    tmp = tempfile.mkdtemp()
    out = os.path.join(tmp, "jaguar.in")
    # JaguarInput exposes saveAs in this build; fall back to save() if absent.
    if hasattr(ji, "saveAs"):
        ji.saveAs(out)
    else:
        ji.save(out)
    with open(out) as fh:
        text = fh.read()
    # saveAs may also emit a companion geometry file (referenced via MAEFILE:).
    companions = [
        os.path.join(tmp, f) for f in os.listdir(tmp) if f != "jaguar.in"
    ]
    return {"input_text": text, "in_path": out, "companions": companions}


if __name__ == "__main__":
    _wio.main(run)
