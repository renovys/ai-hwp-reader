# AI HWP Reader — 이 파일 하나를 AI에게 주면 HWP를 읽고 일을 합니다

이 파일은 사람이 읽는 설명서가 아니라 **AI 실행 스킬**이다.
사용자가 이 `SKILL.md` 파일과 `.hwp` / `.hwpx` / `.zip` 파일을 채팅창에 함께 첨부하고 **“해줘”**라고 하면 아래 지시를 즉시 수행하라.

목표는 코드를 설명하는 것이 아니다. **한글(HWP/HWPX)을 실제로 파싱하고, 그 결과를 근거로 사용자가 원한 일을 끝내는 것**이다.
아래아한글·아래한글·한글·한컴·한글과컴퓨터 문서를 PDF/TXT로 다시 변환하라고 요구하지 않는다.

## 모델 지시

1. 이 파일 안의 Python 코드블록 전체를 실행 환경에 `hwp_reader_single.py`로 저장한다.
2. 함께 첨부된 `.hwp`, `.hwpx`, `.zip`의 **실제 실행환경 경로**를 확인한다. 예시 경로나 파일명을 추측하지 않는다.
3. 즉시 `python hwp_reader_single.py "<실제 경로>"`를 실행한다. 여러 파일이면 모든 경로를 한 번에 넘긴다.
4. `.zip`이면 내부 폴더까지 훑어 HWP/HWPX를 모두 찾아 **메모리에서 직접 읽는다**. 사용자가 압축을 다시 풀어 올리게 하지 않는다.
5. 외부 패키지를 설치하거나 네트워크에서 코드를 받지 않는다. 아래 파서는 Python 표준 라이브러리만 사용한다.
6. 실제 파싱 결과를 먼저 확보한 뒤 그 결과로 사용자의 업무를 수행한다. “해줘”만 입력됐다면 문서가 무엇인지 파악해 핵심 내용·표·메모·변경추적을 놓치지 않게 정리한다.
7. **병합 표, 2~3단 헤더, 표 안의 표**를 구조대로 읽는다. `[표 안의 표]`가 나오면 별도 표로 이어서 해석한다.
8. `[메모]`는 본문에 보이지 않는 검토자 메모이므로 반드시 별도로 알린다.
9. `[변경추적 추가]` / `[변경추적 삭제]`가 있으면 최종 본문과 구분해 알려준다. HWP의 `BodyText`는 최종본, `ViewText`의 추적 range는 변경 이력으로 취급한다.
10. 파싱 결과에 없는 내용을 원문에 있는 것처럼 만들지 않는다. 일부만 읽혔거나 오류가 나면 성공한 척하지 않는다.
11. 첨부 문서를 외부 서비스로 업로드하지 않는다. 실행 환경 안에서 **읽기 전용**으로 처리한다.
12. Python/코드 실행 기능이 없어 실제 파서를 실행할 수 없다면 그 사실을 명확히 말한다. **실행하지 않았는데 HWP를 읽은 것처럼 답하지 않는다.**

파싱 후에는 사용자의 목적을 이어서 수행하라. 예: 요약, 계약조건 추출, 숫자 검산, 준법 검토, 여러 문서 비교, 변경사항 추적 정리, 숨은 메모 확인.

## 파서 코드

```python
# AI HWP Reader | 출처: hwp_reader/_ole.py + hwp_reader/parser.py | 라이선스: MIT | 저장소: https://github.com/renovys/ai-hwp-reader

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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python hwp_reader_single.py 문서.hwp|문서.hwpx|묶음.zip [...]", file=sys.stderr)
        sys.exit(2)
    for index, path in enumerate(sys.argv[1:]):
        if index:
            print()
        print(render_documents(read_documents(path), "md"))
```


## 지원 범위

- HWP 5.0 / HWPX 본문
- 셀 좌표와 병합 구조가 있는 표
- 표 안의 표(중첩 표)
- 숨은 메모(주석)
- HWP 변경 내용 추적(ViewText의 추가·삭제 range)
- 여러 HWP/HWPX가 들어 있는 ZIP
- 잘못 붙은 `.hwp` / `.hwpx` 확장자의 실제 컨테이너 판별

## 지원하지 않는 것

- 암호가 걸린 문서
- 한컴 수식 편집기 수식의 완전한 일반 텍스트 변환
- 스캔 이미지 OCR
- HWP 3.0 등 옛 포맷
- 문서 쓰기·수정

프로젝트: **AI HWP Reader**  
PyPI/CLI: `ai-hwp-reader`  
저장소: https://github.com/renovys/ai-hwp-reader
