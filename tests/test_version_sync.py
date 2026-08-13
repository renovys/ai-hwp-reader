"""버전 정본이 한 곳(hwp_reader/__init__.py)임을 강제하는 회귀시험.

0.5.1에서 pyproject만 올리고 __init__을 두는 바람에 PyPI 0.5.1의 CLI가 0.5.0을 찍었다.
"""

import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _pkg_version():
    return re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "hwp_reader" / "__init__.py").read_text(encoding="utf-8")).group(1)


def test_pyproject와_패키지_버전이_같다():
    proj = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    assert proj == _pkg_version()


def test_생성물_헤더와_스킬문서_버전이_같다():
    ver = _pkg_version()
    assert f"v{ver} " in (ROOT / "skill" / "hwp_reader_single.py").read_text(encoding="utf-8").splitlines()[0]
    subprocess.run([sys.executable, "tools/build_skill_package.py"], cwd=ROOT, check=True, capture_output=True)
    with zipfile.ZipFile(ROOT / "dist" / "ai-hwp-reader-skill.zip") as z:
        assert f"v{ver}" in z.read("ai-hwp-reader/SKILL.md").decode("utf-8")


def test_설치된_CLI가_같은_버전을_찍는다():
    p = subprocess.run([sys.executable, "-c", "import hwp_reader;print(hwp_reader.__version__)"], cwd=ROOT, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == _pkg_version()
