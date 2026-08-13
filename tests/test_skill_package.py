"""업로드용 스킬 패키지 회귀시험."""

import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _build(tmp_path):
    out = ROOT / "dist" / "ai-hwp-reader-skill.zip"
    subprocess.run([sys.executable, "tools/build_skill_package.py"], cwd=ROOT, check=True, capture_output=True)
    return out


def test_패키지_구성이_스킬_규격을_지킨다(tmp_path):
    z = _build(tmp_path)
    with zipfile.ZipFile(z) as f:
        names = sorted(f.namelist())
        doc = f.read("ai-hwp-reader/SKILL.md").decode("utf-8")
    assert names == [
        "ai-hwp-reader/LICENSE",
        "ai-hwp-reader/SKILL.md",
        "ai-hwp-reader/scripts/hwp_reader_single.py",
    ]
    assert doc.startswith("---\n")
    front = doc.split("---\n", 2)[1]
    assert re.search(r"^name: ai-hwp-reader$", front, re.M)
    assert re.search(r"^description: .{40,}$", front, re.M)


def test_패키지_버전이_pyproject와_같다():
    ver = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    with zipfile.ZipFile(ROOT / "dist" / "ai-hwp-reader-skill.zip") as f:
        doc = f.read("ai-hwp-reader/SKILL.md").decode("utf-8")
    assert f"v{ver}" in doc
    assert "__VERSION__" not in doc


def test_패키지_안_파서가_실제로_돈다(tmp_path):
    sys.path.insert(0, str(ROOT / "tests"))
    from make_fixture import write_hwpx

    src = tmp_path / "표.hwpx"
    write_hwpx(str(src))
    with zipfile.ZipFile(ROOT / "dist" / "ai-hwp-reader-skill.zip") as f:
        f.extractall(tmp_path)
    script = tmp_path / "ai-hwp-reader" / "scripts" / "hwp_reader_single.py"
    p = subprocess.run([sys.executable, str(script), str(src)], capture_output=True)
    out = p.stdout.decode("utf-8", "replace")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert "[메모]" in out
    assert "| 품목 |" in out


def test_비UTF8_환경에서도_한글_출력이_죽지_않는다(tmp_path):
    """윈도우 cp949/cp1252 콘솔·파이프에서 한글 출력이 UnicodeEncodeError로 죽던 회귀."""
    import os

    sys.path.insert(0, str(ROOT / "tests"))
    from make_fixture import write_hwpx

    src = tmp_path / "표.hwpx"
    write_hwpx(str(src))
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    p = subprocess.run(
        [sys.executable, str(ROOT / "skill" / "hwp_reader_single.py"), str(src)],
        capture_output=True, env=env,
    )
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert "[메모]" in p.stdout.decode("utf-8", "replace")
