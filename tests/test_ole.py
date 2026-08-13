"""표준 라이브러리 CFB 리더 시험."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hwp_reader import parser                         # noqa: E402
from hwp_reader._ole import OleFile                 # noqa: E402
from make_ole import hwp_records, write_hwp, write_ole  # noqa: E402


@pytest.fixture()
def 시험용_hwp(tmp_path):
    """CFB의 mini FAT와 일반 FAT 경로를 함께 타기 위한 컨테이너 fixture."""
    return write_hwp(tmp_path / "시험.hwp", parser, large=True)


@pytest.fixture()
def 파서용_hwp(tmp_path):
    """실제 HWP FileHeader 시그니처를 가진 최소 HWP 5.0 fixture."""
    header = bytearray(256)
    header[:len(parser.HWP_SIGNATURE)] = parser.HWP_SIGNATURE
    return write_ole(
        tmp_path / "파서시험.hwp",
        {
            "FileHeader": bytes(header),
            "BodyText/Section0": hwp_records(parser),
        },
    )


def test_작은_스트림과_큰_스트림을_각각_읽는다(시험용_hwp):
    ole = OleFile(시험용_hwp)
    assert ole.exists("FileHeader")
    assert ole.exists("BodyText/Section0")
    assert len(ole.open("FileHeader")) < 4096
    assert len(ole.open("BodyText/Section0")) > 4096
    assert ole.open("BodyText/Section0") == OleFile(
        Path(시험용_hwp).read_bytes()).open("BodyText/Section0")


def test_olefile과_우리_리더가_모든_스트림_바이트를_같게_읽는다(시험용_hwp):
    reference = pytest.importorskip("olefile").OleFileIO(시험용_hwp)
    try:
        expected_names = sorted("/".join(parts) for parts in reference.listdir())
        ours = OleFile(시험용_hwp)
        assert ours.listdir() == expected_names
        for name in expected_names:
            assert ours.open(name) == reference.openstream(name.split("/")).read()
    finally:
        reference.close()


def test_hwp_파서가_실제_시그니처_fixture의_표를_끝까지_읽는다(파서용_hwp):
    blocks = parser.read_hwp(파서용_hwp)
    table = next(block for block in blocks if block["type"] == "table")
    assert blocks[0] == {"type": "text", "text": "OLE 시험 문서"}
    assert table["grid"] == [["품목", "금액"], ["의자", "180,000"]]
    assert any(block.get("text") == "끝" for block in blocks)
