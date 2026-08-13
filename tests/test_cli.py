"""CLI 회귀 시험. 실제로 프로세스를 띄워서 확인한다."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from make_fixture import write_hwpx                     # noqa: E402


def _run(*args, encoding=None):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    if encoding:
        env["PYTHONIOENCODING"] = encoding
    return subprocess.run([sys.executable, "-m", "hwp_reader.cli", *args],
                          capture_output=True, env=env)


@pytest.fixture()
def 예산서(tmp_path):
    return write_hwpx(tmp_path / "예산서.hwpx")


def test_도움말은_종료_0이다():
    assert _run("--help").returncode == 0


def test_모르는_옵션은_종료_2다(예산서):
    assert _run(예산서, "--없는옵션").returncode == 2


def test_없는_파일은_종료_1이다():
    assert _run("/없는/경로.hwp").returncode == 1


@pytest.mark.parametrize("enc", ["cp949", "cp1252", "ascii"])
def test_콘솔이_한글을_못_받는_인코딩이어도_죽지_않는다(예산서, enc):
    """윈도우 콘솔 기본값이 여기 해당한다. 고치기 전에는 --help부터 터졌다."""
    assert _run("--help", encoding=enc).returncode == 0
    assert _run(예산서, encoding=enc).returncode == 0


def test_표와_메모가_함께_나온다(예산서):
    out = _run(예산서).stdout.decode("utf-8", "replace")
    assert "1,944,000" in out and "[메모]" in out


def test_메모만_뽑는다(예산서):
    out = _run(예산서, "--memos-only").stdout.decode("utf-8", "replace")
    assert "최신 자료 기준으로" in out and "1,944,000" not in out


def test_표만_뽑는다(예산서):
    out = _run(예산서, "--tables-only").stdout.decode("utf-8", "replace")
    assert "1,944,000" in out and "◎ 예산 집행 내역" not in out


def test_폴더로_저장하면_문서마다_한_파일(예산서, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    assert _run(예산서, "--format", "md", "-o", str(out_dir) + os.sep).returncode == 0
    written = list(out_dir.glob("*.md"))
    assert len(written) == 1
    assert "| 정가 |" in written[0].read_text(encoding="utf-8")


def test_json은_한_줄에_한_문서(예산서):
    import json
    out = _run(예산서, "--format", "json").stdout.decode("utf-8")
    lines = [l for l in out.splitlines() if l.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["blocks"][1]["type"] == "table"
