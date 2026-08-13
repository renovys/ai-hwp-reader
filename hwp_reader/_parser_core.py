"""AI가 한글 문서(HWP/HWPX)를 구조대로 읽게 하는 파서.

본문뿐 아니라 병합 표, 표 안의 표, 메모, 변경추적 정보를 보존한다.
기본 파서는 Python 표준 라이브러리만 사용하며 문서를 수정하지 않는다.
"""

import io
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
HWPTAG_PARA_RANGE_TAG = HWPTAG_BEGIN + 54
HWPTAG_CTRL_HEADER = HWPTAG_BEGIN + 55
HWPTAG_LIST_HEADER = HWPTAG_BEGIN + 56
HWPTAG_TABLE = HWPTAG_BEGIN + 61
HWPTAG_MEMO_LIST = HWPTAG_BEGIN + 77

CELL_OFFSET = 8
HWP_SIGNATURE = b"HWP Document File"
MAX_TABLE_CELLS = 1_000_000
MAX_ARCHIVE_DOCUMENTS = 200
MAX_ARCHIVE_MEMBER_SIZE = 256 * 1024 * 1024
ARCHIVE_EXTS = ('.hwp', '.hwpx')

CHAR_CTRL = {0, 10, 13}
WIDE_CTRL = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18,
             19, 20, 21, 22, 23}
TRACK_INSERT = 0x10
TRACK_DELETE = 0x11


def _label(source, name=None):
    if name:
        return name
    if isinstance(source, (str, os.PathLike)):
        return os.fspath(source)
    return '<메모리 문서>'


def _section_number(name):
    match = re.search(r'(\d+)(?:\.[^.]+)?$', name)
    return int(match.group(1)) if match else sys.maxsize


def _validate_table_shape(n_rows, n_cols, what="표"):
    if n_rows < 0 or n_cols < 0:
        raise ValueError(f"손상된 {what}: 행·열 수가 음수다")
    if n_rows and n_cols and n_rows * n_cols > MAX_TABLE_CELLS:
        raise ValueError(f"손상된 {what}: 표 격자가 비정상적으로 크다 ({n_rows}x{n_cols})")


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


def _decode_change_range(payload, start, end):
    """변경추적 range의 일반 텍스트만 위치 그대로 읽는다."""
    units = len(payload) // 2
    if start < 0 or end < start or start >= units:
        return ''
    end = min(end, units - 1)
    codes = [struct.unpack_from('<H', payload, i * 2)[0]
             for i in range(start, end + 1)]
    # 추적 range가 확장 제어문자를 가로지르면 텍스트 변경이 아니다.
    if any(code < 0x20 for code in codes):
        return ''
    raw = payload[start * 2:(end + 1) * 2]
    text = raw.decode('utf-16-le', 'replace')
    return re.sub(r'\s+', ' ', text).strip()


def _read_stream(ole, name, compressed):
    raw = ole.open(name)
    if compressed:
        try:
            return zlib.decompress(raw, -15)
        except zlib.error:
            return raw
    return raw


def _grid(cells, n_rows, n_cols):
    _validate_table_shape(n_rows, n_cols)
    grid = [['' for _ in range(n_cols)] for _ in range(n_rows)]
    for cell in cells:
        if 0 <= cell['row'] < n_rows and 0 <= cell['col'] < n_cols:
            grid[cell['row']][cell['col']] = cell['text']
    return [row for row in grid if any(str(v).strip() for v in row)]


