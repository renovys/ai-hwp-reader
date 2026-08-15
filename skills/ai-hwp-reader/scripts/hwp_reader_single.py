# AI HWP Reader v0.5.2 | source-sha256:e894b206bd5f6ff9 | 표준 라이브러리 only | MIT | https://github.com/renovys/ai-hwp-reader

"""표준 라이브러리만으로 읽는 OLE Compound File Binary 컨테이너.

HWP 5.0이 사용하는 CFB/OLE 컨테이너를 읽기 전용으로 해석한다.
Microsoft CFB v3(512-byte sector)와 v4(4096-byte sector)의 헤더 규칙을
검증하고, FAT/DIFAT/mini FAT의 순환·범위 오류를 명시적으로 거부한다.
"""

import os
import struct


FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
DIFSECT = 0xFFFFFFFC
NOSTREAM = 0xFFFFFFFF

OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
MINI_CUTOFF = 4096
MAX_DIRECTORY_ENTRIES = 1_000_000


class OleFile:
    """OLE 파일에서 스트림을 이름으로 읽는다.

    HWP 5.0에 필요한 CFB 읽기 부분만 구현한다. 디렉터리의 형제 노드와
    저장소 자식 노드를 따라가 스트림 경로를 만들고, 작은 스트림은 mini FAT,
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
        if self._data[:8] != OLE_SIGNATURE:
            self._bad("OLE 시그니처가 아니다")

        (
            self.minor_version,
            self.major_version,
            byte_order,
            sector_shift,
            mini_sector_shift,
        ) = struct.unpack_from("<5H", self._data, 0x18)

        if self.major_version not in (3, 4):
            self._bad("CFB major version이 3 또는 4가 아니다")
        if byte_order != 0xFFFE:
            self._bad("byte order가 little-endian(0xFFFE)이 아니다")

        expected_shift = 9 if self.major_version == 3 else 12
        if sector_shift != expected_shift:
            self._bad(
                "major version과 sector shift가 맞지 않는다 "
                f"(v{self.major_version}, shift={sector_shift})"
            )
        if mini_sector_shift != 6:
            self._bad("mini sector shift가 6(64바이트)이 아니다")

        self.sector_size = 1 << sector_shift
        self.mini_sector_size = 1 << mini_sector_shift
        self._sector_base = self.sector_size

        if len(self._data) < self._sector_base:
            self._bad("헤더 섹터가 파일보다 크다")
        if len(self._data) % self.sector_size:
            self._bad("파일 길이가 섹터 크기의 배수가 아니다")
        if self.major_version == 4 and any(self._data[512:self.sector_size]):
            self._bad("CFB v4 헤더 패딩 3584바이트가 0이 아니다")

        self._num_dir_sectors = struct.unpack_from("<I", self._data, 0x28)[0]
        self._num_fat_sectors = struct.unpack_from("<I", self._data, 0x2C)[0]
        self._first_dir_sector = struct.unpack_from("<I", self._data, 0x30)[0]
        self._mini_cutoff = struct.unpack_from("<I", self._data, 0x38)[0]
        self._first_mini_fat_sector = struct.unpack_from(
            "<I", self._data, 0x3C
        )[0]
        self._num_mini_fat_sectors = struct.unpack_from(
            "<I", self._data, 0x40
        )[0]
        self._first_difat_sector = struct.unpack_from(
            "<I", self._data, 0x44
        )[0]
        self._num_difat_sectors = struct.unpack_from(
            "<I", self._data, 0x48
        )[0]
        self._header_difat = list(
            struct.unpack_from("<109I", self._data, 0x4C)
        )

        if self.major_version == 3 and self._num_dir_sectors != 0:
            self._bad("CFB v3의 directory sector count가 0이 아니다")
        if self._mini_cutoff != MINI_CUTOFF:
            self._bad("mini stream cutoff가 4096바이트가 아니다")

        if self._num_mini_fat_sectors == 0:
            if self._first_mini_fat_sector not in (FREESECT, ENDOFCHAIN):
                self._bad("mini FAT 시작 섹터가 개수 0과 맞지 않는다")
        elif self._first_mini_fat_sector in (FREESECT, ENDOFCHAIN):
            self._bad("mini FAT 섹터가 있는데 시작 섹터가 없다")

        if self._num_difat_sectors == 0:
            if self._first_difat_sector not in (FREESECT, ENDOFCHAIN):
                self._bad("DIFAT 시작 섹터가 개수 0과 맞지 않는다")
        elif self._first_difat_sector in (FREESECT, ENDOFCHAIN):
            self._bad("DIFAT 섹터가 있는데 시작 섹터가 없다")

        self._sector_count = len(self._data) // self.sector_size - 1
        if self._sector_count <= 0:
            self._bad("데이터 섹터가 없다")
        if self._num_fat_sectors == 0:
            self._bad("FAT 섹터가 없다")

        for count, what in (
            (self._num_fat_sectors, "FAT"),
            (self._num_mini_fat_sectors, "mini FAT"),
            (self._num_difat_sectors, "DIFAT"),
        ):
            if count > self._sector_count:
                self._bad(f"{what} 섹터 수가 전체 섹터 수를 넘는다")

    def _read_sector(self, sector):
        if sector in (FREESECT, ENDOFCHAIN, FATSECT, DIFSECT, NOSTREAM):
            self._bad("예약된 값을 섹터 번호로 사용했다")
        if (
            not isinstance(sector, int)
            or sector < 0
            or sector >= self._sector_count
        ):
            self._bad("섹터 번호가 파일 범위를 벗어났다")

        # CFB의 sector N은 (N + 1) * sector_size에서 시작한다.
        start = self._sector_base + sector * self.sector_size
        end = start + self.sector_size
        if end > len(self._data):
            self._bad("섹터가 파일 끝을 넘는다")
        return self._data[start:end]

    def _read_fat(self):
        fat_sectors = [
            sid for sid in self._header_difat if sid != FREESECT
        ]
        next_difat = self._first_difat_sector
        seen_difat = set()
        entries_per_sector = self.sector_size // 4

        while len(fat_sectors) < self._num_fat_sectors:
            if (
                self._num_difat_sectors == 0
                or next_difat in (FREESECT, ENDOFCHAIN)
            ):
                self._bad("DIFAT 체인이 FAT 전체를 가리키지 않는다")
            if next_difat in seen_difat:
                self._bad("DIFAT 체인이 순환한다")
            seen_difat.add(next_difat)
            if len(seen_difat) > self._num_difat_sectors:
                self._bad("DIFAT 섹터 수가 헤더와 다르다")

            block = self._read_sector(next_difat)
            values = struct.unpack(
                "<{}I".format(entries_per_sector), block
            )
            fat_sectors.extend(
                sid for sid in values[:-1] if sid != FREESECT
            )
            next_difat = values[-1]

        if len(fat_sectors) < self._num_fat_sectors:
            self._bad("FAT 섹터 목록이 부족하다")
        if len(fat_sectors) > self._num_fat_sectors:
            self._bad("DIFAT에 선언된 FAT 섹터 수보다 많은 항목이 있다")

        if len(set(fat_sectors)) != len(fat_sectors):
            self._bad("FAT 섹터 번호가 중복됐다")

        fat = []
        for sid in fat_sectors:
            fat.extend(
                struct.unpack(
                    "<{}I".format(entries_per_sector),
                    self._read_sector(sid),
                )
            )

        for sid in fat_sectors:
            if sid >= len(fat) or fat[sid] != FATSECT:
                self._bad("FAT 섹터가 FATSECT로 표시되지 않았다")
        for sid in seen_difat:
            if sid >= len(fat) or fat[sid] != DIFSECT:
                self._bad("DIFAT 섹터가 DIFSECT로 표시되지 않았다")

        return fat

    def _chain(self, start, table, needed=None, what="FAT"):
        if needed == 0:
            return []
        if start in (FREESECT, ENDOFCHAIN, NOSTREAM):
            self._bad(f"{what} 체인의 시작 섹터가 없다")
        if needed is not None and needed > len(table):
            self._bad(f"{what} 체인이 가질 수 있는 섹터 수를 넘는다")

        out = []
        seen = set()
        sector = start

        while True:
            if sector in seen:
                self._bad(f"{what} 체인이 순환한다")
            if (
                not isinstance(sector, int)
                or sector < 0
                or sector >= len(table)
            ):
                self._bad(f"{what} 체인의 섹터 번호가 범위를 벗어났다")

            seen.add(sector)
            out.append(sector)
            next_sector = table[sector]

            if needed is not None and len(out) >= needed:
                if next_sector != ENDOFCHAIN:
                    self._bad(f"{what} 체인이 선언된 크기보다 길다")
                return out

            if next_sector == ENDOFCHAIN:
                if needed is None:
                    return out
                self._bad(f"{what} 체인이 예상보다 짧다")
            if next_sector in (FREESECT, FATSECT, DIFSECT, NOSTREAM):
                self._bad(f"{what} 체인이 예약된 섹터를 가리킨다")
            sector = next_sector

    def _read_regular(self, start, size, what="스트림"):
        if size == 0:
            return b""
        if size > self._sector_count * self.sector_size:
            self._bad(f"{what} 크기가 파일 전체 용량을 넘는다")

        needed = (size + self.sector_size - 1) // self.sector_size
        sectors = self._chain(start, self._fat, needed, what)
        raw = b"".join(self._read_sector(sid) for sid in sectors)
        if len(raw) < size:
            self._bad(f"{what} 데이터가 부족하다")
        return raw[:size]

    def _read_mini_fat(self):
        count = self._num_mini_fat_sectors
        if count == 0:
            if self._first_mini_fat_sector not in (
                FREESECT,
                ENDOFCHAIN,
            ):
                self._bad("mini FAT 시작 섹터가 수와 맞지 않는다")
            return []

        sectors = self._chain(
            self._first_mini_fat_sector,
            self._fat,
            count,
            "mini FAT",
        )
        raw = b"".join(self._read_sector(sid) for sid in sectors)
        values = struct.unpack("<{}I".format(len(raw) // 4), raw)
        return list(values)

    def _read_directory(self):
        if self._first_dir_sector in (FREESECT, ENDOFCHAIN, NOSTREAM):
            self._bad("디렉터리 시작 섹터가 없다")

        needed = (
            self._num_dir_sectors if self.major_version == 4 else None
        )
        if self.major_version == 4 and not needed:
            self._bad("CFB v4의 directory sector count가 0이다")

        sectors = self._chain(
            self._first_dir_sector,
            self._fat,
            needed,
            "디렉터리",
        )
        raw = b"".join(self._read_sector(sid) for sid in sectors)
        if len(raw) < 128:
            self._bad("디렉터리 엔트리가 없다")
        if len(raw) // 128 > MAX_DIRECTORY_ENTRIES:
            self._bad(
                f"디렉터리 엔트리가 {MAX_DIRECTORY_ENTRIES}개를 넘는다"
            )

        entries = []
        for offset in range(0, len(raw) - 127, 128):
            chunk = raw[offset:offset + 128]
            name_length = struct.unpack_from("<H", chunk, 0x40)[0]

            if name_length == 0:
                name = ""
            else:
                if (
                    name_length < 2
                    or name_length > 64
                    or name_length % 2
                ):
                    self._bad("디렉터리 이름 길이가 올바르지 않다")
                if chunk[name_length - 2:name_length] != b"\0\0":
                    self._bad("디렉터리 이름이 NUL로 끝나지 않는다")
                try:
                    name = chunk[:name_length - 2].decode("utf-16-le")
                except UnicodeDecodeError:
                    self._bad("디렉터리 이름이 UTF-16LE가 아니다")

            entry_type = chunk[0x42]
            if entry_type not in (0, 1, 2, 5):
                self._bad("알 수 없는 디렉터리 엔트리 종류다")

            if self.major_version == 3:
                # MS-CFB는 v3의 high DWORD가 오래된 구현에서
                # 초기화되지 않았을 수 있으므로 low DWORD만 사용하라고 한다.
                size = struct.unpack_from("<I", chunk, 0x78)[0]
            else:
                size = struct.unpack_from("<Q", chunk, 0x78)[0]

            entries.append({
                "name": name,
                "type": entry_type,
                "left": struct.unpack_from("<I", chunk, 0x44)[0],
                "right": struct.unpack_from("<I", chunk, 0x48)[0],
                "child": struct.unpack_from("<I", chunk, 0x4C)[0],
                "start": struct.unpack_from("<I", chunk, 0x74)[0],
                "size": size,
            })

        roots = [
            i for i, entry in enumerate(entries) if entry["type"] == 5
        ]
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
            if (
                not isinstance(index, int)
                or index < 0
                or index >= len(self._entries)
            ):
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
                path = "/".join(
                    part for part in (parent, entry["name"]) if part
                )
                stack.append((entry["child"], path))
            elif entry["type"] == 2:
                path = "/".join(
                    part for part in (parent, entry["name"]) if part
                )
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
            root["start"],
            root["size"],
            what="mini stream",
        )
        return self._root_mini_stream

    def exists(self, name):
        """`name`이라는 스트림이 있는지 돌려준다."""
        return name in self._streams

    def open(self, name):
        """스트림 전체를 바이트로 읽는다."""
        try:
            entry = self._streams[name]
        except (KeyError, TypeError):
            raise KeyError(f"OLE 스트림이 없다: {name}") from None

        size = entry["size"]
        if size == 0:
            if entry["start"] != ENDOFCHAIN:
                self._bad("빈 스트림의 시작 섹터가 올바르지 않다")
            return b""

        if size >= self._mini_cutoff:
            return self._read_regular(entry["start"], size)

        needed = (
            size + self.mini_sector_size - 1
        ) // self.mini_sector_size
        mini_sectors = self._chain(
            entry["start"],
            self._mini_fat,
            needed,
            "mini stream",
        )
        mini_stream = self._get_root_mini_stream()
        chunks = []

        for sector in mini_sectors:
            start = sector * self.mini_sector_size
            end = min(
                start + self.mini_sector_size,
                len(mini_stream),
            )
            if start >= len(mini_stream):
                self._bad("mini stream이 루트 stream 범위를 벗어났다")
            chunks.append(mini_stream[start:end])

        raw = b"".join(chunks)
        if len(raw) < size:
            self._bad("mini stream 데이터가 부족하다")
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

"""0.4 계열의 파싱 정확성 보강.

