"""0.5 MCP 입력·출력 보강 회귀시험."""

import json

import pytest

pytest.importorskip("mcp")

from hwp_reader import mcp_server  # noqa: E402


def test_mcp_paths_accepts_zip(tmp_path):
    path = tmp_path / "bundle.zip"
    path.write_bytes(b"PK")
    assert mcp_server._paths(str(path)) == [str(path)]


def test_mcp_large_json_stays_valid(monkeypatch):
    monkeypatch.setattr(mcp_server, "_LIMIT", 120)
    value = [{"file": "x", "grid": ["가" * 200]}]
    parsed = json.loads(mcp_server._json(value))
    assert parsed["truncated"] is True
    assert isinstance(parsed["preview"], str)
