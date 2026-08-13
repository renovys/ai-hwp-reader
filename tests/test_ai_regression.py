"""AI 입력 품질에 직접 영향을 주는 추가 회귀 시험."""

import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwp_reader import parser  # noqa: E402
from make_fixture import HP, HS  # noqa: E402


def test_HWP_FileHeader_시그니처와_플래그를_검증한다():
    head = bytearray(parser.HWP_SIGNATURE + b"\0" * (37 - len(parser.HWP_SIGNATURE)))
    head[36] = 0x03
    assert parser._hwp_flags(bytes(head), "x.hwp") == (True, True)
    with pytest.raises(ValueError, match="시그니처"):
        parser._hwp_flags(b"X" * 37, "x.hwp")


def test_비정상적으로_큰_표는_메모리를_할당하기_전에_막는다():
    parser._validate_table_shape(1000, 1000)
    with pytest.raises(ValueError, match="비정상적으로 크다"):
        parser._validate_table_shape(1001, 1000)


def test_HWP_LIST_HEADER가_잘리면_명시적으로_실패한다():
    records = [
        (parser.HWPTAG_TABLE, 1, b"\0" * 4 + b"\x01\0\x01\0"),
        (parser.HWPTAG_LIST_HEADER, 1, b"123"),
    ]
    with pytest.raises(ValueError, match="LIST_HEADER"):
        parser._parse_table(records, 0)


def test_HWPX_중첩표를_부모셀위치와_별도구조로_보존한다(tmp_path):
    inner = (
        '<hp:tbl rowCnt="1" colCnt="2"><hp:tr>'
        '<hp:tc><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        '<hp:subList><hp:p><hp:run><hp:t>A</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
        '<hp:tc><hp:cellAddr colAddr="1" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        '<hp:subList><hp:p><hp:run><hp:t>B</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
        '</hp:tr></hp:tbl>'
    )
    outer = (
        '<hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
        '<hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        '<hp:subList><hp:p><hp:run><hp:t>앞</hp:t>' + inner +
        '<hp:t>뒤</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl>'
    )
    xml = f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}"><hp:p><hp:run>{outer}</hp:run></hp:p></hs:sec>'
    path = tmp_path / "nested.hwpx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Contents/section0.xml", xml)

    table = next(b for b in parser.read(path) if b["type"] == "table")
    assert table["grid"][0][0] == "앞뒤 ⟨표 안의 표⟩"
    nested = table["nested_tables"][0]
    assert (nested["row"], nested["col"]) == (0, 0)
    assert nested["table"]["grid"] == [["A", "B"]]
    output = parser.render([table], "md")
    assert "[표 안의 표 · 1행 1열]" in output
    assert "A" in output and "B" in output


def test_HWPX_음수_셀주소는_조용히_보정하지_않는다(tmp_path):
    xml = (
        f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}"><hp:tbl rowCnt="1" colCnt="1"><hp:tr>'
        '<hp:tc><hp:cellAddr colAddr="-1" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        '<hp:subList><hp:p><hp:run><hp:t>X</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
        '</hp:tr></hp:tbl></hs:sec>'
    )
    path = tmp_path / "negative.hwpx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Contents/section0.xml", xml)
    with pytest.raises(ValueError, match="셀 주소가 음수"):
        parser.read(path)


def test_손상된_HWPX_XML은_어느_섹션인지_알린다(tmp_path):
    path = tmp_path / "broken.hwpx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Contents/section3.xml", "<broken>")
    with pytest.raises(ValueError, match="section3.xml"):
        parser.read(path)


def test_HWPX_섹션확장자_대소문자가_달라도_숫자순서로_읽는다(tmp_path):
    path = tmp_path / "upper.hwpx"
    def xml(text):
        return (f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}">'
                f'<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p></hs:sec>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Contents/section10.XML", xml("열"))
        z.writestr("Contents/section2.xml", xml("둘"))
    assert [b["text"] for b in parser.read(path)] == ["둘", "열"]