기존 파서의 공개 API는 그대로 두고, 형식이 모호하거나 손상된 입력을 조용히
보정해 정상 문서처럼 보이게 만들 수 있는 내부 경로만 교체한다.
"""


def install(module):
    """파서 코어 모듈에 정확성 보강 함수를 설치한다."""

    def _validate_cells(cells, n_rows, n_cols, what="표"):
        seen = set()
        for cell in cells:
            row = cell["row"]
            col = cell["col"]
            rowspan = cell["rowspan"]
            colspan = cell["colspan"]

            if row < 0 or col < 0:
                raise ValueError(f"손상된 {what}: 셀 주소가 음수다")
            if rowspan <= 0 or colspan <= 0:
                raise ValueError(f"손상된 {what}: 셀 병합 크기가 0 이하이다")
            if row + rowspan > n_rows or col + colspan > n_cols:
                raise ValueError(
                    f"손상된 {what}: 셀 범위가 표 격자를 벗어난다 "
                    f"(row={row}, col={col}, rowspan={rowspan}, colspan={colspan})"
                )
            key = (row, col)
            if key in seen:
                raise ValueError(
                    f"손상된 {what}: 같은 셀 주소가 중복됐다 ({row}, {col})"
                )
            seen.add(key)

    def _decode_utf16(raw, what):
        try:
            return raw.decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"손상된 {what}: UTF-16LE 문자열이 깨졌다"
            ) from exc

    def _decode_text(payload):
        """PARA_TEXT의 글자와 제어문자를 경계 손실 없이 분리한다."""
        if len(payload) % 2:
            raise ValueError(
                "손상된 HWP PARA_TEXT: UTF-16LE 바이트 수가 홀수다"
            )

        out, run = [], bytearray()
        i, n = 0, len(payload) // 2

        def flush():
            if run:
                out.append(_decode_utf16(bytes(run), "HWP PARA_TEXT"))
                run.clear()

        while i < n:
            code = module.struct.unpack_from("<H", payload, i * 2)[0]
            if code in module.WIDE_CTRL:
                flush()
                if i + 8 > n:
                    raise ValueError(
                        "손상된 HWP PARA_TEXT: 8워드 제어문자가 잘렸다"
                    )
                i += 8
                continue
            if code in module.CHAR_CTRL:
                flush()
                out.append(" ")
                i += 1
                continue
            run += payload[i * 2:i * 2 + 2]
            i += 1

        flush()
        text = "".join(out)
        return "".join(
            " " if ord(ch) < 0x20 or ord(ch) == 0x7F else ch
            for ch in text
        )

    def _decode_change_range(payload, start, end):
        """범위가 문단 밖이면 잘라 맞추지 않고 변경 텍스트로 채택하지 않는다."""
        if len(payload) % 2:
            return ""
        units = len(payload) // 2
        if start < 0 or end < start or start >= units or end >= units:
            return ""

        codes = [
            module.struct.unpack_from("<H", payload, i * 2)[0]
            for i in range(start, end + 1)
        ]
        if any(code < 0x20 for code in codes):
            return ""

        raw = payload[start * 2:(end + 1) * 2]
        try:
            text = raw.decode("utf-16-le")
        except UnicodeDecodeError:
            return ""
        return module.re.sub(r"\s+", " ", text).strip()

    def _read_stream(ole, name, compressed):
        raw = ole.open(name)
        if not compressed:
            return raw
        try:
            return module.zlib.decompress(raw, -15)
        except module.zlib.error as exc:
            raise ValueError(
                f"{name}: HWP 압축 스트림이 손상됐다"
            ) from exc

    def _grid(cells, n_rows, n_cols):
        """빈 행도 원래 행 좌표의 일부이므로 삭제하지 않는다."""
        module._validate_table_shape(n_rows, n_cols)
        _validate_cells(cells, n_rows, n_cols)
        grid = [["" for _ in range(n_cols)] for _ in range(n_rows)]
        for cell in cells:
            grid[cell["row"]][cell["col"]] = cell["text"]
        return grid

    def _parse_table(records, idx):
        """HWP TABLE과 셀 좌표/병합 크기를 보수적으로 복원한다."""
        _, level, payload = records[idx]
        if len(payload) < 8:
            raise ValueError(
                "손상된 HWP 표: TABLE payload가 8바이트보다 짧다"
            )
        n_rows, n_cols = module.struct.unpack_from("<HH", payload, 4)
        module._validate_table_shape(n_rows, n_cols, "HWP 표")

        cells, nested, cur = [], [], None
        i = idx + 1
        while i < len(records):
            tag, lv, data = records[i]
            if lv < level:
                break
            if (
                tag in (module.HWPTAG_CTRL_HEADER, module.HWPTAG_TABLE)
                and lv <= level
            ):
                break

            if tag == module.HWPTAG_TABLE and lv > level:
                table, next_i = _parse_table(records, i)
                if table["grid"]:
                    nested.append({
                        "row": cur["row"] if cur else None,
                        "col": cur["col"] if cur else None,
                        "table": table,
                    })
                    if cur is not None:
                        cur["text"] = (
                            cur["text"] + " ⟨표 안의 표⟩"
                        ).strip()
                i = next_i
                continue

            if (
                tag == module.HWPTAG_CTRL_HEADER
                and cur is not None
                and data[:4][::-1] == b"%unk"
            ):
                cur["text"] = (cur["text"] + " ⟨메모⟩").strip()

            if tag == module.HWPTAG_LIST_HEADER and lv == level:
                if len(data) < module.CELL_OFFSET + 8:
                    raise ValueError(
                        "손상된 HWP 표: LIST_HEADER 셀 정보가 잘렸다"
                    )
                col, row, cspan, rspan = module.struct.unpack_from(
                    "<4H", data, module.CELL_OFFSET
                )
                cur = {
                    "row": row,
                    "col": col,
                    "rowspan": rspan,
                    "colspan": cspan,
                    "text": "",
                }
                cells.append(cur)
            elif tag == module.HWPTAG_PARA_TEXT and cur is not None:
                piece = _decode_text(data).strip()
                if piece:
                    cur["text"] = (
                        cur["text"] + " " + piece
                    ).strip()
            i += 1

        _validate_cells(cells, n_rows, n_cols, "HWP 표")
        return {
            "rows": n_rows,
            "cols": n_cols,
            "cells": cells,
            "grid": _grid(cells, n_rows, n_cols),
            "nested_tables": nested,
        }, i

    def _hwpx_int(node, *names):
        if node is None:
            return None
        for name in names:
            value = node.get(name)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"손상된 HWPX: {name} 값이 정수가 아니다 ({value!r})"
                ) from exc
        return None

    def _hwpx_table(node):
        """HWPX 표의 선언 크기와 실제 셀 좌표가 서로 맞는지 확인한다."""
        cells, nested = [], []
        rows = [
            tr for tr in node
            if module._hwpx_local(tr.tag) == "tr"
        ]
        cursor = {}

        for r, tr in enumerate(rows):
            for tc in tr:
                if module._hwpx_local(tc.tag) != "tc":
                    continue

                addr = next(
                    (
                        c for c in tc
                        if module._hwpx_local(c.tag) == "cellAddr"
                    ),
                    None,
                )
                span = next(
                    (
                        c for c in tc
                        if module._hwpx_local(c.tag) == "cellSpan"
                    ),
                    None,
                )

                colspan = _hwpx_int(span, "colSpan", "colspan")
                rowspan = _hwpx_int(span, "rowSpan", "rowspan")
                colspan = 1 if colspan is None else colspan
                rowspan = 1 if rowspan is None else rowspan
                if colspan <= 0 or rowspan <= 0:
                    raise ValueError(
                        "손상된 HWPX 표: 셀 병합 크기가 0 이하이다"
                    )

                col = _hwpx_int(addr, "colAddr", "col")
                row = _hwpx_int(addr, "rowAddr", "row")
                if addr is not None and ((col is None) != (row is None)):
                    raise ValueError(
                        "손상된 HWPX 표: 셀 주소의 행·열 중 하나만 있다"
                    )
                if (
                    (col is not None and col < 0)
                    or (row is not None and row < 0)
                ):
                    raise ValueError(
                        "손상된 HWPX 표: 셀 주소가 음수다"
                    )

                if col is None or row is None:
                    row = r
                    col = cursor.get(r, 0)
                    while any(
                        c["row"] <= row < c["row"] + c["rowspan"]
                        and c["col"] <= col < c["col"] + c["colspan"]
                        for c in cells
                    ):
                        col += 1
                    cursor[r] = col + colspan

                nested_nodes = module._direct_nested_tables(tc)
                text = module._hwpx_text_of(tc)
                if nested_nodes:
                    text = (
                        text + " ⟨표 안의 표⟩"
                    ).strip()

                cells.append({
                    "row": row,
                    "col": col,
                    "rowspan": rowspan,
                    "colspan": colspan,
                    "text": text,
                })

                for nested_node in nested_nodes:
                    table = _hwpx_table(nested_node)
                    if table["grid"]:
                        nested.append({
                            "row": row,
                            "col": col,
                            "table": table,
                        })

        declared_rows = _hwpx_int(node, "rowCnt", "rowcnt")
        declared_cols = _hwpx_int(node, "colCnt", "colcnt")
        if declared_rows is not None and declared_rows < 0:
            raise ValueError("손상된 HWPX 표: rowCnt가 음수다")
        if declared_cols is not None and declared_cols < 0:
            raise ValueError("손상된 HWPX 표: colCnt가 음수다")

        actual_rows = max(
            [c["row"] + c["rowspan"] for c in cells] or [0]
        )
        actual_cols = max(
            [c["col"] + c["colspan"] for c in cells] or [0]
        )
        if declared_rows is not None and actual_rows > declared_rows:
            raise ValueError(
                "손상된 HWPX 표: 셀 범위가 선언된 rowCnt를 넘는다"
            )
        if declared_cols is not None and actual_cols > declared_cols:
            raise ValueError(
                "손상된 HWPX 표: 셀 범위가 선언된 colCnt를 넘는다"
            )

        n_rows = actual_rows if declared_rows is None else declared_rows
        n_cols = actual_cols if declared_cols is None else declared_cols
        module._validate_table_shape(n_rows, n_cols, "HWPX 표")
        _validate_cells(cells, n_rows, n_cols, "HWPX 표")
        return {
            "rows": n_rows,
            "cols": n_cols,
            "cells": cells,
            "grid": _grid(cells, n_rows, n_cols),
            "nested_tables": nested,
        }

    module._validate_cells = _validate_cells
    module._decode_utf16 = _decode_utf16
    module._decode_text = _decode_text
    module._decode_change_range = _decode_change_range
    module._read_stream = _read_stream
    module._grid = _grid
    module._parse_table = _parse_table
    module._hwpx_int = _hwpx_int
    module._hwpx_table = _hwpx_table

    return module

install(sys.modules[__name__])

"""일부 한컴 생성 CFB의 비표준 할당표를 제한적으로 읽는 호환 리더.

