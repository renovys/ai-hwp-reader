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


def test_플러그인_트리와_매니페스트가_규격대로다():
    """`skills/`는 커밋되는 생성물이고 플러그인이 실제로 로드하는 경로다.

    여기서는 구성·형식만 본다. **커밋 누락**(정본을 고치고 빌드를 안 돌린 채 커밋)은
    이 검사로 잡히지 않는다 — 같은 pytest 세션의 다른 시험이 빌드를 돌려 트리를 복구해
    버리기 때문이다. 그 게이트는 CI의 `git diff --exit-code -- skills` 단계가 맡는다.
    """
    import json

    ver = re.search(
        r'__version__\s*=\s*"([^"]+)"',
        (ROOT / "hwp_reader" / "__init__.py").read_text(encoding="utf-8"),
    ).group(1)
    expected = {
        "SKILL.md": (ROOT / "skill" / "agent" / "SKILL.md").read_text(encoding="utf-8").replace("__VERSION__", ver),
        "scripts/hwp_reader_single.py": (ROOT / "skill" / "hwp_reader_single.py").read_text(encoding="utf-8"),
        "LICENSE": (ROOT / "LICENSE").read_text(encoding="utf-8"),
    }

    tree = ROOT / "skills" / "ai-hwp-reader"
    for rel, body in expected.items():
        got = tree / rel
        assert got.is_file(), f"플러그인 트리에 없는 파일: {got}"
        assert got.read_text(encoding="utf-8") == body, (
            f"정본과 어긋난다: {got} — tools/build_skill_package.py 를 다시 돌려라"
        )

    meta = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert meta["name"] == "ai-hwp-reader"
    assert re.fullmatch(r"\d+\.\d+\.\d+", meta["version"])
    assert [p["name"] for p in market["plugins"]] == ["ai-hwp-reader"]
