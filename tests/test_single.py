"""생성된 단일 파일 배포본 시험."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SINGLE = ROOT / "skill" / "hwp_reader_single.py"
sys.path.insert(0, str(ROOT))

from make_fixture import write_hwpx                    # noqa: E402


def test_단일_파일을_실행하면_표_내용이_출력된다(tmp_path):
    document = write_hwpx(tmp_path / "예산서.hwpx")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, str(SINGLE), document],
                            cwd=ROOT, capture_output=True, env=env)
    output = result.stdout.decode("utf-8", "replace")
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "| 정가 |" in output and "1,944,000" in output
