# hwp-reader — a Korean HWP/HWPX parser that keeps the tables

**Read HWP files without Hancom Office. Merged table cells intact, hidden memos included.**

[![PyPI](https://img.shields.io/pypi/v/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![Python](https://img.shields.io/pypi/pyversions/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![tests](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> HWP · HWPX · Hangul Word Processor · Korean document parser · HWP text extraction · HWP table extraction

[한국어](README.md)

HWP is a document format used by Korean government offices, schools and companies. It is
common in official forms, budgets, estimates, notices and other Korean business documents.

## 3 steps without installation

No terminal, no Python installation, no package installation.

1. Open [SKILL.md](SKILL.md) in a browser and **copy the whole document**.
2. **Paste it** into a ChatGPT, Claude or Gemini conversation, then upload the HWP file.
3. Ask for the contents — in Korean, **"이거 줘"** is enough.

[SKILL.md](SKILL.md) contains the full parser in a code block. The single-file distribution is
`skill/hwp_reader_single.py`. The parser has zero external dependencies, so one Python file runs
directly in a chatbot code-execution environment. Chatbot sandboxes do not have internet access,
so external package installation is unavailable. That does not matter because the parser uses no
external packages.

The result looks like this.

```text
[표]
품목 | 수량 | 금액
사무용 의자 | 12 | 1,944,000
[메모] 최신 자료 기준으로 업데이트해주세요.
```

## If you came here because

- You uploaded an HWP file to a chatbot and the table disappeared.
- You asked about an estimate or budget and received the wrong numbers.
- You are on a Mac without Hancom Office and need to read HWP.

## Why do tables disappear?

Korean government, school and company documents often put the important content inside tables.
General text extraction can leave only `<table>` like this:

```
◎ Project overview
<table>

◎ Budget execution
<table>
```

The document appears to have been read, but the table content is gone. A chatbot can give a
wrong answer before anyone notices the omission.

hwp-reader reads the same document like this:

```
[table]
(unit: KRW) |  |  |  |  |  |
Item        | Spec   | Qty | Unit price |          | Amount    |
            |        |     | List       | Discount | Supply    | VAT
Office chair| KS-320 | 12  | 180,000    | 162,000  | 1,944,000 | 194,400
```

Two-row headers and merged cells keep their positions, so numbers do not shift into the next
column.

## Three things are different

### 1. Merged cells are read in place

Korean forms often have headers merged across two or three rows. If a cell position is missed,
every number can shift one column while still looking plausible.

hwp-reader restores the table grid from the row, column and merge information recorded in the
document. The internal fields and byte offsets are described in [the HWP format notes](docs/hwp-format.md).

### 2. Hidden memos are included

HWP documents carry **memos (comments)** that are invisible in the body text. Reviewers may put
instructions such as an update request there, and ordinary text extraction drops them.

The memo position remains marked as `⟨메모⟩`, and the memo text is preserved as a separate
`[메모]` block in document order.

```text
[메모] 최신 자료 기준으로 업데이트해주세요.
[메모] 단가표 개정본으로 다시 계산 부탁드립니다.
```

### 3. It is fast

It takes about 0.1 second per document.

## Connect Claude Desktop and Cursor

If you do not want to paste SKILL.md into every conversation, register hwp-reader as an MCP
server in Claude Desktop or Cursor. The client can then read local documents directly.

The `[mcp]` extra is optional. Use the additional installation in the developer section only
when you need MCP. It includes the MCP Python SDK and HTTP server stack and installs 29 packages.
The base parser has zero external dependencies.

Put this JSON in the MCP settings for Claude Desktop or Cursor.

```json
{
  "mcpServers": {
    "hwp-reader": {
      "command": "hwp-reader-mcp"
    }
  }
}
```

## Not supported

`.hwp` (Hangul 5.0) and `.hwpx` files are read, but these functions are not supported.

| Case | Result |
|---|---|
| Password-protected documents | ❌ Remove the password and save the document again. |
| Hancom equation editor equations | ❌ Not extracted as text. |
| Scanned images | ❌ They are pictures and require OCR. |
| HWP 3.0 and older formats | ❌ Unsupported. |
| Writing or editing documents | ❌ Read-only. No writing feature is provided. |

## For developers

This section covers direct use from a terminal, the Python API and MCP.

### Installation

```bash
pip install hwp-reader
```

The base parser runs without external packages. That is why installing `hwp-reader` adds no
external package.

### Command line

The command accepts files or folders and can receive multiple targets.

```text
hwp-reader [--format text|md|json] [--tables-only] [--memos-only]
           [-r|--recursive] [-o|--out PATH] [--version] TARGET [TARGET ...]
```

| Option | Description |
|---|---|
| `--format text\|md\|json` | Output format. The default is `text`. |
| `--tables-only` | Output tables only. |
| `--memos-only` | Output hidden memos only. |
| `-r`, `--recursive` | Read subfolders when the target is a folder. |
| `-o`, `--out PATH` | Save to a file or folder. A folder gets one output file per document. |
| `--version` | Print the version. |

```bash
hwp-reader document.hwp                 # body + tables + memos
hwp-reader document.hwp --format md     # Markdown output
hwp-reader document.hwp --tables-only   # tables only
hwp-reader document.hwp --memos-only    # hidden memos only
hwp-reader ./folder -r                  # recurse into subfolders
hwp-reader ./folder --format md -o ./out
hwp-reader document.hwp --format json
```

### Python API

```python
from hwp_reader import read, render

blocks = read("document.hwp")
markdown = render(blocks, "md")

for block in blocks:
    if block["type"] == "table":
        for row in block["grid"]:
            print(row)
    elif block["type"] == "memo":
        print("Memo:", block["text"])
```

`read()` returns a list of dictionaries in document order.

```python
{"type": "text",  "text": "..."}
{"type": "table", "rows": 9, "cols": 5, "grid": [[...], ...], "cells": [...]}
{"type": "memo",  "text": "Please update with the latest figures."}
```

Each `cells` entry contains `row`, `col`, `rowspan`, `colspan` and `text`. A merged cell's value
appears only at the top-left position in `grid`. `render(blocks, "text")` returns plain text and
`render(blocks, "md")` returns Markdown.

### MCP tools

Install the optional MCP extra when needed.

```bash
pip install "hwp-reader[mcp]"
```

The `[mcp]` extra includes the MCP Python SDK and HTTP server stack and installs 29 packages.
There are three tools, all read-only. Each accepts a file path or folder path.

| Tool | Returns |
|---|---|
| `hwp_read` | Body text, tables and memos in document order. `format` is `text` or `md`. |
| `hwp_tables` | Tables only, as a JSON grid. |
| `hwp_memos` | Hidden memos only. |

The default transport is local `stdio`.

### HTTP transport

```bash
hwp-reader-mcp --transport http --port 8000
```

The default address is `http://127.0.0.1:8000/mcp`.

## Verification

- Five parsing pitfalls are fixed as regression tests, and each was confirmed to fail on the pre-fix code first.
- The OLE reader was cross-checked against `olefile`; every stream's bytes match.
- On real business documents, output is identical before and after dependency removal.
- CI covers Python 3.9–3.13 on Linux, macOS and Windows.
- The checks are reproducible with `pytest`.

## Contributing

A reproducing document makes an issue easier to investigate. If the document is confidential,
include the beginning of `hwp-reader document.hwp --format json` and describe which table is
misaligned.

Useful reports include:

- tables whose merge structure comes out wrong;
- documents whose memos are missed;
- paragraphs with garbled characters; and
- reproducible HWPX parsing problems.

## If you searched for this

- how to upload a Korean HWP file to ChatGPT (챗지피티에 한글파일 올리는 법)
- read HWP in Claude (클로드 hwp 읽기)
- Gemini HWP (제미나이 hwp)
- when HWP tables cannot be read (hwp 표가 안 읽힐 때)
- how to open HWP on a Mac
- upload HWP to ChatGPT, Claude or Gemini
- open HWP without Hancom Office
- read HWP in Python, extract HWP text, extract HWP tables
- process HWP on a Linux server
- prepare HWP for an LLM or RAG pipeline, HWP MCP server
- parse HWPX and read OWPML XML

Implemented from the Hangul Word Processor File Format 5.0 specification published by Hancom.

## License

MIT