def _parse_table(records, idx):
    """HWP TABLE 하나를 읽고 표 안의 표도 parent cell과 함께 보존한다."""
    _, level, payload = records[idx]
    if len(payload) < 8:
        raise ValueError("손상된 HWP 표: TABLE payload가 8바이트보다 짧다")
    n_rows, n_cols = struct.unpack_from('<HH', payload, 4)
    _validate_table_shape(n_rows, n_cols, "HWP 표")

    cells, nested, cur = [], [], None
    i = idx + 1
    while i < len(records):
        tag, lv, data = records[i]
        if lv < level:
            break
        if tag in (HWPTAG_CTRL_HEADER, HWPTAG_TABLE) and lv <= level:
            break
        if tag == HWPTAG_TABLE and lv > level:
            table, next_i = _parse_table(records, i)
            if table['grid']:
                nested.append({'row': cur['row'] if cur else None,
                               'col': cur['col'] if cur else None,
                               'table': table})
                if cur is not None:
                    cur['text'] = (cur['text'] + ' ⟨표 안의 표⟩').strip()
            i = next_i
            continue
        if tag == HWPTAG_CTRL_HEADER and cur is not None and data[:4][::-1] == b'%unk':
            cur['text'] = (cur['text'] + ' ⟨메모⟩').strip()
        if tag == HWPTAG_LIST_HEADER and lv == level:
            if len(data) < CELL_OFFSET + 8:
                raise ValueError("손상된 HWP 표: LIST_HEADER 셀 정보가 잘렸다")
            col, row, cspan, rspan = struct.unpack_from('<4H', data, CELL_OFFSET)
            cur = {'row': row, 'col': col, 'rowspan': rspan or 1,
                   'colspan': cspan or 1, 'text': ''}
            cells.append(cur)
        elif tag == HWPTAG_PARA_TEXT and cur is not None:
            piece = _decode_text(data).strip()
            if piece:
                cur['text'] = (cur['text'] + ' ' + piece).strip()
        i += 1

    return {'rows': n_rows, 'cols': n_cols, 'cells': cells,
            'grid': _grid(cells, n_rows, n_cols), 'nested_tables': nested}, i


def _parse_memo(records, idx):
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


def _parse_change_ranges(records, section=None):
    """ViewText의 PARA_RANGE_TAG에서 추가/삭제 변경추적 구간을 읽는다."""
    out = []
    current_text = None
    for tag, _, payload in records:
        if tag == HWPTAG_PARA_TEXT:
            current_text = payload
            continue
        if tag != HWPTAG_PARA_RANGE_TAG or current_text is None or len(payload) % 12:
            continue
        for offset in range(0, len(payload), 12):
            start, end, raw_tag = struct.unpack_from('<III', payload, offset)
            kind_code = raw_tag >> 24
            if kind_code not in (TRACK_INSERT, TRACK_DELETE):
                continue
            text = _decode_change_range(current_text, start, end)
            if not text:
                continue
            out.append({
                'type': 'revision',
                'kind': 'insert' if kind_code == TRACK_INSERT else 'delete',
                'text': text,
                'section': section,
                'start': start,
                'end': end,
                'change_id': raw_tag & 0xFFFFFF,
            })
    return out


def _read_hwp_changes(ole, compressed):
    names = sorted((name for name in ole.listdir()
                    if name.startswith('ViewText/Section')),
                   key=_section_number)
    changes = []
    for name in names:
        changes.extend(_parse_change_ranges(
            _records(_read_stream(ole, name, compressed)), _section_number(name)))
    unique, seen = [], set()
    for change in changes:
        key = (change['kind'], change['text'], change['section'],
               change['start'], change['end'])
        if key not in seen:
            seen.add(key)
            unique.append(change)
    return unique


def _hwp_flags(head, label):
    if len(head) <= 36:
        raise ValueError(f"{label}: FileHeader가 37바이트보다 짧다")
    if not head.startswith(HWP_SIGNATURE):
        raise ValueError(f"{label}: HWP 5.0 FileHeader 시그니처가 아니다")
    return bool(head[36] & 0x01), bool(head[36] & 0x02)


def read_hwp(source, name=None):
    """HWP 5.0 최종본과 표·메모·변경추적을 읽는다."""
    label = _label(source, name)
    try:
        ole = OleFile(source)
    except ValueError:
        raise ValueError(f"{label}: OLE HWP 파일이 아니다") from None
    if not ole.exists('FileHeader'):
        raise ValueError(f"{label}: FileHeader 스트림이 없다")
    compressed, encrypted = _hwp_flags(ole.open('FileHeader'), label)
    if encrypted:
        raise RuntimeError(f"{label}: 암호가 걸린 문서다. 암호를 풀고 다시 저장할 것")

    names = sorted((stream for stream in ole.listdir()
                    if stream.startswith('BodyText/Section')),
                   key=_section_number)
    if not names:
        raise ValueError(f"{label}: BodyText 섹션이 없다")

    blocks = []
    for stream in names:
        records = _records(_read_stream(ole, stream, compressed))
        i = 0
        while i < len(records):
            tag, _, payload = records[i]
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

    blocks.extend(_read_hwp_changes(ole, compressed))
    return blocks


