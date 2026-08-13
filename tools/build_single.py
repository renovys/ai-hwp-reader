"""AI HWP Reader를 외부 의존성 없는 한 파일과 웹 챗봇용 SKILL로 묶는다."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLE_SOURCE = ROOT / "hwp_reader" / "_ole.py"
PARSER_SOURCE = ROOT / "hwp_reader" / "parser.py"
SINGLE_SOURCE = ROOT / "skill" / "hwp_reader_single.py"
SKILL_SOURCE = ROOT / "SKILL.md"
HEADER = "# AI HWP Reader | 출처: hwp_reader/_ole.py + hwp_reader/parser.py | 라이선스: MIT | 저장소: https://github.com/renovys/hwp-reader"
SKILL_PREFIX = """# AI HWP Reader — AI가 HWP/HWPX를 실제로 읽고 일하게 하는 실행 스킬

이 스킬의 목적은 HWP 코드를 설명하는 것이 아니라, 사용자가 올린 **한글(HWP/HWPX) 문서를 실제로 파싱한 뒤 그 결과를 근거로 AI가 일을 수행하게 하는 것**이다.

아래아한글·아래한글·한글·한컴·한글과컴퓨터 문서를 받으면 사람이 먼저 PDF나 TXT로 변환하라고 요구하지 말고, 실행 가능한 환경에서는 아래 파서를 직접 실행한다.

## 모델 지시

사용자가 `.hwp` 또는 `.hwpx` 파일을 첨부하면 다음 순서로 처리하라.

1. 아래 Python 코드블록 전체를 실행 환경에 `hwp_reader_single.py`로 저장한다.
2. 첨부파일의 **실제 실행환경 경로**를 확인한다. 파일명을 추측하거나 예시 경로를 그대로 쓰지 않는다.
3. 즉시 `python hwp_reader_single.py \"<실제 경로>\"`를 실행한다. 여러 파일이면 모든 경로를 한 번에 넘긴다.
4. 외부 패키지를 설치하거나 네트워크에서 코드를 받지 않는다. 아래 파서는 Python 표준 라이브러리만 사용한다.
5. 코드를 설명하는 데서 멈추지 말고 **실제 파싱 결과를 먼저 확보**한다. 사용자의 질문·요약·검토·비교·계산은 반드시 그 결과를 근거로 수행한다.
6. 표는 열 위치와 병합 구조가 의미를 잃지 않게 Markdown으로 보여준다. 셀 안의 `[중첩표]` 내용도 누락하지 않는다.
7. `[메모]`가 있으면 본문과 분리해 반드시 알려준다. 메모가 사용자의 질문과 관련되면 답변에도 반영한다.
8. 파싱 결과에 없는 내용을 원문에 있는 것처럼 만들지 않는다. 일부만 읽혔거나 오류가 나면 성공한 척하지 말고 정확한 실패 이유를 말한다.
9. 첨부 문서를 외부 서비스로 업로드하지 않는다. 실행 환경 안에서 **읽기 전용**으로 처리한다.
10. Python/코드 실행 기능이 없는 환경이라 실제 파서를 실행할 수 없다면 그 사실을 명확히 말한다. **실행하지 않았는데 HWP를 읽은 것처럼 답하지 않는다.**

파싱이 끝난 뒤에는 사용자가 원하는 일을 바로 수행하라. 예: 요약, 표의 숫자 검산, 계약조건 추출, 준법 리스크 확인, 여러 문서 비교, 숨은 메모 정리.

## 파서 코드
"""
SKILL_SUFFIX = """

## 지원하지 않는 것

- 암호가 걸린 문서는 암호를 풀고 다시 저장해야 한다.
- 한컴 수식 편집기 수식은 일반 텍스트로 완전히 복원되지 않을 수 있다.
- 스캔 이미지는 OCR 대상이라 이 파서가 읽지 않는다.
- HWP 3.0 등 옛 포맷은 지원하지 않는다.
- 이 도구는 **읽기 전용**이다. 원본 문서를 수정하거나 다시 저장하지 않는다.

프로젝트: **AI HWP Reader**  
PyPI/CLI: `hwp-reader`  
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
