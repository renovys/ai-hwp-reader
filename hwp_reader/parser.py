"""AI가 한글 문서(HWP 5.0 / HWPX)의 본문·표·메모를 구조대로 읽게 한다.

기본 파서는 Python 표준 라이브러리만 사용한다. HWP 5.0과 HWPX를 같은 블록
인터페이스로 반환해 ChatGPT·Claude·Gemini 같은 AI가 표 안의 숫자와 숨은 메모까지
근거로 삼을 수 있게 한다.

    from hwp_reader import read, render
    blocks = read("보고서.hwp")
    print(render(blocks, "md"))

blocks는 문서 순서대로 담긴 dict 목록이다.

    {"type": "text",  "text": "..."}
    {"type": "table", "rows": 9, "cols": 5, "grid": [[...], ...], "cells": [...]}
    {"type": "memo",  "text": "2Q 보고서로 수정해주세요."}
"""

import os
import re
import struct
import sys
import zipfile
import zlib
from xml.etree import ElementTree

from ._ole import OleFile

HWPTAG_BEGIN = 16
HWPTAG_PARA_HEADER = HWPTAG_BEGIN + 50
HWPTAG_PARA_TEXT = HWPTAG_BEGIN + 51
HWPTAG_CTRL_HEADER = HWPTAG_BEGIN + 55
HWPTAG_LIST_HEADER = HWPTAG_BEGIN + 56
HWPTAG_TABLE = HWPTAG_BEGIN + 61
HWPTAG_MEMO_LIST = HWPTAG_BEGIN + 77

CELL_OFFSET = 8
HWP_SIGNATURE = b"HWP Document File"
MAX_TABLE_CELLS = 1_000_000

CHAR_CTRL = {0, 10, 13}
WIDE_CTRL = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18,
             19, 20, 21, 22, 23}


def _section_number(name):
    """Section10이 Section2보다 앞서는 문자열 정렬 문제를 막는다."""
    match = re.search(r'(\d+)(?:\.[^.]+)?$', name)
    return int(match.group(1)) if match else sys.maxsize


def _validate_table_shape(n_rows, n_cols, what="표"):
    """손상된 문서가 비정상적으로 큰 격자를 할당하지 못하게 한다."""
    if n_rows < 0 or n_cols < 0:
        raise ValueError(f"손상된 {what}: 행·열 수가 음수다")
    if n_rows and n_cols and n_rows * n_cols > MAX_TABLE_CELLS:
        raise ValueError(f"손상된 {what}: 표 격자가 비정상적으로 크다 ({n_rows}x{n_cols})")


def _inline_table(grid):
    """중첩 표를 부모 셀 안에서도 AI가 잃지 않도록 한 줄 표기로 보존한다."""
    if not grid:
        return ""
    rows = [' | '.join(cell.strip() for cell in row) for row in grid]
    return '[중첩표] ' + ' / '.join(rows)


def _records(data):
    """레코드 스트림을 (tag, level, payload)로 풀어낸다."""
    out = []
    pos, end = 0, len(data)
    while pos < end:
        if pos + 4 > end:
            raise ValueError("손상된 HWP 레코드: 헤더가 4바이트보다 짧다")
        header = struct.unpack_from('<I', data, pos)[0]
        tag = header & 0x3FF
        level = (header >> 10) & 0x3FF
        size = (header >> 20) & 0xFFF
        pos += 4
        if size == 0xFFF:
            if pos + 4 > end:
                raise ValueError("손상된 HWP 레코드: 확장 크기가 잘렸다")
            size = struct.unpack_from('<I', data, pos)[0]
            pos += 4
        if size > end - pos:
            raise ValueError("손상된 HWP 레코드: payload가 섹션 끝을 넘는다")
        out.append((tag, level, data[pos:pos + size]))
        pos += size
    return out


def _decode_text(payload):
    """PARA_TEXT의 UTF-16LE 글자와 개체 제어를 분리한다."""
    out, run = [], bytearray()
    i, n = 0, len(payload) // 2
    while i < n:
        code = struct.unpack_from('<H', payload, i * 2)[0]
        if code in WIDE_CTRL or code in CHAR_CTRL:
            if run:
                out.append(run.decode('utf-16-le', 'replace'))
                run = bytearray()
            out.append(' ' if code in CHAR_CTRL else '')
            i += 8 if code in WIDE_CTRL else 1
            continue
        run += payload[i * 2:i * 2 + 2]
        i += 1
    if run:
        out.append(run.decode('utf-16-le', 'replace'))
    return ''.join(' ' if ord(ch) < 0x20 or ord(ch) == 0x7F else ch
                   for ch in ''.join(out))


