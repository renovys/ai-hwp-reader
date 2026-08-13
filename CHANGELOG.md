# Changelog

## 0.3.0

- 프로젝트 메시징을 **AI HWP Reader**로 재정의했습니다. 목표를 단순 HWP 파싱이 아니라 “AI가 HWP/HWPX를 직접 읽고 그 내용을 근거로 일하게 하는 것”으로 명확히 했습니다.
- HWPX 셀 안의 중첩 표 내용을 더 이상 버리지 않고 `[중첩표]` 표기로 부모 셀 텍스트에 보존하며, `nested_tables` 구조도 함께 반환합니다.
- HWP `FileHeader`가 실제 `HWP Document File` 시그니처인지 확인해 비-HWP OLE 문서를 조용히 오인하지 않습니다.
- 손상된 `LIST_HEADER`, 음수 HWPX 셀 주소, 비정상적으로 큰 표 격자를 명시적으로 거부합니다.
- 손상된 HWPX XML은 실패한 `sectionN.xml` 이름을 오류에 포함합니다.
- HWPX 섹션 확장자의 대소문자가 달라도 숫자 순서대로 읽습니다.
- `SKILL.md`를 “파싱부터 하고, 그 결과로 사용자의 실제 업무를 수행한다”는 AI 실행 흐름으로 강화했습니다.
- README/영문 README/PyPI 메타데이터를 AI 중심 포지셔닝으로 전면 개편했습니다.

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
