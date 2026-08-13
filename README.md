# hwp-reader — HWP 파서 / 한컴 문서 읽기

**한컴 없이 HWP 파일을 읽습니다. 표는 병합 구조까지, 숨은 메모까지.**

[![PyPI](https://img.shields.io/pypi/v/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![Python](https://img.shields.io/pypi/pyversions/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![tests](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> HWP · HWPX · 한컴 · 한컴오피스 · 한글파일 · 아래아한글 · 한글과컴퓨터 · HWP 파싱 · HWP 텍스트 추출 · HWP 표 추출

[English](README.en.md)

## 설치 없이 3단계

터미널도, 파이썬도, 패키지 설치도 필요 없습니다.

1. [SKILL.md](SKILL.md)를 브라우저에서 열고 **전체를 복사**합니다.
2. ChatGPT·Claude·Gemini 대화창에 **붙여넣고**, HWP 파일을 올립니다.
3. **"이거 줘"**라고 입력합니다.

[SKILL.md](SKILL.md)에는 파서 전체가 코드블록으로 들어 있습니다. 단일 파일 배포본은
`skill/hwp_reader_single.py`입니다. 파서의 외부 의존성은 0개이므로 파이썬 파일 하나로
챗봇 코드 실행 환경에서 그대로 실행됩니다. 챗봇 샌드박스에는 인터넷이 없어 외부 패키지를
설치할 수 없지만, 이 파서는 외부 패키지를 사용하지 않으므로 문제가 되지 않습니다.

결과는 다음처럼 나옵니다.

```text
[표]
품목 | 수량 | 금액
사무용 의자 | 12 | 1,944,000
[메모] 최신 자료 기준으로 업데이트해주세요.
```

## 이런 일 때문에 오셨다면

- 챗봇에 HWP를 올렸더니 표가 사라졌습니다.
- 견적서나 예산서의 숫자가 틀리게 나왔습니다.
- 맥이라 한글이 없고, 한컴 없이 HWP를 읽어야 합니다.

## 왜 표가 사라지나

한국 관공서·학교·기업 문서는 공문, 사업계획서, 견적서, 계약서, 회의록, 신청 서식처럼
표 안에 내용이 들어 있는 경우가 많습니다. 일반적인 텍스트 추출은 표를 다음처럼
`<표>` 하나로 남길 수 있습니다.

```
◎ 사업 개요
<표>

◎ 예산 집행 내역
<표>
```

문서를 읽은 것처럼 보여도 표의 내용은 사라진 상태입니다. 사람이 누락을 알아채기 전에
챗봇이 잘못된 답을 낼 수 있습니다.

hwp-reader는 같은 문서를 다음처럼 읽습니다.

```
[표]
(단위: 원) |  |  |  |  |  |
품목        | 규격   | 수량 | 단가    |         | 금액      |
            |        |      | 정가    | 할인가  | 공급가    | 부가세
사무용 의자 | KS-320 | 12   | 180,000 | 162,000 | 1,944,000 | 194,400
```

2단 헤더와 병합된 셀의 위치가 유지되므로 숫자가 옆 칸으로 밀리지 않습니다.

## 세 가지가 다릅니다

### 1. 병합 셀을 읽습니다

한국 문서의 표는 헤더가 2~3단으로 병합된 경우가 많습니다. 셀 위치를 놓치면 숫자가
한 칸씩 밀리지만 값 자체는 그럴듯해 보여 오류를 알아채기 어렵습니다.

hwp-reader는 원본에 기록된 행·열 위치와 병합 범위를 기준으로 표 격자를 복원합니다.
내부 표기와 오프셋 단위는 [HWP 형식 문서](docs/hwp-format.md)에 정리되어 있습니다.

### 2. 숨은 메모를 읽습니다

한글 문서에는 본문에 보이지 않는 **메모(주석)** 가 있습니다. 검토자가 최신 자료로
수정하라는 지시를 메모에 남기기도 하지만, 일반 텍스트 추출에서는 이 내용이 빠집니다.

본문에는 메모가 달린 위치가 `⟨메모⟩`로 표시되고, 메모 내용은 문서 순서에 따라 별도의
`[메모]` 블록으로 보존됩니다.

```text
[메모] 최신 자료 기준으로 업데이트해주세요.
[메모] 단가표 개정본으로 다시 계산 부탁드립니다.
```

### 3. 빠릅니다

문서 하나를 읽는 데 약 0.1초입니다.

## Claude Desktop·Cursor에 붙이기

매번 SKILL.md를 대화창에 붙여넣기 싫은 사람은 Claude Desktop·Cursor에 MCP로 등록할 수
있습니다. 이 방법은 로컬 문서를 클라이언트가 직접 읽게 합니다.

`[mcp]` 추가 기능은 선택 사항입니다. MCP를 사용할 때만 개발자용 절의 추가 설치를
진행하면 됩니다. 이 추가 기능에는 MCP 파이썬 SDK와 HTTP 서버 스택이 포함되어 29개
패키지가 함께 설치됩니다. 기본 파서는 외부 의존성이 0개입니다.

Claude Desktop과 Cursor의 MCP 설정 JSON에 다음 내용을 넣습니다.

```json
{
  "mcpServers": {
    "hwp-reader": {
      "command": "hwp-reader-mcp"
    }
  }
}
```

## 안 되는 것

`.hwp`(한글 5.0)와 `.hwpx`는 읽지만, 다음 기능은 지원하지 않습니다.

| 항목 | 결과 |
|---|---|
| 암호 문서 | ❌ 암호를 풀고 다시 저장한 문서가 필요합니다. |
| 한컴 수식 편집기 수식 | ❌ 텍스트로 추출하지 않습니다. |
| 스캔 이미지 | ❌ 그림이므로 OCR이 필요합니다. |
| HWP 3.0 등 옛 포맷 | ❌ 지원하지 않습니다. |
| 문서 쓰기·수정 | ❌ 읽기 전용이며 쓰기 기능이 없습니다. |

## 개발자용

터미널, 파이썬 API, MCP로 직접 사용할 때의 안내입니다.

### 설치

```bash
pip install hwp-reader
```

기본 파서는 외부 패키지 없이 동작합니다. `hwp-reader` 설치가 외부 패키지를 추가로
설치하지 않는 이유도 같습니다.

### 명령줄

명령은 파일 또는 폴더를 인자로 받으며, 여러 대상을 함께 지정할 수 있습니다.

```text
hwp-reader [--format text|md|json] [--tables-only] [--memos-only]
           [-r|--recursive] [-o|--out 경로] [--version] 대상 [대상 ...]
```

| 옵션 | 설명 |
|---|---|
| `--format text\|md\|json` | 출력 형식입니다. 기본값은 `text`입니다. |
| `--tables-only` | 표만 출력합니다. |
| `--memos-only` | 숨은 메모만 출력합니다. |
| `-r`, `--recursive` | 폴더를 하위 폴더까지 읽습니다. |
| `-o`, `--out 경로` | 결과를 파일 또는 폴더에 저장합니다. 폴더이면 문서마다 한 파일을 만듭니다. |
| `--version` | 버전을 출력합니다. |

```bash
hwp-reader 문서.hwp                    # 본문 + 표 + 메모
hwp-reader 문서.hwp --format md        # 마크다운 출력
hwp-reader 문서.hwp --tables-only      # 표만
hwp-reader 문서.hwp --memos-only       # 숨은 메모만
hwp-reader ./폴더 -r                   # 하위 폴더까지
hwp-reader ./폴더 --format md -o ./out # 파일로 저장
hwp-reader 문서.hwp --format json      # JSON 출력
```

### 파이썬 API

```python
from hwp_reader import read, render

blocks = read("문서.hwp")
markdown = render(blocks, "md")

for block in blocks:
    if block["type"] == "table":
        for row in block["grid"]:
            print(row)
    elif block["type"] == "memo":
        print("메모:", block["text"])
```

`read()`는 문서 순서대로 dict 목록을 반환합니다.

```python
{"type": "text",  "text": "..."}
{"type": "table", "rows": 9, "cols": 5, "grid": [[...], ...], "cells": [...]}
{"type": "memo",  "text": "최신 자료 기준으로 업데이트해주세요."}
```

`cells`의 각 항목에는 `row`, `col`, `rowspan`, `colspan`, `text`가 들어 있습니다.
병합된 셀의 값은 `grid`의 좌상단 위치에만 들어갑니다. `render(blocks, "text")`는
일반 텍스트를, `render(blocks, "md")`는 마크다운을 반환합니다.

### MCP 도구

MCP를 사용하려면 선택 기능을 추가합니다.

```bash
pip install "hwp-reader[mcp]"
```

`[mcp]`는 MCP 파이썬 SDK와 HTTP 서버 스택을 포함하며 29개 패키지를 설치합니다.
도구는 세 가지이고 모두 읽기 전용입니다. 파일 경로 또는 폴더 경로를 받습니다.

| 도구 | 반환 내용 |
|---|---|
| `hwp_read` | 본문·표·메모를 문서 순서대로 반환합니다. `format`은 `text` 또는 `md`입니다. |
| `hwp_tables` | 표만 JSON 격자로 반환합니다. |
| `hwp_memos` | 숨은 메모만 반환합니다. |

기본 전송은 로컬 `stdio`입니다.

### HTTP 전송

```bash
hwp-reader-mcp --transport http --port 8000
```

기본 주소는 `http://127.0.0.1:8000/mcp`입니다.

## 검증

- 파싱 함정 다섯 가지를 회귀 시험으로 고정했고, 수정 전 코드에서 먼저 실패함을 확인했습니다.
- OLE 리더는 `olefile`과 교차 검증해 모든 스트림 바이트가 일치합니다.
- 실제 업무 문서에서 의존성 제거 전후 출력이 동일합니다.
- Python 3.9~3.13 · 리눅스 · 맥 · 윈도우 CI에서 확인합니다.
- `pytest`로 재현할 수 있습니다.

## 기여

재현되는 문서를 함께 제보하면 원인을 확인하기 쉽습니다. 사내 문서라 제공하기 어렵다면
`hwp-reader 문서.hwp --format json`의 앞부분과 어느 표가 어떻게 어긋나는지만 적어도
됩니다.

다음 제보를 환영합니다.

- 병합 구조가 어긋나는 표
- 메모가 잡히지 않는 문서
- 글자가 깨져 나오는 문단
- HWPX에서 재현되는 문제

## 이런 걸 찾으셨다면

- 챗지피티에 한글파일 올리는 법
- 클로드 hwp 읽기
- 제미나이 hwp
- hwp 표가 안 읽힐 때
- 맥에서 hwp 여는 법
- ChatGPT·Claude·Gemini에 한글 파일 올리기
- 한컴 없이 한글 문서 열기
- 파이썬으로 HWP 파일 읽기, HWP 텍스트 추출, HWP 표 추출
- 리눅스 서버에서 HWP 처리, 맥에서 아래아한글 파일 읽기
- HWP를 LLM·RAG에 넣기 위한 전처리, HWP MCP 서버
- HWPX 파싱, 개방형 한글 문서(OWPML) XML 읽기

한글과컴퓨터가 공개한 한글문서파일형식(HWP) 5.0 규격을 근거로 구현했습니다.

## 라이선스

MIT