def _read_stream(ole, name, compressed):
    raw = ole.open(name)
    if compressed:
        try:
            return zlib.decompress(raw, -15)
        except zlib.error:
            return raw
    return raw


def _grid(cells, n_rows, n_cols):
    """셀 목록을 행·열 격자로 복원한다. 병합 셀은 좌상단에만 값을 둔다."""
    _validate_table_shape(n_rows, n_cols)
    grid = [['' for _ in range(n_cols)] for _ in range(n_rows)]
    for c in cells:
        if 0 <= c['row'] < n_rows and 0 <= c['col'] < n_cols:
            grid[c['row']][c['col']] = c['text']
    return [row for row in grid if any(v.strip() for v in row)]


def _parse_table(records, idx):
    """TABLE 레코드 하나를 읽어 격자와 셀 목록을 돌려준다."""
    tag, level, payload = records[idx]
    if len(payload) < 8:
        raise ValueError("손상된 HWP 표: TABLE payload가 8바이트보다 짧다")
    n_rows, n_cols = struct.unpack_from('<HH', payload, 4)
    _validate_table_shape(n_rows, n_cols, "HWP 표")

    cells, cur = [], None
    i = idx + 1
    while i < len(records):
        t, lv, data = records[i]
        if lv < level:
            break
        if t in (HWPTAG_CTRL_HEADER, HWPTAG_TABLE) and lv <= level:
            break
        if t == HWPTAG_CTRL_HEADER and cur is not None and data[:4][::-1] == b'%unk':
            cur['text'] = (cur['text'] + ' ⟨메모⟩').strip()
        if t == HWPTAG_LIST_HEADER and lv == level:
            if len(data) < CELL_OFFSET + 8:
                raise ValueError("손상된 HWP 표: LIST_HEADER 셀 정보가 잘렸다")
            col, row, cspan, rspan = struct.unpack_from('<4H', data, CELL_OFFSET)
            cur = {'row': row, 'col': col, 'rowspan': rspan or 1,
                   'colspan': cspan or 1, 'text': ''}
            cells.append(cur)
        elif t == HWPTAG_PARA_TEXT and cur is not None:
            piece = _decode_text(data).strip()
            if piece:
                cur['text'] = (cur['text'] + ' ' + piece).strip()
        i += 1

    return {'rows': n_rows, 'cols': n_cols, 'cells': cells,
            'grid': _grid(cells, n_rows, n_cols)}, i


def _parse_memo(records, idx):
    """메모(주석) 하나를 읽는다."""
    level = records[idx][1]
    parts = []
    i = idx + 1
    while i < len(records):
        tag, lv, data = records[i]
        if tag == HWPTAG_MEMO_LIST or tag == HWPTAG_TABLE:
            break
        if tag == HWPTAG_CTRL_HEADER and lv <= level:
            break
        if tag == HWPTAG_PARA_TEXT:
            piece = _decode_text(data).strip()
            if piece:
                parts.append(piece)
        i += 1
    return ' '.join(parts).strip(), i


def _hwp_flags(head, path):
    """FileHeader의 형식·압축·암호 플래그를 검증해 돌려준다."""
    if len(head) <= 36:
        raise ValueError(f"{path}: FileHeader가 37바이트보다 짧다")
    if not head.startswith(HWP_SIGNATURE):
        raise ValueError(f"{path}: HWP 5.0 FileHeader 시그니처가 아니다")
    compressed = bool(head[36] & 0x01)
    encrypted = bool(head[36] & 0x02)
    return compressed, encrypted


