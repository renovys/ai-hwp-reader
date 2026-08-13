"""생성된 단일 파일 배포본 시험."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SINGLE = ROOT / "skill" / "hwp_reader_single.py"
sys.path.insert(0, str(ROOT))

from make_fixture import write_hwpx                    # noqa: E402


def _run(*documents):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(SINGLE), *documents],
                          cwd=ROOT, capture_output=True, env=env)


def test_단일_파일을_실행하면_표_내용이_출력된다(tmp_path):
    document = write_hwpx(tmp_path / "예산서.hwpx")
    result = _run(document)
    output = result.stdout.decode("utf-8", "replace")
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "| 정가 |" in output and "1,944,000" in output


def test_단일_파일이_여러_첨부문서를_파일경계를_유지해_읽는다(tmp_path):
    first = write_hwpx(tmp_path / "첫째.hwpx", memo=False)
    second = write_hwpx(tmp_path / "둘째.hwpx", memo=False)
    result = _run(first, second)
    output = result.stdout.decode("utf-8", "replace")
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "첫째.hwpx" in output
    assert "둘째.hwpx" in output
    assert output.count("=" * 70) >= 4
    assert output.count("1,944,000") == 2
