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
