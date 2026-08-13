# Changelog

## 0.2.0

- HWP 본문에 남아 출력되던 C0 제어문자를 안전하게 공백으로 정리합니다.
- `Section10`이 `Section2`보다 먼저 읽히던 문자열 정렬 문제를 고쳐 HWP/HWPX 다중 섹션을 숫자 순서대로 읽습니다.
- HWPX 문단 내부 메모가 있을 때 앞뒤 본문을 중복 처리할 수 있던 경로를 분리했습니다.
- Markdown 표 셀 안의 `|`와 백슬래시를 이스케이프합니다.
- 잘린 HWP 레코드와 잘린 TABLE payload를 명시적인 오류로 처리합니다.
- `skill/hwp_reader_single.py`가 여러 문서를 한 번에 받을 수 있습니다.
- `SKILL.md`를 웹 챗봇에서 실제 코드 실행을 우선하도록 강화하고, 실행 기능이 없을 때 읽은 척 답하지 않도록 명시했습니다.
- 생성된 단일 파일과 `SKILL.md` 코드블록이 `tools/build_single.py`의 결과와 같은지 회귀 시험으로 고정했습니다.

## 0.1.0

- HWP 5.0 / HWPX 본문·표 파싱.
- 병합 셀 좌표 복원.
- HWP/HWPX 메모 추출.
- 외부 런타임 의존성 없는 기본 파서.
- CLI, Python API, 선택형 MCP 서버, 웹 챗봇용 `SKILL.md` 제공.
