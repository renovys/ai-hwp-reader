"""HWP 문단 내부 숨은 메모 회귀시험."""

from hwp_reader import parser
from hwp_reader._reader_v05 import _parse_hwp_section


def test_문단_내부_MEMO_LIST도_별도_메모로_보존한다():
    records = [
        (parser.HWPTAG_PARA_HEADER, 0, b"\0" * 24),
        (parser.HWPTAG_PARA_TEXT, 1, "본문".encode("utf-16-le")),
        (parser.HWPTAG_MEMO_LIST, 1, b"\0" * 4),
        (parser.HWPTAG_LIST_HEADER, 1, b"\0" * 16),
        (parser.HWPTAG_PARA_HEADER, 1, b"\0" * 24),
        (parser.HWPTAG_PARA_TEXT, 2, "검토 메모".encode("utf-16-le")),
    ]
    blocks = _parse_hwp_section(
        parser._core, records,
        {"para_shapes": [], "numberings": [], "bullets": [], "bin_data": []},
        {"numbering": None, "auto": {}, "outline": 0, "seen": set()},
    )
    assert {"type": "memo", "text": "검토 메모"} in blocks
