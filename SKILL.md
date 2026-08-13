# HWP/HWPX 읽기 — 웹 챗봇 실행 지침

이 문서를 **통째로** 대화창에 붙여넣은 뒤 `.hwp` 또는 `.hwpx` 파일을 올리세요. 그 다음 **"이거 줘"**라고 하거나 문서에 대해 질문하면 됩니다.

## 모델 지시

사용자가 HWP/HWPX 파일을 첨부하면 다음 순서로 처리하라.

1. 아래 Python 코드블록 전체를 실행 환경에 `hwp_reader_single.py`로 저장한다.
2. 첨부파일의 **실제 실행환경 경로**를 확인한 뒤 즉시 `python hwp_reader_single.py "<경로>"`를 실행한다. 여러 파일이면 모든 경로를 한 번에 넘긴다.
3. 외부 패키지를 설치하거나 네트워크에서 코드를 받으려 하지 않는다. 아래 코드는 Python 표준 라이브러리만 사용한다.
4. 코드를 설명하는 데서 멈추지 말고 **실제 실행 결과를 먼저** 보여준다. 표는 Markdown 표 형태를 유지하고 `[메모]`가 있으면 본문과 분리해 빠뜨리지 않는다.
5. 사용자의 후속 질문에는 반드시 방금 파싱한 결과를 근거로 답한다. 파싱 결과에 없는 내용을 원문에 있는 것처럼 만들지 않는다.
6. 첨부 문서를 외부 서비스로 업로드하지 않는다. 실행 환경 안에서 읽기 전용으로 처리한다.
7. Python/코드 실행 기능이 없는 환경이라 실제 파서를 실행할 수 없다면 그 사실을 명확히 말한다. **실행하지 않았는데 문서를 읽은 것처럼 답하지 않는다.**

## 파서 코드