# -------------------------------------------------------------------- HWPX

def _hwpx_local(tag):
    return tag.rsplit('}', 1)[-1] if isinstance(tag, str) else ''


def _hwpx_int(node, *names):
    if node is None:
        return None
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


def _direct_nested_tables(node):
    found = []
    def walk(n):
        for child in n:
            if _hwpx_local(child.tag) == 'tbl':
                found.append(child)
            else:
                walk(child)
    walk(node)
    return found


def _hwpx_table(node):
    """HWPX 표 하나를 셀 좌표와 표 안의 표까지 살려 읽는다."""
    cells, nested = [], []
    rows = [tr for tr in node if _hwpx_local(tr.tag) == 'tr']
    cursor = {}
    for r, tr in enumerate(rows):
        for tc in tr:
            if _hwpx_local(tc.tag) != 'tc':
                continue
            addr = next((c for c in tc if _hwpx_local(c.tag) == 'cellAddr'), None)
            span = next((c for c in tc if _hwpx_local(c.tag) == 'cellSpan'), None)
            colspan = _hwpx_int(span, 'colSpan', 'colspan') or 1
            rowspan = _hwpx_int(span, 'rowSpan', 'rowspan') or 1
            col = _hwpx_int(addr, 'colAddr', 'col')
            row = _hwpx_int(addr, 'rowAddr', 'row')
            if (col is not None and col < 0) or (row is not None and row < 0):
                raise ValueError("손상된 HWPX 표: 셀 주소가 음수다")
            if col is None or row is None:
                row = r
                col = cursor.get(r, 0)
                while any(c['row'] <= row < c['row'] + c['rowspan']
                          and c['col'] <= col < c['col'] + c['colspan'] for c in cells):
                    col += 1
                cursor[r] = col + colspan

            nested_nodes = _direct_nested_tables(tc)
            text = _hwpx_text_of(tc)
            if nested_nodes:
                text = (text + ' ⟨표 안의 표⟩').strip()
            cells.append({'row': row, 'col': col, 'rowspan': rowspan,
                          'colspan': colspan, 'text': text})
            for nested_node in nested_nodes:
                table = _hwpx_table(nested_node)
                if table['grid']:
                    nested.append({'row': row, 'col': col, 'table': table})

    n_rows = _hwpx_int(node, 'rowCnt', 'rowcnt') or 0
    n_cols = _hwpx_int(node, 'colCnt', 'colcnt') or 0
    n_rows = max([n_rows] + [c['row'] + c['rowspan'] for c in cells] or [0])
    n_cols = max([n_cols] + [c['col'] + c['colspan'] for c in cells] or [0])
    _validate_table_shape(n_rows, n_cols, "HWPX 표")
    return {'rows': n_rows, 'cols': n_cols, 'cells': cells,
            'grid': _grid(cells, n_rows, n_cols), 'nested_tables': nested}


def _hwpx_append_memos(node, blocks):
    local = _hwpx_local(node.tag)
    memos = ([node] if local == 'memo' else
             [m for m in node.iter() if _hwpx_local(m.tag) == 'memo'])
    for memo in memos:
        text = _hwpx_text_of(memo)
        if text:
            blocks.append({'type': 'memo', 'text': text})


def _hwpx_walk(node, blocks):
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


def _zip_handle(source):
    if isinstance(source, (bytes, bytearray, memoryview)):
        return io.BytesIO(bytes(source))
    return source


def _is_zip(source):
    try:
        return zipfile.is_zipfile(_zip_handle(source))
    except (OSError, TypeError, ValueError):
        return False