정상 입력은 항상 `_ole.OleFile`이 먼저 처리한다. 이 클래스는 strict 리더가
거부한 뒤에만 사용하며, 시그니처·섹터 크기·범위·DIFAT 순환·stream 크기 같은
안전 불변식은 그대로 유지하고 FAT 표식/중복처럼 실제 문서에서 관찰되는
할당표 비정합만 완화한다.

동작 설계 교차검증: edwardkim/rhwp LenientCfbReader (MIT).
"""

import struct




class CompatOleFile(OleFile):
    """strict CFB 실패 후에만 쓰는 제한적 호환 리더."""

    def __init__(self, path_or_bytes):
        self.compat_warnings = []
        super().__init__(path_or_bytes)

    def _read_fat(self):
        """DIFAT의 중복 FAT SID와 잘못된 자체 표식만 제한적으로 허용한다."""
        raw_ids = [sid for sid in self._header_difat if sid != FREESECT]
        next_difat = self._first_difat_sector
        seen_difat = set()
        entries_per_sector = self.sector_size // 4

        while len(raw_ids) < self._num_fat_sectors:
            if self._num_difat_sectors == 0 or next_difat in (FREESECT, ENDOFCHAIN):
                break
            if next_difat in seen_difat:
                self._bad("호환 모드에서도 DIFAT 체인 순환은 허용하지 않는다")
            if len(seen_difat) >= self._num_difat_sectors:
                self._bad("DIFAT 섹터 수가 헤더와 다르다")
            seen_difat.add(next_difat)
            block = self._read_sector(next_difat)
            values = struct.unpack("<{}I".format(entries_per_sector), block)
            raw_ids.extend(sid for sid in values[:-1] if sid != FREESECT)
            next_difat = values[-1]

        unique = []
        seen = set()
        for sid in raw_ids[:self._num_fat_sectors]:
            if sid in (FREESECT, ENDOFCHAIN, FATSECT, DIFSECT, NOSTREAM):
                continue
            if not isinstance(sid, int) or sid < 0 or sid >= self._sector_count:
                self._bad("호환 FAT 섹터 번호가 파일 범위를 벗어났다")
            if sid in seen:
                self.compat_warnings.append("DIFAT의 중복 FAT 섹터 참조를 한 번만 사용했다")
                continue
            seen.add(sid)
            unique.append(sid)

        if not unique:
            self._bad("호환 모드에서도 읽을 FAT 섹터가 없다")
        if len(unique) > self._sector_count:
            self._bad("호환 FAT 섹터 수가 전체 섹터 수를 넘는다")

        fat = []
        for sid in unique:
            fat.extend(struct.unpack(
                "<{}I".format(entries_per_sector), self._read_sector(sid)
            ))

        for sid in unique:
            if sid >= len(fat):
                self._bad("FAT 테이블이 FAT 섹터 자체를 포함하지 못한다")
            if fat[sid] != FATSECT:
                self.compat_warnings.append("FAT 섹터의 FATSECT 표식 불일치를 허용했다")
        for sid in seen_difat:
            if sid >= len(fat):
                self._bad("FAT 테이블이 DIFAT 섹터 자체를 포함하지 못한다")
            if fat[sid] != DIFSECT:
                self.compat_warnings.append("DIFAT 섹터의 DIFSECT 표식 불일치를 허용했다")
        return fat

    def _chain(self, start, table, needed=None, what="FAT"):
        """선언 stream 크기 이후의 불필요한 FAT 꼬리만 잘라낸다.

        필요한 구간 내부의 순환·예약값·범위 오류는 strict와 동일하게 실패한다.
        """
        if needed == 0:
            return []
        if start in (FREESECT, ENDOFCHAIN, NOSTREAM):
            self._bad(f"{what} 체인의 시작 섹터가 없다")
        if needed is not None and needed > len(table):
            self._bad(f"{what} 체인이 가질 수 있는 섹터 수를 넘는다")

        out = []
        seen = set()
        sector = start
        while True:
            if sector in seen:
                self._bad(f"{what} 체인이 순환한다")
            if not isinstance(sector, int) or sector < 0 or sector >= len(table):
                self._bad(f"{what} 체인의 섹터 번호가 범위를 벗어났다")
            seen.add(sector)
            out.append(sector)
            next_sector = table[sector]

            if needed is not None and len(out) >= needed:
                if next_sector != ENDOFCHAIN:
                    self.compat_warnings.append(f"{what} 체인의 선언 크기 이후 꼬리를 무시했다")
                return out
            if next_sector == ENDOFCHAIN:
                if needed is None:
                    return out
                self._bad(f"{what} 체인이 예상보다 짧다")
            if next_sector in (FREESECT, FATSECT, DIFSECT, NOSTREAM):
                self._bad(f"{what} 체인이 예약된 섹터를 가리킨다")
            sector = next_sector

StrictOleFile = OleFile

"""strict CFB 우선, 알려진 비표준 할당표에만 호환 재시도를 적용한다."""

from contextvars import ContextVar




_COMPAT = ContextVar("ai_hwp_reader_compat_cfb", default=None)


def current_compat_warnings():
    """현재 읽기 호출에서 호환 CFB가 쓰였다면 경고 목록을 반환한다."""
    return _COMPAT.get()


class FallbackOleFile:
    """정상 문서는 strict 경로 하나만 타는 OLE 팩토리."""

    def __new__(cls, source):
        _COMPAT.set(None)
        try:
            ole = StrictOleFile(source)
            ole.compat_mode = False
            ole.compat_warnings = []
            return ole
        except ValueError as strict_error:
            try:
                ole = CompatOleFile(source)
            except ValueError:
                raise strict_error
            ole.compat_mode = True
            ole.strict_error = str(strict_error)
            warnings = tuple(ole.compat_warnings) or ("비표준 CFB 할당표를 호환 모드로 읽었다",)
            _COMPAT.set(warnings)
            return ole

"""0.5 계열 실문서 의미 복원 계층.

