"""0.4.0 파싱 정확성·구조 보존 회귀시험."""

import io
import struct
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hwp_reader import parser  # noqa: E402
from hwp_reader._ole import (ENDOFCHAIN, FATSECT, FREESECT, NOSTREAM, OleFile)  # noqa: E402
from make_fixture import HP, HS  # noqa: E402
from make_ole import write_ole  # noqa: E402


def _u16(*codes):
    return b"".join(struct.pack("<H", code) for code in codes)


def _cell(col, row, colspan=1, rowspan=1):
    return (
        b"\0" * parser.CELL_OFFSET
        + struct.pack("<4H", col, row, colspan, rowspan)
    )


def _hwpx_bytes(xml):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", xml)
    return buf.getvalue()


def _minimal_v4_cfb():
    sector_size = 4096
    stream = b"A" * sector_size

    directory = bytearray(sector_size)

    def entry(offset, name, kind, child, start, size):
        raw_name = name.encode("utf-16-le") + b"\0\0"
        directory[offset:offset + len(raw_name)] = raw_name
        struct.pack_into(
            "<HBBIII",
            directory,
            offset + 0x40,
            len(raw_name),
            kind,
            1,
            NOSTREAM,
            NOSTREAM,
            child,
        )
        struct.pack_into("<I", directory, offset + 0x74, start)
        struct.pack_into("<Q", directory, offset + 0x78, size)

    entry(0, "Root Entry", 5, 1, ENDOFCHAIN, 0)
    entry(128, "X", 2, NOSTREAM, 0, len(stream))

    fat = [FREESECT] * (sector_size // 4)
    fat[0] = ENDOFCHAIN
    fat[1] = ENDOFCHAIN
    fat[2] = FATSECT
    fat_sector = struct.pack("<{}I".format(len(fat)), *fat)

    header = bytearray(sector_size)
    header[:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    struct.pack_into("<HHHHH", header, 0x18, 0x003E, 4, 0xFFFE, 12, 6)
    struct.pack_into("<I", header, 0x28, 1)
    struct.pack_into("<I", header, 0x2C, 1)
    struct.pack_into("<I", header, 0x30, 1)
    struct.pack_into("<I", header, 0x38, 4096)
    struct.pack_into("<I", header, 0x3C, ENDOFCHAIN)
    struct.pack_into("<I", header, 0x40, 0)
    struct.pack_into("<I", header, 0x44, ENDOFCHAIN)
    struct.pack_into("<I", header, 0x48, 0)
    difat = [2] + [FREESECT] * 108
    struct.pack_into("<109I", header, 0x4C, *difat)

    return bytes(header) + stream + bytes(directory) + fat_sector


def test_HWP_UTF16_홀수바이트는_실패한다():
    with pytest.raises(ValueError, match="홀수"):
        parser._decode_text(b"\x00")


def test_HWP_8워드_제어가_잘리면_실패한다():
    payload = _u16(ord("가"), 4) + b"\0" * 10
    with pytest.raises(ValueError, match="8워드"):
        parser._decode_text(payload)


def test_HWP_잘못된_UTF16을_대체문자로_숨기지_않는다():
    with pytest.raises(ValueError, match="UTF-16LE"):
        parser._decode_text(b"\x00\xd8")


def test_HWP_압축플래그가_켜졌는데_DEFLATE가_깨지면_raw로_되돌리지_않는다():
    class FakeOle:
        def open(self, _):
            return b"not-deflate"

    with pytest.raises(ValueError, match="압축"):
        parser._read_stream(FakeOle(), "BodyText/Section0", True)


def test_표의_빈행을_삭제하지_않는다():
    cells = [
        {"row": 0, "col": 0, "rowspan": 1, "colspan": 1, "text": "위"},
        {"row": 2, "col": 0, "rowspan": 1, "colspan": 1, "text": "아래"},
    ]
    assert parser._grid(cells, 3, 1) == [["위"], [""], ["아래"]]


def test_HWP_span이_0이면_실패한다():
    records = [
        (
            parser.HWPTAG_TABLE,
            1,
            b"\0" * 4 + struct.pack("<HH", 1, 1),
        ),
        (parser.HWPTAG_LIST_HEADER, 1, _cell(0, 0, colspan=0)),
    ]
    with pytest.raises(ValueError, match="0 이하"):
        parser._parse_table(records, 0)


def test_HWP_셀이_선언격자밖으로_나가면_실패한다():
    records = [
        (
            parser.HWPTAG_TABLE,
            1,
            b"\0" * 4 + struct.pack("<HH", 1, 1),
        ),
        (parser.HWPTAG_LIST_HEADER, 1, _cell(1, 0)),
        (
            parser.HWPTAG_PARA_TEXT,
            2,
            "밖".encode("utf-16-le"),
        ),
    ]
    with pytest.raises(ValueError, match="격자를 벗어난다"):
        parser._parse_table(records, 0)


def test_같은_셀시작점이_중복되면_실패한다():
    cells = [
        {"row": 0, "col": 0, "rowspan": 1, "colspan": 1, "text": "A"},
        {"row": 0, "col": 0, "rowspan": 1, "colspan": 1, "text": "B"},
    ]
    with pytest.raises(ValueError, match="중복"):
        parser._grid(cells, 1, 1)


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("rowCnt", "x"),
        ("colCnt", "1.5"),
    ],
)
def test_HWPX_표크기_속성이_정수가_아니면_실패한다(attribute, value):
    attrs = {"rowCnt": "1", "colCnt": "1"}
    attrs[attribute] = value
    xml = (
        f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}">'
        f'<hp:tbl rowCnt="{attrs["rowCnt"]}" colCnt="{attrs["colCnt"]}"/>'
        "</hs:sec>"
    )
    with pytest.raises(ValueError, match="정수가 아니다"):
        parser.read(_hwpx_bytes(xml), name="bad.hwpx")


