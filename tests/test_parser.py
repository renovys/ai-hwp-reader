"""파서 회귀 시험.

여기 담긴 시험은 `docs/hwp-format.md`에 적어 둔 파싱 함정에 대응한다.
고장 나면 "그럴듯해 보이는데 틀린 결과"가 나오는 자리들이다.
"""

import struct
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwp_reader import parser, read, render          # noqa: E402
from make_fixture import HP, HS, write_hwpx          # noqa: E402


def _rec(tag, level, payload):
    if len(payload) >= 0xFFF:
        head = tag | (level << 10) | (0xFFF << 20)
        return struct.pack("<II", head, len(payload)) + payload
    return struct.pack("<I", tag | (level << 10) | (len(payload) << 20)) + payload


def test_레코드_헤더를_태그_레벨_크기로_쪼갠다():
    data = _rec(parser.HWPTAG_PARA_TEXT, 2, b"ab") + _rec(parser.HWPTAG_TABLE, 1, b"cd")
    assert parser._records(data) == [
        (parser.HWPTAG_PARA_TEXT, 2, b"ab"),
        (parser.HWPTAG_TABLE, 1, b"cd"),
    ]


def test_크기가_0xFFF면_뒤_4바이트가_진짜_크기다():
    payload = b"x" * 0x2000
    assert parser._records(_rec(parser.HWPTAG_PARA_TEXT, 0, payload)) == [
        (parser.HWPTAG_PARA_TEXT, 0, payload)
    ]


def test_잘린_레코드를_조용히_삼키지_않는다():
    with pytest.raises(ValueError, match="payload"):
        parser._records(_rec(parser.HWPTAG_PARA_TEXT, 0, b"abcd")[:-1])
    with pytest.raises(ValueError, match="헤더"):
        parser._records(b"\x00\x01")


def _u16(*codes):
    return b"".join(struct.pack("<H", c) for c in codes)


def test_넓은_제어문자는_16바이트를_건너뛴다():
    payload = (_u16(ord("가"))
               + _u16(4) + b"\xff" * 14
               + _u16(ord("나")))
    assert parser._decode_text(payload) == "가나"


def test_좁은_제어문자는_공백_한_칸이_된다():
    assert parser._decode_text(_u16(ord("가"), 13, ord("나"))) == "가 나"


def test_남은_C0_제어문자도_공백으로_정리한다():
    assert parser._decode_text(_u16(ord("가"), 31, ord("나"))) == "가 나"


def test_서로게이트_쌍이_깨지지_않는다():
    payload = "가𝕏나".encode("utf-16-le")
    assert parser._decode_text(payload) == "가𝕏나"


def _cell(col, row, colspan=1, rowspan=1):
    return b"\x00" * parser.CELL_OFFSET + struct.pack("<4H", col, row, colspan, rowspan)


def test_셀_좌표는_오프셋_8부터_읽는다():
    records = [
        (parser.HWPTAG_TABLE, 1, b"\x00" * 4 + struct.pack("<HH", 2, 2)),
        (parser.HWPTAG_LIST_HEADER, 1, _cell(0, 0)),
        (parser.HWPTAG_PARA_TEXT, 2, "품목".encode("utf-16-le")),
        (parser.HWPTAG_LIST_HEADER, 1, _cell(1, 0)),
        (parser.HWPTAG_PARA_TEXT, 2, "금액".encode("utf-16-le")),
        (parser.HWPTAG_LIST_HEADER, 1, _cell(0, 1)),
        (parser.HWPTAG_PARA_TEXT, 2, "의자".encode("utf-16-le")),
        (parser.HWPTAG_LIST_HEADER, 1, _cell(1, 1)),
        (parser.HWPTAG_PARA_TEXT, 2, "180,000".encode("utf-16-le")),
    ]
    table, _ = parser._parse_table(records, 0)
    assert table["grid"] == [["품목", "금액"], ["의자", "180,000"]]
    assert {(c["row"], c["col"]) for c in table["cells"]} == {(0, 0), (0, 1), (1, 0), (1, 1)}