정상 HWP/HWPX의 기존 fast path를 유지하면서 문단 번호·글머리표, 각주·미주,
하이퍼링크, 수식 스크립트, 글상자·이미지 참조처럼 AI가 문서 의미를 이해하는 데
필요한 구조를 추가로 보존한다.

포맷/동작 교차검증: edwardkim/rhwp, chrisryugj/kordoc (MIT).
"""

MAX_HWP_RECORDS = 500_000
MAX_HWP_STREAM_BYTES = 256 * 1024 * 1024
MAX_HWP_TOTAL_BYTES = 512 * 1024 * 1024
MAX_HWPX_SECTION_BYTES = 64 * 1024 * 1024
MAX_HWPX_TOTAL_XML_BYTES = 256 * 1024 * 1024
MAX_FEATURE_DEPTH = 8
MAX_HYPERLINK_LENGTH = 2_000

TAG_BIN_DATA = 0x12
TAG_NUMBERING = 0x17
TAG_BULLET = 0x18
TAG_DOC_PARA_SHAPE = 0x19
TAG_EQEDIT = 0x58
TAG_SHAPE_COMPONENT = 0x4C
TAG_SHAPE_COMPONENT_PICTURE = 0x55


def _cid(text):
    return int.from_bytes(text.encode("ascii"), "big")


CTRL_TBL = _cid("tbl ")
CTRL_GSO = _cid("gso ")
CTRL_EQED = _cid("eqed")
CTRL_HEAD = _cid("head")
CTRL_FOOT = _cid("foot")
CTRL_FN = _cid("fn  ")
CTRL_EN = _cid("en  ")
CTRL_ATNO = _cid("atno")
CTRL_NWNO = _cid("nwno")
CTRL_SECD = _cid("secd")
CTRL_OLE = _cid("ole ")
FIELD_HLK = _cid("%hlk")

KNOWN_CTRL_IDS = {
    CTRL_TBL, CTRL_GSO, CTRL_EQED, CTRL_HEAD, CTRL_FOOT,
    CTRL_FN, CTRL_EN, CTRL_ATNO, CTRL_NWNO, CTRL_SECD, CTRL_OLE,
}


def _swap32(value):
    return int.from_bytes(value.to_bytes(4, "little"), "big")


def _is_field_id(value):
    return ((value >> 24) & 0xFF) == 0x25


def _normalize_ctrl_id(value):
    if value in KNOWN_CTRL_IDS or _is_field_id(value):
        return value
    swapped = _swap32(value)
    if swapped in KNOWN_CTRL_IDS or _is_field_id(swapped):
        return swapped
    return value


def _records_limited(module, data):
    out = []
    pos, end = 0, len(data)
    while pos < end:
        if len(out) >= MAX_HWP_RECORDS:
            raise ValueError(f"손상된 HWP 레코드: {MAX_HWP_RECORDS}개 상한을 넘는다")
        if pos + 4 > end:
            raise ValueError("손상된 HWP 레코드: 헤더가 4바이트보다 짧다")
        header = module.struct.unpack_from("<I", data, pos)[0]
        tag = header & 0x3FF
        level = (header >> 10) & 0x3FF
        size = (header >> 20) & 0xFFF
        pos += 4
        if size == 0xFFF:
            if pos + 4 > end:
                raise ValueError("손상된 HWP 레코드: 확장 크기가 잘렸다")
            size = module.struct.unpack_from("<I", data, pos)[0]
            pos += 4
        if size > end - pos:
            raise ValueError("손상된 HWP 레코드: payload가 섹션 끝을 넘는다")
        out.append((tag, level, data[pos:pos + size]))
        pos += size
    return out


def _inflate_raw_limited(module, raw, max_bytes, what):
    dec = module.zlib.decompressobj(-15)
    try:
        out = dec.decompress(raw, max_bytes + 1)
    except module.zlib.error as exc:
        raise ValueError(f"{what}: HWP 압축 스트림이 손상됐다") from exc
    if len(out) > max_bytes or dec.unconsumed_tail:
        raise ValueError(f"{what}: 압축 해제 결과가 {max_bytes}바이트 상한을 넘는다")
    try:
        out += dec.flush(max_bytes + 1 - len(out))
    except module.zlib.error as exc:
        raise ValueError(f"{what}: HWP 압축 스트림이 손상됐다") from exc
    if len(out) > max_bytes:
        raise ValueError(f"{what}: 압축 해제 결과가 {max_bytes}바이트 상한을 넘는다")
    if not dec.eof:
        raise ValueError(f"{what}: HWP 압축 스트림이 끝나기 전에 잘렸다")
    return out


def _hwp_string(module, data, offset):
    if offset + 2 > len(data):
        return "", len(data)
    length = module.struct.unpack_from("<H", data, offset)[0]
    start = offset + 2
    end = start + length * 2
    if end > len(data):
        raise ValueError("손상된 DocInfo: UTF-16 문자열이 레코드 끝을 넘는다")
    if not length:
        return "", start
    return module._decode_utf16(data[start:end], "HWP DocInfo"), end


def _parse_docinfo(module, ole, compressed):
    info = {"para_shapes": [], "numberings": [], "bullets": [], "bin_data": []}
    if not ole.exists("DocInfo"):
        return info
    records = module._records(module._read_stream(ole, "DocInfo", compressed))
    for tag, _level, data in records:
        if tag == TAG_DOC_PARA_SHAPE and len(data) >= 4:
            attr = module.struct.unpack_from("<I", data, 0)[0]
            info["para_shapes"].append({
                "head_type": (attr >> 23) & 0x03,
                "level": (attr >> 25) & 0x07,
                "numbering_id": module.struct.unpack_from("<H", data, 30)[0]
                if len(data) >= 32 else 0,
            })
        elif tag == TAG_BIN_DATA and len(data) >= 2:
            attr = module.struct.unpack_from("<H", data, 0)[0]
            kind = attr & 0x000F
            if kind == 0:
                info["bin_data"].append({"kind": "link", "storage_id": 0, "extension": ""})
            else:
                storage_id = module.struct.unpack_from("<H", data, 2)[0] if len(data) >= 4 else 0
                extension, _ = _hwp_string(module, data, 4)
                info["bin_data"].append({
                    "kind": "storage" if kind == 2 else "embed",
                    "storage_id": storage_id,
                    "extension": extension.strip(".\0"),
                })
        elif tag == TAG_NUMBERING and len(data) >= 14:
            formats, number_formats = [], []
            starts = [1] * 7
            offset = 0
            for _ in range(7):
                if offset + 12 > len(data):
                    formats.append("")
                    number_formats.append(0)
                    continue
                attr = module.struct.unpack_from("<I", data, offset)[0]
                number_formats.append((attr >> 5) & 0x0F)
                offset += 12
                value, offset = _hwp_string(module, data, offset)
                formats.append(value)
            base_start = 1
            if offset + 2 <= len(data):
                base_start = module.struct.unpack_from("<H", data, offset)[0] or 1
                offset += 2
            for level in range(7):
                if offset + 4 <= len(data):
                    starts[level] = module.struct.unpack_from("<I", data, offset)[0] or 1
                    offset += 4
                else:
                    starts[level] = base_start
            info["numberings"].append({
                "formats": formats, "number_formats": number_formats, "starts": starts,
            })
        elif tag == TAG_BULLET and len(data) >= 14:
            code = module.struct.unpack_from("<H", data, 12)[0]
            info["bullets"].append(chr(code) if code and code != 0xFFFF else "•")
    return info


class _NumberingState:
    def __init__(self):
        self.current = 0
        self.counters = [0] * 7
        self.history = {}

    def advance(self, numbering_id, level):
        level = min(max(level, 0), 6)
        if self.current != numbering_id:
            if self.current:
                self.history[self.current] = self.counters[:]
            if numbering_id in self.history:
                self.counters = self.history[numbering_id][:]
            else:
                old = self.counters
                self.counters = [0] * 7
                for i in range(level):
                    self.counters[i] = old[i]
            self.current = numbering_id
        self.counters[level] += 1
        for i in range(level + 1, 7):
            self.counters[i] = 0
        return self.counters[:]


def _roman(number):
    if number <= 0 or number > 3999:
        return str(number)
    pairs = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
             (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
             (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
    out = []
    for value, glyph in pairs:
        while number >= value:
            number -= value
            out.append(glyph)
    return "".join(out)


def _latin(number, upper=True):
    if number <= 0:
        return str(number)
    out = ""
    base = 65 if upper else 97
    while number:
        number -= 1
        out = chr(base + number % 26) + out
        number //= 26
    return out


def _east_asian(number, digits, units, zero):
    if number == 0:
        return zero
    if number < 0 or number > 99999:
        return str(number)
    result, unit = "", 0
    while number:
        digit = number % 10
        if digit:
            d = "" if digit == 1 and unit else digits[digit]
            result = d + units[unit] + result
        number //= 10
        unit += 1
    return result


def _format_number(number, code, auto=False):
    if code == 1:
        return chr(0x2460 + number - 1) if 1 <= number <= 20 else str(number)
    if code == 2:
        return _roman(number)
    if code == 3:
        return _roman(number).lower()
    if code == 4:
        return _latin(number, True)
    if code == 5:
        return _latin(number, False)
    ganada_code = 6 if auto else 8
    hangul_code = 7 if auto else 12
    hanja_code = 8 if auto else 13
    if code == ganada_code:
        table = "가나다라마바사아자차카타파하"
        return table[number - 1] if 1 <= number <= len(table) else str(number)
    if not auto and code == 10:
        table = "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ"
        return table[number - 1] if 1 <= number <= len(table) else str(number)
    if code == hangul_code:
        return _east_asian(number,
                           ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"],
                           ["", "십", "백", "천", "만"], "영")
    if code == hanja_code:
        return _east_asian(number,
                           ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"],
                           ["", "十", "百", "千", "萬"], "零")
    return str(number)


def _expand_numbering(fmt, counters, numbering):
    out, i = [], 0
    while i < len(fmt):
        if fmt[i] == "^" and i + 1 < len(fmt) and fmt[i + 1] in "1234567":
            idx = int(fmt[i + 1]) - 1
            count = counters[idx] if idx < len(counters) else 0
            start = numbering["starts"][idx] if idx < len(numbering["starts"]) else 1
            number = start - 1 + count if count else start
            code = numbering["number_formats"][idx] if idx < len(numbering["number_formats"]) else 0
            out.append(_format_number(number, code))
            i += 2
        else:
            out.append(fmt[i])
            i += 1
    return "".join(out)


__all__ = [
    "MAX_HWP_RECORDS", "MAX_HWP_STREAM_BYTES", "MAX_HWP_TOTAL_BYTES",
    "MAX_HWPX_SECTION_BYTES", "MAX_HWPX_TOTAL_XML_BYTES", "MAX_FEATURE_DEPTH",
    "MAX_HYPERLINK_LENGTH", "TAG_BIN_DATA", "TAG_NUMBERING", "TAG_BULLET",
    "TAG_DOC_PARA_SHAPE", "TAG_EQEDIT", "TAG_SHAPE_COMPONENT",
    "TAG_SHAPE_COMPONENT_PICTURE", "CTRL_TBL", "CTRL_GSO", "CTRL_EQED",
    "CTRL_HEAD", "CTRL_FOOT", "CTRL_FN", "CTRL_EN", "CTRL_ATNO",
    "CTRL_NWNO", "CTRL_SECD", "CTRL_OLE", "FIELD_HLK",
    "_normalize_ctrl_id", "_records_limited", "_parse_docinfo",
    "_NumberingState", "_format_number", "_expand_numbering",
]

"""HWP 0.5 문단·컨트롤 의미 복원."""


_EXTENDED = set(range(1, 4)) | set(range(11, 13)) | set(range(14, 19)) | set(range(21, 24))
_INLINE = set(range(4, 10)) | set(range(19, 21))


def _field_url(command):
    out, escaped = [], False
    for ch in command:
        if escaped: out.append(ch); escaped = False
        elif ch == "\\": escaped = True
        elif ch == ";": break
        else: out.append(ch)
    value = "".join(out).strip()
    return value if value and len(value) <= MAX_HYPERLINK_LENGTH and value.lower().startswith(("http://", "https://", "mailto:", "#")) else ""


def _field_command(module, data):
    if len(data) < 11: return ""
    length = module.struct.unpack_from("<H", data, 9)[0]
    end = 11 + length * 2
    return module._decode_utf16(data[11:end], "HWP 하이퍼링크 필드").rstrip("\0") if length and end <= len(data) else ""


def _child_end(records, index, end):
    level = records[index][1]; pos = index + 1
    while pos < end and records[pos][1] > level: pos += 1
    return pos


def _child_text(module, records, start, end):
    parts = []
    for tag, _level, data in records[start:end]:
        if tag == module.HWPTAG_PARA_TEXT:
            text = module._decode_text(data).strip()
            if text: parts.append(text)
    return " ".join(parts)


def _child_text_without_tables(module, records, start, end):
    """머리말/꼬리말의 표 셀 문자를 평문과 중복시키지 않는다."""
    parts = []; pos = start
    while pos < end:
        tag, _level, data = records[pos]
        if tag == module.HWPTAG_CTRL_HEADER and len(data) >= 4:
            ctrl = _normalize_ctrl_id(module.struct.unpack_from("<I", data)[0])
            if ctrl == CTRL_TBL:
                pos = _child_end(records, pos, end)
                continue
        if tag == module.HWPTAG_PARA_TEXT:
            text = module._decode_text(data).strip()
            if text: parts.append(text)
        pos += 1
    return " ".join(parts)


def _child_tables(module, records, start, end):
    tables = []; pos = start
    while pos < end:
        tag, _level, data = records[pos]
        if tag == module.HWPTAG_CTRL_HEADER and len(data) >= 4:
            ctrl = _normalize_ctrl_id(module.struct.unpack_from("<I", data)[0])
            if ctrl == CTRL_TBL:
                finish = _child_end(records, pos, end)
                for i in range(pos + 1, finish):
                    if records[i][0] == module.HWPTAG_TABLE:
                        table, _ = module._parse_table(records, i)
                        if table.get("grid"): tables.append(table)
                        break
                pos = finish
                continue
        pos += 1
    return tables


def _table_identity(table):
    return (
        table.get("rows", 0), table.get("cols", 0),
        tuple((c.get("row"), c.get("col"), c.get("rowspan", 1), c.get("colspan", 1), c.get("text", ""))
              for c in table.get("cells", [])),
    )


def _equation(module, records, start, end):
    for tag, _level, data in records[start:end]:
        if tag == TAG_EQEDIT and len(data) >= 6:
            length = module.struct.unpack_from("<H", data, 4)[0]; stop = 6 + length * 2
            if length and stop <= len(data):
                return module._decode_utf16(data[6:stop], "HWP 수식").replace("\0", "").strip()
    return ""


def _image_name(module, data, docinfo):
    if len(data) < 73: return ""
    ident = module.struct.unpack_from("<H", data, 71)[0]
    if not ident: return ""
    items = docinfo.get("bin_data", []); item = items[ident - 1] if ident <= len(items) else None
    if item and item.get("kind") == "link": return f"외부연결:{ident}"
    storage = (item.get("storage_id", 0) if item else ident) or ident
    ext = (item.get("extension") or "bin") if item else "bin"
    return f"BIN{storage:04X}.{ext}"


def control_effect(module, records, index, end, docinfo, state):
    data = records[index][2]; finish = _child_end(records, index, end)
    if len(data) < 4: return {"inline": "", "blocks": [], "end": finish}
    ctrl = _normalize_ctrl_id(module.struct.unpack_from("<I", data)[0]); blocks = []; inline = ""
    if ctrl == CTRL_EQED:
        value = _equation(module, records, index + 1, finish)
        if value: inline = f"[수식: {value}]"
    elif ctrl in (CTRL_FN, CTRL_EN):
        kind = "각주" if ctrl == CTRL_FN else "미주"; typ = 1 if ctrl == CTRL_FN else 2
        number = state["auto"].get(typ, 1); state["auto"][typ] = number + 1
        value = _child_text(module, records, index + 1, finish); inline = f"[{kind} {number}]"
        if value: blocks.append({"type": "note", "kind": kind, "number": number, "text": value})
    elif ctrl in (CTRL_HEAD, CTRL_FOOT):
        kind = "header" if ctrl == CTRL_HEAD else "footer"
        value = _child_text_without_tables(module, records, index + 1, finish)
        if value:
            key = kind + "\0" + value
            if key not in state["seen"]: state["seen"].add(key); blocks.append({"type": kind, "text": value})
        for table in _child_tables(module, records, index + 1, finish):
            key = (kind, "table", _table_identity(table))
            if key not in state["seen"]:
                state["seen"].add(key)
                blocks.append({"type": "table", "context": kind, **table})
    elif ctrl == CTRL_ATNO and len(data) >= 8:
        attr = module.struct.unpack_from("<I", data, 4)[0]; typ = attr & 15; fmt = (attr >> 4) & 255
        number = state["auto"].get(typ, 1); state["auto"][typ] = number + 1
        pre = module.struct.unpack_from("<H", data, 12)[0] if len(data) >= 14 else 0
        post = module.struct.unpack_from("<H", data, 14)[0] if len(data) >= 16 else 0
        inline = (chr(pre) if pre else "") + _format_number(number, fmt, auto=True) + (chr(post) if post else "")
    elif ctrl == CTRL_NWNO and len(data) >= 10:
        attr = module.struct.unpack_from("<I", data, 4)[0]; number = module.struct.unpack_from("<H", data, 8)[0]
        if number: state["auto"][attr & 15] = number
    elif ctrl == CTRL_SECD and len(data) >= 20: state["outline"] = module.struct.unpack_from("<H", data, 18)[0]
    elif ctrl == FIELD_HLK:
        url = _field_url(_field_command(module, data))
        if url: blocks.append({"type": "hyperlink", "url": url})
    elif ctrl == CTRL_TBL:
        for pos in range(index + 1, finish):
            if records[pos][0] == module.HWPTAG_TABLE:
                table, _ = module._parse_table(records, pos)
                if table.get("grid"): blocks.append({"type": "table", **table})
                break
    elif ctrl == CTRL_GSO:
        value = _child_text(module, records, index + 1, finish)
        if value: blocks.append({"type": "textbox", "text": value})
        for tag, _level, payload in records[index + 1:finish]:
            if tag == TAG_SHAPE_COMPONENT_PICTURE:
                name = _image_name(module, payload, docinfo)
                if name: blocks.append({"type": "image", "name": name})
    return {"inline": inline, "blocks": blocks, "end": finish}


def decode_para(module, payloads, controls):
    out, ctrl_index = [], 0
    for data in payloads:
        if len(data) % 2: raise ValueError("손상된 HWP PARA_TEXT: UTF-16LE 바이트 수가 홀수다")
        pos, units = 0, len(data) // 2
        while pos < units:
            code = module.struct.unpack_from("<H", data, pos * 2)[0]
            if code >= 32:
                start = pos
                while pos < units and module.struct.unpack_from("<H", data, pos * 2)[0] >= 32: pos += 1
                out.append(module._decode_utf16(data[start * 2:pos * 2], "HWP PARA_TEXT")); continue
            if code in _EXTENDED or code in _INLINE:
                if pos + 8 > units: raise ValueError("손상된 HWP PARA_TEXT: 8워드 제어문자가 잘렸다")
                if code in _EXTENDED:
                    if ctrl_index < len(controls) and controls[ctrl_index].get("inline"): out.append(controls[ctrl_index]["inline"])
                    ctrl_index += 1
                elif code == 9: out.append("\t")
                pos += 8; continue
            if code in (0, 10): out.append("\n")
            elif code == 24: out.append("-")
            elif code == 30: out.append("\u00a0")
            elif code == 31: out.append(" ")
            pos += 1
    return "".join(out).replace("\x7f", " ").strip()


def paragraph_prefix(module, header, docinfo, state):
    data = header[2]
    if len(data) < 10: return ""
    shape_id = module.struct.unpack_from("<H", data, 8)[0]; shapes = docinfo.get("para_shapes", [])
    if shape_id >= len(shapes): return ""
    shape = shapes[shape_id]; typ = shape.get("head_type", 0); level = min(shape.get("level", 0), 6); ident = shape.get("numbering_id", 0)
    if typ in (1, 2):
        if typ == 1 and not ident: ident = state.get("outline", 0)
        defs = docinfo.get("numberings", [])
        if not ident or ident > len(defs): return ""
        definition = defs[ident - 1]; counters = state["numbering"].advance(ident, level)
        fmt = definition["formats"][level] if level < len(definition["formats"]) else ""
        return _expand_numbering(fmt, counters, definition).strip()
    if typ == 3:
        bullets = docinfo.get("bullets", [])
        if ident and ident <= len(bullets): return bullets[ident - 1]
    return ""

"""HWP 배포용 ViewText 읽기 지원. 표준 라이브러리만 사용한다.

