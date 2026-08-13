"""0.5.0 실문서 의미 복원·보안 회귀시험."""

import io
import struct
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hwp_reader import parser  # noqa: E402
from hwp_reader._ole import ENDOFCHAIN, OleFile  # noqa: E402
from hwp_reader._ole_fallback import FallbackOleFile  # noqa: E402
from hwp_reader._parser_controls_text import decode_para  # noqa: E402
from hwp_reader._viewtext import aes128_ecb_decrypt  # noqa: E402
from make_ole import write_ole  # noqa: E402

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS = "http://www.hancom.co.kr/hwpml/2011/section"


def _hwpx(xml):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", xml)
    return buf.getvalue()


def test_AES128_표준_복호화_벡터():
    key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
    ciphertext = bytes.fromhex("3925841d02dc09fbdc118597196a0b32")
    expected = bytes.fromhex("3243f6a8885a308d313198a2e0370734")
    assert aes128_ecb_decrypt(ciphertext, key) == expected


def test_0_5_레코드_리더가_실제로_활성화된다():
    payload = b"A" * 3
    header = (parser.HWPTAG_PARA_TEXT | (len(payload) << 20)).to_bytes(4, "little")
    assert parser._records(header + payload) == [(parser.HWPTAG_PARA_TEXT, 0, payload)]


def test_HWP_제어문자_탭과_일반문자를_보존한다():
    tab = struct.pack("<H", 9) + b"\0" * 14
    payload = "앞".encode("utf-16-le") + tab + "뒤".encode("utf-16-le")
    assert decode_para(parser._core, [payload], []) == "앞\t뒤"


def test_CFB_strict가_FAT_자체표식_오류를_거부하고_호환모드는_제한복구한다(tmp_path):
    path = write_ole(tmp_path / "compat.ole", {"X": b"abc"})
    raw = bytearray(Path(path).read_bytes())
    fat_sid = struct.unpack_from("<I", raw, 0x4C)[0]
    fat_offset = 512 + fat_sid * 512
    struct.pack_into("<I", raw, fat_offset + fat_sid * 4, ENDOFCHAIN)

    with pytest.raises(ValueError, match="FATSECT"):
        OleFile(raw)
    recovered = FallbackOleFile(raw)
    assert recovered.compat_mode is True
    assert recovered.open("X") == b"abc"
    assert recovered.compat_warnings


def test_CFB_호환모드도_잘못된_byte_order는_복구하지_않는다(tmp_path):
    path = write_ole(tmp_path / "bad-order.ole", {"X": b"abc"})
    raw = bytearray(Path(path).read_bytes())
    struct.pack_into("<H", raw, 0x1C, 0xFEFF)
    with pytest.raises(ValueError, match="byte order"):
        FallbackOleFile(raw)


def test_HWPX_각주_수식_링크_이미지_참조를_함께_보존한다():
    xml = (
        f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}">'
        '<hp:p><hp:run><hp:t>본문 </hp:t>'
        '<hp:footNote><hp:p><hp:run><hp:t>각주 내용</hp:t></hp:run></hp:p></hp:footNote>'
        '<hp:equation><hp:script><hp:t>x+y</hp:t></hp:script></hp:equation>'
        '<hp:hyperlink href="https://example.com"><hp:t>링크</hp:t></hp:hyperlink>'
        '<hp:pic binaryItemIDRef="BIN0001"/>'
        '</hp:run></hp:p></hs:sec>'
    )
    blocks = parser.read(_hwpx(xml), name="meaning.hwpx")
    rendered = parser.render(blocks, "md")
    assert "본문" in rendered
    assert "[수식: x+y]" in rendered
    assert "[각주] 각주 내용" in rendered
    assert "[하이퍼링크] https://example.com" in rendered
    assert "[이미지 · BIN0001]" in rendered


def test_HWPX_변경추적_삭제구간은_최종본문에서_제외한다():
    xml = (
        f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}">'
        '<hp:p><hp:run><hp:deleteBegin/><hp:t>삭제할 문장</hp:t>'
        '<hp:deleteEnd/><hp:t>남길 문장</hp:t></hp:run></hp:p></hs:sec>'
    )
    rendered = parser.render(parser.read(_hwpx(xml), name="track.hwpx"))
    assert "남길 문장" in rendered
    assert "삭제할 문장" not in rendered


def test_HWPX_DTD_ENTITY는_파싱전에_거부한다():
    xml = (
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY boom "x">]>'
        f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}"><hp:p>'
        '<hp:run><hp:t>&boom;</hp:t></hp:run></hp:p></hs:sec>'
    )
    with pytest.raises(ValueError, match="DTD/ENTITY"):
        parser.read(_hwpx(xml), name="entity.hwpx")


def test_ZIP_중복경로를_거부한다():
    buf = io.BytesIO()
    with pytest.warns(UserWarning):
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("a.hwp", b"one")
            zf.writestr("a.hwp", b"two")
    with pytest.raises(ValueError, match="중복"):
        parser.read_documents(buf.getvalue())


def test_ZIP_한문서_실패가_다른문서_처리를_막지_않는다():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.hwp", b"not-hwp")
        zf.writestr("b.hwp", b"also-not-hwp")
    docs = parser.read_documents(buf.getvalue())
    assert [doc["file"] for doc in docs] == ["a.hwp", "b.hwp"]
    assert all("error" in doc for doc in docs)
    rendered = parser.render_documents(docs)
    assert "a.hwp" in rendered and "b.hwp" in rendered
    assert rendered.count("[실패]") == 2
