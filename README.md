# AI HWP Reader

### 이제 당신의 AI가 한글(HWP/HWPX)을 읽고, 그 안의 **표·숫자·숨은 메모까지 가지고 일을 합니다.**

**ChatGPT · Claude · Gemini를 위한 AI-native HWP/HWPX reader.**  
한컴 설치 없이 · 외부 런타임 의존성 없이 · 원본 수정 없이

[![PyPI](https://img.shields.io/pypi/v/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![Python](https://img.shields.io/pypi/pyversions/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![tests](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[English](README.en.md)

> 아래아한글 · 아래한글 · 한글 · 한컴 · 한글과컴퓨터 문서를 AI에게 넘길 때, 사람이 먼저 PDF나 텍스트로 바꿔 주는 대신 **AI가 직접 파서를 실행해 원문 구조를 읽게 하는 것**이 이 프로젝트의 목적입니다.

## HWP를 “열어보는 것”이 아니라, AI가 HWP로 일을 하게 합니다

기존 흐름은 번거롭습니다.

```text
HWP → 사람이 한컴으로 열기 → PDF/텍스트로 변환 → AI에 다시 업로드 → 질문
```

AI HWP Reader가 노리는 흐름은 이렇습니다.

```text
HWP/HWPX → AI가 파서 실행 → 본문 + 표 + 메모를 구조대로 확보 → 바로 분석·검토·요약
```

코드 실행이 가능한 AI 환경이라면, `SKILL.md` 하나를 붙여넣고 문서를 올리는 것으로 시작할 수 있습니다. 파서는 Python 표준 라이브러리만 사용하고 네트워크 요청을 하지 않습니다.

이제 AI에게 이런 일을 바로 시킬 수 있습니다.

```text
이 펀드 제안서에서 결성액, 출자요청액, 존속기간, 관리보수, 성과보수만 표로 정리해줘.
이 준법 체크리스트에서 투자제한 리스크와 확인이 필요한 항목만 뽑아줘.
이 계약서의 우선매수권, 공동매도권, 양도제한 조항을 비교해줘.
이 예산표 숫자 합계를 검산하고 이상한 칸이 있으면 알려줘.
본문 말고 검토자가 남긴 메모만 모아줘.
```

## 설치 없이 3단계

터미널도, Python 설치도, `pip install`도 필요 없습니다.

1. [SKILL.md](SKILL.md)를 열고 **전체를 복사**합니다.
2. ChatGPT·Claude·Gemini 같은 코드 실행형 AI 대화창에 붙여넣고 `.hwp` 또는 `.hwpx` 파일을 올립니다.
3. **“이거 줘”**, **“요약해줘”**, **“표의 숫자 검산해줘”**처럼 바로 일을 시킵니다.

`SKILL.md`에는 파서 전체와 **설명만 하지 말고 실제 첨부파일을 파싱하라**는 실행 지시가 함께 들어 있습니다. 실행 기능이 없는 환경에서는 읽은 척하지 않고 그 사실을 알리도록 되어 있습니다.

여러 파일도 한 번에 처리할 수 있습니다.

```bash
python hwp_reader_single.py 계약서.hwp 정관.hwp 신청서.hwpx
```

## 왜 AI에는 “표를 살리는 것”이 중요할까

한국의 공문, 투자제안서, 준법 체크리스트, 예산서, 견적서, 계약서, 신청서에는 핵심 정보가 표 안에 들어가는 경우가 많습니다. 텍스트만 뽑는 경로가 표를 놓치면 문서를 읽은 것처럼 보이면서도 **금액, 지분율, 조건, 일정, 평가결과**가 빠질 수 있습니다.

```text
◎ 투자 개요
<표>

◎ 주요 조건
<표>
```

AI가 위 텍스트만 받으면 중요한 내용을 근거로 쓸 수 없습니다.

AI HWP Reader는 셀의 행·열 주소와 병합 범위를 기준으로 표 격자를 복원합니다.

```text
| 품목 | 규격 | 수량 | 단가 |  | 금액 |  |
|---|---|---|---|---|---|---|
|  |  |  | 정가 | 할인가 | 공급가 | 부가세 |
| 사무용 의자 | KS-320 | 12 | 180,000 | 162,000 | 1,944,000 | 194,400 |
```

본문에 보이지 않는 검토 메모도 별도 블록으로 보존합니다.

```text
[메모] 최신 자료 기준으로 업데이트해주세요.
```

## AI가 놓치기 쉬운 구조를 의도적으로 보존합니다

| 문제 | AI HWP Reader의 처리 |
|---|---|
| 병합된 2~3단 헤더 | `row`·`col`·`rowspan`·`colspan`으로 원래 위치 복원 |
| 표 안의 표 | 중첩 표 내용을 부모 셀에 `[중첩표]`로 보존하고 구조도 함께 유지 |
| 숨은 메모(주석) | 메모 위치와 실제 메모 본문을 분리해 추출 |
| 여러 Section | `Section10`이 `Section2`보다 앞서지 않도록 숫자 순서로 정렬 |
| 잘못 붙은 확장자 | `.hwp`/`.hwpx` 이름보다 실제 컨테이너를 보고 판별 |
| 손상된 문서 | 일부만 읽고 성공한 척하지 않고 명시적으로 실패 |
| Markdown 표의 `|` | 셀 내부 문자를 이스케이프해 열 구조 유지 |
| 원본 문서 | **읽기 전용**. 수정·저장 기능 없음 |

HWP 5.0의 OLE/CFB 컨테이너 리더까지 직접 포함하므로 기본 파서의 **외부 런타임 의존성은 0개**입니다.

## AI용으로 설계한 이유

이 프로젝트는 “HWP를 Python으로 파싱할 수 있다”에서 끝내지 않습니다. 목표는 **AI가 문서를 읽은 뒤 바로 일을 수행할 수 있는 입력**을 만드는 것입니다.

그래서 다음을 우선합니다.

- **구조 보존**: 숫자가 들어 있는 표의 열 위치가 밀리지 않아야 합니다.
- **누락 방지**: 본문 밖 메모와 중첩 표도 AI 입력에서 사라지면 안 됩니다.
- **문서 순서 유지**: 앞뒤 문맥이 바뀌면 요약과 판단도 바뀝니다.
- **실패를 크게**: 조용한 부분 성공보다 명시적 오류가 안전합니다.
- **오프라인 실행**: AI 샌드박스에서 인터넷이나 추가 패키지 없이 실행할 수 있어야 합니다.
- **읽기 전용**: 원본 HWP/HWPX를 건드리지 않습니다.

## 지원 범위

| 항목 | 지원 |
|---|---|
| HWP 5.0 본문 | ✅ |
| HWP 5.0 표·병합 셀 | ✅ |
| HWP 메모(주석) | ✅ |
| HWPX 본문·표 | ✅ |
| HWPX 중첩 표 내용 | ✅ |
| HWPX 메모 | ✅ |
| 잘못 붙은 `.hwp`/`.hwpx` 확장자 자동 판별 | ✅ |
| 암호 문서 | ❌ 암호를 풀고 다시 저장해야 합니다. |
| 한컴 수식 편집기 수식의 완전한 텍스트 복원 | ❌ |
| 스캔 이미지 OCR | ❌ |
| HWP 3.0 등 옛 포맷 | ❌ |
| 문서 쓰기·수정 | ❌ |

## 개발자라면

브랜드는 **AI HWP Reader**이고, 호환성을 위해 PyPI 패키지·Python import·CLI 이름은 기존 `hwp-reader` / `hwp_reader`를 유지합니다.

### 설치

```bash
pip install hwp-reader
```

### Python

```python
from hwp_reader import read, render

blocks = read("문서.hwp")
print(render(blocks, "md"))
```

`read()`는 문서 순서대로 블록을 반환합니다.

```python
{"type": "text",  "text": "..."}
{"type": "table", "rows": 9, "cols": 5, "grid": [[...], ...], "cells": [...]}
{"type": "memo",  "text": "최신 자료 기준으로 업데이트해주세요."}
```

표의 `cells`에는 `row`, `col`, `rowspan`, `colspan`, `text`가 들어 있습니다. HWPX 셀 안에 중첩 표가 있으면 해당 셀에 `nested_tables`도 추가됩니다.

### CLI

```bash
hwp-reader 문서.hwp
hwp-reader 문서.hwp --format md
hwp-reader 문서.hwp --tables-only
hwp-reader 문서.hwp --memos-only
hwp-reader ./폴더 -r
hwp-reader ./폴더 --format md -o ./out
hwp-reader 문서.hwp --format json
```

```text
hwp-reader [--format text|md|json] [--tables-only] [--memos-only]
           [-r|--recursive] [-o|--out 경로] [--version] 대상 [대상 ...]
```

## Claude Desktop·Cursor MCP

로컬 파일 경로를 AI 클라이언트에 직접 넘기고 싶다면 선택 기능을 설치합니다.

```bash
pip install "hwp-reader[mcp]"
```

```json
{
  "mcpServers": {
    "hwp-reader": {
      "command": "hwp-reader-mcp"
    }
  }
}
```

도구는 모두 읽기 전용입니다.

| 도구 | 반환 내용 |
|---|---|
| `hwp_read` | 본문·표·메모를 문서 순서대로 반환 |
| `hwp_tables` | 표를 JSON 격자로 반환 |
| `hwp_memos` | 숨은 메모만 반환 |

## 검증 철학: “에러 없음”보다 “조용히 틀리지 않음”

HWP 파싱에서 위험한 것은 예외보다 **그럴듯하게 틀린 결과**입니다. AI는 빠진 숫자나 밀린 열도 자연스럽게 해석해 버릴 수 있기 때문입니다.

회귀 시험은 다음 종류의 실패를 집중적으로 고정합니다.

- HWP 셀 좌표 오프셋과 병합 범위
- HWP 제어문자의 실제 바이트 폭과 잔여 C0 제어문자
- UTF-16 서로게이트 쌍
- HWP FileHeader 실제 시그니처
- HWP/HWPX 다중 섹션 숫자 순서
- HWPX 셀 주소가 없는 경우의 병합 회피
- HWPX 중첩 표 누락 방지
- 표 안 문단의 본문 중복 방지
- 문단 안 메모의 위치·중복 방지
- Markdown 셀 이스케이프
- 손상 레코드·비정상 표 크기를 부분 성공으로 처리하지 않기
- 생성된 `skill/hwp_reader_single.py`와 `SKILL.md`가 정본 소스와 일치하는지 확인

CI는 Python 3.9~3.13과 Linux·macOS·Windows에서 실행합니다.

## 속도

일반적인 업무 문서는 **문서 하나에 약 0.1초** 수준으로 읽습니다.

## 개발 원칙

- **읽기 전용**: HWP/HWPX 쓰기·수정 기능을 넣지 않습니다.
- **실문서 비공개**: 실제 업무 문서는 회귀검증에만 사용하고 저장소에 커밋하지 않습니다.
- **생성물 단일 정본**: `skill/hwp_reader_single.py`와 `SKILL.md`는 `tools/build_single.py`가 정본 소스에서 생성합니다.
- **오프라인 파싱**: 파서 자체는 네트워크 요청을 하지 않습니다.
- **AI 입력 품질 우선**: 기능 수보다 표·메모·문서 순서를 정확하게 보존하는 것을 우선합니다.

저수준 HWP/HWPX 파싱 메모는 [docs/hwp-format.md](docs/hwp-format.md), 변경 내역은 [CHANGELOG.md](CHANGELOG.md)를 참고하세요.

## 제보·기여

사내 문서를 공개할 수 없다면 원본을 올리지 않아도 됩니다. 어떤 표가 어떻게 어긋나는지, 누락된 메모가 있는지, 오류 메시지와 최소 재현 조건만으로도 도움이 됩니다.

특히 다음 제보를 환영합니다.

- 병합 구조가 어긋나는 표
- 표 안의 표가 누락되는 문서
- 메모가 잡히지 않는 문서
- 글자가 깨지는 문단
- 여러 섹션의 순서가 이상한 문서
- HWPX에서 본문이 중복되는 경우

## 검색어

AI HWP Reader, ChatGPT HWP, 챗지피티 HWP, 챗지피티 한글파일, Claude HWP, Gemini HWP, AI 한글파일, 아래아한글 AI, 아래한글 AI, 한컴 AI, 한글과컴퓨터 HWP, HWP 파서, HWP 텍스트 추출, HWP 표 추출, HWPX 파싱, 맥에서 HWP 읽기, 한컴 없이 한글 문서 열기, Python HWP, HWP MCP, HWP LLM/RAG 전처리.

한글과컴퓨터가 공개한 한글문서파일형식(HWP) 5.0 규격을 근거로 구현했습니다.

## 라이선스

MIT
