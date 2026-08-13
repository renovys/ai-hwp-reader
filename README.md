# AI HWP Reader

## 이제 당신의 AI가 HWP를 읽고, 그 문서로 일을 합니다.

**ChatGPT · Claude · Gemini에게 아래아한글(HWP/HWPX)을 그대로 주세요.**  
본문만 훑는 것이 아니라 **병합된 표, 표 안의 표, 숨은 메모, 변경 내용 추적**까지 꺼내서 AI가 요약하고, 검토하고, 비교하고, 계산하고, 답하게 합니다.

[![PyPI](https://img.shields.io/pypi/v/ai-hwp-reader)](https://pypi.org/project/ai-hwp-reader/)
[![Python](https://img.shields.io/pypi/pyversions/ai-hwp-reader)](https://pypi.org/project/ai-hwp-reader/)
[![tests](https://github.com/renovys/ai-hwp-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/renovys/ai-hwp-reader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> **아래아한글 · 아래한글 · 한글 · 한컴 · 한글과컴퓨터 · HWP · HWPX → AI**

[English](README.en.md)

---

## 가장 쉬운 사용법 — 파일 하나 받으면 끝

터미널을 열 필요도, Python을 알 필요도, `pip install`을 할 필요도 없습니다.

### 1. `SKILL.md` 하나를 다운로드합니다

**[⬇ SKILL.md 다운로드](./SKILL.md?raw=1)**

### 2. AI 채팅창에 같이 첨부합니다

`SKILL.md`와 읽고 싶은 `.hwp` / `.hwpx` / `.zip` 파일을 **같이** 올립니다.

### 3. 한마디만 합니다

```text
해줘
```

끝입니다.

`SKILL.md` 안에는 **외부 의존성 0개의 HWP/HWPX 파서 전체와 AI 실행 지시**가 들어 있습니다. 코드 실행이 가능한 AI 환경에서는 파서를 실제로 실행한 뒤, 그 결과를 근거로 문서 업무를 계속합니다.

```text
SKILL.md + 계약서.hwp
→ “해줘”
→ 계약 핵심조건 / 표 / 메모 / 변경추적까지 읽고 정리
```

```text
SKILL.md + 투자자료.zip
→ “해줘”
→ ZIP 내부 HWP/HWPX를 전부 찾아 파일별로 읽고 비교
```

**HWP를 PDF로 바꾸고, 표를 엑셀로 옮기고, 다시 AI에게 설명하는 중간 작업을 없애는 것이 이 프로젝트의 목적입니다.**

---

## “HWP를 읽었다”와 “HWP를 제대로 읽었다”는 다릅니다

한국의 공문, 제안서, 투자검토서, 계약서, 신청서, 준법 체크리스트는 중요한 내용이 표 안에 들어 있는 경우가 많습니다.

텍스트만 평평하게 추출하면 이런 식이 될 수 있습니다.

```text
1. 투자조건
<표>

2. 주요 의무사항
<표>
```

문서는 읽힌 것처럼 보이지만 **투자금액, 단가, 지분율, 예외조건, 결재정보 같은 핵심이 표와 함께 사라질 수 있습니다.**

AI HWP Reader는 셀 주소와 병합 범위를 복원합니다.

```text
| 구분 | 투자금액 | 투자단가 | 지분율 |
|---|---:|---:|---:|
| 신주 | 1,000,011,950원 | 14,570원 | 4.7% |
```

그리고 본문 밖에 숨어 있는 검토 메모도 따로 꺼냅니다.

```text
[메모] 최신 자료 기준으로 업데이트해주세요.
```

변경 내용 추적이 남은 HWP라면 최종 본문과 별도로 표시합니다.

```text
[변경추적 삭제] 기존 문구
[변경추적 추가] 수정 문구
```

AI는 이제 “HWP 파일이 첨부되어 있다”는 사실이 아니라 **HWP 안에 실제로 들어 있는 구조와 내용**을 근거로 일할 수 있습니다.

---

## 무엇을 읽나

| HWP 안의 정보 | 지원 | AI에게 전달되는 방식 |
|---|---:|---|
| 일반 본문 | ✅ | 문서 순서대로 텍스트 |
| 일반 표 | ✅ | 행·열 구조 보존 |
| 병합된 표 | ✅ | `rowspan` / `colspan`과 원래 셀 위치 보존 |
| 2단·3단 표 헤더 | ✅ | 아래 행이 왼쪽으로 밀리지 않게 복원 |
| **표 안의 표** | ✅ | 부모 셀 위치 + 별도 중첩 표로 보존 |
| 숨은 메모(주석) | ✅ | `[메모]` 블록으로 분리 |
| **HWP 변경 내용 추적** | ✅ | `ViewText`의 추가/삭제 range를 별도 표시 |
| 여러 섹션 | ✅ | `Section2` / `Section10`을 숫자 순서로 정렬 |
| 확장자가 잘못 붙은 HWP/HWPX | ✅ | 실제 컨테이너를 보고 판별 |
| **HWP/HWPX가 여러 개 든 ZIP** | ✅ | 압축을 직접 열고 내부 폴더까지 탐색 |
| 암호 문서 | ❌ | 암호를 풀고 다시 저장해야 함 |
| 스캔 이미지 OCR | ❌ | OCR 영역 |
| 한컴 수식 편집기 수식 완전 복원 | ❌ | 일반 텍스트로 완전 복원하지 않음 |
| HWP 3.0 등 옛 포맷 | ❌ | HWP 5.0 / HWPX 대상 |
| 문서 쓰기·수정 | ❌ | **읽기 전용** |

---

## AI에게 특히 중요한 네 가지

### 1. 병합된 표를 위치 그대로 읽습니다

값만 순서대로 가져오면 2단 헤더에서 숫자가 다른 열로 밀려도 결과가 그럴듯해 보입니다. 이게 가장 위험합니다.

AI HWP Reader는 HWP/HWPX에 저장된 **행·열 주소와 병합 범위**를 사용합니다.

```text
품목 | 규격 | 수량 | 단가        | 금액
     |      |      | 정가 | 할인가 | 공급가 | 부가세
```

### 2. 표 안의 표도 버리지 않습니다

실무 HWP에는 셀 안에 다시 표가 들어가는 문서가 있습니다. 바깥 표만 읽고 내부 표를 버리면 정작 세부 조건이 사라집니다.

AI HWP Reader는 부모 셀에 `⟨표 안의 표⟩` 위치를 남기고 중첩 표를 별도로 렌더링합니다.

```text
[표 안의 표 · 3행 2열]
| 세부항목 | 금액 |
|---|---:|
| A | 100 |
```

### 3. 화면에서 안 보이는 메모도 읽습니다

한글의 메모는 본문 텍스트와 별개로 저장됩니다. 검토자가 남긴 “이 숫자 다시 확인”, “최신본으로 교체” 같은 지시가 일반 텍스트 추출에서 빠질 수 있습니다.

AI HWP Reader는 메모를 `[메모]`로 분리합니다.

### 4. 변경 내용 추적도 최종본과 구분합니다

HWP 변경추적 정보는 `BodyText`와 별도의 `ViewText/Section#`에 저장됩니다. AI HWP Reader는 **최종 본문은 최종본대로 읽고**, 변경추적의 추가·삭제 range는 따로 꺼냅니다.

즉 AI에게 “현재 문서가 무엇을 말하는지”와 “어디를 고쳤는지”를 함께 줄 수 있습니다.

---

## ZIP도 그냥 올리세요

사용자가 압축을 풀 필요가 없습니다.

```text
보고자료.zip
├── 01_영업보고서.hwp
├── 02_준법체크.hwpx
└── 하위폴더/
    └── 03_계약서.hwp
```

AI HWP Reader는 ZIP 안에서 `.hwp` / `.hwpx`만 찾아 **디스크에 다시 풀지 않고 메모리에서 직접 파싱**합니다.

AI에게는 파일 경계를 유지해서 전달합니다.

```text
======================================================================
01_영업보고서.hwp
======================================================================
...

======================================================================
02_준법체크.hwpx
======================================================================
...
```

여러 문서를 한 번에 비교하거나 공통 항목을 뽑는 작업에 바로 쓸 수 있습니다.

---

## 왜 AI 채팅용 `SKILL.md`가 핵심인가

이 프로젝트의 1순위 사용자는 Python 개발자가 아닙니다.

**HWP를 받은 직장인이 ChatGPT, Claude, Gemini에게 바로 일을 시키는 것**이 기본 사용 시나리오입니다.

그래서 `SKILL.md`는 단순 설명 문서가 아닙니다.

- 파서 전체 코드 포함
- 외부 패키지 필요 없음
- 첨부파일의 실제 샌드박스 경로를 찾아 실행하도록 지시
- ZIP이면 내부 HWP/HWPX 자동 탐색
- 표·중첩 표·메모·변경추적을 놓치지 않도록 지시
- 실행하지 못했으면 읽은 척하지 않도록 지시
- 파싱 후 요약·검토·비교·계산 등 **사용자가 원한 실제 업무까지 이어서 수행**하도록 지시

즉 `SKILL.md` 하나가 **AI에게 HWP 읽는 법을 그 자리에서 장착하는 파일**입니다.

---

## 개발자라면

PyPI 패키지와 CLI는 `ai-hwp-reader`입니다. Python import는 `hwp_reader` 그대로이고, 예전 `hwp-reader` 명령도 함께 깔려 계속 동작합니다.

### 설치

```bash
pip install ai-hwp-reader
```

기본 런타임 의존성은 **0개**입니다.

### Python

```python
from hwp_reader import read, render

blocks = read("계약서.hwp")
print(render(blocks, "md"))
```

ZIP까지 한 번에:

```python
from hwp_reader import read_documents, render_documents

documents = read_documents("보고자료.zip")
print(render_documents(documents, "md"))
```

반환 블록 예시:

```python
{"type": "text", "text": "..."}

{
    "type": "table",
    "rows": 9,
    "cols": 5,
    "grid": [[...], ...],
    "cells": [...],
    "nested_tables": [...],
}

{"type": "memo", "text": "최신 자료 기준으로 업데이트해주세요."}

{
    "type": "revision",
    "kind": "insert",          # 또는 delete
    "text": "수정된 문구",
    "section": 2,
}
```

### CLI

```bash
ai-hwp-reader 문서.hwp --format md
ai-hwp-reader 문서.hwpx --format json
ai-hwp-reader 문서묶음.zip --format md
ai-hwp-reader 문서.hwp --tables-only
ai-hwp-reader 문서.hwp --memos-only
ai-hwp-reader 문서.hwp --revisions-only
ai-hwp-reader ./폴더 -r
```

### MCP

```bash
pip install "ai-hwp-reader[mcp]"
```

Claude Desktop·Cursor 등의 MCP 클라이언트에서 로컬 문서를 읽을 때 사용할 수 있습니다. MCP 도구도 읽기 전용입니다.

---

## 검증 철학: “에러 없음”보다 “조용히 틀리지 않음”

HWP 파싱은 **에러가 나는 것보다 틀린 값을 멀쩡한 값처럼 내놓는 것이 더 위험합니다.**

그래서 다음을 회귀시험으로 고정합니다.

- HWP TABLE 셀 좌표 오프셋
- 병합 셀의 `rowspan` / `colspan`
- 2단 헤더 열 밀림 방지
- HWP 제어문자의 1워드 / 8워드 폭
- UTF-16 서로게이트 쌍
- 잔여 C0 제어문자 제거
- HWPX 주소 없는 셀의 병합영역 회피
- 표 안 문단의 본문 중복 방지
- **표 안의 표 보존**
- 숨은 메모 추출
- 문단 중간 메모의 앞뒤 본문 순서
- **ViewText 변경추적 추가/삭제 range**
- HWP/HWPX 다중 섹션 숫자 순서
- Markdown `|` 이스케이프
- HWP FileHeader 시그니처 검증
- 잘린 레코드·셀 정보·손상 XML 명시적 실패
- 비정상적으로 큰 표의 메모리 할당 방지
- **ZIP 내부 HWP/HWPX 자동 탐색**
- `SKILL.md`와 단일 파일 배포본이 정본 소스와 일치하는지 확인

CI는 Python 3.9~3.13, Linux·macOS·Windows에서 실행합니다.

실제 업무 문서는 회귀검증에 사용하되 저장소에는 넣지 않습니다. 공개 테스트는 `tests/`의 생성 fixture만 사용합니다.

---

## 성능과 프라이버시

- 일반적인 문서는 **약 0.1초/문서** 수준으로 파싱합니다.
- 기본 파서는 네트워크 요청을 하지 않습니다.
- HWP/HWPX를 읽기만 하며 원본을 수정하거나 다시 저장하지 않습니다.
- 웹 AI에서 사용할 때도 `SKILL.md`는 문서를 외부 서비스로 다시 업로드하지 말고 현재 실행환경 안에서 처리하도록 지시합니다.

---

## 프로젝트 구조

```text
SKILL.md                    AI 채팅창에 첨부하는 1순위 배포본
skill/hwp_reader_single.py  외부 의존성 없는 단일 파일 파서
hwp_reader/parser.py        HWP 5.0 / HWPX 파서
hwp_reader/_ole.py          표준 라이브러리 OLE/CFB 리더
hwp_reader/cli.py           CLI
hwp_reader/mcp_server.py    선택형 MCP 서버
tools/build_single.py       단일 파일 + SKILL.md 생성 정본
docs/hwp-format.md          HWP 파싱 함정과 구현 노트
tests/                      생성 fixture 기반 회귀시험
```

`SKILL.md`와 `skill/hwp_reader_single.py`의 파서 코드는 손으로 따로 관리하지 않습니다. `tools/build_single.py`가 정본 소스에서 생성합니다.

---

## 이름에 대하여

**프로젝트/제품:** AI HWP Reader  
**PyPI:** `ai-hwp-reader`  
**Python:** `hwp_reader`

예전 `hwp-reader`가 “파일을 읽는 라이브러리”였다면, **AI HWP Reader는 “당신의 AI가 HWP를 읽고 일을 하게 만드는 도구”**입니다.

---

## 라이선스

MIT

한글과컴퓨터가 공개한 HWP 5.0 / OWPML 문서 형식을 근거로 구현했습니다.