def read_hwp(path):
    """HWP 5.0을 문서 순서대로 블록 목록으로 읽는다."""
    try:
        ole = OleFile(path)
    except ValueError:
        raise ValueError(
            f"{path}: OLE 파일이 아니다. HWPX면 확장자를 .hwpx로 두고 다시 실행"
        ) from None

    if not ole.exists('FileHeader'):
        raise ValueError(f"{path}: FileHeader 스트림이 없다")
    compressed, encrypted = _hwp_flags(ole.open('FileHeader'), path)
    if encrypted:
        raise RuntimeError(f"{path}: 암호가 걸린 문서다. 암호를 풀고 다시 저장할 것")

    names = sorted((name for name in ole.listdir()
                    if name.startswith('BodyText/Section')),
                   key=_section_number)
    if not names:
        raise ValueError(f"{path}: BodyText 섹션이 없다")

    blocks = []
    for name in names:
        records = _records(_read_stream(ole, name, compressed))
        i = 0
        while i < len(records):
            tag, level, payload = records[i]
            if tag == HWPTAG_TABLE:
                table, i = _parse_table(records, i)
                if table['grid']:
                    blocks.append({'type': 'table', **table})
                continue
            if tag == HWPTAG_MEMO_LIST:
                memo, i = _parse_memo(records, i)
                if memo:
                    blocks.append({'type': 'memo', 'text': memo})
                continue
            if tag == HWPTAG_PARA_TEXT:
                line = _decode_text(payload).strip()
                if line:
                    blocks.append({'type': 'text', 'text': line})
            i += 1
    return blocks


def _hwpx_local(tag):
    return tag.rsplit('}', 1)[-1] if isinstance(tag, str) else ''


def _hwpx_int(node, *names):
    """속성 이름이 판마다 달라 후보를 순서대로 본다."""
    for name in names:
        value = node.get(name)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _hwpx_text_of(node):
    """이 노드가 품은 글자를 모은다. 중첩 표는 별도 처리하므로 제외한다."""
    out = []

    def walk(n):
        for child in n:
            local = _hwpx_local(child.tag)
            if local == 'tbl':
                continue
            if local == 't' and child.text:
                out.append(child.text)
            walk(child)

    walk(node)
    return re.sub(r'\s+', ' ', ''.join(out)).strip()


def _hwpx_cell_content(node):
    """셀의 일반 글자와 중첩 표를 함께 읽는다."""
    out = []
    nested_tables = []

    def walk(n):
        for child in n:
            local = _hwpx_local(child.tag)
            if local == 'tbl':
                nested = _hwpx_table(child)
                if nested['grid']:
                    nested_tables.append(nested)
                    out.append(' ' + _inline_table(nested['grid']) + ' ')
                continue
            if local == 't' and child.text:
                out.append(child.text)
            walk(child)

    walk(node)
    text = re.sub(r'\s+', ' ', ''.join(out)).strip()
    return text, nested_tables


def _hwpx_table(node):
    """<hp:tbl> 하나를 셀 좌표와 중첩 표 내용까지 살려 읽는다."""
    cells = []
    rows = [tr for tr in node if _hwpx_local(tr.tag) == 'tr']
    cursor = {}

    for r, tr in enumerate(rows):
        for tc in tr:
            if _hwpx_local(tc.tag) != 'tc':
                continue
            addr = next((c for c in tc if _hwpx_local(c.tag) == 'cellAddr'), None)
            span = next((c for c in tc if _hwpx_local(c.tag) == 'cellSpan'), None)

            colspan = _hwpx_int(span, 'colSpan', 'colspan') if span is not None else None
            rowspan = _hwpx_int(span, 'rowSpan', 'rowspan') if span is not None else None
            colspan = colspan if colspan is not None and colspan > 0 else 1
            rowspan = rowspan if rowspan is not None and rowspan > 0 else 1

            col = _hwpx_int(addr, 'colAddr', 'col') if addr is not None else None
            row = _hwpx_int(addr, 'rowAddr', 'row') if addr is not None else None
            if (col is not None and col < 0) or (row is not None and row < 0):
                raise ValueError("손상된 HWPX 표: 셀 주소가 음수다")
            if col is None or row is None:
                row = r
                col = cursor.get(r, 0)
                while any(c['row'] <= row < c['row'] + c['rowspan']
                          and c['col'] <= col < c['col'] + c['colspan'] for c in cells):
                    col += 1
                cursor[r] = col + colspan

            text, nested_tables = _hwpx_cell_content(tc)
            cell = {'row': row, 'col': col, 'rowspan': rowspan,
                    'colspan': colspan, 'text': text}
            if nested_tables:
                cell['nested_tables'] = nested_tables
            cells.append(cell)

    n_rows = _hwpx_int(node, 'rowCnt', 'rowcnt') or 0
    n_cols = _hwpx_int(node, 'colCnt', 'colcnt') or 0
    n_rows = max([n_rows] + [c['row'] + c['rowspan'] for c in cells] or [0])
    n_cols = max([n_cols] + [c['col'] + c['colspan'] for c in cells] or [0])
    _validate_table_shape(n_rows, n_cols, "HWPX 표")

    return {'rows': n_rows, 'cols': n_cols, 'cells': cells,
            'grid': _grid(cells, n_rows, n_cols)}


