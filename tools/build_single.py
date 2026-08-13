"""AI HWP Reader를 외부 의존성 없는 한 파일과 웹 챗봇용 SKILL로 묶는다."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLE_SOURCE = ROOT / "hwp_reader" / "_ole.py"
PARSER_SOURCE = ROOT / "hwp_reader" / "parser.py"
SINGLE_SOURCE = ROOT / "skill" / "hwp_reader_single.py"
SKILL_SOURCE = ROOT / "SKILL.md"
HEADER = "# AI HWP Reader | 출처: hwp_reader/_ole.py + hwp_reader/parser.py | 라이선스: MIT | 저장소: https://github.com/renovys/hwp-reader"
SKILL_PREFIX = """# AI HWP Reader — 이 파일 하나를 AI에게 주면 HWP를 읽고 일을 합니다

이 파일은 사람이 읽는 설명서가 아니라 **AI 실행 스킬**이다.
사용자가 이 `SKILL.md` 파일과 `.hwp` / `.hwpx` / `.zip` 파일을 채팅창에 함께 첨부하고 **“해줘”**라고 하면 아래 지시를 즉시 수행하라.

목표는 코드를 설명하는 것이 아니다. **한글(HWP/HWPX)을 실제로 파싱하고, 그 결과를 근거로 사용자가 원한 일을 끝내는 것**이다.
아래아한글·아래한글·한글·한컴·한글과컴퓨터 문서를 PDF/TXT로 다시 변환하라고 요구하지 않는다.

## 모델 지시

1. 이 파일 안의 Python 코드블록 전체를 실행 환경에 `hwp_reader_single.py`로 저장한다.
2. 함께 첨부된 `.hwp`, `.hwpx`, `.zip`의 **실제 실행환경 경로**를 확인한다. 예시 경로나 파일명을 추측하지 않는다.
3. 즉시 `python hwp_reader_single.py "<실제 경로>"`를 실행한다. 여러 파일이면 모든 경로를 한 번에 넘긴다.
4. `.zip`이면 내부 폴더까지 훑어 HWP/HWPX를 모두 찾아 **메모리에서 직접 읽는다**. 사용자가 압축을 다시 풀어 올리게 하지 않는다.
5. 외부 패키지를 설치하거나 네트워크에서 코드를 받지 않는다. 아래 파서는 Python 표준 라이브러리만 사용한다.
6. 실제 파싱 결과를 먼저 확보한 뒤 그 결과로 사용자의 업무를 수행한다. “해줘”만 입력됐다면 문서가 무엇인지 파악해 핵심 내용·표·메모·변경추적을 놓치지 않게 정리한다.
7. **병합 표, 2~3단 헤더, 표 안의 표**를 구조대로 읽는다. `[표 안의 표]`가 나오면 별도 표로 이어서 해석한다.
8. `[메모]`는 본문에 보이지 않는 검토자 메모이므로 반드시 별도로 알린다.
9. `[변경추적 추가]` / `[변경추적 삭제]`가 있으면 최종 본문과 구분해 알려준다. HWP의 `BodyText`는 최종본, `ViewText`의 추적 range는 변경 이력으로 취급한다.
10. 파싱 결과에 없는 내용을 원문에 있는 것처럼 만들지 않는다. 일부만 읽혔거나 오류가 나면 성공한 척하지 않는다.
11. 첨부 문서를 외부 서비스로 업로드하지 않는다. 실행 환경 안에서 **읽기 전용**으로 처리한다.
12. Python/코드 실행 기능이 없어 실제 파서를 실행할 수 없다면 그 사실을 명확히 말한다. **실행하지 않았는데 HWP를 읽은 것처럼 답하지 않는다.**

파싱 후에는 사용자의 목적을 이어서 수행하라. 예: 요약, 계약조건 추출, 숫자 검산, 준법 검토, 여러 문서 비교, 변경사항 추적 정리, 숨은 메모 확인.

## 파서 코드
"""
SKILL_SUFFIX = """

## 지원 범위

- HWP 5.0 / HWPX 본문
- 셀 좌표와 병합 구조가 있는 표
- 표 안의 표(중첩 표)
- 숨은 메모(주석)
- HWP 변경 내용 추적(ViewText의 추가·삭제 range)
- 여러 HWP/HWPX가 들어 있는 ZIP
- 잘못 붙은 `.hwp` / `.hwpx` 확장자의 실제 컨테이너 판별

## 지원하지 않는 것

- 암호가 걸린 문서
- 한컴 수식 편집기 수식의 완전한 일반 텍스트 변환
- 스캔 이미지 OCR
- HWP 3.0 등 옛 포맷
- 문서 쓰기·수정

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
        "        print(\"사용법: python hwp_reader_single.py 문서.hwp|문서.hwpx|묶음.zip [...]\", file=sys.stderr)\n"
        "        sys.exit(2)\n"
        "    for index, path in enumerate(sys.argv[1:]):\n"
        "        if index:\n"
        "            print()\n"
        "        print(render_documents(read_documents(path), \"md\"))"
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
