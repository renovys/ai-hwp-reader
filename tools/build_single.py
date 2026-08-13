"""HWP/HWPX 파서를 외부 의존성 없는 한 파일과 웹 챗봇용 SKILL로 묶는다."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLE_SOURCE = ROOT / "hwp_reader" / "_ole.py"
PARSER_SOURCE = ROOT / "hwp_reader" / "parser.py"
SINGLE_SOURCE = ROOT / "skill" / "hwp_reader_single.py"
SKILL_SOURCE = ROOT / "SKILL.md"
HEADER = "# 출처: hwp_reader/_ole.py + hwp_reader/parser.py | 라이선스: MIT | 저장소: https://github.com/renovys/hwp-reader"
SKILL_PREFIX = """# HWP/HWPX 읽기 — 웹 챗봇 실행 지침

이 문서를 **통째로** 대화창에 붙여넣은 뒤 `.hwp` 또는 `.hwpx` 파일을 올리세요. 그 다음 **\"이거 줘\"**라고 하거나 문서에 대해 질문하면 됩니다.

## 모델 지시

사용자가 HWP/HWPX 파일을 첨부하면 다음 순서로 처리하라.

1. 아래 Python 코드블록 전체를 실행 환경에 `hwp_reader_single.py`로 저장한다.
2. 첨부파일의 **실제 실행환경 경로**를 확인한 뒤 즉시 `python hwp_reader_single.py \"<경로>\"`를 실행한다. 여러 파일이면 모든 경로를 한 번에 넘긴다.
3. 외부 패키지를 설치하거나 네트워크에서 코드를 받으려 하지 않는다. 아래 코드는 Python 표준 라이브러리만 사용한다.
4. 코드를 설명하는 데서 멈추지 말고 **실제 실행 결과를 먼저** 보여준다. 표는 Markdown 표 형태를 유지하고 `[메모]`가 있으면 본문과 분리해 빠뜨리지 않는다.
5. 사용자의 후속 질문에는 반드시 방금 파싱한 결과를 근거로 답한다. 파싱 결과에 없는 내용을 원문에 있는 것처럼 만들지 않는다.
6. 첨부 문서를 외부 서비스로 업로드하지 않는다. 실행 환경 안에서 읽기 전용으로 처리한다.
7. Python/코드 실행 기능이 없는 환경이라 실제 파서를 실행할 수 없다면 그 사실을 명확히 말한다. **실행하지 않았는데 문서를 읽은 것처럼 답하지 않는다.**

## 파서 코드
"""
SKILL_SUFFIX = """

## 지원하지 않는 것

- 암호가 걸린 문서는 암호를 풀고 다시 저장해야 한다.
- 한컴 수식 편집기 수식은 일반 텍스트로 복원되지 않을 수 있다.
- 스캔 이미지는 OCR 대상이라 이 파서가 읽지 않는다.
- HWP 3.0 등 옛 포맷은 지원하지 않는다.
- 이 도구는 **읽기 전용**이다. 원본 문서를 수정하거나 저장하지 않는다.

저장소: https://github.com/renovys/hwp-reader
"""


def build_source():
    ole = OLE_SOURCE.read_text(encoding="utf-8").rstrip()
    parser = PARSER_SOURCE.read_text(encoding="utf-8")
    import_line = "from ._ole import OleFile"
    if parser.count(import_line) != 1:
        raise RuntimeError("parser.py에서 _ole import를 하나 찾지 못했다")
    parser = parser.replace(import_line, "").rstrip()
    main = (
        "if __name__ == \"__main__\":\n"
        "    if len(sys.argv) < 2:\n"
        "        print(\"사용법: python hwp_reader_single.py 문서.hwp [문서2.hwpx ...]\", file=sys.stderr)\n"
        "        sys.exit(2)\n"
        "    paths = sys.argv[1:]\n"
        "    for index, path in enumerate(paths):\n"
        "        if len(paths) > 1:\n"
        "            if index:\n"
        "                print()\n"
        "            print(\"===== {} =====\".format(os.path.basename(path)))\n"
        "        print(render(read(path), \"md\"))"
    )
    return "\n\n".join((HEADER, ole, parser, main))


def build_skill(single):
    return SKILL_PREFIX.rstrip() + "\n\n```python\n" + single + "\n```\n" + SKILL_SUFFIX


def main():
    single = build_source()
    SINGLE_SOURCE.parent.mkdir(parents=True, exist_ok=True)
    SINGLE_SOURCE.write_text(single, encoding="utf-8")
    SKILL_SOURCE.write_text(build_skill(single), encoding="utf-8")
    print(f"생성: {SINGLE_SOURCE.relative_to(ROOT)}")
    print("생성: SKILL.md")


if __name__ == "__main__":
    main()