def _is_hwpx(source):
    if not _is_zip(source):
        return False
    try:
        with zipfile.ZipFile(_zip_handle(source)) as zf:
            return any(re.match(r'Contents/section\d+\.[Xx][Mm][Ll]$', n)
                       for n in zf.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def read_hwpx(source, name=None):
    label = _label(source, name)
    if not _is_zip(source):
        raise ValueError(f"{label}: HWPX가 아니다(ZIP 컨테이너가 아님)")
    blocks = []
    with zipfile.ZipFile(_zip_handle(source)) as zf:
        sections = sorted((n for n in zf.namelist()
                           if re.match(r'Contents/section\d+\.[Xx][Mm][Ll]$', n)),
                          key=_section_number)
        if not sections:
            raise ValueError(f"{label}: Contents/sectionN.xml을 찾지 못했다")
        for section in sections:
            try:
                root = ElementTree.fromstring(zf.read(section))
            except ElementTree.ParseError as exc:
                raise ValueError(f"{label}: 손상된 HWPX XML ({section})") from exc
            _hwpx_walk(root, blocks)
    return blocks


# ------------------------------------------------------------------ 입력 묶음

def read(source, name=None):
    """HWP/HWPX 한 문서를 읽는다. 확장자보다 실제 컨테이너를 우선한다."""
    label = _label(source, name)
    if _is_hwpx(source):
        return read_hwpx(source, name=label)
    if _is_zip(source):
        raise ValueError(f"{label}: 여러 문서가 든 ZIP이다. read_documents()를 사용할 것")
    return read_hwp(source, name=label)


def read_documents(source):
    """HWP/HWPX 또는 여러 문서가 든 ZIP을 한 번에 읽는다.

    ZIP은 디스크에 풀지 않고 멤버 바이트를 직접 읽는다.
    반환값: [{"file": "문서.hwp", "blocks": [...]}, ...]
    """
    label = _label(source)
    if not _is_zip(source) or _is_hwpx(source):
        return [{'file': os.path.basename(label), 'blocks': read(source)}]

    documents = []
    with zipfile.ZipFile(_zip_handle(source)) as zf:
        members = [info for info in zf.infolist()
                   if not info.is_dir()
                   and not info.filename.startswith('__MACOSX/')
                   and info.filename.lower().endswith(ARCHIVE_EXTS)]
        if not members:
            raise ValueError(f"{label}: ZIP 안에 HWP/HWPX가 없다")
        if len(members) > MAX_ARCHIVE_DOCUMENTS:
            raise ValueError(f"{label}: ZIP 안 문서가 {MAX_ARCHIVE_DOCUMENTS}개를 넘는다")
        for info in members:
            if info.file_size > MAX_ARCHIVE_MEMBER_SIZE:
                raise ValueError(f"{label}: ZIP 멤버가 너무 크다: {info.filename}")
            data = zf.read(info)
            documents.append({'file': info.filename,
                              'blocks': read(data, name=info.filename)})
    return documents


# ------------------------------------------------------------------ 출력

def _md_cell(text):
    return str(text).replace('\\', '\\\\').replace('|', '\\|').replace('\n', '<br>')


def _render_table(table, fmt, lines):
    grid = table.get('grid') or []
    if not grid:
        return
    if fmt == 'md':
        width = max(len(row) for row in grid)
        padded = [row + [''] * (width - len(row)) for row in grid]
        escaped = [[_md_cell(cell) for cell in row] for row in padded]
        lines.append('| ' + ' | '.join(escaped[0]) + ' |')
        lines.append('|' + '---|' * width)
        for row in escaped[1:]:
            lines.append('| ' + ' | '.join(row) + ' |')
        lines.append('')
    else:
        lines.append('[표]')
        for row in grid:
            lines.append(' | '.join(str(cell) for cell in row))
        lines.append('')

    for nested in table.get('nested_tables', []):
        row, col = nested.get('row'), nested.get('col')
        where = '' if row is None or col is None else f' · {row + 1}행 {col + 1}열'
        lines.append(f'[표 안의 표{where}]')
        _render_table(nested['table'], fmt, lines)


def render(blocks, fmt='text', tables_only=False):
    lines = []
    for block in blocks:
        kind = block['type']
        if kind == 'memo':
            lines.append('[메모] ' + block['text'])
            continue
        if kind == 'revision':
            label = '추가' if block['kind'] == 'insert' else '삭제'
            lines.append(f'[변경추적 {label}] {block["text"]}')
            continue
        if kind == 'text':
            if not tables_only:
                lines.append(block['text'])
            continue
        if kind == 'table':
            _render_table(block, fmt, lines)
    return '\n'.join(lines)


def render_documents(documents, fmt='md'):
    """여러 문서를 AI가 파일별로 구분하기 쉬운 문자열로 렌더링한다."""
    chunks = []
    for document in documents:
        chunks.append(f'\n{"=" * 70}\n{document["file"]}\n{"=" * 70}\n')
        chunks.append(render(document['blocks'], fmt))
    return '\n'.join(chunks).strip()
