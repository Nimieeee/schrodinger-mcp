"""Layer-2 smoke tests: fast checks against the real Schrödinger install (seconds).

Marked ``suite`` so they can be skipped where Schrödinger is absent:
    pytest -m "not suite"
"""

import shutil

import pytest

pytestmark = pytest.mark.suite


def _have_suite() -> bool:
    try:
        from schrodinger_mcp import installation

        installation.find_root()
        return True
    except Exception:
        return False


skip_no_suite = pytest.mark.skipif(not _have_suite(), reason="Schrödinger not installed")


@skip_no_suite
def test_detect_installation():
    from schrodinger_mcp.tools.foundation import detect_installation

    d = detect_installation()
    assert d["version"]["release"]  # e.g. "2026-1"
    assert d["installed_workflows"]["glide"] is True
    assert "nvidia" in d["gpu"]


@skip_no_suite
def test_smiles_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHRODINGER_MCP_HOME", str(tmp_path))
    from schrodinger_mcp.tools import foundation

    r = foundation.smiles_to_3d(["CCO"], output_format="mae", titles=["ethanol"])
    assert r["num_written"] == 1
    conv = foundation.convert_structure(r["output_path"], "sdf")
    info = foundation.structure_info(conv["output_path"])
    assert info["num_structures"] == 1
    assert info["structures"][0]["num_atoms"] == 9  # ethanol with explicit H


@skip_no_suite
async def test_mcp_protocol_lists_tools():
    """The stdio server registers the expected tool surface."""
    from schrodinger_mcp.server import mcp

    tools = {t.name for t in await mcp.list_tools()}
    for expected in (
        "detect_installation",
        "ligprep",
        "generate_glide_grid",
        "glide_dock",
        "summarize_docking",
        "qikprop",
        "prime_mmgbsa",
        "get_job_status",
    ):
        assert expected in tools