```python
# 출처: hwp_reader/_ole.py + hwp_reader/parser.py | 라이선스: MIT | 저장소: https://github.com/renovys/hwp-reader

"""표준 라이브러리만으로 읽는 OLE Compound File Binary 컨테이너."""

import os
import struct


FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
DIFSECT = 0xFFFFFFFC
NOSTREAM = 0xFFFFFFFF


class OleFile:
    """OLE 파일에서 스트림을 이름으로 읽는다.

    HWP 5.0에 필요한 CFB 읽기 부분만 구현한다. 디렉터리의 형제 노드와
    저장소 자식 노드를 따라가 스트림 경로를 만들고, 작은 스트림은 미니 FAT,
    큰 스트림은 일반 FAT으로 읽는다.
    """

    def __init__(self, path_or_bytes):
        self._data = self._load(path_or_bytes)
        self._parse_header()
        self._fat = self._read_fat()
        self._mini_fat = self._read_mini_fat()
        self._entries, self._root_index = self._read_directory()
        self._root_mini_stream = None
        self._streams = self._make_stream_map()

    @staticmethod
    def _load(path_or_bytes):
        if isinstance(path_or_bytes, (bytes, bytearray, memoryview)):
            return bytes(path_or_bytes)
        if isinstance(path_or_bytes, (str, os.PathLike)):
            with open(path_or_bytes, "rb") as fp:
                return fp.read()
        raise ValueError("손상된 OLE 파일: 경로 또는 바이트가 아니다")

    @staticmethod
    def _bad(message):
        raise ValueError("손상된 OLE 파일: " + message)

    def _parse_header(self):
        if len(self._data) < 512:
            self._bad("헤더가 512바이트보다 짧다")
        if self._data[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            self._bad("OLE 시그니처가 아니다")

        sector_shift = struct.unpack_from("<H", self._data, 0x1E)[0]
        mini_sector_shift = struct.unpack_from("<H", self._data, 0x20)[0]
        if not 9 <= sector_shift <= 16:
            self._bad("섹터 크기가 올바르지 않다")
        if not 2 <= mini_sector_shift < sector_shift:
            self._bad("미니 섹터 크기가 올바르지 않다")

        self.sector_size = 1 << sector_shift
        self.mini_sector_size = 1 << mini_sector_shift
        self._num_dir_sectors = struct.unpack_from("<I", self._data, 0x28)[0]
        self._num_fat_sectors = struct.unpack_from("<I", self._data, 0x2C)[0]
        self._first_dir_sector = struct.unpack_from("<I", self._data, 0x30)[0]
        self._mini_cutoff = struct.unpack_from("<I", self._data, 0x38)[0]
        self._first_mini_fat_sector = struct.unpack_from("<I", self._data, 0x3C)[0]
        self._num_mini_fat_sectors = struct.unpack_from("<I", self._data, 0x40)[0]
        self._first_difat_sector = struct.unpack_from("<I", self._data, 0x44)[0]
        self._num_difat_sectors = struct.unpack_from("<I", self._data, 0x48)[0]
        self._header_difat = list(struct.unpack_from("<109I", self._data, 0x4C))

        if not self._mini_cutoff:
            self._bad("미니 스트림 컷오프가 0이다")
        self._sector_count = (len(self._data) - 512) // self.sector_size
        if self._sector_count == 0:
            self._bad("데이터 섹터가 없다")
        if self._num_fat_sectors == 0:
            self._bad("FAT 섹터가 없다")

    def _read_sector(self, sector):
        if sector in (FREESECT, ENDOFCHAIN, FATSECT, DIFSECT, NOSTREAM):
            self._bad("예약된 값을 섹터 번호로 사용했다")
        if not isinstance(sector, int) or sector < 0 or sector >= self._sector_count:
            self._bad("섹터 번호가 파일 범위를 벗어났다")
        start = 512 + sector * self.sector_size
        end = start + self.sector_size
        if end > len(self._data):
            self._bad("섹터가 파일 끝을 넘는다")
        return self._data[start:end]

    def _read_fat(self):
        fat_sectors = [sid for sid in self._header_difat if sid != FREESECT]
        next_difat = self._first_difat_sector
        seen_difat = set()
        entries_per_difat = self.sector_size // 4

        while len(fat_sectors) < self._num_fat_sectors:
            if self._num_difat_sectors == 0 or next_difat in (
                    FREESECT, ENDOFCHAIN):
                self._bad("DIFAT 체인이 FAT 전체를 가리키지 않는다")
            if next_difat in seen_difat:
                self._bad("DIFAT 체인이 순환한다")
            seen_difat.add(next_difat)
            if len(seen_difat) > self._num_difat_sectors:
                self._bad("DIFAT 섹터 수가 헤더와 다르다")

            block = self._read_sector(next_difat)
            values = struct.unpack("<{}I".format(entries_per_difat), block)
            fat_sectors.extend(sid for sid in values[:-1] if sid != FREESECT)
            next_difat = values[-1]

        if len(fat_sectors) < self._num_fat_sectors:
            self._bad("FAT 섹터 목록이 부족하다")
        fat_sectors = fat_sectors[:self._num_fat_sectors]

        fat = []
        for sid in fat_sectors:
            fat.extend(struct.unpack("<{}I".format(entries_per_difat),
                                     self._read_sector(sid)))
        return fat

    def _chain(self, start, table, needed=None, what="FAT"):
        if needed == 0:
            return []
        if start in (FREESECT, ENDOFCHAIN, NOSTREAM):
            self._bad("{} 체인의 시작 섹터가 없다".format(what))

        out = []
        seen = set()
        sector = start
        while True:
            if sector in seen:
                self._bad("{} 체인이 순환한다".format(what))
            if not isinstance(sector, int) or sector < 0 or sector >= len(table):
                self._bad("{} 체인의 섹터 번호가 범위를 벗어났다".format(what))
            seen.add(sector)
            out.append(sector)

            if needed is not None and len(out) >= needed:
                return out

            next_sector = table[sector]
            if next_sector == ENDOFCHAIN:
                if needed is None:
                    return out
                self._bad("{} 체인이 예상보다 짧다".format(what))
            if next_sector in (FREESECT, FATSECT, DIFSECT, NOSTREAM):
                self._bad("{} 체인이 예약된 섹터를 가리킨다".format(what))
            sector = next_sector

    def _read_regular(self, start, size, full_sectors=False, what="스트림"):
        if size == 0:
            return b""
        needed = (size + self.sector_size - 1) // self.sector_size
        sectors = self._chain(start, self._fat, needed, what)
        raw = b"".join(self._read_sector(sid) for sid in sectors)
        if len(raw) < size:
            self._bad("{} 데이터가 부족하다".format(what))
        return raw if full_sectors else raw[:size]

    def _read_mini_fat(self):
        count = self._num_mini_fat_sectors
        if count == 0:
            if self._first_mini_fat_sector not in (FREESECT, ENDOFCHAIN):
                self._bad("미니 FAT 시작 섹터가 수와 맞지 않는다")
            return []
        sectors = self._chain(self._first_mini_fat_sector, self._fat, count,
                               "미니 FAT")
        raw = b"".join(self._read_sector(sid) for sid in sectors)
        values = struct.unpack("<{}I".format(len(raw) // 4), raw)
        return list(values)

    def _read_directory(self):
        if self._first_dir_sector in (FREESECT, ENDOFCHAIN, NOSTREAM):
            self._bad("디렉터리 시작 섹터가 없다")
        needed = self._num_dir_sectors or None
        sectors = self._chain(self._first_dir_sector, self._fat, needed,
                              "디렉터리")
        raw = b"".join(self._read_sector(sid) for sid in sectors)
        if len(raw) < 128:
            self._bad("디렉터리 엔트리가 없다")

        entries = []
        for offset in range(0, len(raw) - 127, 128):
            chunk = raw[offset:offset + 128]
            name_length = struct.unpack_from("<H", chunk, 0x40)[0]
            if name_length == 0:
                name = ""
            else:
                if name_length < 2 or name_length > 64 or name_length % 2:
                    self._bad("디렉터리 이름 길이가 올바르지 않다")
                try:
                    name = chunk[:name_length - 2].decode("utf-16-le")
                except UnicodeDecodeError:
                    self._bad("디렉터리 이름이 UTF-16LE가 아니다")

            entry_type = chunk[0x42]
            if entry_type not in (0, 1, 2, 5):
                self._bad("알 수 없는 디렉터리 엔트리 종류다")
            entries.append({
                "name": name,
                "type": entry_type,
                "left": struct.unpack_from("<I", chunk, 0x44)[0],
                "right": struct.unpack_from("<I", chunk, 0x48)[0],
                "child": struct.unpack_from("<I", chunk, 0x4C)[0],
                "start": struct.unpack_from("<I", chunk, 0x74)[0],
                "size": struct.unpack_from("<Q", chunk, 0x78)[0],
            })

        roots = [i for i, entry in enumerate(entries) if entry["type"] == 5]
        if len(roots) != 1:
            self._bad("루트 디렉터리가 하나가 아니다")
        return entries, roots[0]

    def _make_stream_map(self):
        root = self._entries[self._root_index]
        streams = {}
        seen = {self._root_index}
        stack = [(root["child"], "")]

        while stack:
            index, parent = stack.pop()
            if index == NOSTREAM:
                continue
            if not isinstance(index, int) or index < 0 or index >= len(self._entries):
                self._bad("디렉터리 노드 번호가 범위를 벗어났다")
            if index in seen:
                self._bad("디렉터리 트리가 순환하거나 중복됐다")
            seen.add(index)
            entry = self._entries[index]
            if entry["type"] == 0:
                self._bad("사용하지 않는 디렉터리 엔트리를 참조했다")

            stack.append((entry["right"], parent))
            stack.append((entry["left"], parent))

            if entry["type"] == 1:
                path = "/".join(p for p in (parent, entry["name"]) if p)
                stack.append((entry["child"], path))
            elif entry["type"] == 2:
                path = "/".join(p for p in (parent, entry["name"]) if p)
                if not path or path in streams:
                    self._bad("디렉터리 스트림 이름이 중복됐다")
                streams[path] = entry
            elif entry["type"] == 5:
                self._bad("루트 디렉터리를 자식으로 참조했다")

        return streams

    def _get_root_mini_stream(self):
        if self._root_mini_stream is not None:
            return self._root_mini_stream
        root = self._entries[self._root_index]
        self._root_mini_stream = self._read_regular(
            root["start"], root["size"], full_sectors=True, what="미니 스트림")
        return self._root_mini_stream

    def exists(self, name):
        """`name`이라는 스트림이 있는지 돌려준다."""
        return name in self._streams

    def open(self, name):
        """스트림 전체를 바이트로 읽는다."""
        try:
            entry = self._streams[name]
        except (KeyError, TypeError):
            raise KeyError("OLE 스트림이 없다: {}".format(name)) from None

        size = entry["size"]
        if size == 0:
            if entry["start"] != ENDOFCHAIN:
                self._bad("빈 스트림의 시작 섹터가 올바르지 않다")
            return b""
        if size >= self._mini_cutoff:
            return self._read_regular(entry["start"], size)

        needed = (size + self.mini_sector_size - 1) // self.mini_sector_size
        mini_sectors = self._chain(entry["start"], self._mini_fat, needed,
                                   "미니 스트림")
        mini_stream = self._get_root_mini_stream()
        chunks = []
        for sector in mini_sectors:
            start = sector * self.mini_sector_size
            end = start + self.mini_sector_size
            if end > len(mini_stream):
                self._bad("미니 스트림이 루트 스트림 범위를 벗어났다")
            chunks.append(mini_stream[start:end])
        raw = b"".join(chunks)
        if len(raw) < size:
            self._bad("미니 스트림 데이터가 부족하다")
        return raw[:size]

    def listdir(self):
        """스트림 경로를 `부모/이름` 형식으로 정렬해 돌려준다."""
        return sorted(self._streams)

"""한글 문서(HWP 5.0 / HWPX)를 표 구조까지 살려 읽는다.

HWP 5.0과 HWPX 모두 표준 라이브러리만으로 읽는다. 한컴 오피스도,
한컴 라이선스도 필요 없다.

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

    # 실제 문서에서 U+001F 같은 C0 제어 문자가 글자 데이터로 남는 경우가 있다.
    # 폭이 있는 HWP 제어문자와 달리 이미 UTF-16 글자로 해석된 뒤이므로 공백으로만 정리한다.
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


def _section_number(name):
    """Section10이 Section2보다 앞서는 문자열 정렬 문제를 막는다."""
    match = re.search(r'(\d+)(?:\.xml)?$', name)
    return int(match.group(1)) if match else sys.maxsize


def _grid(cells, n_rows, n_cols):
    """셀 목록을 행·열 격자로 복원한다. 병합 셀은 좌상단에만 값을 둔다."""
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
        ole = OleFile(path)
    except ValueError:
        raise ValueError(
            f"{path}: OLE 파일이 아니다. HWPX면 확장자를 .hwpx로 두고 다시 실행"
        ) from None

    if not ole.exists('FileHeader'):
        raise ValueError(f"{path}: FileHeader 스트림이 없다")
    head = ole.open('FileHeader')
    if len(head) <= 36:
        raise ValueError(f"{path}: FileHeader가 37바이트보다 짧다")
    compressed = bool(head[36] & 0x01)
    if head[36] & 0x02:
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
                # 표 안의 문단은 _parse_table이 이미 가져갔으므로 남는 것은 본문이다.
                # 제목·머리글이 레벨 1 이상에 놓이는 문서가 있어 레벨로 거르지 않는다.
                line = _decode_text(payload).strip()
                if line:
                    blocks.append({'type': 'text', 'text': line})
            i += 1
    return blocks


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
    with zipfile.ZipFile(path) as z:
        sections = sorted((n for n in z.namelist()
                           if re.match(r'Contents/section\d+\.xml$', n)),
                          key=_section_number)
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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python hwp_reader_single.py 문서.hwp [문서2.hwpx ...]", file=sys.stderr)
        sys.exit(2)
    paths = sys.argv[1:]
    for index, path in enumerate(paths):
        if len(paths) > 1:
            if index:
                print()
            print("===== {} =====".format(os.path.basename(path)))
        print(render(read(path), "md"))
```


## 지원하지 않는 것

- 암호가 걸린 문서는 암호를 풀고 다시 저장해야 한다.
- 한컴 수식 편집기 수식은 일반 텍스트로 복원되지 않을 수 있다.
- 스캔 이미지는 OCR 대상이라 이 파서가 읽지 않는다.
- HWP 3.0 등 옛 포맷은 지원하지 않는다.
- 이 도구는 **읽기 전용**이다. 원본 문서를 수정하거나 저장하지 않는다.

저장소: https://github.com/renovys/hwp-reader
