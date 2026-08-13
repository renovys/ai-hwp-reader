# hwp-reader — a Korean HWP/HWPX parser that keeps the tables

**Read HWP files without Hancom Office. Merged table cells intact, hidden memos included.**

[![PyPI](https://img.shields.io/pypi/v/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![Python](https://img.shields.io/pypi/pyversions/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![tests](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[한국어](README.md)

```bash
pip install hwp-reader
hwp-reader document.hwp
```

```bash
pip install "git+https://github.com/renovys/hwp-reader"   # straight from the repo
```

HWP is the document format used by nearly every Korean government office, school and
company. If you process Korean paperwork, you will receive `.hwp` files.

No Hancom Office, no license, no LibreOffice, no Windows, no Node.js. One dependency
(`olefile`), and it runs on macOS, Linux and Windows. Reads both `.hwp` (Hangul 5.0)
and `.hwpx` (OWPML).

## Why another one

In Korean documents almost everything lives inside tables. Most extractors drop them:

```
◎ Project overview
<table>

◎ Budget
<table>
```

That looks like success but the content is gone. A 150 KB document coming out as 5 KB
of text is this failure. An LLM reading it will confidently answer "nothing notable"
before a human notices.

hwp-reader reads the same document like this:

```
[table]
(unit: KRW) |  |  |  |  |  |
Item        | Spec   | Qty | Unit price |          | Amount    |
            |        |     | List       | Discount | Supply    | VAT
Office chair| KS-320 | 12  | 180,000    | 162,000  | 1,944,000 | 194,400
```

Two-row headers and merged cells keep their positions. Numbers do not shift into the
next column.

## Works with any model, on any platform

Nothing here is tied to a vendor or a runtime. It is a local Python program with three
ways in.

| Where | How |
|---|---|
| Claude Code, Claude Desktop, Codex CLI, Gemini CLI, Cursor, VS Code, Windsurf, Zed | **Register as an MCP server** |
| ChatGPT / Claude / Gemini / Copilot **web** | **Convert to Markdown and upload** |
| Python, RAG, batch jobs, cron | **`import hwp_reader`** or `--format json` |

### 1. As an MCP server

```bash
pip install "hwp-reader[mcp]"
```

> **Skip this if you are not using MCP.** The base install pulls exactly one package,
> `olefile`. The `[mcp]` extra brings the MCP Python SDK, which in turn pulls an HTTP
> server stack (uvicorn, starlette, pydantic and friends) for a total of 29 packages.
> That is the SDK's own dependency tree, so it is kept strictly optional — the CLI and
> the Python API work fully without it.

```bash
claude mcp add hwp-reader -- hwp-reader-mcp     # Claude Code
codex mcp add hwp-reader -- hwp-reader-mcp      # Codex CLI
```

For Claude Desktop, Cursor, Windsurf, Zed and Gemini CLI, add the same block to the
client's MCP settings JSON:

```json
{
  "mcpServers": {
    "hwp-reader": { "command": "hwp-reader-mcp" }
  }
}
```

VS Code (Copilot agent mode) uses `.vscode/mcp.json` with a `"servers"` key instead.

Clients that take remote connectors can use HTTP:

```bash
hwp-reader-mcp --transport http --port 8000     # http://127.0.0.1:8000/mcp
```

Both MCP Python SDK 1.x (`FastMCP`) and 2.x (`MCPServer`) are supported, so whichever
version you have installed will work.

Three tools, all read-only. Each accepts a file path or a folder path.

| Tool | What it returns |
|---|---|
| `hwp_read` | Body text, tables and memos in document order (`format`: `text` \| `md`) |
| `hwp_tables` | Tables only, as a JSON grid |
| `hwp_memos` | Hidden memos only |

### 2. Upload to a web chatbot

Web chatbots cannot reach local tools, and uploading a raw `.hwp` loses the tables.
Convert first:

```bash
hwp-reader ./inbox --format md -o ./converted
```

Every document in the folder becomes one `.md` file. Attach those.

### 3. From Python

```python
from hwp_reader import read, render

blocks = read("document.hwp")
context = render(blocks, "md")        # Markdown to feed an LLM
```

## Three things it does differently

### 1. Merged cells survive

Korean forms love headers merged across two or three rows. Miss the cell coordinates
and every number shifts one column over — and nobody notices, because the values still
look plausible.

hwp-reader reads the cell address and span from the HWP records themselves, and uses
`cellAddr` / `cellSpan` for HWPX. Tables are not flattened into a single Markdown
layer, so you can still tell which column a merged header covered.

[docs/hwp-format.md](docs/hwp-format.md) documents why this is commonly wrong, down to
byte offsets, with a self-check for each pitfall — useful even if you use a different
parser.

### 2. Hidden memos come out

HWP documents carry memos (comments) that are invisible in the body text. Reviewers put
instructions there: "please update this with the latest figures". Plain text extraction
drops them, and you lose the request entirely.

```bash
$ hwp-reader ./inbox --memos-only

plan_v3.hwp
  - Please update with the latest figures.
settlement_final.hwp
  - Recalculate using the revised price table.
```

A `⟨메모⟩` marker is left in the body where the memo was anchored, so you can tell which
item the request belongs to.

### 3. It is fast

Measured on 11 real documents (150–280 KB, ~1,600 tables).

| Method | Time | Table content | Merge structure |
|---|---|---|---|
| **hwp-reader** | **1.5 s** | kept | correct |
| hwp5html + HTML parsing | ~22 min | kept | correct |
| hwp5txt | 3 s | all lost | — |

About 0.1 second per document.

## Choosing between tools

**Pick this one if you** want to call it from Python directly, need a CLI for cron and
CI, want a small install (one pip package, one dependency, no Node.js runtime), work on
an air-gapped machine (zero network calls), must not miss reviewer memos, or handle
tables full of money where a wrong read is worse than no read.

**Pick something else if you** need to *write* or edit documents, render pages to
SVG/HTML, extract images or equations, or need headers, footers and footnotes.
hwp-reader reads body text, tables and memos, and stays read-only on purpose: editing
HWP programmatically breaks formatting quietly, and a broken document sent outside is a
real incident.

## Command line

```bash
hwp-reader document.hwp                 # body + tables + memos
hwp-reader ./folder --format md         # tables as Markdown
hwp-reader ./folder --tables-only
hwp-reader ./folder --memos-only
hwp-reader ./folder -r                  # recurse into subfolders
hwp-reader ./folder --format md -o ./out
hwp-reader document.hwp --format json
```

Folders are processed as a whole, and failures are reported with a reason instead of
being skipped silently. A file whose extension does not match its actual container
(an HWPX saved as `.hwp`) is detected and read anyway.

## Python API

```python
blocks = read("document.hwp")
# {"type": "text",  "text": "..."}
# {"type": "table", "rows": 9, "cols": 5, "grid": [[...], ...], "cells": [...]}
# {"type": "memo",  "text": "..."}
```

`cells` carries `row`, `col`, `rowspan`, `colspan` and `text` per cell, so the merge
layout can be reconstructed exactly. Merged cells hold their value in the top-left
position of the grid.

## Not supported

| Case | Result |
|---|---|
| Password-protected documents | Reported and stopped. Remove the password and save again |
| Hancom equation editor | Not extracted as text |
| Scanned images | Pictures, not text. You need OCR |
| HWP 3.0 and older | Unsupported |
| Writing or editing | Never. Read-only by design |

## Verification

Checked against 11 table-heavy real-world documents: body and table content matches the
`hwp5html` route, column alignment is correct on two-row merged headers, and the numbers
inside tables match the originals.

The five pitfalls in [docs/hwp-format.md](docs/hwp-format.md) are pinned by regression
tests in `tests/` — each one was confirmed to fail on the pre-fix code before being
added. CI runs on Python 3.9–3.13 across Linux, macOS and Windows.

```bash
pip install -e ".[dev]" && pytest
```

HWPX has been verified with spec-built fixtures and small real documents; large HWPX
files are not yet covered. Please open an issue if one misbehaves.

> Do not trust extraction blindly. The structure is restored faithfully, but a table
> that is wrong in the original stays wrong. If numbers matter, verify a relation that
> closes inside the table, such as a total against the sum of its items.

## Contributing

A reproducing document is the fastest path. If it is confidential, the first part of
`hwp-reader file.hwp --format json` plus a description of which table is off is enough.

Most welcome: tables whose merge structure comes out wrong, documents whose memos are
missed, paragraphs with garbled characters.

Implemented from the Hangul Word Processor File Format 5.0 specification published by
Hancom.

## License

MIT
