"""ai-hwp-reader MCP 서버.

Claude Code·Claude Desktop, Codex CLI, Gemini CLI, Cursor, VS Code 등 MCP
클라이언트에서 HWP/HWPX/ZIP을 읽기 전용으로 다룬다. 문서를 네트워크로 보내지 않는다.
"""

import argparse
import json
import os
import sys

from . import __version__
from .parser import read_documents, render_documents

try:
    from mcp.server import MCPServer as _Server
except ImportError:                                    # pragma: no cover
    try:
        from mcp.server.fastmcp import FastMCP as _Server
    except ImportError:
        sys.exit("MCP SDK가 없습니다.  pip install 'ai-hwp-reader[mcp]'")

mcp = _Server("ai-hwp-reader")
_LIMIT = 400_000
_EXTENSIONS = (".hwp", ".hwpx", ".zip")


def _paths(target: str) -> list:
    if os.path.isfile(target):
        return [target]
    if os.path.isdir(target):
        return sorted(
            os.path.join(target, name)
            for name in os.listdir(target)
            if name.lower().endswith(_EXTENSIONS)
        )
    raise FileNotFoundError(f"{target}: 파일이나 폴더를 찾을 수 없습니다")


def _clip(text: str) -> str:
    if len(text) <= _LIMIT:
        return text
    return text[:_LIMIT] + f"\n\n…(길이 제한으로 잘렸습니다. 전체 {len(text):,}자)"


def _json(value) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=1)
    if len(text) <= _LIMIT:
        return text
    # JSON을 중간에서 잘라 문법을 깨뜨리지 않는다.
    return json.dumps(
        {
            "truncated": True,
            "message": f"응답이 {_LIMIT:,}자 제한을 넘어 미리보기만 반환합니다.",
            "preview": text[:_LIMIT // 2],
        },
        ensure_ascii=False,
        indent=1,
    )


def _docs(path):
    return read_documents(path)


@mcp.tool()
def hwp_read(path: str, format: str = "text") -> str:
    """HWP/HWPX/ZIP 또는 해당 파일들이 든 폴더를 읽어 구조 보존 텍스트를 반환한다."""
    out = []
    for item in _paths(path):
        try:
            out.append(render_documents(_docs(item), format))
        except Exception as exc:                       # noqa: BLE001
            out.append(f"===== {os.path.basename(item)} =====\n[실패] {exc}")
    return _clip("\n\n".join(out))


@mcp.tool()
def hwp_tables(path: str) -> str:
    """HWP/HWPX/ZIP의 표만 JSON 격자로 반환한다."""
    out = []
    for item in _paths(path):
        try:
            for doc in _docs(item):
                if doc.get("error"):
                    out.append({"file": doc["file"], "error": doc["error"]})
                    continue
                tables = [
                    {"rows": block["rows"], "cols": block["cols"], "grid": block["grid"]}
                    for block in doc.get("blocks", [])
                    if block.get("type") == "table"
                ]
                out.append({"file": doc["file"], "tables": tables})
        except Exception as exc:                       # noqa: BLE001
            out.append({"file": os.path.basename(item), "error": str(exc)})
    return _json(out)


@mcp.tool()
def hwp_memos(path: str) -> str:
    """HWP/HWPX/ZIP의 숨은 메모만 파일별로 반환한다."""
    lines = []
    for item in _paths(path):
        try:
            for doc in _docs(item):
                if doc.get("error"):
                    lines.append(f"{doc['file']}: [실패] {doc['error']}")
                    continue
                memos = [
                    block.get("text", "") for block in doc.get("blocks", [])
                    if block.get("type") == "memo"
                ]
                if memos:
                    lines.append(doc["file"])
                    lines.extend(f"  - {memo}" for memo in memos)
        except Exception as exc:                       # noqa: BLE001
            lines.append(f"{os.path.basename(item)}: [실패] {exc}")
    return _clip("\n".join(lines)) if lines else "메모가 없습니다."


@mcp.tool()
def hwp_revisions(path: str) -> str:
    """HWP/HWPX/ZIP에서 변경추적 추가·삭제 항목만 반환한다."""
    lines = []
    for item in _paths(path):
        try:
            for doc in _docs(item):
                if doc.get("error"):
                    lines.append(f"{doc['file']}: [실패] {doc['error']}")
                    continue
                revisions = [
                    block for block in doc.get("blocks", [])
                    if block.get("type") == "revision"
                ]
                if revisions:
                    lines.append(doc["file"])
                    for block in revisions:
                        label = "추가" if block.get("kind") == "insert" else "삭제"
                        lines.append(f"  - [{label}] {block.get('text', '')}")
        except Exception as exc:                       # noqa: BLE001
            lines.append(f"{os.path.basename(item)}: [실패] {exc}")
    return _clip("\n".join(lines)) if lines else "변경추적 항목이 없습니다."


def _serve(transport, host, port):
    if transport == "stdio":
        mcp.run()
        return
    try:
        mcp.run("streamable-http", host=host, port=port)
    except TypeError:                                  # pragma: no cover
        settings = getattr(mcp, "settings", None)
        if settings is None:
            raise
        settings.host, settings.port = host, port
        mcp.run("streamable-http")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ai-hwp-reader-mcp",
        description="한글 문서(HWP/HWPX/ZIP) 읽기 도구를 MCP로 노출한다",
    )
    parser.add_argument("--transport", default="stdio", choices=["stdio", "http"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--version", action="version", version=f"ai-hwp-reader-mcp {__version__}")
    args = parser.parse_args(argv)
    _serve(args.transport, args.host, args.port)


if __name__ == "__main__":
    main()
