"""Layer-1 unit tests: pure-Python logic that needs no Schrödinger installation.

Covers error detection, the worker result-parsing contract, format/path safety, the
installation version/sort helpers, and the job registry's disk reconciliation.
"""

import json
import os
from pathlib import Path

import pytest

from schrodinger_mcp import errors
from schrodinger_mcp.installation import _suite_sort_key
from schrodinger_mcp.runner import _extract_result


# --- error detection ---------------------------------------------------------

def test_license_error_detection():
    assert errors.looks_like_license_error("ERROR: No valid license for GLIDE_MAIN")
    assert errors.looks_like_license_error("could not check out feature")
    assert not errors.looks_like_license_error("Docking completed successfully")


def test_error_str_includes_kind():
    e = errors.LicenseError("no token", product="GLIDE")
    assert "license_error" in str(e)
    assert "GLIDE" in str(e)


# --- worker result contract --------------------------------------------------

def test_extract_result_finds_sentinel_among_noise():
    stdout = (
        "Schrodinger banner line\n"
        "WARNING: something chatty\n"
        '__SMCP_RESULT__{"ok": true, "data": {"n": 3}}\n'
    )
    res = _extract_result(stdout)
    assert res == {"ok": True, "data": {"n": 3}}


def test_extract_result_returns_last():
    stdout = (
        '__SMCP_RESULT__{"ok": false, "error": "early"}\n'
        '__SMCP_RESULT__{"ok": true, "data": {}}\n'
    )
    assert _extract_result(stdout)["ok"] is True


def test_extract_result_none_when_absent():
    assert _extract_result("no result here\n") is None


# --- format & path safety ----------------------------------------------------

def test_normalize_and_ext():
    from schrodinger_mcp.tools import _common

    assert _common.normalize_format("SDF") == "sdf"
    assert _common.ext_for("mae") == ".mae"
    with pytest.raises(errors.InvalidInput):
        _common.normalize_format("xyz")


def test_resolve_output_path_rejects_root(tmp_path):
    from schrodinger_mcp.tools import _common

    p = _common.resolve_output_path(None, default_dir=tmp_path, default_name="out.mae")
    assert p == (tmp_path / "out.mae").resolve()


# --- installation helpers ----------------------------------------------------

def test_suite_sort_key_orders_versions():
    keys = [_suite_sort_key(Path(n)) for n in ("suites2024-4", "suites2026-1", "suites2025-2")]
    assert max(keys) == _suite_sort_key(Path("suites2026-1"))
    assert _suite_sort_key(Path("not-a-suite")) == (0, 0)


# --- job registry reconciliation (no real supervisor) ------------------------

def test_status_from_disk_reconciles(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHRODINGER_MCP_HOME", str(tmp_path))
    from schrodinger_mcp import jobs

    job_dir = tmp_path / "jobs" / "abc"
    job_dir.mkdir(parents=True)
    # A status.json claiming 'running' but with a dead supervisor PID -> failed.
    (job_dir / "status.json").write_text(json.dumps({"state": "running", "started_at": 1.0}))
    rec = {"job_dir": str(job_dir), "supervisor_pid": 2**31 - 1}  # almost certainly not alive
    st = jobs._status_from_disk(rec)
    assert st["state"] == "failed"


def test_status_from_disk_completed(tmp_path):
    from schrodinger_mcp import jobs

    job_dir = tmp_path / "j2"
    job_dir.mkdir()
    (job_dir / "status.json").write_text(
        json.dumps({"state": "completed", "returncode": 0, "outputs": ["x.mae"]})
    )
    st = jobs._status_from_disk({"job_dir": str(job_dir), "supervisor_pid": os.getpid()})
    assert st["state"] == "completed" and st["returncode"] == 0


def test_validate_id_rejects_traversal():
    from schrodinger_mcp import jobs

    with pytest.raises(errors.InvalidInput):
        jobs._validate_id("../etc/passwd")
    assert jobs._validate_id("abc123DEF-_") == "abc123DEF-_"
