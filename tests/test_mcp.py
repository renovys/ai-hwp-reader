"""MCP 서버 시험.

MCP 파이썬 SDK가 깔려 있을 때만 돈다(`pip install 'ai-hwp-reader[mcp]'`).
SDK 1.x의 FastMCP와 2.x의 MCPServer 양쪽에서 같은 결과가 나와야 한다.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("mcp")

from hwp_reader import mcp_server                       # noqa: E402
from make_fixture import write_hwpx                     # noqa: E402


@pytest.fixture()
def 예산서(tmp_path):
    return write_hwpx(tmp_path / "예산서.hwpx")


def test_도구가_넷_등록된다():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    assert {t.name for t in tools} == {
        "hwp_read", "hwp_tables", "hwp_memos", "hwp_revisions"
    }


def test_hwp_read가_표를_살려_돌려준다(예산서):
    out = mcp_server.hwp_read(예산서)
    assert "1,944,000" in out and "◎ 예산 집행 내역" in out


def test_hwp_tables는_격자_JSON이다(예산서):
    import json
    tables = json.loads(mcp_server.hwp_tables(예산서))
    assert tables[0]["tables"][0]["grid"][2][3] == "정가"


def test_hwp_memos는_숨은_메모만_준다(예산서):
    assert "최신 자료 기준으로" in mcp_server.hwp_memos(예산서)


def test_없는_경로는_이유를_말한다():
    with pytest.raises(FileNotFoundError):
        mcp_server.hwp_read("/없는/경로.hwp")
