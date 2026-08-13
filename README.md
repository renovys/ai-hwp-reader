# hwp-reader — HWP 파서 / 한컴 문서 읽기

**한컴 없이 HWP 파일을 읽습니다. 표는 병합 구조까지, 숨은 메모까지.**

[![PyPI](https://img.shields.io/pypi/v/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![Python](https://img.shields.io/pypi/pyversions/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![tests](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> HWP · HWPX · 한컴 · 한컴오피스 · 한글파일 · 아래아한글 · 한글과컴퓨터 · HWP 파싱 · HWP 텍스트 추출 · HWP 표 추출

[English](README.en.md)

```bash
pip install hwp-reader
hwp-reader 문서.hwp
```

```bash
pip install "git+https://github.com/renovys/hwp-reader"   # 저장소에서 바로
```

한컴 오피스 설치도, 한컴 라이선스도 필요 없습니다. LibreOffice도, 윈도우도,
Node.js도 필요 없습니다. 의존성은 `olefile` 하나뿐이고 맥·리눅스·윈도우 어디서나
돕니다.

`.hwp`(한글 5.0)와 `.hwpx`(개방형 한글 문서) 양쪽을 읽습니다.

| | |
|---|---|
| 설치 | `pip install hwp-reader` — 한 번이면 끝, 폐쇄망도 wheel 하나 |
| 실행에 필요한 것 | 파이썬 3.9 이상. 그게 전부입니다 |
| 의존성 | `olefile` **1개**. HWPX는 표준 라이브러리만 (MCP 서버로 쓸 때만 SDK 추가) |
| 붙는 곳 | MCP 클라이언트 전부 · 웹 챗봇 · 파이썬 코드 · 셸 |
| 쓰는 방법 | CLI · `import hwp_reader` · MCP 서버(stdio/HTTP) |
| 문서를 고치나 | 아니요. **읽기 전용**입니다 |
| 네트워크 | 호출 0건. 문서가 밖으로 나가지 않습니다 |

## 왜 또 만들었나

한국에서 일하면 한글 파일이 옵니다. 공문, 사업계획서, 견적서, 계약서, 회의록,
각종 신청 서식, 학교 가정통신문. 그런데 그 안의 내용은 거의 전부 표 안에 들어
있습니다. 그래서 기존 도구로 뽑으면 이런 게 나옵니다.

```
◎ 사업 개요
<표>

◎ 예산 집행 내역
<표>
```

성공한 것처럼 보이지만 알맹이가 통째로 사라진 껍데기입니다. 150KB짜리 문서가
5KB 텍스트로 나오면 이 상태입니다. 사람이 눈치채기 전에 LLM이 먼저 "특이사항
없음"이라고 답합니다.

hwp-reader는 같은 문서를 이렇게 읽습니다.

```
[표]
(단위: 원) |  |  |  |  |  |
품목        | 규격   | 수량 | 단가    |         | 금액      |
            |        |      | 정가    | 할인가  | 공급가    | 부가세
사무용 의자 | KS-320 | 12   | 180,000 | 162,000 | 1,944,000 | 194,400
```

2단 헤더도, 병합된 셀도 자리를 지킵니다. 숫자가 옆 칸으로 밀리지 않습니다.

## 어디서나 씁니다 — 모델도 플랫폼도 안 가립니다

어느 회사의 모델에도, 어느 런타임에도 묶여 있지 않습니다. 로컬에서 도는 파이썬
프로그램일 뿐이고, 붙이는 길이 셋입니다.

| 쓰는 곳 | 방법 |
|---|---|
| Claude Code · Claude Desktop · Codex CLI · Gemini CLI · Cursor · VS Code · Windsurf · Zed | **MCP 서버로 등록** — 아래 한 줄 |
| ChatGPT · Claude · Gemini · Copilot **웹** | **마크다운으로 뽑아 업로드** — 로컬 도구를 못 붙이는 곳 |
| 파이썬 · RAG · 배치 · cron | **`import hwp_reader`** 또는 `--format json` |

### 1. MCP 서버로 붙이기

```bash
pip install "hwp-reader[mcp]"
```

> **MCP를 안 쓰시면 이 줄은 필요 없습니다.** 기본 설치(`pip install hwp-reader`)가
> 끌어오는 패키지는 `olefile` 하나뿐입니다. `[mcp]`를 붙이면 MCP 파이썬 SDK가
> 딸려 오는데, 그 SDK가 HTTP 서버 스택(uvicorn·starlette·pydantic 등)까지 함께
> 가져와 29개가 됩니다. SDK 쪽 구조라 더 줄일 수 없어서, 아예 선택 항목으로
> 떼어 놨습니다. CLI와 파이썬 API는 이것 없이 그대로 다 됩니다.

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

**Claude Desktop · Cursor · Windsurf · Zed** — 각 앱의 MCP 설정 JSON에 같은 모양으로
넣습니다.

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

**원격 커넥터를 받는 클라이언트** — HTTP로도 뜹니다.

```bash
hwp-reader-mcp --transport http --port 8000     # http://127.0.0.1:8000/mcp
```

MCP 파이썬 SDK는 1.x(`FastMCP`)와 2.x(`MCPServer`)의 API가 다른데 양쪽을 모두
지원하므로, 어느 버전이 깔려 있어도 그대로 돕니다.

도구는 셋뿐입니다. 읽기 전용이라 문서를 건드리지 않습니다.

| 도구 | 하는 일 |
|---|---|
| `hwp_read` | 본문·표·메모를 문서 순서대로 (`format`: `text` \| `md`) |
| `hwp_tables` | 표만 JSON 격자로 |
| `hwp_memos` | 숨은 메모만 |

셋 다 파일 경로와 폴더 경로를 모두 받습니다. 폴더를 주면 안의 한글 문서를 전부
읽습니다.

### 2. 웹 챗봇에 올리기 (MCP를 못 붙이는 곳)

ChatGPT, Claude, Gemini 웹에는 로컬 도구를 붙일 수 없습니다. 한글 파일을 그대로
올리면 표가 뭉개지고요. 변환해서 올리면 됩니다.

```bash
hwp-reader ./받은문서 --format md -o ./변환본
```

폴더 안의 문서가 하나씩 `.md`로 떨어집니다. 그걸 첨부하면 끝입니다.

### 3. 파이썬으로 붙이기

MCP를 거치지 않고 코드에서 바로 부릅니다. RAG 인덱싱, 배치 변환, 사내 파이프라인은
이쪽이 맞습니다.

```python
from hwp_reader import read, render

blocks = read("문서.hwp")
context = render(blocks, "md")        # LLM에 넣을 마크다운
```

## 세 가지가 다릅니다

### 1. 병합된 셀을 제대로 읽습니다

한국 문서 양식은 헤더가 2~3단으로 병합된 표를 사랑합니다. 여기서 셀 좌표를 놓치면
숫자가 통째로 한 칸씩 밀리는데, 읽는 사람은 알아채지 못합니다. 값이 다 그럴듯해
보이니까요.

hwp-reader는 HWP 레코드의 셀 좌표(행·열·병합 수)를 규격대로 읽어 격자를
복원합니다. HWPX도 `cellAddr`·`cellSpan`을 그대로 씁니다. 표를 마크다운 한 겹으로
납작하게 눌러 담지 않기 때문에, 2단 헤더가 어느 열에 걸려 있었는지가 남습니다.

왜 이게 흔히 틀리는지는 [docs/hwp-format.md](docs/hwp-format.md)에 오프셋 단위로
적어 뒀습니다. 자가 진단법까지 넣었으니, 다른 구현을 쓰고 계셔도 지금 쓰는 도구가
맞게 읽는지 그 문서로 확인해 보실 수 있습니다.

### 2. 숨은 메모를 뽑아냅니다

한글 문서에는 본문에 안 보이는 **메모(주석)** 가 달립니다. 검토자가 "이 부분 최신
자료로 수정해주세요" 같은 지시를 여기 적어 보내죠. 문서를 텍스트로 뽑으면 이게
사라집니다. 요청받은 일을 통째로 놓치게 됩니다.

```bash
$ hwp-reader ./받은문서 --memos-only

계획서_v3.hwp
  - 최신 자료 기준으로 업데이트해주세요.
정산서_최종.hwp
  - 단가표 개정본으로 다시 계산 부탁드립니다.
  - 이 항목은 담당 부서 확인 후 반영해주세요.
```

메모가 달린 자리에는 본문에 `⟨메모⟩` 표시가 남아서, 어느 항목에 붙은 요청인지 바로
찾을 수 있습니다.

### 3. 빠릅니다

150~280KB짜리 실제 문서 11개(표 1,600여 개)로 잰 값입니다.

| 방법 | 소요 시간 | 표 내용 | 병합 구조 |
|---|---|---|---|
| **hwp-reader** | **1.5초** | 보존 | 정확 |
| hwp5html + HTML 파싱 | 약 22분 | 보존 | 정확 |
| hwp5txt | 3초 | 전부 소실 | — |

문서 하나에 0.1초입니다. 폴더째 던져도 됩니다.

## 다른 도구를 쓰다 오셨다면

한글 문서를 다루는 오픈소스는 이미 여럿 있습니다. 고르실 수 있게 적습니다.

**이 도구가 맞는 경우**

- 파이썬 코드에서 직접 부르고 싶다 — `import hwp_reader` 한 줄이면 됩니다. MCP
  서버를 띄우고 그 위에서만 쓰는 구조가 아닙니다
- MCP 없이 셸·cron·CI에서 폴더째 변환하고 싶다 — CLI가 본체입니다
- 설치가 가벼워야 한다 — `pip install` 한 번, 의존성 1개, Node.js 런타임 불필요
- 폐쇄망·오프라인 서버에서 돌려야 한다 — wheel 하나 넣으면 끝, 네트워크 호출 0건
- 받은 문서에 달린 **검토 메모**를 놓치면 안 된다
- 금액이 든 병합 표를 **틀리게 읽느니 안 읽는 게 나은** 일을 한다

**다른 도구가 나은 경우** — 솔직하게 적습니다

- 문서를 **고쳐야 한다** (텍스트 치환, 표 행 추가, 서식 변경, 새 문서 생성).
  hwp-reader는 읽기 전용이고 앞으로도 그렇습니다
- 페이지를 **이미지·SVG·HTML로 렌더**해야 한다
- **이미지·수식**을 파일로 추출해야 한다
- 머리말·꼬리말·각주까지 필요하다 (본문·표·메모만 읽습니다)

쓰기를 넣지 않은 건 게을러서가 아닙니다. 한글 문서를 프로그램으로 고치면 서식이
조용히 깨지는데, 그 문서가 대외로 나가면 사고가 됩니다. 읽기만 정확하게 하는 쪽을
택했고, 그래서 이 저장소는 "정확히 읽었는가"만 책임집니다.

## 쓰는 법

### 명령줄

```bash
hwp-reader 문서.hwp                    # 본문 + 표 + 메모
hwp-reader ./폴더 --format md          # 표를 마크다운으로
hwp-reader ./폴더 --tables-only        # 표만
hwp-reader ./폴더 --memos-only         # 숨은 메모만
hwp-reader ./폴더 -r                   # 하위 폴더까지
hwp-reader ./폴더 --format md -o ./out # 파일로 저장 (웹 챗봇에 올릴 때)
hwp-reader 문서.hwp --format json      # 프로그램으로 넘길 때
```

폴더를 주면 안의 한글 문서를 전부 처리하고, 실패한 파일은 이유와 함께 목록으로
알려줍니다. 조용히 넘어가지 않습니다.

확장자가 실제 형식과 어긋나도(`.hwp`로 저장된 HWPX 등) 내용을 보고 알아서
읽습니다.

### 파이썬

```python
from hwp_reader import read, render

blocks = read("문서.hwp")

for b in blocks:
    if b["type"] == "table":
        for row in b["grid"]:      # 병합 셀은 좌상단에만 값이 있습니다
            print(row)
    elif b["type"] == "memo":
        print("메모:", b["text"])

print(render(blocks, "md"))         # 마크다운 문자열로
```

`read()`는 문서 순서 그대로 dict 목록을 돌려줍니다.

```python
{"type": "text",  "text": "..."}
{"type": "table", "rows": 9, "cols": 5, "grid": [[...], ...], "cells": [...]}
{"type": "memo",  "text": "최신 자료 기준으로 업데이트해주세요."}
```

`cells`에는 셀마다 `row`, `col`, `rowspan`, `colspan`, `text`가 들어 있어서 병합
구조를 그대로 다시 그릴 수 있습니다.

파일은 로컬에서만 읽습니다. 네트워크 호출이 한 줄도 없어서, 계약서나 인사 자료
같은 민감한 문서에 써도 밖으로 나가지 않습니다.

## 포맷별 지원

| | `.hwp` (한글 5.0) | `.hwpx` (OWPML) |
|---|---|---|
| 본문 | ✅ | ✅ |
| 표 (병합 구조 포함) | ✅ | ✅ |
| 숨은 메모 | ✅ | ✅ |
| 암호 문서 | 이유를 밝히고 멈춤 | 이유를 밝히고 멈춤 |
| 쓰기·수정 | ❌ (설계상 안 합니다) | ❌ (설계상 안 합니다) |

## 안 되는 것

| 상황 | 결과 |
|---|---|
| 암호가 걸린 문서 | 그렇다고 알려주고 멈춤. 암호를 풀고 다시 저장하세요 |
| 한컴 수식 편집기 수식 | 텍스트로 안 나옵니다 |
| 스캔해서 붙인 이미지 | 글자가 아니라 그림입니다. OCR이 필요합니다 |
| HWP 3.0 등 옛 포맷 | 미지원 |
| 문서 쓰기·수정 | 하지 않습니다. 읽기 전용입니다 |

## 검증

표가 많은 실무 문서 11개(150~280KB, 표 1,600여 개)로 확인했습니다.

- `hwp5html` 경로로 뽑은 결과와 본문·표 내용이 일치
- 2단 헤더·병합 셀이 있는 표에서 열 정렬이 정확
- 표 안 숫자를 원문과 대조해 일치 확인

여기에 더해, [docs/hwp-format.md](docs/hwp-format.md)에 적은 함정 다섯 가지는
`tests/`에 회귀 시험으로 박아 뒀습니다. **고치기 전 코드에서 먼저 실패하는 것을
확인하고 넣은 시험입니다.** 파이썬 3.9~3.13 · 리눅스 · 맥 · 윈도우에서 CI로 돕니다.

```bash
pip install -e ".[dev]" && pytest
```

HWPX는 규격대로 만든 시험 문서와 소규모 실문서로 확인했습니다. 대용량 HWPX는 아직
못 돌려 봤으니, 큰 파일에서 어긋나면 이슈로 알려주세요.

> 추출 결과를 그대로 믿지 마세요. 구조는 정확히 복원하지만, 원문 표 자체가 틀린
> 문서는 그대로 옮겨옵니다. 숫자를 다룬다면 합계가 항목의 합과 맞는지처럼 표 안에서
> 닫히는 관계를 한 번 검산하시길 권합니다. 실무에서 부호가 빠진 셀, 연도마다 작성
> 기준이 다른 열을 실제로 만났습니다.

## 기여

이슈를 올리실 때 재현되는 문서를 함께 주시면 가장 빠릅니다. 사내 문서라 못 주시는
경우가 많을 텐데, 그럴 땐 `hwp-reader 파일.hwp --format json`의 앞부분과 어느 표가
어떻게 어긋나는지만 적어주셔도 됩니다.

특히 반깁니다.

- 병합 구조가 어긋나는 표
- 메모가 안 잡히는 문서
- 글자가 깨져 나오는 문단

## 이런 걸 찾으셨다면

아래 중 하나로 검색해 들어오셨다면 제대로 찾아오신 겁니다.

- 파이썬으로 HWP 파일 읽기 / HWP 텍스트 추출 / HWP 표 추출
- 한컴 없이 한글 문서 열기, 한컴 오피스 안 깔고 hwp 변환하기
- 리눅스 서버에서 HWP 처리, 맥에서 아래아한글 파일 읽기
- HWPX 파싱, 개방형 한글 문서(OWPML) XML 읽기
- HWP를 LLM·RAG에 넣기 위한 전처리, HWP MCP 서버
- ChatGPT·Claude·Gemini에 한글 파일 올리기, HWP를 마크다운으로 변환
- hwp5txt가 표를 못 읽는 문제, HWP 표 셀 병합 좌표가 어긋나는 문제

한글과컴퓨터가 공개한 한글문서파일형식(HWP) 5.0 규격을 근거로 구현했습니다.

## 라이선스

MIT
