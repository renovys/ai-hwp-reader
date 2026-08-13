"""hwp-reader MCP 서버.

MCP를 말하는 도구라면 무엇에든 붙습니다. Claude Code·Claude Desktop, Codex CLI,
Gemini CLI, Cursor, VS Code, Windsurf, Zed 모두 같은 한 줄로 등록합니다.

    hwp-reader-mcp                 stdio (기본. 로컬 CLI·데스크톱 앱용)
    hwp-reader-mcp --transport http --port 8000
                                   streamable HTTP (원격 커넥터를 받는 웹 클라이언트용)

도구는 세 개뿐입니다. 읽기 전용이라 문서를 건드리지 않고, 네트워크로 문서를
보내지도 않습니다.

    hwp_read     본문·표·메모를 문서 순서대로
    hwp_tables   표만, 격자 그대로
    hwp_memos    숨은 메모만

MCP 파이썬 SDK는 2.0에서 `FastMCP`가 `MCPServer`로 바뀌었습니다. 둘 다 지원하므로
어느 버전이 깔려 있어도 그대로 돕니다.
"""

import argparse
import json
import os
import sys

from . import __version__
from .parser import read, render

try:                                                   # SDK 2.x
    from mcp.server import MCPServer as _Server
except ImportError:                                    # pragma: no cover
    try:                                               # SDK 1.x
        from mcp.server.fastmcp import FastMCP as _Server
    except ImportError:
        sys.exit("MCP SDK가 없습니다.  pip install 'hwp-reader[mcp]'")

mcp = _Server("hwp-reader")

_LIMIT = 400_000        # 한 번에 돌려줄 최대 글자 수


def _paths(target: str) -> list:
    if os.path.isfile(target):
        return [target]
    if os.path.isdir(target):
        return sorted(os.path.join(target, n) for n in os.listdir(target)
                      if n.lower().endswith((".hwp", ".hwpx")))
    raise FileNotFoundError(f"{target}: 파일이나 폴더를 찾을 수 없습니다")


def _clip(text: str) -> str:
    if len(text) <= _LIMIT:
        return text
    return text[:_LIMIT] + f"\n\n…(길이 제한으로 잘렸습니다. 전체 {len(text):,}자)"


@mcp.tool()
def hwp_read(path: str, format: str = "text") -> str:
    """한글 문서(HWP/HWPX)를 읽어 본문·표·메모를 문서 순서대로 돌려준다.

    Args:
        path: .hwp/.hwpx 파일 경로, 또는 그런 파일이 든 폴더 경로
        format: "text"(기본) 또는 "md"(표를 마크다운으로)
    """
    out = []
    for p in _paths(path):
        try:
            out.append(f"===== {os.path.basename(p)} =====\n"
                       + render(read(p), format))
        except Exception as exc:                       # noqa: BLE001
            out.append(f"===== {os.path.basename(p)} =====\n[실패] {exc}")
    return _clip("\n\n".join(out))


@mcp.tool()
def hwp_tables(path: str) -> str:
    """표만 JSON 격자로 돌려준다. 병합된 셀은 좌상단에만 값이 들어간다.

    Args:
        path: .hwp/.hwpx 파일 경로 또는 폴더 경로
    """
    out = []
    for p in _paths(path):
        try:
            tables = [{"rows": b["rows"], "cols": b["cols"], "grid": b["grid"]}
                      for b in read(p) if b["type"] == "table"]
            out.append({"file": os.path.basename(p), "tables": tables})
        except Exception as exc:                       # noqa: BLE001
            out.append({"file": os.path.basename(p), "error": str(exc)})
    return _clip(json.dumps(out, ensure_ascii=False, indent=1))


@mcp.tool()
def hwp_memos(path: str) -> str:
    """문서에 달린 숨은 메모(주석)만 뽑아낸다.

    본문에는 보이지 않아 놓치기 쉬운 검토 요청이 여기 들어 있는 경우가 많다.

    Args:
        path: .hwp/.hwpx 파일 경로 또는 폴더 경로
    """
    lines = []
    for p in _paths(path):
        try:
            memos = [b["text"] for b in read(p) if b["type"] == "memo"]
        except Exception as exc:                       # noqa: BLE001
            lines.append(f"{os.path.basename(p)}: [실패] {exc}")
            continue
        if memos:
            lines.append(os.path.basename(p))
            lines.extend(f"  - {m}" for m in memos)
    return "\n".join(lines) if lines else "메모가 없습니다."


def _serve(transport, host, port):
    if transport == "stdio":
        mcp.run()
        return
    try:                                               # SDK 2.x는 실행 인자로 받는다
        mcp.run("streamable-http", host=host, port=port)
    except TypeError:                                  # pragma: no cover
        settings = getattr(mcp, "settings", None)      # SDK 1.x는 설정 객체로 받는다
        if settings is None:
            raise
        settings.host, settings.port = host, port
        mcp.run("streamable-http")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="hwp-reader-mcp",
        description="한글 문서(HWP/HWPX) 읽기 도구를 MCP로 노출한다",
    )
    ap.add_argument("--transport", default="stdio", choices=["stdio", "http"],
                    help="stdio(기본)는 로컬 클라이언트, http는 원격 커넥터용")
    ap.add_argument("--host", default="127.0.0.1",
                    help="--transport http일 때 바인딩 주소 (기본 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8000,
                    help="--transport http일 때 포트 (기본 8000)")
    ap.add_argument("--version", action="version",
                    version=f"hwp-reader-mcp {__version__}")
    args = ap.parse_args(argv)
    _serve(args.transport, args.host, args.port)


if __name__ == "__main__":
    main()
