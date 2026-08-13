"""0.5 최종 자원상한 회귀시험."""

import io
import zlib
import zipfile

import pytest

from hwp_reader import parser
from hwp_reader import _v05_enable


class _FakeOle:
    def __init__(self, payload):
        self.payload = payload

    def open(self, _name):
        return self.payload


def _raw_deflate(data):
    encoder = zlib.compressobj(level=9, wbits=-15)
    return encoder.compress(data) + encoder.flush()


def _hwpx(xml):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", xml)
    return buf.getvalue()


def test_패키지_읽기경로도_DEFLATE_출력상한을_적용한다(monkeypatch):
    payload = _raw_deflate(b"A" * 256)
    monkeypatch.setattr(_v05_enable._reader_runtime, "MAX_HWP_STREAM_BYTES", 64)
    with pytest.raises(ValueError, match="상한"):
        parser._core._read_stream(_FakeOle(payload), "BodyText/Section0", True)


def test_DTD가_64KiB_뒤에_있어도_XML_파싱전에_거부한다():
    xml = " " * 70_000 + '<!DOCTYPE x [<!ENTITY boom "x">]><sec><p><t>&boom;</t></p></sec>'
    with pytest.raises(ValueError, match="DTD/ENTITY"):
        parser.read(_hwpx(xml), name="late-doctype.hwpx")


def test_ZIP_멤버수_상한을_적용한다(monkeypatch):
    monkeypatch.setattr(_v05_enable, "_MAX_ZIP_MEMBERS", 2)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.hwp", b"x")
        zf.writestr("b.hwp", b"x")
        zf.writestr("c.hwp", b"x")
    with pytest.raises(ValueError, match="ZIP 멤버"):
        parser.read_documents(buf.getvalue())


def test_ZIP_정규화_중복경로와_상위경로를_거부한다():
    duplicate = io.BytesIO()
    with zipfile.ZipFile(duplicate, "w") as zf:
        zf.writestr("dir/a.hwp", b"x")
        zf.writestr("dir/./a.hwp", b"x")
    with pytest.raises(ValueError, match="중복"):
        parser.read_documents(duplicate.getvalue())

    traversal = io.BytesIO()
    with zipfile.ZipFile(traversal, "w") as zf:
        zf.writestr("../a.hwp", b"x")
    with pytest.raises(ValueError, match="비정상 ZIP 경로"):
        parser.read_documents(traversal.getvalue())
