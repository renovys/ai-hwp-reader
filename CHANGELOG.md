# Changelog

## 0.5.0

- HWP/HWPX의 **각주·미주, 하이퍼링크, 한컴 수식 스크립트, 이미지 참조, 글상자 텍스트**를 AI가 구분해 사용할 수 있는 구조로 보존합니다.
- HWP `DocInfo`의 문단 번호·개요·글머리표 정의를 읽어 숫자·로마자·영문·가나다·한글/한자 숫자 형식을 복원합니다.
- 배포용 HWP의 `ViewText/Section#`을 표준 라이브러리만으로 복호화해 읽습니다. 열기 암호와 DRM은 여전히 명시적으로 거부합니다.
- 정상 CFB/OLE은 기존 strict 리더로 먼저 읽고, 일부 한컴 생성 파일의 알려진 할당표 비정합에 한해서만 **제한적 호환 fallback**을 사용합니다. 필수 체인의 순환·범위·예약값 오류는 호환 모드에서도 거부합니다.
- 병합 셀의 시작 주소뿐 아니라 **실제 점유 범위가 서로 겹치는 경우**도 오류로 처리합니다.
- HWPX XML의 깊이·노드·크기와 ZIP의 누적 크기·비정상 압축률·중복 경로를 제한하고 DTD/ENTITY를 파싱 전에 차단합니다.
- 여러 문서가 든 ZIP에서 한 파일이 실패해도 다른 파일은 계속 처리하고 실패 이유를 파일별로 분리합니다.
- MCP가 HWP/HWPX뿐 아니라 ZIP도 직접 읽고, `hwp_revisions` 도구로 변경추적만 조회할 수 있습니다. 큰 JSON 결과도 중간 절단으로 문법을 깨뜨리지 않습니다.
- `SKILL.md`와 단일 파일 배포본에도 같은 0.5 파서 계층이 생성되도록 번들 생성을 확장했습니다.
- `rhwp`와 `kordoc`의 MIT 구현을 형식 동작 교차검증에 활용하고 `THIRD_PARTY_NOTICES.md`에 고지를 남겼습니다.

## 0.3.1

- 프로젝트 이름을 **ai-hwp-reader**로 통일했습니다. 저장소는 `github.com/renovys/ai-hwp-reader`, PyPI 패키지와 CLI는 `ai-hwp-reader`입니다.
- Python import 이름은 `hwp_reader` 그대로이고, 예전 `hwp-reader` / `hwp-reader-mcp` 명령도 함께 설치돼 계속 동작합니다.

## 0.3.0

- 프로젝트 메시징을 **AI HWP Reader**로 재정의했습니다. 목표를 단순 HWP 파싱이 아니라 “AI가 HWP/HWPX를 직접 읽고 그 내용을 근거로 일하게 하는 것”으로 명확히 했습니다.
- README 첫 사용 흐름을 **`SKILL.md` 다운로드 → SKILL과 HWP/HWPX/ZIP을 채팅창에 함께 첨부 → `해줘`**로 재설계했습니다. 복사·붙여넣기가 필요 없습니다.
- 여러 HWP/HWPX가 든 ZIP을 하위 폴더까지 자동 탐색하고, 멤버를 디스크에 다시 풀지 않고 메모리에서 직접 파싱합니다. `read_documents()` / `render_documents()` API와 CLI ZIP 입력을 추가했습니다.
- HWP 변경 내용 추적이 저장되는 `ViewText/Section#`의 `PARA_RANGE_TAG`를 읽어 추가/삭제 변경 구간을 `revision` 블록으로 분리합니다. `BodyText`의 최종 본문과 섞지 않습니다.
- HWP와 HWPX의 **표 안의 표**를 부모 셀 위치와 별도 `nested_tables` 구조로 보존하고 렌더링합니다.
- HWP `FileHeader`가 실제 `HWP Document File` 시그니처인지 확인해 비-HWP OLE 문서를 조용히 오인하지 않습니다.
- 손상된 `LIST_HEADER`, 음수 HWPX 셀 주소, 비정상적으로 큰 표 격자, 손상 XML을 명시적으로 거부합니다.
- HWPX 섹션 확장자의 대소문자가 달라도 숫자 순서대로 읽습니다.
- `SKILL.md`가 ZIP·중첩 표·메모·변경추적까지 읽은 뒤 사용자의 실제 업무를 계속 수행하도록 실행 지시를 강화했습니다.
- PyPI 메타데이터와 한국어/영문 README를 AI 중심 포지셔닝으로 개편했습니다.

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
