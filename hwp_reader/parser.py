"""한글 문서(HWP 5.0 / HWPX)를 표 구조까지 살려 읽는다.

의존성은 HWP 5.0을 읽을 때의 olefile 하나뿐이고, HWPX는 표준 라이브러리만으로 읽는다.
한컴 오피스도, 한컴 라이선스도 필요 없다.

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

HWPTAG_BEGIN = 16
HWPTAG_PARA_HEADER = HWPTAG_BEGIN + 50   # 66
HWPTAG_PARA_TEXT = HWPTAG_BEGIN + 51     # 67
HWPTAG_CTRL_HEADER = HWPTAG_BEGIN + 55   # 71
HWPTAG_LIST_HEADER = HWPTAG_BEGIN + 56   # 72
HWPTAG_TABLE = HWPTAG_BEGIN + 61         # 77
HWPTAG_MEMO_LIST = HWPTAG_BEGIN + 77     # 93 · 메모(주석) 본문이 이 뒤에 붙는다

CELL_OFFSET = 8   # col(2) row(2) colspan(2) rowspan(2)

# 본문 글자 스트림에 섞인 제어 문자. 폭을 틀리면 뒤따르는 이진 데이터가 글자로 새어
# 나와 숫자 뒤에 깨진 문자가 붙는다(예: "12,600浵ࡦ").
CHAR_CTRL = {0, 10, 13}                      # 1워드
WIDE_CTRL = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18,
             19, 20, 21, 22, 23}             # 8워드(16바이트)


# ------------------------------------------------------------------ HWP 5.0

def _records(data):
    """레코드 스트림을 (tag, level, payload)로 풀어낸다."""
    out = []
    pos, end = 0, len(data)
    while pos + 4 <= end:
        header = struct.unpack_from('<I', data, pos)[0]
        tag = header & 0x3FF
        level = (header >> 10) & 0x3FF
        size = (header >> 20) & 0xFFF
        pos += 4
        if size == 0xFFF:
            size = struct.unpack_from('<I', data, pos)[0]
            pos += 4
        out.append((tag, level, data[pos:pos + size]))
        pos += size
    return out


def _decode_text(payload):
    """PARA_TEXT는 UTF-16LE인데 개체 자리를 나타내는 제어 문자가 섞여 있다."""
    out, run = [], bytearray()
    i, n = 0, len(payload) // 2
    while i < n:
        code = struct.unpack_from('<H', payload, i * 2)[0]
        if code in WIDE_CTRL or code in CHAR_CTRL:
            # 서로게이트 쌍이 깨지지 않도록 모아둔 구간을 먼저 해석한다
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
    return ''.join(out)


def _read_stream(ole, name, compressed):
    raw = ole.openstream(name).read()
    if compressed:
        try:
            return zlib.decompress(raw, -15)
        except zlib.error:
            return raw
    return raw


def _grid(cells, n_rows, n_cols):
    """셀 목록을 행·열 격자로 복원한다. 병합 셀은 좌상단에만 값을 둔다."""
    grid = [['' for _ in range(n_cols)] for _ in range(n_rows)]
    for c in cells:
        if c['row'] < n_rows and c['col'] < n_cols:
            grid[c['row']][c['col']] = c['text']
    return [row for row in grid if any(v.strip() for v in row)]


def _parse_table(records, idx):
    """TABLE 레코드 하나를 읽어 격자와 셀 목록을 돌려준다."""
    tag, level, payload = records[idx]
    n_rows, n_cols = struct.unpack_from('<HH', payload, 4)

    cells, cur = [], None
    i = idx + 1
    while i < len(records):
        t, lv, data = records[i]
        if lv < level:
            break
        if t in (HWPTAG_CTRL_HEADER, HWPTAG_TABLE) and lv <= level:
            break
        if t == HWPTAG_CTRL_HEADER and cur is not None and data[:4][::-1] == b'%unk':
            # 메모가 달린 자리. 본문은 문서 끝의 메모 목록에 따로 있으므로 표시만 남긴다.
            cur['text'] = (cur['text'] + ' ⟨메모⟩').strip()
        if t == HWPTAG_LIST_HEADER and lv == level and len(data) >= CELL_OFFSET + 8:
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
    """메모(주석) 하나를 읽는다.

    검토자가 "2Q 보고서로 수정해주세요" 같은 지시를 메모로 달아 보내는 일이 많은데,
    본문에는 안 보이므로 놓치기 쉽다. 반드시 뽑아서 보여준다.
    """
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


def read_hwp(path):
    """HWP 5.0을 문서 순서대로 [{'type':'text'|'table', ...}] 로 읽는다."""
    try:
        import olefile
    except ImportError:
        raise RuntimeError("olefile이 없다: pip install olefile --break-system-packages")

    if not olefile.isOleFile(path):
        raise ValueError(f"{path}: OLE 파일이 아니다. HWPX면 확장자를 .hwpx로 두고 다시 실행")

    ole = olefile.OleFileIO(path)
    try:
        head = ole.openstream('FileHeader').read()
        compressed = bool(head[36] & 0x01)
        if head[36] & 0x02:
            raise RuntimeError(f"{path}: 암호가 걸린 문서다. 암호를 풀고 다시 저장할 것")

        names = sorted('/'.join(e) for e in ole.listdir()
                       if '/'.join(e).startswith('BodyText/Section'))
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
                    # 표 안의 문단은 _parse_table이 이미 가져갔으므로 남는 것은 본문이다.
                    # 제목·머리글이 레벨 1 이상에 놓이는 문서가 있어 레벨로 거르지 않는다.
                    line = _decode_text(payload).strip()
                    if line:
                        blocks.append({'type': 'text', 'text': line})
                i += 1
        return blocks
    finally:
        ole.close()


# -------------------------------------------------------------------- HWPX

def _hwpx_local(tag):
    return tag.rsplit('}', 1)[-1] if isinstance(tag, str) else ''


def _hwpx_int(node, *names):
    """속성 이름이 판마다 달라 후보를 순서대로 본다(colAddr/col, colSpan/colspan …)."""
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
    """이 노드가 품은 글자를 모은다. 중첩된 표 안의 글자는 빼고 센다."""
    out = []

    def walk(n):
        for child in n:
            local = _hwpx_local(child.tag)
            if local == 'tbl':
                continue                    # 중첩 표는 표 블록으로 따로 나간다
            if local == 't' and child.text:
                out.append(child.text)
            walk(child)

    walk(node)
    return re.sub(r'\s+', ' ', ''.join(out)).strip()


def _hwpx_table(node):
    """<hp:tbl> 하나를 셀 좌표까지 살려 읽는다.

    HWP 5.0과 마찬가지로 셀마다 행·열 주소와 병합 수가 붙어 있다(`cellAddr`,
    `cellSpan`). 이걸 무시하고 <hp:tr> 안의 <hp:tc>를 나온 순서대로 채우면
    병합된 헤더에서 열이 통째로 밀린다. 아래 표의 셋째 줄이 그 예다.

        (단위: 원)
        품목 | 규격 | 수량 | 단가        | 금액
                            정가 | 할인가 | 공급가 | 부가세   ← 0번 열부터 채워짐

    주소가 없는 문서(구현체마다 생략하는 경우가 있다)는 병합 수를 누적해 자리를
    잡는 방식으로 되돌린다.
    """
    cells = []
    rows = [tr for tr in node if _hwpx_local(tr.tag) == 'tr']
    cursor = {}                              # 주소가 없을 때 쓸 열 커서

    for r, tr in enumerate(rows):
        for tc in tr:
            if _hwpx_local(tc.tag) != 'tc':
                continue
            addr = next((c for c in tc if _hwpx_local(c.tag) == 'cellAddr'), None)
            span = next((c for c in tc if _hwpx_local(c.tag) == 'cellSpan'), None)

            colspan = _hwpx_int(span, 'colSpan', 'colspan') if span is not None else None
            rowspan = _hwpx_int(span, 'rowSpan', 'rowspan') if span is not None else None
            colspan = colspan or 1
            rowspan = rowspan or 1

            col = _hwpx_int(addr, 'colAddr', 'col') if addr is not None else None
            row = _hwpx_int(addr, 'rowAddr', 'row') if addr is not None else None
            if col is None or row is None:
                row = r
                col = cursor.get(r, 0)
                while any(c['row'] <= row < c['row'] + c['rowspan']
                          and c['col'] <= col < c['col'] + c['colspan'] for c in cells):
                    col += 1
                cursor[r] = col + colspan

            cells.append({'row': row, 'col': col, 'rowspan': rowspan,
                          'colspan': colspan, 'text': _hwpx_text_of(tc)})

    n_rows = _hwpx_int(node, 'rowCnt', 'rowcnt') or 0
    n_cols = _hwpx_int(node, 'colCnt', 'colcnt') or 0
    n_rows = max([n_rows] + [c['row'] + c['rowspan'] for c in cells] or [0])
    n_cols = max([n_cols] + [c['col'] + c['colspan'] for c in cells] or [0])

    return {'rows': n_rows, 'cols': n_cols, 'cells': cells,
            'grid': _grid(cells, n_rows, n_cols)}


def _hwpx_walk(node, blocks):
    """문서 순서를 지키며 문단·표·메모를 뽑는다.

    표 안의 문단은 <hp:tc> 밑에 다시 <hp:p>로 들어 있다. 그래서 문서 전체를
    평평하게 훑으면 셀 내용이 본문으로 한 번 더 나온다(LLM에 넣으면 같은 표를
    두 번 읽는다). 표를 만나면 그 아래로는 내려가지 않는 방식으로 막는다.
    """
    for child in node:
        local = _hwpx_local(child.tag)
        if local == 'tbl':
            table = _hwpx_table(child)
            if table['grid']:
                blocks.append({'type': 'table', **table})
        elif local in ('memo', 'memogroup'):
            for memo in ([child] if local == 'memo' else
                         [m for m in child.iter() if _hwpx_local(m.tag) == 'memo']):
                text = _hwpx_text_of(memo)
                if text:
                    blocks.append({'type': 'memo', 'text': text})
        elif local == 'p':
            _hwpx_paragraph(child, blocks)
        else:
            _hwpx_walk(child, blocks)


def _hwpx_paragraph(para, blocks):
    """문단 하나. 문단 도중에 표가 끼어들면 그 자리에서 표 블록으로 끊는다."""
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
                _hwpx_walk(n, blocks)
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
    with zipfile.ZipFile(path) as z:
        sections = sorted(n for n in z.namelist()
                          if re.match(r'Contents/section\d+\.xml$', n))
        if not sections:
            raise ValueError(f"{path}: Contents/sectionN.xml을 찾지 못했다")

        for name in sections:
            _hwpx_walk(ElementTree.fromstring(z.read(name)), blocks)
    return blocks


# ------------------------------------------------------------------ 출력

def read(path):
    """확장자로 갈래를 정하되, 어긋나면 내용을 보고 되돌린다.

    받은 문서의 확장자가 실제 형식과 다른 일이 흔하다(.hwp로 저장된 HWPX 등).
    확장자를 믿고 실패로 끝내지 않고 실제 컨테이너를 확인한다.
    """
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
            lines.append('| ' + ' | '.join(padded[0]) + ' |')
            lines.append('|' + '---|' * width)
            for row in padded[1:]:
                lines.append('| ' + ' | '.join(row) + ' |')
            lines.append('')
        else:
            lines.append('[표]')
            for row in grid:
                lines.append(' | '.join(row))
            lines.append('')
    return '\n'.join(lines)
