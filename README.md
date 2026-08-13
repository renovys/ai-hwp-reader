# hwp-reader — HWP 파서 / 한컴 문서 읽기

**한컴 없이 HWP 파일을 읽습니다. 표는 병합 구조까지, 숨은 메모까지.**

[![PyPI](https://img.shields.io/pypi/v/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![Python](https://img.shields.io/pypi/pyversions/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![tests](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> HWP · HWPX · 한컴 · 한컴오피스 · 한글파일 · 아래아한글 · 한글과컴퓨터 · HWP 파싱 · HWP 텍스트 추출 · HWP 표 추출

[English](README.en.md)

## 이런 일 때문에 오셨다면

- 한글 파일을 ChatGPT에 올렸더니 표 내용이 통째로 빠졌습니다.
- 견적서나 예산서를 AI에 물었더니 숫자를 엉뚱하게 답합니다.
- 맥이라 한글이 설치되지 않았거나, 한컴 없이 HWP를 읽어야 합니다.

## 3분 만에 쓰기

웹 챗봇에 HWP를 올려야 할 때는 먼저 마크다운 파일로 변환합니다.

### 맥

Spotlight에서 `터미널`을 검색해 실행합니다. 단축키는 `⌘ + Space`입니다.

### 윈도우

시작 메뉴에서 `명령 프롬프트`를 검색해 실행합니다.

파이썬이 없다면 [python.org](https://www.python.org/downloads/)에서 Python 3.9 이상을
설치합니다. macOS에는 대개 파이썬이 이미 있습니다.

터미널에서 설치합니다.

```bash
pip install hwp-reader
```

윈도우에서 `pip`가 인식되지 않으면 다음 명령을 사용합니다.

```bat
py -m pip install hwp-reader
```

문서 한 개를 `.md` 파일로 저장합니다.

```bash
hwp-reader 문서.hwp --format md -o ./문서.md
```

실행 화면에는 다음과 같이 표시됩니다.

```text
$ hwp-reader 문서.hwp --format md -o ./문서.md
1개 문서를 ./문서.md에 저장했다
```

이제 생성된 `문서.md`를 ChatGPT·Claude·Gemini 웹 대화창에 끌어다 놓으면 됩니다.
문서 내용은 로컬에서 처리되며 네트워크 호출은 0건입니다.

여러 문서는 폴더 단위로 처리합니다. `변환본` 폴더를 먼저 만든 뒤 실행하면 문서마다
하나의 `.md` 파일이 생성됩니다.

```bash
mkdir 변환본
hwp-reader ./받은문서 --format md -o ./변환본
```

하위 폴더까지 포함하려면 `-r`을 추가합니다.

```bash
hwp-reader ./받은문서 -r --format md -o ./변환본
```

## Claude Desktop·Cursor에 붙이기

파일을 변환하지 않고 데스크톱 클라이언트가 로컬 문서를 직접 읽게 하려면 MCP 서버로
등록합니다.

```bash
pip install "hwp-reader[mcp]"
```

> **MCP를 안 쓰시면 이 줄은 필요 없습니다.** 기본 설치(`pip install hwp-reader`)의
> 의존성은 `olefile` 하나입니다. `[mcp]`를 붙이면 MCP 파이썬 SDK와 HTTP 서버 스택이
> 함께 설치되어 패키지 29개가 됩니다. MCP가 필요할 때만 추가 설치하도록 분리했습니다.

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

설정이 끝나면 클라이언트에서 파일 또는 폴더 경로를 hwp-reader에 전달할 수 있습니다.
제공하는 도구는 `hwp_read`, `hwp_tables`, `hwp_memos` 세 가지이며 모두 읽기 전용입니다.

## 터미널이 정 어려우시면

이 도구는 로컬 설치가 필요합니다. 별도의 웹 변환 서비스, GUI 앱, 설치 관리자는
제공하지 않습니다. 터미널을 사용할 수 없다면 현재 이 저장소만으로는 진행할 방법이
없습니다.

## 왜 또 만들었나

한국에서 사용하는 공문, 사업계획서, 견적서, 계약서, 회의록, 신청 서식, 학교 가정통신문은
표 안에 내용이 들어 있는 경우가 많습니다. 기존 방식으로 텍스트를 뽑으면 다음처럼 표가
`<표>` 하나로 사라집니다.

```
◎ 사업 개요
<표>

◎ 예산 집행 내역
<표>
```

성공한 것처럼 보이지만 내용이 통째로 사라진 상태입니다. 150KB짜리 문서가 5KB 텍스트로
줄어들면 이 문제를 의심해야 합니다. 사람이 누락을 알아채기 전에 LLM이 "특이사항 없음"과
같은 답을 낼 수 있습니다.

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

### 1. 병합된 셀을 제대로 읽습니다

한국 문서의 표는 헤더가 2~3단으로 병합된 경우가 많습니다. 셀 위치를 놓치면 숫자가
한 칸씩 밀리지만 값 자체는 그럴듯해 보여 오류를 알아채기 어렵습니다.

hwp-reader는 원본에 기록된 행·열 위치와 병합 범위를 기준으로 표 격자를 복원합니다.
내부 표기와 오프셋 단위가 왜 중요한지는 [docs/hwp-format.md](docs/hwp-format.md)에
정리되어 있습니다.

### 2. 숨은 메모를 뽑아냅니다

한글 문서에는 본문에 보이지 않는 **메모(주석)** 가 있습니다. 검토자가 최신 자료로
수정하라는 지시를 메모에 남기기도 하지만, 일반 텍스트 추출에서는 이 내용이 빠집니다.

```bash
$ hwp-reader ./받은문서 --memos-only

계획서_v3.hwp
  - 최신 자료 기준으로 업데이트해주세요.
정산서_최종.hwp
  - 단가표 개정본으로 다시 계산 부탁드립니다.
  - 이 항목은 담당 부서 확인 후 반영해주세요.
```

HWP 표 안에서 메모가 달린 자리는 본문에 `⟨메모⟩`로 표시됩니다. 일반 출력에서는
메모 내용도 `[메모]`가 붙은 별도 블록으로 문서 순서에 따라 보존됩니다.

### 3. 빠릅니다

실제 업무 문서 기준 문서 하나에 약 0.1초입니다.

| 방법 | 속도 | 표 내용 | 병합 구조 |
|---|---|---|---|
| **hwp-reader** | **문서 하나에 약 0.1초** | 보존 | 정확 |
| hwp5html 경유 | 느림 | 보존 | 정확 |
| hwp5txt | 빠름 | 표가 전부 소실 | — |

## 다른 도구를 쓰다 오셨다면

한글 문서를 다루는 도구는 용도에 따라 선택해야 합니다.

**이 도구가 맞는 경우**

- 파이썬 코드에서 직접 읽거나 MCP 없이 셸·cron·CI에서 폴더를 처리해야 합니다.
- 설치가 가벼워야 합니다. 기본 설치 의존성은 `olefile` 하나이며 Node.js가 필요하지
  않습니다.
- 폐쇄망·오프라인 서버에서 사용해야 합니다. 네트워크 호출은 0건입니다.
- 문서에 달린 검토 메모를 놓치면 안 됩니다.
- 금액이 들어 있는 병합 표를 부정확하게 읽는 것보다 읽지 않는 편이 나은 업무입니다.

**다른 도구가 더 나은 경우**

- 문서를 고치거나 표 행을 추가하거나 서식을 변경하거나 새 문서를 만들어야 합니다.
- 페이지를 이미지·SVG·HTML로 렌더링해야 합니다.
- 이미지·수식을 파일로 추출해야 합니다.
- 머리말·꼬리말·각주까지 필요합니다. hwp-reader는 본문·표·메모를 읽습니다.

hwp-reader는 읽기 전용이며 앞으로도 쓰기·수정 기능을 넣지 않습니다. 프로그램으로 한글
문서를 고칠 때 서식이 조용히 깨질 수 있으므로, 이 저장소는 문서를 정확히 읽는 일에
범위를 둡니다.

## 개발자용

### 명령줄

명령은 파일 또는 폴더를 인자로 받으며, 여러 대상을 함께 지정할 수도 있습니다.

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
hwp-reader ./폴더 --format md          # 표를 마크다운으로
hwp-reader ./폴더 --tables-only        # 표만
hwp-reader ./폴더 --memos-only         # 숨은 메모만
hwp-reader ./폴더 -r                   # 하위 폴더까지
hwp-reader ./폴더 --format md -o ./out # 파일로 저장
hwp-reader 문서.hwp --format json      # 프로그램으로 넘길 때
```

폴더를 지정하면 `.hwp`와 `.hwpx` 문서를 처리합니다. 실패한 파일은 이유와 함께
알립니다. 확장자가 실제 형식과 달라도 내용을 확인해 읽습니다.

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

`cells`에는 셀마다 `row`, `col`, `rowspan`, `colspan`, `text`가 들어 있습니다. 병합된
셀은 `grid`의 좌상단 위치에만 값이 들어갑니다. `render(blocks, "text")`는 일반 텍스트,
`render(blocks, "md")`는 마크다운 문자열을 반환합니다.

### MCP

MCP 설치는 기본 설치와 분리되어 있습니다. `[mcp]` 추가 설치에는 MCP 파이썬 SDK와
HTTP 서버 스택이 포함되어 총 29개 패키지가 설치됩니다. MCP를 사용하지 않으면
`pip install hwp-reader`만 필요합니다.

도구는 다음 세 가지이며 모두 읽기 전용입니다. 세 도구 모두 파일 경로와 폴더 경로를
받습니다.

| 도구 | 반환 내용 |
|---|---|
| `hwp_read` | 본문·표·메모를 문서 순서대로 반환합니다. `format`은 `text` 또는 `md`입니다. |
| `hwp_tables` | 표만 JSON 격자로 반환합니다. |
| `hwp_memos` | 숨은 메모만 반환합니다. |

기본 전송은 로컬 `stdio`입니다. HTTP 전송은 다음과 같이 실행합니다.

```bash
hwp-reader-mcp --transport http --port 8000
```

기본 주소는 `http://127.0.0.1:8000/mcp`입니다. MCP 파이썬 SDK 1.x의 `FastMCP`와
2.x의 `MCPServer`를 모두 지원합니다.

#### 클라이언트 설정

**Claude Code**

```bash
claude mcp add hwp-reader -- hwp-reader-mcp
```

**Codex CLI**

```bash
codex mcp add hwp-reader -- hwp-reader-mcp
```

**Gemini CLI** — `~/.gemini/settings.json`

```json
{
  "mcpServers": {
    "hwp-reader": { "command": "hwp-reader-mcp" }
  }
}
```

**VS Code (Copilot 에이전트 모드)** — `.vscode/mcp.json`

```json
{
  "servers": {
    "hwp-reader": { "command": "hwp-reader-mcp" }
  }
}
```

### 포맷별 지원

| | `.hwp` (한글 5.0) | `.hwpx` (OWPML) |
|---|---|---|
| 본문 | ✅ | ✅ |
| 표 (병합 구조 포함) | ✅ | ✅ |
| 숨은 메모 | ✅ | ✅ |
| 암호 문서 | 이유를 밝히고 멈춤 | 이유를 밝히고 멈춤 |
| 쓰기·수정 | ❌ (설계상 안 합니다) | ❌ (설계상 안 합니다) |

### 안 되는 것

| 상황 | 결과 |
|---|---|
| 암호가 걸린 문서 | 그렇다고 알려주고 멈춥니다. 암호를 풀고 다시 저장해야 합니다. |
| 한컴 수식 편집기 수식 | 텍스트로 나오지 않습니다. |
| 스캔해서 붙인 이미지 | 글자가 아니라 그림입니다. OCR이 필요합니다. |
| HWP 3.0 등 옛 포맷 | 지원하지 않습니다. |
| 문서 쓰기·수정 | 하지 않습니다. 읽기 전용입니다. |

### 기여

이슈를 올리실 때 재현되는 문서를 함께 주시면 원인을 확인하기 쉽습니다. 사내 문서라
제공하기 어렵다면 `hwp-reader 파일.hwp --format json`의 앞부분과 어느 표가 어떻게
어긋나는지만 적어 주셔도 됩니다.

특히 다음 제보를 환영합니다.

- 병합 구조가 어긋나는 표
- 메모가 잡히지 않는 문서
- 글자가 깨져 나오는 문단
- 대용량 HWPX에서 재현되는 문제

### 검증

다음 방식으로 동작을 확인합니다.

1. [docs/hwp-format.md](docs/hwp-format.md)에 정리한 파싱 함정 다섯 가지를 회귀 시험으로
   고정했습니다. 수정 전 코드에서 먼저 실패하는 것을 확인한 뒤 시험을 넣었습니다.
2. Python 3.9~3.13, 리눅스·맥·윈도우에서 CI가 실행됩니다.
3. 표 내용과 숫자를 다른 추출 경로인 `hwp5html`의 결과 및 원문과 대조했습니다.
4. 다음 명령으로 누구나 검증을 재현할 수 있습니다.

```bash
pip install -e ".[dev]" && pytest
```

> 추출 결과를 그대로 믿지 마십시오. 구조는 정확히 복원하지만, 원문 표 자체가 틀린
> 문서는 그대로 옮겨옵니다. 숫자를 다룬다면 합계가 항목의 합과 맞는지처럼 표 안에서
> 닫히는 관계를 한 번 검산하시기 바랍니다. 실무에서 부호가 빠진 셀, 연도마다 작성
> 기준이 다른 열을 실제로 만났습니다.

## 이런 걸 찾으셨다면

- 챗지피티에 한글파일 올리는 법
- hwp 표가 안 읽힐 때
- 맥에서 hwp 여는 법
- ChatGPT·Claude·Gemini에 한글 파일 올리기
- 한컴 없이 한글 문서 열기, 한컴오피스 없이 hwp 변환하기
- 파이썬으로 HWP 파일 읽기, HWP 텍스트 추출, HWP 표 추출
- 리눅스 서버에서 HWP 처리, 맥에서 아래아한글 파일 읽기
- HWP를 LLM·RAG에 넣기 위한 전처리, HWP MCP 서버
- HWPX 파싱, 개방형 한글 문서(OWPML) XML 읽기
- hwp5txt가 표를 못 읽는 문제, HWP 표 셀 병합 좌표가 어긋나는 문제

한글과컴퓨터가 공개한 한글문서파일형식(HWP) 5.0 규격을 근거로 구현했습니다.

## 라이선스

MIT
