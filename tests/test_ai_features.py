"""AI HWP Reader의 사용자 경로와 신규 구조 보존 회귀시험."""

import io
import struct
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwp_reader import read, read_documents, render, render_documents  # noqa: E402
from hwp_reader import parser  # noqa: E402
from make_fixture import HP, HS, write_hwpx  # noqa: E402


def test_변경추적_추가와_삭제를_ViewText_range에서_읽는다():
    text = "가나다라마바사".encode("utf-16-le")
    ranges = (
        struct.pack("<III", 1, 2, (parser.TRACK_DELETE << 24) | 7)
        + struct.pack("<III", 3, 4, (parser.TRACK_INSERT << 24) | 8)
    )
    records = [
        (parser.HWPTAG_PARA_TEXT, 0, text),
        (parser.HWPTAG_PARA_RANGE_TAG, 0, ranges),
    ]
    changes = parser._parse_change_ranges(records, section=2)
    assert [(c["kind"], c["text"]) for c in changes] == [
        ("delete", "나다"),
        ("insert", "라마"),
    ]
    rendered = render(changes, "md")
    assert "[변경추적 삭제] 나다" in rendered
    assert "[변경추적 추가] 라마" in rendered


def test_변경추적_range가_확장제어문자를_가로지르면_버린다():
    payload = struct.pack("<H", 2) + b"\x00" * 14 + "정상".encode("utf-16-le")
    ranges = struct.pack("<III", 0, 3, parser.TRACK_INSERT << 24)
    records = [
        (parser.HWPTAG_PARA_TEXT, 0, payload),
        (parser.HWPTAG_PARA_RANGE_TAG, 0, ranges),
    ]
    assert parser._parse_change_ranges(records) == []


def _nested_hwpx_bytes():
    inner = (
        '<hp:tbl rowCnt="1" colCnt="2">'
        '<hp:tr>'
        '<hp:tc><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        '<hp:subList><hp:p><hp:run><hp:t>안쪽A</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
        '<hp:tc><hp:cellAddr colAddr="1" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        '<hp:subList><hp:p><hp:run><hp:t>안쪽B</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
        '</hp:tr></hp:tbl>'
    )
    outer = (
        '<hp:tbl rowCnt="1" colCnt="1"><hp:tr>'
        '<hp:tc><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        '<hp:subList><hp:p><hp:run><hp:t>바깥</hp:t>' + inner +
        '</hp:run></hp:p></hp:subList></hp:tc>'
        '</hp:tr></hp:tbl>'
    )
    xml = (f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}">'
           f'<hp:p><hp:run>{outer}</hp:run></hp:p></hs:sec>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/section0.xml", xml)
    return buf.getvalue()


def test_HWPX_표안의표를_별도_구조와_렌더링으로_보존한다():
    blocks = read(_nested_hwpx_bytes(), name="nested.hwpx")
    table = next(b for b in blocks if b["type"] == "table")
    assert "표 안의 표" in table["grid"][0][0]
    assert table["nested_tables"][0]["table"]["grid"] == [["안쪽A", "안쪽B"]]
    output = render(blocks, "md")
    assert "[표 안의 표 · 1행 1열]" in output
    assert "안쪽A" in output and "안쪽B" in output


def test_ZIP_안의_HWPX를_하위폴더까지_자동으로_읽는다(tmp_path):
    first = Path(write_hwpx(tmp_path / "첫째.hwpx")).read_bytes()
    second = Path(write_hwpx(tmp_path / "둘째.hwpx", memo=False)).read_bytes()
    archive = tmp_path / "문서묶음.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("첫째.hwpx", first)
        z.writestr("하위/둘째.hwpx", second)
        z.writestr("무시.txt", "not a document")
    documents = read_documents(archive)
    assert [d["file"] for d in documents] == ["첫째.hwpx", "하위/둘째.hwpx"]
    output = render_documents(documents)
    assert "첫째.hwpx" in output and "하위/둘째.hwpx" in output
    assert "1,944,000" in output


def test_HWPX자체_ZIP은_묶음으로_오인하지_않는다(tmp_path):
    path = write_hwpx(tmp_path / "문서.hwpx")
    documents = read_documents(path)
    assert len(documents) == 1
    assert documents[0]["file"] == "문서.hwpx"
    assert any(b["type"] == "table" for b in documents[0]["blocks"])


def test_일반ZIP을_read로_직접읽으면_명확히_안내한다(tmp_path):
    archive = tmp_path / "묶음.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("x.txt", "x")
    try:
        read(archive)
    except ValueError as exc:
        assert "read_documents" in str(exc)
    else:
        raise AssertionError("일반 ZIP은 read()에서 거부되어야 한다")
