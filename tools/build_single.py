"""HWP/HWPX 파서를 외부 의존성 없는 한 파일로 묶는다."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLE_SOURCE = ROOT / "hwp_reader" / "_ole.py"
PARSER_SOURCE = ROOT / "hwp_reader" / "parser.py"
SINGLE_SOURCE = ROOT / "skill" / "hwp_reader_single.py"
SKILL_SOURCE = ROOT / "SKILL.md"
HEADER = "# 출처: hwp_reader/_ole.py + hwp_reader/parser.py | 라이선스: MIT | 저장소: https://github.com/renovys/hwp-reader"


def build_source():
    ole = OLE_SOURCE.read_text(encoding="utf-8").rstrip()
    parser = PARSER_SOURCE.read_text(encoding="utf-8")
    import_line = "from ._ole import OleFile"
    if parser.count(import_line) != 1:
        raise RuntimeError("parser.py에서 _ole import를 하나 찾지 못했다")
    parser = parser.replace(import_line, "").rstrip()
    main = (
        "if __name__ == \"__main__\":\n"
        "    if len(sys.argv) != 2:\n"
        "        print(\"사용법: python hwp_reader_single.py 문서.hwp\", file=sys.stderr)\n"
        "        sys.exit(2)\n"
        "    print(render(read(sys.argv[1]), \"md\"))"
    )
    return "\n\n".join((HEADER, ole, parser, main))


def update_skill(single):
    text = SKILL_SOURCE.read_text(encoding="utf-8")
    matches = list(re.finditer(r"```python\n.*?\n```", text, re.S))
    if len(matches) != 1:
        raise RuntimeError("SKILL.md에는 Python 코드 블록이 정확히 하나 있어야 한다")
    match = matches[0]
    replacement = "```python\n" + single + "\n```"
    text = text[:match.start()] + replacement + text[match.end():]
    SKILL_SOURCE.write_text(text, encoding="utf-8")


def main():
    single = build_source()
    SINGLE_SOURCE.parent.mkdir(parents=True, exist_ok=True)
    SINGLE_SOURCE.write_text(single, encoding="utf-8")
    update_skill(single)
    print(f"생성: {SINGLE_SOURCE.relative_to(ROOT)}")
    print("갱신: SKILL.md 코드 블록")


if __name__ == "__main__":
    main()
