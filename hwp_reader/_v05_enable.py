"""0.5 의미 복원 계층을 코어에 연결한다."""
import posixpath
import sys

from . import _parser_core
from ._ole_fallback import FallbackOleFile, current_compat_warnings
from ._reader_v05 import install

_parser_core.OleFile = FallbackOleFile
install(_parser_core)

# _reader_v05의 함수들은 자기 모듈 전역을 런타임에 조회한다. 패키지와 단일 파일
# 모두 같은 방식으로 보강하기 위해 install 함수가 속한 실제 모듈을 잡는다.
_reader_runtime = sys.modules[install.__module__]
_original_xml_guard = _reader_runtime._xml_guard
_original_zip_guard = _reader_runtime._zip_guard
_MAX_ZIP_MEMBERS = 10_000


def _bounded_read_stream(ole, name, compressed):
    """정상 HWP fast path를 유지하면서 DEFLATE 출력 크기를 먼저 제한한다."""
    raw = ole.open(name)
    limit = _reader_runtime.MAX_HWP_STREAM_BYTES
    if len(raw) > limit:
        raise ValueError(f"{name}: HWP 스트림이 처리 상한을 넘는다")
    if not compressed:
        return raw

    decoder = _parser_core.zlib.decompressobj(-15)
    try:
        out = decoder.decompress(raw, limit + 1)
        if len(out) > limit or decoder.unconsumed_tail:
            raise ValueError(f"{name}: 압축 해제 결과가 처리 상한을 넘는다")
        out += decoder.flush(limit + 1 - len(out))
    except _parser_core.zlib.error as exc:
        raise ValueError(f"{name}: HWP 압축 스트림이 손상됐다") from exc
    if len(out) > limit or not decoder.eof or decoder.unconsumed_tail:
        raise ValueError(f"{name}: HWP 압축 스트림이 비정상적이거나 처리 상한을 넘는다")
    return out


def _guarded_xml(module, raw, section):
    # XML 선언부 앞에 긴 공백/주석을 둬 64 KiB 선두 검사만 우회하는 입력도 막는다.
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise ValueError(f"{section}: DTD/ENTITY가 있는 XML은 거부한다")
    return _original_xml_guard(module, raw, section)


def _guarded_zip(zf, label):
    infos = zf.infolist()
    if len(infos) > _MAX_ZIP_MEMBERS:
        raise ValueError(f"{label}: ZIP 멤버가 {_MAX_ZIP_MEMBERS}개 처리 상한을 넘는다")

    normalized = set()
    for info in infos:
        name = info.filename.replace("\\", "/")
        norm = posixpath.normpath(name)
        if norm.startswith("../") or norm == ".." or norm.startswith("/"):
            raise ValueError(f"{label}: 비정상 ZIP 경로다: {info.filename}")
        key = norm.casefold()
        if key in normalized:
            raise ValueError(f"{label}: 정규화한 ZIP 경로가 중복됐다: {info.filename}")
        normalized.add(key)
    return _original_zip_guard(zf, label)



# parser.py에서 hardening을 먼저 설치하므로 이 최종 bounded reader가 유지된다.
_parser_core._read_stream = _bounded_read_stream
_reader_runtime._xml_guard = _guarded_xml
_reader_runtime._zip_guard = _guarded_zip

_base_read_hwp = _parser_core.read_hwp
_base_read_hwpx = _parser_core.read_hwpx
_base_render = _parser_core.render


def _validate_table(table, what="표"):
    rows = table.get("rows", 0)
    cols = table.get("cols", 0)
    if rows and cols:
        occupied = bytearray(rows * cols)
        for cell in table.get("cells", []):
            row = cell.get("row", 0)
            col = cell.get("col", 0)
            rowspan = cell.get("rowspan", 1)
            colspan = cell.get("colspan", 1)
            for r in range(row, row + rowspan):
                start = r * cols + col
                end = start + colspan
                if any(occupied[start:end]):
                    raise ValueError(
                        f"손상된 {what}: 병합 셀 범위가 서로 겹친다 "
                        f"(row={row}, col={col}, rowspan={rowspan}, colspan={colspan})"
                    )
                occupied[start:end] = b"\x01" * colspan
    for nested in table.get("nested_tables", []):
        child = nested.get("table")
        if child:
            _validate_table(child, what + " 안의 표")


def _validate_blocks(blocks):
    for block in blocks:
        if block.get("type") == "table":
            _validate_table(block)


def _read_hwp(source, name=None):
    blocks = _base_read_hwp(source, name=name)
    _validate_blocks(blocks)
    notes = current_compat_warnings()
    if notes:
        blocks.insert(0, {"type": "warning", "text": "비표준 CFB 호환 모드: " + "; ".join(notes)})
    return blocks


def _read_hwpx(source, name=None):
    blocks = _base_read_hwpx(source, name=name)
    _validate_blocks(blocks)
    return blocks


def _render(blocks, fmt="text", tables_only=False):
    visible = [
        {"type": "text", "text": "[경고] " + block.get("text", "")}
        if block.get("type") == "warning" else block
        for block in blocks
    ]
    return _base_render(visible, fmt, tables_only)


_parser_core.read_hwp = _read_hwp
_parser_core.read_hwpx = _read_hwpx
_parser_core.render = _render
