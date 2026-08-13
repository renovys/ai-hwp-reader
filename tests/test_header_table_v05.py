"""HWP 머리말·꼬리말 내부 표 구조 회귀시험."""

import struct

from hwp_reader import parser
from hwp_reader._parser_features import _NumberingState
from hwp_reader._reader_v05 import _parse_hwp_section


def _cell(col, row, colspan=1, rowspan=1):
    return b"\0" * parser.CELL_OFFSET + struct.pack("<4H", col, row, colspan, rowspan)


def _state():
    return {"numbering": _NumberingState(), "auto": {}, "outline": 0, "seen": set()}


def _docinfo():
    return {"para_shapes": [], "numberings": [], "bullets": [], "bin_data": []}


def test_머리말_안_표를_평문으로_납작하게_만들지_않는다():
    records = [
        (parser.HWPTAG_PARA_HEADER, 0, b"\0" * 24),
        (parser.HWPTAG_CTRL_HEADER, 1, b"head"),
        (parser.HWPTAG_CTRL_HEADER, 2, b"tbl "),
        (parser.HWPTAG_TABLE, 3, b"\0" * 4 + struct.pack("<HH", 1, 2)),
        (parser.HWPTAG_LIST_HEADER, 3, _cell(0, 0)),
        (parser.HWPTAG_PARA_TEXT, 4, "구분".encode("utf-16-le")),
        (parser.HWPTAG_LIST_HEADER, 3, _cell(1, 0)),
        (parser.HWPTAG_PARA_TEXT, 4, "값".encode("utf-16-le")),
    ]

    blocks = _parse_hwp_section(parser._core, records, _docinfo(), _state())

    assert blocks == [{
        "type": "table",
        "context": "header",
        "rows": 1,
        "cols": 2,
        "cells": [
            {"row": 0, "col": 0, "rowspan": 1, "colspan": 1, "text": "구분"},
            {"row": 0, "col": 1, "rowspan": 1, "colspan": 1, "text": "값"},
        ],
        "grid": [["구분", "값"]],
        "nested_tables": [],
    }]
