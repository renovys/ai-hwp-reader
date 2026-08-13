"""0.5 표 병합 범위 추가 회귀시험."""

import pytest

from hwp_reader._v05_enable import _validate_table


def test_merged_cell_overlap_is_rejected():
    table = {
        "rows": 2,
        "cols": 3,
        "cells": [
            {"row": 0, "col": 0, "rowspan": 1, "colspan": 2, "text": "A"},
            {"row": 0, "col": 1, "rowspan": 2, "colspan": 1, "text": "B"},
        ],
        "nested_tables": [],
    }
    with pytest.raises(ValueError, match="겹친다"):
        _validate_table(table)
