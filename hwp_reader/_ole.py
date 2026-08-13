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
