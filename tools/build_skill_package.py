#!/usr/bin/env python3
"""업로드용 에이전트 스킬 패키지(zip)를 만든다.

챗봇에 그때그때 첨부하는 단일 `SKILL.md`와 달리, 이 zip은 **한 번 등록해 두면
다음 대화에서도 그대로 쓰이는** 스킬 패키지다. 안의 구조는 에이전트 스킬 규격을 따른다.

    ai-hwp-reader/SKILL.md                  YAML frontmatter(name·description) + 지시문
    ai-hwp-reader/scripts/hwp_reader_single.py   의존성 0 파서(생성물)
    ai-hwp-reader/LICENSE                   MIT

사용법:
  build_skill_package.py            dist/ai-hwp-reader-skill.zip 생성
  build_skill_package.py --dry      만들 내용만 보여주고 쓰지 않음
"""
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "skill" / "agent" / "SKILL.md"
PARSER = ROOT / "skill" / "hwp_reader_single.py"
LICENSE = ROOT / "LICENSE"
OUT = ROOT / "dist" / "ai-hwp-reader-skill.zip"
NAME = "ai-hwp-reader"


def _utf8_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def version():
    """정본은 hwp_reader/__init__.py다. pyproject와 어긋나면 멈춘다."""
    pkg = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "hwp_reader" / "__init__.py").read_text(encoding="utf-8"))
    proj = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    if not pkg or not proj:
        sys.exit("[실패] 버전을 못 찾았다")
    if pkg.group(1) != proj.group(1):
        sys.exit(f"[실패] 버전이 어긋난다: __init__={pkg.group(1)} pyproject={proj.group(1)}")
    return pkg.group(1)


def main():
    _utf8_console()
    dry = "--dry" in sys.argv[1:]
    for a in sys.argv[1:]:
        if a in ("-h", "--help"):
            print(__doc__)
            return
        if a != "--dry":
            print(f"모르는 옵션: {a}", file=sys.stderr); sys.exit(2)

    for p in (DOC, PARSER, LICENSE):
        if not p.is_file():
            sys.exit(f"[실패] 없는 파일: {p}")

    ver = version()
    doc = DOC.read_text(encoding="utf-8").replace("__VERSION__", ver)
    if "__VERSION__" in doc or f"v{ver}" not in doc:
        sys.exit("[실패] SKILL.md의 버전 자리를 채우지 못했다")
    if not doc.startswith("---\n") or f"name: {NAME}\n" not in doc:
        sys.exit("[실패] SKILL.md frontmatter가 규격과 다르다")

    parser = PARSER.read_text(encoding="utf-8")
    members = {
        f"{NAME}/SKILL.md": doc,
        f"{NAME}/scripts/hwp_reader_single.py": parser,
        f"{NAME}/LICENSE": LICENSE.read_text(encoding="utf-8"),
    }

    if dry:
        print(f"[예행(DRY)] {OUT} 를 만들 것 (v{ver})")
        for k, v in members.items():
            print(f"   {k}  {len(v):,}자")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in members.items():
            z.writestr(k, v)

    with zipfile.ZipFile(OUT) as z:
        bad = z.testzip()
        if bad:
            sys.exit(f"[실패] zip이 깨졌다: {bad}")
        got = sorted(z.namelist())
    if got != sorted(members):
        sys.exit(f"[실패] zip 구성이 다르다: {got}")

    print(f"generated: {OUT.relative_to(ROOT)} (v{ver}, {OUT.stat().st_size:,}바이트)")
    for k in got:
        print(f"   {k}")


if __name__ == "__main__":
    main()
