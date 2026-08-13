"""생성물이 정본 소스와 항상 동기화되는지 확인한다."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import bundle_v05  # noqa: E402


def test_단일파일과_SKILL_코드블록은_0_5_빌드출력과_같다():
    expected = bundle_v05.build_source()
    assert (ROOT / "skill" / "hwp_reader_single.py").read_text(encoding="utf-8") == expected

    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"```python\n(.*?)\n```", skill, re.S)
    assert match is not None
    assert match.group(1) == expected
