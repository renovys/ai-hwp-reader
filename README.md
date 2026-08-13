# hwp-reader — ChatGPT에서 HWP 읽기 / 한컴 없는 HWP·HWPX 파서

**한컴 없이 HWP·HWPX를 읽습니다. 표는 병합 위치까지, 숨은 메모까지.**

[![PyPI](https://img.shields.io/pypi/v/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![Python](https://img.shields.io/pypi/pyversions/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![tests](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[English](README.en.md)

## 설치 없이 ChatGPT·Claude·Gemini에서 쓰기

터미널도, Python 설치도, `pip install`도 필요 없습니다.

1. [SKILL.md](SKILL.md)를 열고 **전체를 복사**합니다.
2. ChatGPT·Claude·Gemini 대화창에 붙여넣은 뒤 `.hwp` 또는 `.hwpx` 파일을 올립니다.
3. **“이거 줘”** 또는 문서에 대해 알고 싶은 내용을 입력합니다.

`SKILL.md`에는 외부 의존성이 없는 파서 전체와 **실제로 코드를 실행하라는 지시**가 함께 들어 있습니다. 챗봇이 코드를 실행할 수 있는 환경이라면 첨부파일을 그 환경 안에서 읽고 결과를 보여줍니다. 파서 자체는 네트워크 요청을 하지 않습니다.

> 모델이 코드 설명만 하고 문서를 읽지 않는다면 `SKILL.md` 첫 부분의 실행 지시를 다시 포함해 붙여넣으세요. 실행 기능이 없는 챗봇은 실제로 읽을 수 없으며, `SKILL.md`는 그 경우 읽은 척 답하지 말도록 명시합니다.

결과는 다음처럼 나옵니다.

```text
| 품목 | 수량 | 금액 |
|---|---|---|
| 사무용 의자 | 12 | 1,944,000 |

[메모] 최신 자료 기준으로 업데이트해주세요.
```

여러 파일을 한 번에 처리할 수도 있습니다. 단일 파일 배포본 `skill/hwp_reader_single.py`는 여러 문서 경로를 인자로 받습니다.

```bash
python hwp_reader_single.py 계약서.hwp 정관.hwp 신청서.hwpx
```

## 왜 필요한가

한국 관공서·학교·기업 문서는 공문, 사업계획서, 견적서, 계약서, 신청서처럼 **핵심 내용이 표 안에 들어 있는 경우가 많습니다.** 일반 텍스트 추출이 표 내용을 놓치면 문서를 읽은 것처럼 보이면서 숫자와 조건만 빠질 수 있습니다.

```text
◎ 사업 개요
<표>

◎ 예산 집행 내역
<표>
```

hwp-reader는 표의 행·열 주소와 병합 범위를 읽어 격자를 복원합니다.

```text
[표]
(단위: 원) |  |  |  |  |  |
품목        | 규격   | 수량 | 단가    |         | 금액      |
            |        |      | 정가    | 할인가  | 공급가    | 부가세
사무용 의자 | KS-320 | 12   | 180,000 | 162,000 | 1,944,000 | 194,400
```

## 핵심 기능

### 병합 셀 위치 보존

HWP와 HWPX에 기록된 셀 좌표와 `rowspan`·`colspan`을 사용합니다. 2~3단 헤더에서도 아래 행의 값이 왼쪽으로 밀리지 않습니다. 저수준 오프셋과 파싱 함정은 [HWP 형식 노트](docs/hwp-format.md)에 정리되어 있습니다.

### 숨은 메모(주석) 추출

본문에 보이지 않는 검토 메모도 별도 블록으로 가져옵니다. HWP에서 메모가 달린 셀은 `⟨메모⟩`로 위치를 남기고 실제 메모 본문은 `[메모]`로 출력합니다.

### 외부 의존성 0

기본 파서는 Python 표준 라이브러리만 사용합니다. HWP 5.0의 OLE/CFB 컨테이너 리더도 포함되어 있어 `olefile`이 필요하지 않습니다.

### 읽기 전용

문서를 읽기만 합니다. 원본 HWP/HWPX를 수정하거나 다시 저장하는 기능은 넣지 않습니다.

### 약 0.1초/문서

일반적인 업무 문서는 문서 하나를 읽는 데 약 0.1초입니다.

## 지원 범위

| 항목 | 지원 |
|---|---|
| HWP 5.0 본문 | ✅ |
| HWP 5.0 표·병합 셀 | ✅ |
| HWP 메모(주석) | ✅ |
| HWPX 본문·표 | ✅ |
| HWPX 메모 | ✅ |
| 잘못 붙은 `.hwp`/`.hwpx` 확장자 자동 판별 | ✅ |
| 암호 문서 | ❌ 암호를 풀고 다시 저장해야 합니다. |
| 한컴 수식 편집기 수식의 텍스트 변환 | ❌ |
| 스캔 이미지 OCR | ❌ |
| HWP 3.0 등 옛 포맷 | ❌ |
| 문서 쓰기·수정 | ❌ |

## 개발자용

### 설치

```bash
pip install hwp-reader
```

기본 설치는 외부 런타임 의존성을 추가하지 않습니다.

### CLI

```text
hwp-reader [--format text|md|json] [--tables-only] [--memos-only]
           [-r|--recursive] [-o|--out 경로] [--version] 대상 [대상 ...]
```

```bash
hwp-reader 문서.hwp
hwp-reader 문서.hwp --format md
hwp-reader 문서.hwp --tables-only
hwp-reader 문서.hwp --memos-only
hwp-reader ./폴더 -r
hwp-reader ./폴더 --format md -o ./out
hwp-reader 문서.hwp --format json
```

### Python API

```python
from hwp_reader import read, render

blocks = read("문서.hwp")
print(render(blocks, "md"))

for block in blocks:
    if block["type"] == "table":
        print(block["grid"])
    elif block["type"] == "memo":
        print("메모:", block["text"])
```

`read()`는 문서 순서대로 블록을 반환합니다.

```python
{"type": "text",  "text": "..."}
{"type": "table", "rows": 9, "cols": 5, "grid": [[...], ...], "cells": [...]}
{"type": "memo",  "text": "최신 자료 기준으로 업데이트해주세요."}
```

표의 `cells`에는 `row`, `col`, `rowspan`, `colspan`, `text`가 들어 있습니다. 병합 셀의 값은 `grid` 좌상단에만 둡니다.

## Claude Desktop·Cursor MCP

로컬 클라이언트에서 파일 경로를 직접 넘기고 싶다면 선택 기능을 설치합니다.

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

기본 전송은 로컬 `stdio`입니다. HTTP가 필요하면 다음처럼 실행합니다.

```bash
hwp-reader-mcp --transport http --port 8000
```

## 정확성에 신경 쓴 부분

HWP 파서는 실패보다 **그럴듯하게 틀린 결과**가 더 위험합니다. 그래서 다음 항목을 회귀 시험으로 고정합니다.

- HWP 셀 좌표 오프셋과 병합 범위
- HWP 제어문자의 실제 바이트 폭과 잔여 C0 제어문자 정리
- UTF-16 서로게이트 쌍
- HWP/HWPX 다중 섹션의 숫자 순서
- HWPX 셀 주소가 없는 경우의 병합 회피
- 표 안 문단의 본문 중복 방지
- 문단 안 메모의 위치·중복 방지
- Markdown 셀의 `|` 이스케이프
- 손상된 레코드를 조용히 일부만 읽지 않고 명시적으로 실패
- 생성된 `skill/hwp_reader_single.py`와 `SKILL.md` 코드블록이 정본 소스와 일치하는지 확인

CI는 Python 3.9~3.13과 Linux·macOS·Windows에서 실행합니다.

## 개발 원칙

- **읽기 전용**: 문서 쓰기·수정 기능을 추가하지 않습니다.
- **실문서 비공개**: 테스트 fixture는 코드로 생성하며 실제 업무 HWP/HWPX를 저장소에 넣지 않습니다.
- **생성물 단일 정본**: `skill/hwp_reader_single.py`와 `SKILL.md`의 Python 코드블록은 `tools/build_single.py`가 `hwp_reader/_ole.py`와 `hwp_reader/parser.py`에서 생성합니다.
- **오프라인 파싱**: 파서 자체는 네트워크 요청을 하지 않습니다.

## 제보·기여

사내 문서를 공개할 수 없다면 원본을 올리지 않아도 됩니다. 어느 표가 어떻게 어긋나는지, 오류 메시지와 재현 가능한 최소 조건을 이슈에 적어 주세요.

특히 다음 제보가 유용합니다.

- 병합 구조가 어긋나는 표
- 메모가 잡히지 않는 문서
- 글자가 깨지는 문단
- 여러 섹션의 순서가 이상한 문서
- HWPX에서 본문이 중복되는 경우

변경 내역은 [CHANGELOG.md](CHANGELOG.md)를 참고하세요.

## 관련 검색어

ChatGPT HWP, 챗지피티 한글파일, Claude HWP, Gemini HWP, HWP 파서, HWP 텍스트 추출, HWP 표 추출, 맥에서 HWP 읽기, 한컴 없이 한글 문서 열기, Python HWP, HWPX 파싱, HWP MCP, HWP LLM/RAG 전처리.

한글과컴퓨터가 공개한 한글문서파일형식(HWP) 5.0 규격을 근거로 구현했습니다.

## 라이선스

MIT
