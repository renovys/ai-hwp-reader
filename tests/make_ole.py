"""시험용 CFB/OLE 파일을 표준 라이브러리만으로 만든다."""

import math
import struct
from pathlib import Path


SECTOR_SIZE = 512
MINI_SECTOR_SIZE = 64
MINI_CUTOFF = 4096
FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
DIFSECT = 0xFFFFFFFC
NOSTREAM = 0xFFFFFFFF


def _sector_count(size):
    return max(1, (size + SECTOR_SIZE - 1) // SECTOR_SIZE) if size else 0


def _mini_sector_count(size):
    return (size + MINI_SECTOR_SIZE - 1) // MINI_SECTOR_SIZE if size else 0


def _allocate(sectors, data):
    start = len(sectors)
    for offset in range(0, len(data), SECTOR_SIZE):
        chunk = data[offset:offset + SECTOR_SIZE]
        sectors.append(chunk.ljust(SECTOR_SIZE, b"\0"))
    return start if data else ENDOFCHAIN


def _link(fat, start, count):
    if count == 0:
        return ENDOFCHAIN
    for index in range(count):
        sid = start + index
        fat[sid] = ENDOFCHAIN if index + 1 == count else sid + 1
    return start


def _balanced_tree(paths, entries, path_to_index):
    if not paths:
        return NOSTREAM
    middle = len(paths) // 2
    path = paths[middle]
    index = path_to_index[path]
    entries[index]["left"] = _balanced_tree(paths[:middle], entries,
                                               path_to_index)
    entries[index]["right"] = _balanced_tree(paths[middle + 1:], entries,
                                                path_to_index)
    return index


def _directory_bytes(entries):
    raw = bytearray(len(entries) * 128)
    for index, entry in enumerate(entries):
        name = entry["name"].encode("utf-16-le") + b"\0\0"
        if len(name) > 64:
            raise ValueError("시험용 OLE 이름이 31자를 넘었다")
        chunk = bytearray(128)
        chunk[:len(name)] = name
        struct.pack_into("<HBBIII", chunk, 0x40,
                         len(name), entry["type"], 0,
                         entry["left"], entry["right"], entry["child"])
        struct.pack_into("<I", chunk, 0x60, 0)
        struct.pack_into("<QQ", chunk, 0x64, 0, 0)
        struct.pack_into("<I", chunk, 0x74, entry["start"])
        struct.pack_into("<Q", chunk, 0x78, entry["size"])
        raw[index * 128:(index + 1) * 128] = chunk
    return bytes(raw)


def _make_header(num_fat, directory_start, mini_fat_start, num_mini_fat,
                 difat_start, num_difat, fat_sectors):
    header = bytearray(512)
    header[:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    struct.pack_into("<HHHHH", header, 0x18, 0x003E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<I", header, 0x28, 0)              # v3 directory count
    struct.pack_into("<I", header, 0x2C, num_fat)
    struct.pack_into("<I", header, 0x30, directory_start)
    struct.pack_into("<I", header, 0x34, 0)
    struct.pack_into("<I", header, 0x38, MINI_CUTOFF)
    struct.pack_into("<I", header, 0x3C, mini_fat_start)
    struct.pack_into("<I", header, 0x40, num_mini_fat)
    struct.pack_into("<I", header, 0x44, difat_start)
    struct.pack_into("<I", header, 0x48, num_difat)
    difat = list(fat_sectors[:109]) + [FREESECT] * (109 - len(fat_sectors[:109]))
    struct.pack_into("<109I", header, 0x4C, *difat)
    return bytes(header)


def write_ole(path, streams):
    """`이름/경로: 바이트` 사전으로 작은 CFB 파일을 만든다."""
    output_path = Path(path)
    streams = dict(streams)
    if not streams:
        raise ValueError("시험용 OLE 스트림이 없다")
    for name, data in streams.items():
        if not name or name.startswith("/") or "//" in name:
            raise ValueError("시험용 OLE 스트림 경로가 잘못됐다")
        if not isinstance(data, bytes):
            raise TypeError("시험용 OLE 스트림은 바이트여야 한다")

    storage_paths = set()
    for name in streams:
        parts = name.split("/")
        for stop in range(1, len(parts)):
            storage_paths.add("/".join(parts[:stop]))
    if storage_paths & set(streams):
        raise ValueError("시험용 OLE에서 저장소와 스트림 이름이 겹친다")

    entries = [{
        "name": "Root Entry", "path": "", "type": 5,
        "left": NOSTREAM, "right": NOSTREAM, "child": NOSTREAM,
        "start": ENDOFCHAIN, "size": 0,
    }]
    path_to_index = {"": 0}
    for path in sorted(storage_paths, key=lambda value: (value.count("/"), value)):
        path_to_index[path] = len(entries)
        entries.append({
            "name": path.rsplit("/", 1)[-1], "path": path, "type": 1,
            "left": NOSTREAM, "right": NOSTREAM, "child": NOSTREAM,
            "start": ENDOFCHAIN, "size": 0,
        })
    for path in sorted(streams):
        path_to_index[path] = len(entries)
        entries.append({
            "name": path.rsplit("/", 1)[-1], "path": path, "type": 2,
            "left": NOSTREAM, "right": NOSTREAM, "child": NOSTREAM,
            "start": ENDOFCHAIN, "size": len(streams[path]),
        })

    children = {path: [] for path in ("", *storage_paths)}
    for path in list(storage_paths) + list(streams):
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        children[parent].append(path)
    for parent, child_paths in children.items():
        direct = sorted(child_paths, key=lambda value: value.rsplit("/", 1)[-1])
        entries[path_to_index[parent]]["child"] = _balanced_tree(
            direct, entries, path_to_index)

    sectors = []
    mini_fat = []
    mini_data = bytearray()
    for path in sorted(streams):
        entry = entries[path_to_index[path]]
        data = streams[path]
        if len(data) < MINI_CUTOFF:
            count = _mini_sector_count(len(data))
            entry["start"] = len(mini_fat) if count else ENDOFCHAIN
            mini_data.extend(data.ljust(count * MINI_SECTOR_SIZE, b"\0"))
            for index in range(count):
                mini_fat.append(ENDOFCHAIN if index + 1 == count
                                else len(mini_fat) + 1)
        else:
            count = _sector_count(len(data))
            entry["start"] = _allocate(sectors, data)
            _link_placeholder = count
            entry["_regular_count"] = _link_placeholder

    root = entries[0]
    if mini_data:
        root["start"] = _allocate(sectors, bytes(mini_data))
        root["size"] = len(mini_data)
        root["_mini_count"] = _sector_count(len(mini_data))
    else:
        root["start"] = ENDOFCHAIN
        root["size"] = 0
        root["_mini_count"] = 0

    directory_count = max(1, math.ceil(len(entries) * 128 / SECTOR_SIZE))
    directory_start = _allocate(sectors, b"\0" * (directory_count * SECTOR_SIZE))

    mini_fat_start = ENDOFCHAIN
    mini_fat_count = 0
    if mini_fat:
        mini_fat_count = math.ceil(len(mini_fat) * 4 / SECTOR_SIZE)
        mini_fat_raw = struct.pack("<{}I".format(mini_fat_count * SECTOR_SIZE // 4),
                                   *(mini_fat + [FREESECT] *
                                     (mini_fat_count * SECTOR_SIZE // 4 - len(mini_fat))))
        mini_fat_start = _allocate(sectors, mini_fat_raw)

    nonfat_count = len(sectors)
    fat_count = 0
    difat_count = 0
    for _ in range(20):
        new_fat_count = math.ceil((nonfat_count + fat_count + difat_count) /
                                  (SECTOR_SIZE // 4))
        new_difat_count = max(0, math.ceil((new_fat_count - 109) /
                                           (SECTOR_SIZE // 4 - 1)))
        if (new_fat_count, new_difat_count) == (fat_count, difat_count):
            break
        fat_count, difat_count = new_fat_count, new_difat_count
    else:
        raise AssertionError("시험용 OLE FAT 크기 계산이 수렴하지 않았다")

    fat_start = len(sectors)
    sectors.extend([b"\0" * SECTOR_SIZE] * fat_count)
    difat_start = len(sectors) if difat_count else ENDOFCHAIN
    sectors.extend([b"\0" * SECTOR_SIZE] * difat_count)
    total_sectors = len(sectors)
    fat = [FREESECT] * (fat_count * (SECTOR_SIZE // 4))

    # 일반 스트림과 메타데이터 스트림의 FAT 체인을 표시한다.
    for path in streams:
        entry = entries[path_to_index[path]]
        if entry["size"] >= MINI_CUTOFF:
            _link(fat, entry["start"], entry["_regular_count"])
        entry.pop("_regular_count", None)
    if root["size"]:
        _link(fat, root["start"], root["_mini_count"])
    _link(fat, directory_start, directory_count)
    if mini_fat_count:
        _link(fat, mini_fat_start, mini_fat_count)

    fat_sector_ids = list(range(fat_start, fat_start + fat_count))
    for sid in fat_sector_ids:
        fat[sid] = FATSECT
    difat_sector_ids = list(range(difat_start, difat_start + difat_count)) \
        if difat_count else []
    for sid in difat_sector_ids:
        fat[sid] = DIFSECT

    if total_sectors > len(fat):
        raise AssertionError("시험용 OLE FAT가 전체 섹터를 담지 못했다")
    fat_raw = struct.pack("<{}I".format(fat_count * SECTOR_SIZE // 4), *fat)
    for index, sid in enumerate(fat_sector_ids):
        start = index * SECTOR_SIZE
        sectors[sid] = fat_raw[start:start + SECTOR_SIZE]

    for index, sid in enumerate(difat_sector_ids):
        values = fat_sector_ids[109 + index * (SECTOR_SIZE // 4 - 1):
                                109 + (index + 1) * (SECTOR_SIZE // 4 - 1)]
        values = values + [FREESECT] * (SECTOR_SIZE // 4 - 1 - len(values))
        next_sid = (difat_sector_ids[index + 1]
                    if index + 1 < len(difat_sector_ids) else ENDOFCHAIN)
        sectors[sid] = struct.pack("<{}I".format(SECTOR_SIZE // 4),
                                    *(values + [next_sid]))

    directory_raw = _directory_bytes(entries).ljust(
        directory_count * SECTOR_SIZE, b"\0")
    sectors[directory_start:directory_start + directory_count] = [
        directory_raw[offset:offset + SECTOR_SIZE]
        for offset in range(0, len(directory_raw), SECTOR_SIZE)
    ]

    header = _make_header(fat_count, directory_start, mini_fat_start,
                          mini_fat_count, difat_start, difat_count,
                          fat_sector_ids)
    output = header + b"".join(sectors)
    output_path.write_bytes(output)
    return str(output_path)


def hwp_records(parser):
    """표가 하나 있는 HWP 본문 레코드를 만든다."""
    def rec(tag, level, payload):
        if len(payload) >= 0xFFF:
            return (struct.pack("<II", tag | (level << 10) | (0xFFF << 20),
                                len(payload)) + payload)
        return struct.pack("<I", tag | (level << 10) | (len(payload) << 20)) + payload

    def cell(col, row, text):
        body = b"\0" * parser.CELL_OFFSET + struct.pack("<4H", col, row, 1, 1)
        return rec(parser.HWPTAG_LIST_HEADER, 1, body) + rec(
            parser.HWPTAG_PARA_TEXT, 2, text.encode("utf-16-le"))

    table = (b"\0" * 4 + struct.pack("<HH", 2, 2) + b"")
    body = (rec(parser.HWPTAG_PARA_TEXT, 0, "OLE 시험 문서".encode("utf-16-le"))
            + rec(parser.HWPTAG_TABLE, 1, table)
            + cell(0, 0, "품목") + cell(1, 0, "금액")
            + cell(0, 1, "의자") + cell(1, 1, "180,000")
            + rec(parser.HWPTAG_CTRL_HEADER, 0, b"ctrl")
            + rec(parser.HWPTAG_PARA_TEXT, 0, "끝".encode("utf-16-le")))
    return body


def write_hwp(path, parser, large=True):
    """FileHeader와 BodyText/Section0이 있는 시험용 HWP를 쓴다."""
    header = bytearray(256)
    if large:
        records = hwp_records(parser)
        # 유효한 PARA_TEXT 레코드로 4096바이트를 넘겨 일반 FAT도 함께 탄다.
        filler = "가나다라마바사아자차카타파하" * 180
        records += struct.pack(
            "<I", parser.HWPTAG_PARA_TEXT | (0xFFF << 20))
        records += struct.pack("<I", len(filler.encode("utf-16-le")))
        records += filler.encode("utf-16-le")
    else:
        records = hwp_records(parser)
    return write_ole(path, {"FileHeader": bytes(header),
                            "BodyText/Section0": records})