def test_HWPX_span이_0이면_1로_조용히_보정하지_않는다():
    xml = (
        f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}">'
        '<hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
        '<hp:cellAddr rowAddr="0" colAddr="0"/>'
        '<hp:cellSpan rowSpan="0" colSpan="1"/>'
        '<hp:subList><hp:p><hp:run><hp:t>X</hp:t></hp:run></hp:p></hp:subList>'
        "</hp:tc></hp:tr></hp:tbl></hs:sec>"
    )
    with pytest.raises(ValueError, match="0 이하"):
        parser.read(_hwpx_bytes(xml), name="span.hwpx")


def test_HWPX_셀주소가_행열중_하나만_있으면_실패한다():
    xml = (
        f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}">'
        '<hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
        '<hp:cellAddr rowAddr="0"/>'
        '<hp:cellSpan rowSpan="1" colSpan="1"/>'
        '<hp:subList><hp:p><hp:run><hp:t>X</hp:t></hp:run></hp:p></hp:subList>'
        "</hp:tc></hp:tr></hp:tbl></hs:sec>"
    )
    with pytest.raises(ValueError, match="하나만"):
        parser.read(_hwpx_bytes(xml), name="half-address.hwpx")


def test_HWPX_셀범위가_선언된_표크기를_넘으면_실패한다():
    xml = (
        f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}">'
        '<hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
        '<hp:cellAddr rowAddr="0" colAddr="0"/>'
        '<hp:cellSpan rowSpan="1" colSpan="2"/>'
        '<hp:subList><hp:p><hp:run><hp:t>X</hp:t></hp:run></hp:p></hp:subList>'
        "</hp:tc></hp:tr></hp:tbl></hs:sec>"
    )
    with pytest.raises(ValueError, match="colCnt"):
        parser.read(_hwpx_bytes(xml), name="size-mismatch.hwpx")


def test_CFB_v4는_4096바이트_헤더뒤에서_sector0을_읽는다():
    ole = OleFile(_minimal_v4_cfb())
    assert ole.open("X") == b"A" * 4096


def test_CFB_byte_order가_틀리면_거부한다(tmp_path):
    path = write_ole(tmp_path / "x.ole", {"X": b"abc"})
    raw = bytearray(Path(path).read_bytes())
    struct.pack_into("<H", raw, 0x1C, 0xFEFF)
    with pytest.raises(ValueError, match="byte order"):
        OleFile(raw)


def test_CFB_v3_StreamSize_high_DWORD의_쓰레기값을_무시한다(tmp_path):
    path = write_ole(tmp_path / "x.ole", {"X": b"abc"})
    raw = bytearray(Path(path).read_bytes())
    directory_sid = struct.unpack_from("<I", raw, 0x30)[0]
    directory = 512 + directory_sid * 512
    stream_entry = directory + 128
    struct.pack_into("<I", raw, stream_entry + 0x7C, 0xFFFFFFFF)
    assert OleFile(raw).open("X") == b"abc"


def test_CFB_파일끝에_반쪽_sector가_붙으면_거부한다(tmp_path):
    path = write_ole(tmp_path / "x.ole", {"X": b"abc"})
    raw = Path(path).read_bytes() + b"x"
    with pytest.raises(ValueError, match="배수"):
        OleFile(raw)