알고리즘은 HWP 5 배포용 문서 규격과 rhwp/kordoc(MIT), FIPS-197을 교차검증했다.
"""
import struct
import zlib

TAG_DISTRIBUTE_DOC_DATA = 0x1C
S = bytes.fromhex("637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b27509832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cfd0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdbe0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9ee1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16")
IS = bytes.fromhex("52096ad53036a538bf40a39e81f3d7fb7ce339829b2fff87348e4344c4dee9cb547b9432a6c2233dee4c950b42fac34e082ea16628d924b2765ba2496d8bd12572f8f66486689816d4a45ccc5d65b6926c704850fdedb9da5e154657a78d9d8490d8ab008cbcd30af7e45805b8b34506d02c1e8fca3f0f02c1afbd0301138a6b3a9111414f67dcea97f2cfcef0b4e67396ac7422e7ad3585e2f937e81c75df6e47f11a711d29c5896fb7620eaa18be1bfc563e4bc6d279209adbc0fe78cd5af41fdda8338807c731b11210592780ec5f60517fa919b54a0d2de57a9f93c99cefa0e03b4dae2af5b0c8ebbb3c83539961172b047eba77d626e169146355210c7d")
RCON = (1, 2, 4, 8, 16, 32, 64, 128, 27, 54)

class ViewTextError(ValueError):
    pass

class _Lcg:
    def __init__(self, seed):
        self.seed = seed & 0xFFFFFFFF
    def rand(self):
        self.seed = (self.seed * 214013 + 2531011) & 0xFFFFFFFF
        return (self.seed >> 16) & 0x7FFF

def _unscramble(payload):
    if len(payload) < 256:
        raise ViewTextError("DISTRIBUTE_DOC_DATA가 256바이트보다 짧다")
    out = bytearray(payload[:256])
    random = _Lcg(struct.unpack_from("<I", out)[0])
    left = 0
    key = 0
    for index in range(256):
        if not left:
            key = random.rand() & 0xFF
            left = (random.rand() & 15) + 1
        if index >= 4:
            out[index] ^= key
        left -= 1
    return bytes(out)

def _mul(a, b):
    result = 0
    for _ in range(8):
        if b & 1:
            result ^= a
        a = ((a << 1) ^ 0x11B) if a & 0x80 else a << 1
        a &= 0xFF
        b >>= 1
    return result

def _round_keys(key):
    if len(key) != 16:
        raise ViewTextError("AES-128 키 길이가 16바이트가 아니다")
    words = [list(key[offset:offset + 4]) for offset in range(0, 16, 4)]
    for index in range(4, 44):
        temp = words[index - 1][:]
        if index % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [S[value] for value in temp]
            temp[0] ^= RCON[index // 4 - 1]
        words.append([words[index - 4][j] ^ temp[j] for j in range(4)])
    return [sum((words[rnd * 4 + j] for j in range(4)), []) for rnd in range(11)]

def _add_key(state, key):
    for index, value in enumerate(key):
        state[index] ^= value

def _decrypt_block(block, keys):
    state = list(block)
    _add_key(state, keys[10])
    for rnd in range(9, -1, -1):
        previous = state[:]
        for row in range(4):
            for col in range(4):
                state[col * 4 + row] = previous[((col - row) % 4) * 4 + row]
        state[:] = [IS[value] for value in state]
        _add_key(state, keys[rnd])
        if rnd:
            for col in range(4):
                pos = col * 4
                a = state[pos:pos + 4]
                state[pos] = _mul(a[0], 14) ^ _mul(a[1], 11) ^ _mul(a[2], 13) ^ _mul(a[3], 9)
                state[pos + 1] = _mul(a[0], 9) ^ _mul(a[1], 14) ^ _mul(a[2], 11) ^ _mul(a[3], 13)
                state[pos + 2] = _mul(a[0], 13) ^ _mul(a[1], 9) ^ _mul(a[2], 14) ^ _mul(a[3], 11)
                state[pos + 3] = _mul(a[0], 11) ^ _mul(a[1], 13) ^ _mul(a[2], 9) ^ _mul(a[3], 14)
    return bytes(state)

def aes128_ecb_decrypt(data, key):
    if not data or len(data) % 16:
        raise ViewTextError("AES 데이터 길이가 16바이트 배수가 아니다")
    keys = _round_keys(bytes(key))
    return b"".join(_decrypt_block(data[i:i + 16], keys) for i in range(0, len(data), 16))

def decrypt_viewtext_section(data, compressed, max_output=256 * 1024 * 1024):
    if len(data) < 4:
        raise ViewTextError("ViewText 첫 레코드 헤더가 잘렸다")
    header = struct.unpack_from("<I", data)[0]
    tag = header & 0x3FF
    size = (header >> 20) & 0xFFF
    header_size = 4
    if size == 0xFFF:
        if len(data) < 8:
            raise ViewTextError("ViewText 확장 레코드 헤더가 잘렸다")
        size = struct.unpack_from("<I", data, 4)[0]
        header_size = 8
    end = header_size + size
    if tag != TAG_DISTRIBUTE_DOC_DATA or size < 256 or end > len(data):
        raise ViewTextError("DISTRIBUTE_DOC_DATA 레코드가 올바르지 않다")
    payload = _unscramble(data[header_size:header_size + 256])
    offset = 4 + (payload[0] & 15)
    key = payload[offset:offset + 16]
    encrypted = data[end:]
    remainder = len(encrypted) % 16
    if remainder:
        if any(encrypted[-remainder:]):
            raise ViewTextError("ViewText 암호 데이터 끝이 블록 경계에서 잘렸다")
        encrypted = encrypted[:-remainder]
    plain = aes128_ecb_decrypt(encrypted, key)
    if not compressed:
        if len(plain) > max_output:
            raise ViewTextError("ViewText 본문이 처리 상한을 넘는다")
        return plain.rstrip(b"\0")
    decoder = zlib.decompressobj(-15)
    try:
        out = decoder.decompress(plain, max_output + 1)
        out += decoder.flush(max_output + 1 - len(out))
    except zlib.error as exc:
        raise ViewTextError("ViewText DEFLATE가 손상됐다") from exc
    if len(out) > max_output or not decoder.eof or decoder.unconsumed_tail:
        raise ViewTextError("ViewText 압축 해제 결과가 비정상적이다")
    return out

"""0.5 읽기 계층 설치 진입점."""




MAX_XML_DEPTH = 256
MAX_XML_NODES = 2_000_000
MAX_ZIP_RATIO = 1000
MAX_ARCHIVE_TOTAL_SIZE = 1024 * 1024 * 1024


def _parse_paragraph(module, records, start, end, docinfo, state):
    base = records[start][1]; payloads = []; controls = []; blocks = []; pos = start + 1
    while pos < end:
        tag, level, data = records[pos]
        if level == base + 1 and tag == module.HWPTAG_PARA_TEXT:
            payloads.append(data); pos += 1; continue
        if level == base + 1 and tag == module.HWPTAG_MEMO_LIST:
            memo, nxt = module._parse_memo(records, pos)
            if memo: blocks.append({"type": "memo", "text": memo})
            pos = max(pos + 1, nxt); continue
        if level == base + 1 and tag == module.HWPTAG_CTRL_HEADER:
            effect = control_effect(module, records, pos, end, docinfo, state)
            controls.append(effect); blocks.extend(effect["blocks"]); pos = max(pos + 1, effect["end"]); continue
        pos += 1
    text = decode_para(module, payloads, controls); prefix = paragraph_prefix(module, records[start], docinfo, state)
    if prefix: text = (prefix + " " + text).strip()
    out = [{"type": "text", "text": text}] if text else []; out.extend(blocks); return out


def _parse_hwp_section(module, records, docinfo, state):
    blocks = []; pos = 0
    while pos < len(records):
        tag, level, data = records[pos]
        if tag == module.HWPTAG_PARA_HEADER:
            end = pos + 1
            while end < len(records):
                ntag, nlevel, _ = records[end]
                if ntag == module.HWPTAG_PARA_HEADER and nlevel <= level: break
                end += 1
            blocks.extend(_parse_paragraph(module, records, pos, end, docinfo, state)); pos = end; continue
        if tag == module.HWPTAG_MEMO_LIST:
            memo, nxt = module._parse_memo(records, pos)
            if memo: blocks.append({"type": "memo", "text": memo})
            pos = max(pos + 1, nxt); continue
        if tag == module.HWPTAG_TABLE:
            table, nxt = module._parse_table(records, pos)
            if table.get("grid"): blocks.append({"type": "table", **table})
            pos = max(pos + 1, nxt); continue
        if tag == module.HWPTAG_PARA_TEXT:
            text = module._decode_text(data).strip()
            if text: blocks.append({"type": "text", "text": text})
        pos += 1
    return blocks


def _read_hwp(module, source, name=None):
    label = module._label(source, name)
    try: ole = module.OleFile(source)
    except ValueError as exc: raise ValueError(f"{label}: OLE HWP 파일이 아니다 ({exc})") from None
    if not ole.exists("FileHeader"): raise ValueError(f"{label}: FileHeader 스트림이 없다")
    head = ole.open("FileHeader")
    if len(head) < 40 or not head.startswith(module.HWP_SIGNATURE): raise ValueError(f"{label}: HWP 5.0 FileHeader가 아니다")
    flags = module.struct.unpack_from("<I", head, 36)[0]
    compressed, encrypted, distribution, drm = bool(flags & 1), bool(flags & 2), bool(flags & 4), bool(flags & 16)
    if drm: raise RuntimeError(f"{label}: DRM 보호 문서는 읽을 수 없다")
    if encrypted: raise RuntimeError(f"{label}: 열기 암호가 걸린 문서다. 암호를 풀고 다시 저장할 것")
    docinfo = _parse_docinfo(module, ole, compressed); prefix = "ViewText/Section" if distribution else "BodyText/Section"
    names = sorted((s for s in ole.listdir() if s.startswith(prefix)), key=module._section_number)
    if not names: raise ValueError(f"{label}: {'ViewText' if distribution else 'BodyText'} 섹션이 없다")
    state = {"numbering": _NumberingState(), "auto": {}, "outline": 0, "seen": set()}; blocks = []; total = 0
    for stream in names:
        data = decrypt_viewtext_section(ole.open(stream), compressed, MAX_HWP_STREAM_BYTES) if distribution else module._read_stream(ole, stream, compressed)
        total += len(data)
        if len(data) > MAX_HWP_STREAM_BYTES or total > MAX_HWP_TOTAL_BYTES: raise ValueError(f"{label}: HWP 본문이 처리 상한을 넘는다")
        blocks.extend(_parse_hwp_section(module, module._records(data), docinfo, state))
    if not distribution: blocks.extend(module._read_hwp_changes(ole, compressed))
    return blocks


def _xml_guard(module, raw, section):
    if len(raw) > MAX_HWPX_SECTION_BYTES: raise ValueError(f"{section}: HWPX XML이 처리 상한을 넘는다")
    head = raw[:65536].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head: raise ValueError(f"{section}: DTD/ENTITY가 있는 XML은 거부한다")
    try: root = module.ElementTree.fromstring(raw)
    except module.ElementTree.ParseError as exc: raise ValueError(f"손상된 HWPX XML ({section})") from exc
    stack = [(root, 1)]; nodes = 0
    while stack:
        node, depth = stack.pop(); nodes += 1
        if nodes > MAX_XML_NODES: raise ValueError(f"{section}: XML 노드가 처리 상한을 넘는다")
        if depth > MAX_XML_DEPTH: raise ValueError(f"{section}: XML 깊이가 처리 상한을 넘는다")
        stack.extend((child, depth + 1) for child in node)
    return root


def _hwpx_ref(module, node):
    for item in node.iter():
        for key in ("binaryItemIDRef", "href"):
            value = item.get(key)
            if value: return value
    return ""


def _hwpx_para(module, para, blocks):
    buf = []; extras = []; deleted = [0]
    def flush():
        text = module.re.sub(r"[ \t]+", " ", "".join(buf)).strip(); buf.clear()
        if text: blocks.append({"type": "text", "text": text})
    def walk(node, depth=0):
        if depth > MAX_XML_DEPTH: raise ValueError("HWPX 문단 중첩 깊이가 처리 상한을 넘는다")
        for child in node:
            local = module._hwpx_local(child.tag)
            if local == "deleteBegin": deleted[0] += 1; continue
            if local == "deleteEnd": deleted[0] = max(0, deleted[0] - 1); continue
            if local in ("insertBegin", "insertEnd", "hiddenComment", "shapeComment"): continue
            if local == "tbl":
                flush(); table = module._hwpx_table(child)
                if table.get("grid"): blocks.append({"type": "table", **table})
                continue
            if local in ("memo", "memogroup"): flush(); module._hwpx_append_memos(child, blocks); continue
            if local in ("footNote", "endNote", "fn", "en"):
                text = module._hwpx_text_of(child).strip()
                if text: extras.append({"type": "note", "kind": "각주" if local in ("footNote", "fn") else "미주", "text": text})
                continue
            if local == "equation":
                script = next((n for n in child.iter() if module._hwpx_local(n.tag) == "script"), None); text = module._hwpx_text_of(script) if script is not None else ""
                if text: buf.append(f" [수식: {text}] ")
                continue
            if local == "hyperlink":
                url = child.get("url") or child.get("href") or ""
                if url and len(url) <= MAX_HYPERLINK_LENGTH: extras.append({"type": "hyperlink", "url": url})
                walk(child, depth + 1); continue
            if local == "fieldBegin":
                for item in child.iter():
                    if module._hwpx_local(item.tag) == "stringParam" and item.get("name") == "Path":
                        url = (item.text or "").strip()
                        if url and len(url) <= MAX_HYPERLINK_LENGTH: extras.append({"type": "hyperlink", "url": url})
                        break
                continue
            if local in ("pic", "shape", "drawingObject"):
                ref = _hwpx_ref(module, child)
                if ref: extras.append({"type": "image", "name": ref})
                draw = next((n for n in child.iter() if module._hwpx_local(n.tag) == "drawText"), None)
                text = module._hwpx_text_of(draw) if draw is not None else ""
                if text: extras.append({"type": "textbox", "text": text})
                continue
            if local == "t" and child.text and not deleted[0]: buf.append(child.text); walk(child, depth + 1); continue
            if local == "tab" and not deleted[0]: buf.append("\t"); continue
            if local in ("br", "lineBreak") and not deleted[0]: buf.append("\n"); continue
            if local in ("fwSpace", "hwSpace") and not deleted[0]: buf.append(" "); continue
            walk(child, depth + 1)
    walk(para); flush(); blocks.extend(extras)


def _hwpx_walk(module, node, blocks):
    for child in node:
        local = module._hwpx_local(child.tag)
        if local == "tbl":
            table = module._hwpx_table(child)
            if table.get("grid"): blocks.append({"type": "table", **table})
        elif local in ("memo", "memogroup"): module._hwpx_append_memos(child, blocks)
        elif local == "p": _hwpx_para(module, child, blocks)
        else: _hwpx_walk(module, child, blocks)


def _zip_guard(zf, label):
    infos = zf.infolist(); seen = set(); total = 0
    for info in infos:
        if info.filename in seen: raise ValueError(f"{label}: ZIP 경로가 중복됐다: {info.filename}")
        seen.add(info.filename); total += info.file_size
        if total > MAX_ARCHIVE_TOTAL_SIZE: raise ValueError(f"{label}: ZIP 전체 압축 해제 크기가 처리 상한을 넘는다")
        if info.compress_size and info.file_size > 1024 * 1024 and info.file_size / info.compress_size > MAX_ZIP_RATIO: raise ValueError(f"{label}: 비정상 압축률의 ZIP 멤버다: {info.filename}")
    return infos


def _read_hwpx(module, source, name=None):
    label = module._label(source, name)
    if not module._is_zip(source): raise ValueError(f"{label}: HWPX가 아니다(ZIP 컨테이너가 아님)")
    blocks = []
    with module.zipfile.ZipFile(module._zip_handle(source)) as zf:
        infos = _zip_guard(zf, label)
        sections = sorted((i for i in infos if module.re.match(r"Contents/section\d+\.[Xx][Mm][Ll]$", i.filename)), key=lambda i: module._section_number(i.filename))
        if not sections: raise ValueError(f"{label}: Contents/sectionN.xml을 찾지 못했다")
        total = 0
        for info in sections:
            total += info.file_size
            if info.file_size > MAX_HWPX_SECTION_BYTES or total > MAX_HWPX_TOTAL_XML_BYTES: raise ValueError(f"{label}: HWPX XML이 처리 상한을 넘는다")
            _hwpx_walk(module, _xml_guard(module, zf.read(info), info.filename), blocks)
    return blocks


def _read_documents(module, source):
    label = module._label(source)
    if not module._is_zip(source) or module._is_hwpx(source): return [{"file": module.os.path.basename(label), "blocks": module.read(source)}]
    documents = []
    with module.zipfile.ZipFile(module._zip_handle(source)) as zf:
        infos = _zip_guard(zf, label); members = [i for i in infos if not i.is_dir() and not i.filename.startswith("__MACOSX/") and i.filename.lower().endswith(module.ARCHIVE_EXTS)]
        if not members: raise ValueError(f"{label}: ZIP 안에 HWP/HWPX가 없다")
        if len(members) > module.MAX_ARCHIVE_DOCUMENTS: raise ValueError(f"{label}: ZIP 안 문서가 {module.MAX_ARCHIVE_DOCUMENTS}개를 넘는다")
        for info in members:
            if info.file_size > module.MAX_ARCHIVE_MEMBER_SIZE: documents.append({"file": info.filename, "error": "ZIP 멤버가 처리 상한을 넘는다"}); continue
            try: documents.append({"file": info.filename, "blocks": module.read(zf.read(info), name=info.filename)})
            except Exception as exc: documents.append({"file": info.filename, "error": str(exc)})
    return documents


def _render(module, blocks, fmt="text", tables_only=False):
    lines = []
    for block in blocks:
        kind = block.get("type")
        if kind == "memo": lines.append("[메모] " + block["text"])
        elif kind == "revision": lines.append(f"[변경추적 {'추가' if block['kind'] == 'insert' else '삭제'}] {block['text']}")
        elif kind == "note": lines.append(f"[{block.get('kind','주석')}{' ' + str(block['number']) if block.get('number') is not None else ''}] {block.get('text','')}".rstrip())
        elif kind == "hyperlink": lines.append(f"[하이퍼링크] {block.get('url','')}")
        elif kind == "image": lines.append(f"[이미지 · {block.get('name','참조')}]")
        elif kind == "textbox": lines.append(f"[글상자] {block.get('text','')}")
        elif kind == "header": lines.append(f"[머리말] {block.get('text','')}")
        elif kind == "footer": lines.append(f"[꼬리말] {block.get('text','')}")
        elif kind == "text" and not tables_only: lines.append(block["text"])
        elif kind == "table": module._render_table(block, fmt, lines)
    return "\n".join(lines)


def _render_documents(module, documents, fmt="md"):
    chunks = []
    for doc in documents:
        chunks.append(f"\n{'=' * 70}\n{doc['file']}\n{'=' * 70}\n")
        chunks.append("[실패] " + doc["error"] if doc.get("error") else module.render(doc.get("blocks", []), fmt))
    return "\n".join(chunks).strip()


def install(module):
    module._records = lambda data: _records_limited(module, data)
    module.read_hwp = lambda source, name=None: _read_hwp(module, source, name)
    module.read_hwpx = lambda source, name=None: _read_hwpx(module, source, name)
    module.read_documents = lambda source: _read_documents(module, source)
    module.render = lambda blocks, fmt="text", tables_only=False: _render(module, blocks, fmt, tables_only)
    module.render_documents = lambda documents, fmt="md": _render_documents(module, documents, fmt)
    return module

"""0.5 의미 복원 계층을 코어에 연결한다."""
import posixpath
import sys





sys.modules[__name__].OleFile = FallbackOleFile
install(sys.modules[__name__])

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

    decoder = sys.modules[__name__].zlib.decompressobj(-15)
    try:
        out = decoder.decompress(raw, limit + 1)
        if len(out) > limit or decoder.unconsumed_tail:
            raise ValueError(f"{name}: 압축 해제 결과가 처리 상한을 넘는다")
        out += decoder.flush(limit + 1 - len(out))
    except sys.modules[__name__].zlib.error as exc:
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
sys.modules[__name__]._read_stream = _bounded_read_stream
_reader_runtime._xml_guard = _guarded_xml
_reader_runtime._zip_guard = _guarded_zip

_single_base_read_hwp = sys.modules[__name__].read_hwp
_single_base_read_hwpx = sys.modules[__name__].read_hwpx
_single_base_render = sys.modules[__name__].render


def _single_validate_table(table, what="표"):
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
            _single_validate_table(child, what + " 안의 표")


def _single_validate_blocks(blocks):
    for block in blocks:
        if block.get("type") == "table":
            _single_validate_table(block)


def _single_post_read_hwp(source, name=None):
    blocks = _single_base_read_hwp(source, name=name)
    _single_validate_blocks(blocks)
    notes = current_compat_warnings()
    if notes:
        blocks.insert(0, {"type": "warning", "text": "비표준 CFB 호환 모드: " + "; ".join(notes)})
    return blocks


def _single_post_read_hwpx(source, name=None):
    blocks = _single_base_read_hwpx(source, name=name)
    _single_validate_blocks(blocks)
    return blocks


def _single_post_render(blocks, fmt="text", tables_only=False):
    visible = [
        {"type": "text", "text": "[경고] " + block.get("text", "")}
        if block.get("type") == "warning" else block
        for block in blocks
    ]
    return _single_base_render(visible, fmt, tables_only)


sys.modules[__name__].read_hwp = _single_post_read_hwp
sys.modules[__name__].read_hwpx = _single_post_read_hwpx
sys.modules[__name__].render = _single_post_render

if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try: _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError): pass
    if len(sys.argv) < 2:
        print("사용법: python hwp_reader_single.py 문서.hwp|문서.hwpx|묶음.zip [...]", file=sys.stderr)
        sys.exit(2)
    failed = False
    for index, path in enumerate(sys.argv[1:]):
        if index: print()
        try:
            print(render_documents(read_documents(path), "md"))
        except Exception as exc:
            failed = True
            print(f"[실패] {path}: {exc}", file=sys.stderr)
    sys.exit(1 if failed else 0)