def _hwpx_append_memos(node, blocks):
    """memo 또는 memogroup 하나를 중복 없이 메모 블록으로 추가한다."""
    local = _hwpx_local(node.tag)
    memos = ([node] if local == 'memo' else
             [m for m in node.iter() if _hwpx_local(m.tag) == 'memo'])
    for memo in memos:
        text = _hwpx_text_of(memo)
        if text:
            blocks.append({'type': 'memo', 'text': text})


def _hwpx_walk(node, blocks):
    """문서 순서를 지키며 문단·표·메모를 뽑는다."""
    for child in node:
        local = _hwpx_local(child.tag)
        if local == 'tbl':
            table = _hwpx_table(child)
            if table['grid']:
                blocks.append({'type': 'table', **table})
        elif local in ('memo', 'memogroup'):
            _hwpx_append_memos(child, blocks)
        elif local == 'p':
            _hwpx_paragraph(child, blocks)
        else:
            _hwpx_walk(child, blocks)


def _hwpx_paragraph(para, blocks):
    """문단 하나. 문단 도중에 표나 메모가 끼어들면 그 자리에서 블록으로 끊는다."""
    buf = []

    def flush():
        line = re.sub(r'\s+', ' ', ''.join(buf)).strip()
        del buf[:]
        if line:
            blocks.append({'type': 'text', 'text': line})

    def walk(n):
        for child in n:
            local = _hwpx_local(child.tag)
            if local == 'tbl':
                flush()
                table = _hwpx_table(child)
                if table['grid']:
                    blocks.append({'type': 'table', **table})
                continue
            if local in ('memo', 'memogroup'):
                flush()
                _hwpx_append_memos(child, blocks)
                continue
            if local == 't' and child.text:
                buf.append(child.text)
            walk(child)

    walk(para)
    flush()


def read_hwpx(path):
    """HWPX는 ZIP + OWPML(XML)이라 표준 라이브러리만으로 읽힌다."""
    if not zipfile.is_zipfile(path):
        raise ValueError(f"{path}: HWPX가 아니다(ZIP이 아님). HWP 5.0이면 확장자를 .hwp로 둘 것")

    blocks = []
    try:
        with zipfile.ZipFile(path) as z:
            sections = sorted((n for n in z.namelist()
                               if re.match(r'Contents/section\d+\.xml$', n, re.IGNORECASE)),
                              key=_section_number)
            if not sections:
                raise ValueError(f"{path}: Contents/sectionN.xml을 찾지 못했다")

            for name in sections:
                try:
                    root = ElementTree.fromstring(z.read(name))
                except (ElementTree.ParseError, KeyError) as exc:
                    raise ValueError(f"{path}: {name} XML을 읽지 못했다: {exc}") from None
                _hwpx_walk(root, blocks)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{path}: 손상된 HWPX ZIP 컨테이너다: {exc}") from None
    return blocks


def read(path):
    """확장자로 갈래를 정하되, 어긋나면 실제 컨테이너를 보고 되돌린다."""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.hwpx':
        if not zipfile.is_zipfile(path):
            return read_hwp(path)
        return read_hwpx(path)
    if ext == '.hwp':
        if zipfile.is_zipfile(path):
            return read_hwpx(path)
        return read_hwp(path)
    if zipfile.is_zipfile(path):
        return read_hwpx(path)
    return read_hwp(path)


def _md_cell(text):
    """셀 안의 파이프가 Markdown 열 구분자로 해석되지 않게 한다."""
    return text.replace('\\', '\\\\').replace('|', '\\|')


def render(blocks, fmt='text', tables_only=False):
    lines = []
    for b in blocks:
        if b['type'] == 'memo':
            lines.append('[메모] ' + b['text'])
            continue
        if b['type'] == 'text':
            if not tables_only:
                lines.append(b['text'])
            continue
        grid = b['grid']
        if fmt == 'md':
            width = max(len(r) for r in grid)
            padded = [r + [''] * (width - len(r)) for r in grid]
            escaped = [[_md_cell(cell) for cell in row] for row in padded]
            lines.append('| ' + ' | '.join(escaped[0]) + ' |')
            lines.append('|' + '---|' * width)
            for row in escaped[1:]:
                lines.append('| ' + ' | '.join(row) + ' |')
            lines.append('')
        else:
            lines.append('[표]')
            for row in grid:
                lines.append(' | '.join(row))
            lines.append('')
    return '\n'.join(lines)