def test_병합_수를_그대로_들고_온다():
    records = [
        (parser.HWPTAG_TABLE, 1, b"\x00" * 4 + struct.pack("<HH", 2, 4)),
        (parser.HWPTAG_LIST_HEADER, 1, _cell(0, 0, colspan=2, rowspan=1)),
        (parser.HWPTAG_PARA_TEXT, 2, "단가".encode("utf-16-le")),
    ]
    table, _ = parser._parse_table(records, 0)
    assert table["cells"][0]["colspan"] == 2


def test_잘린_TABLE_payload는_명시적으로_실패한다():
    with pytest.raises(ValueError, match="TABLE payload"):
        parser._parse_table([(parser.HWPTAG_TABLE, 1, b"1234567")], 0)


@pytest.fixture()
def 예산서(tmp_path):
    return write_hwpx(tmp_path / "예산서.hwpx")


def test_병합_헤더에서_열이_밀리지_않는다(예산서):
    table = next(b for b in read(예산서) if b["type"] == "table")
    assert table["cols"] == 7
    assert table["grid"][1] == ["품목", "규격", "수량", "단가", "", "금액", ""]
    assert table["grid"][2] == ["", "", "", "정가", "할인가", "공급가", "부가세"]
    assert table["grid"][3][5] == "1,944,000"


def test_주소가_없는_문서는_병합_수로_자리를_잡는다(tmp_path):
    path = write_hwpx(tmp_path / "주소없음.hwpx", addr=False)
    table = next(b for b in read(path) if b["type"] == "table")
    assert table["grid"][2] == ["", "", "", "정가", "할인가", "공급가", "부가세"]


def test_표_안_글자가_본문으로_다시_나오지_않는다(예산서):
    texts = [b["text"] for b in read(예산서) if b["type"] == "text"]
    assert texts == ["◎ 예산 집행 내역", "이상."]


def test_숨은_메모를_뽑아낸다(예산서):
    memos = [b["text"] for b in read(예산서) if b["type"] == "memo"]
    assert memos == ["최신 자료 기준으로 업데이트해주세요."]


def test_문서_순서를_지킨다(예산서):
    assert [b["type"] for b in read(예산서)] == ["text", "table", "text", "memo"]


def test_섹션_번호를_숫자로_정렬한다(tmp_path):
    path = tmp_path / "여러섹션.hwpx"
    def xml(text):
        return (f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}">'
                f'<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p></hs:sec>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Contents/section10.xml", xml("열"))
        z.writestr("Contents/section2.xml", xml("둘"))
        z.writestr("Contents/section0.xml", xml("영"))
    assert [b["text"] for b in read(path)] == ["영", "둘", "열"]


def test_문단_안_메모가_앞뒤_본문을_중복시키지_않는다(tmp_path):
    path = tmp_path / "문단메모.hwpx"
    xml = (f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}"><hp:p><hp:run>'
           '<hp:t>앞</hp:t><hp:memo><hp:p><hp:run><hp:t>검토</hp:t></hp:run></hp:p></hp:memo>'
           '<hp:t>뒤</hp:t></hp:run></hp:p></hs:sec>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Contents/section0.xml", xml)
    assert read(path) == [
        {"type": "text", "text": "앞"},
        {"type": "memo", "text": "검토"},
        {"type": "text", "text": "뒤"},
    ]


def test_마크다운_표는_열_수가_모든_줄에서_같다(예산서):
    lines = [l for l in render(read(예산서), "md").splitlines() if l.startswith("|")]
    assert len({l.count("|") for l in lines}) == 1


def test_마크다운_셀의_파이프를_이스케이프한다():
    blocks = [{"type": "table", "grid": [["조건", "값"], ["A|B", "1"]]}]
    assert "A\\|B" in render(blocks, "md")


def test_확장자가_틀려도_내용을_보고_읽는다(tmp_path):
    path = write_hwpx(tmp_path / "잘못된확장자.hwp")
    assert any(b["type"] == "table" for b in read(path))


def test_암호_문서는_이유를_밝히고_멈춘다(tmp_path):
    path = tmp_path / "빈파일.hwp"
    path.write_bytes(b"not an ole file")
    with pytest.raises(Exception):
        read(str(path))
