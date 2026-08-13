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

## If you came here because

- You uploaded a Korean HWP file to ChatGPT and the table disappeared.
- You asked an AI about an estimate or budget and it returned the wrong numbers.
- You are on a Mac without Hancom Office, or you need to read HWP without Hancom.

## Use it in 3 minutes

Web chatbots work best with a Markdown file made from the HWP first.

### Mac

Open Spotlight with `⌘ + Space`, search for `Terminal`, and launch it.

### Windows

Open the Start menu, search for `Command Prompt`, and launch it.

If Python is not installed, get Python 3.9 or later from
[python.org](https://www.python.org/downloads/). macOS usually already has Python.

Install hwp-reader in the terminal.

```bash
pip install hwp-reader
```

If `pip` is not recognized on Windows, use this instead.

```bat
py -m pip install hwp-reader
```

Convert one document to a `.md` file.

```bash
hwp-reader document.hwp --format md -o ./document.md
```

The terminal prints a result like this.

```text
$ hwp-reader document.hwp --format md -o ./document.md
1개 문서를 ./document.md에 저장했다
```

Drag the new `document.md` into a ChatGPT, Claude or Gemini web conversation. Processing
stays local and makes zero network calls.

For several documents, create a `converted` folder and process the input folder as a unit.
One `.md` file is written per document.

```bash
mkdir converted
hwp-reader ./inbox --format md -o ./converted
```

Add `-r` when documents are also in subfolders.

```bash
hwp-reader ./inbox -r --format md -o ./converted
```

## Connect Claude Desktop and Cursor

To let a desktop client read local documents directly without converting them first, register
hwp-reader as an MCP server.

```bash
pip install "hwp-reader[mcp]"
```

> **If you are not using MCP, you do not need this line.** The base install has exactly one
> dependency, `olefile`. The `[mcp]` extra adds the MCP Python SDK and its HTTP server stack,
> which brings the total to 29 packages. It is optional for that reason.

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

After setup, give the client a file or folder path. The three tools are `hwp_read`,
`hwp_tables` and `hwp_memos`; all are read-only.

## If the terminal is a hard stop

This tool requires a local installation. It does not provide a web conversion service, GUI
app or installer. If using a terminal is not possible, this repository currently has no other
way to run the tool.

## Why another one

In Korean documents almost everything lives inside tables. Most extractors drop them:

```
◎ Project overview
<table>

◎ Budget
<table>
```

That looks like success but the content is gone. A 150 KB document coming out as 5 KB of
text is this failure. An LLM may confidently answer "nothing notable" before a human notices.

hwp-reader reads the same document like this:

```
[table]
(unit: KRW) |  |  |  |  |  |
Item        | Spec   | Qty | Unit price |          | Amount    |
            |        |     | List       | Discount | Supply    | VAT
Office chair| KS-320 | 12  | 180,000    | 162,000  | 1,944,000 | 194,400
```

Two-row headers and merged cells keep their positions. Numbers do not shift into the next
column.

## Three things it does differently

### 1. Merged cells survive

Korean forms often use headers merged across two or three rows. If a cell position is missed,
every number can shift one column over while still looking plausible.

hwp-reader restores the table grid from the row, column and merge information recorded in the
document. The low-level fields and byte offsets are explained in
[docs/hwp-format.md](docs/hwp-format.md).

### 2. Hidden memos come out

HWP documents carry **memos (comments)** that are invisible in the body text. Reviewers may
put instructions such as "please update this with the latest figures" there, and ordinary text
extraction drops them.

```bash
$ hwp-reader ./inbox --memos-only

plan_v3.hwp
  - Please update with the latest figures.
settlement_final.hwp
  - Recalculate using the revised price table.
  - Confirm this item with the responsible department.
```

For an HWP table cell with an anchored memo, the `⟨메모⟩` marker remains at that position.
Normal output also preserves the memo as a separate `[메모]` block in document order.

### 3. It is fast

On real working documents, processing takes about 0.1 second per document.

| Method | Speed | Table content | Merge structure |
|---|---|---|---|
| **hwp-reader** | **about 0.1 s per document** | kept | correct |
| hwp5html route | slow | kept | correct |
| hwp5txt | fast | all tables lost | — |

## If you came from another tool

Different tools fit different jobs.

**This tool is a fit when you**

- need to read from Python directly, or process folders from a shell, cron job or CI without
  an MCP server;
- want a small install: one base dependency, `olefile`, with no Node.js runtime;
- need an offline or air-gapped process with zero network calls;
- must not miss review memos; or
- work with financial tables where a wrong read is worse than no read.

**Another tool is a better fit when you**

- need to write or edit documents, add table rows, change formatting or create new files;
- need to render pages to images, SVG or HTML;
- need to extract images or equations; or
- need headers, footers or footnotes. hwp-reader reads body text, tables and memos.

hwp-reader is read-only and will remain so. Programmatically editing HWP can quietly break
formatting, so this repository stays focused on reading documents accurately.

## For developers

### Command line

The command accepts a file or folder, and it can receive more than one target.

```text
hwp-reader [--format text|md|json] [--tables-only] [--memos-only]
           [-r|--recursive] [-o|--out PATH] [--version] TARGET [TARGET ...]
```

| Option | Description |
|---|---|
| `--format text\|md\|json` | Output format. The default is `text`. |
| `--tables-only` | Output tables only. |
| `--memos-only` | Output hidden memos only. |
| `-r`, `--recursive` | Scan subfolders when the target is a folder. |
| `-o`, `--out PATH` | Save to a file or folder. A folder gets one output file per document. |
| `--version` | Print the version. |

```bash
hwp-reader document.hwp                 # body + tables + memos
hwp-reader ./folder --format md         # tables as Markdown
hwp-reader ./folder --tables-only       # tables only
hwp-reader ./folder --memos-only        # hidden memos only
hwp-reader ./folder -r                  # recurse into subfolders
hwp-reader ./folder --format md -o ./out
hwp-reader document.hwp --format json
```

Folders process `.hwp` and `.hwpx` documents. Failures are reported with their reason rather
than skipped silently. If an extension does not match the actual container, the content is
checked and read accordingly.

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

Each `cells` entry contains `row`, `col`, `rowspan`, `colspan` and `text`. A merged cell's
value appears only at the top-left position in `grid`. `render(blocks, "text")` returns plain
text, while `render(blocks, "md")` returns Markdown.

### MCP

The MCP extra is separate from the base install. It includes the MCP Python SDK and HTTP
server stack, for a total of 29 packages. Without MCP, `pip install hwp-reader` is enough.

All three tools are read-only and accept a file path or folder path.

| Tool | Returns |
|---|---|
| `hwp_read` | Body text, tables and memos in document order. `format` is `text` or `md`. |
| `hwp_tables` | Tables only, as a JSON grid. |
| `hwp_memos` | Hidden memos only. |

The default transport is local `stdio`. Use HTTP with:

```bash
hwp-reader-mcp --transport http --port 8000
```

The default address is `http://127.0.0.1:8000/mcp`. Both MCP Python SDK 1.x (`FastMCP`) and
2.x (`MCPServer`) are supported.

#### Client settings

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

**VS Code (Copilot agent mode)** — `.vscode/mcp.json`

```json
{
  "servers": {
    "hwp-reader": { "command": "hwp-reader-mcp" }
  }
}
```

### Format support

| | `.hwp` (Hangul 5.0) | `.hwpx` (OWPML) |
|---|---|---|
| Body text | ✅ | ✅ |
| Tables, including merged structure | ✅ | ✅ |
| Hidden memos | ✅ | ✅ |
| Password-protected documents | Reported and stopped | Reported and stopped |
| Writing or editing | ❌ (not included by design) | ❌ (not included by design) |

### Not supported

| Case | Result |
|---|---|
| Password-protected documents | Reported and stopped. Remove the password and save again. |
| Hancom equation editor | Not extracted as text. |
| Scanned images | Pictures, not text. OCR is required. |
| HWP 3.0 and older | Unsupported. |
| Writing or editing | Never. Read-only by design. |

### Contributing

A reproducing document is the fastest path to an issue. If it is confidential, the first part
of `hwp-reader file.hwp --format json` plus a description of which table is off is enough.

Most welcome:

- tables whose merge structure comes out wrong;
- documents whose memos are missed;
- paragraphs with garbled characters; and
- reproducible problems with large HWPX files.

### Verification

The following checks define the verification process.

1. The five parsing pitfalls documented in [docs/hwp-format.md](docs/hwp-format.md) are fixed
   as regression tests. Each was confirmed to fail on the pre-fix code before the test was added.
2. CI runs on Python 3.9–3.13 across Linux, macOS and Windows.
3. Table content and numbers are compared with the result of the separate `hwp5html` extraction
   route and with the original document.
4. Anyone can reproduce the checks with:

```bash
pip install -e ".[dev]" && pytest
```

> Do not trust extraction blindly. The structure is restored faithfully, but a table that is
> wrong in the original stays wrong. If numbers matter, verify a relation that closes inside
> the table, such as a total against the sum of its items. In practice, cells with missing signs
> and columns written to different standards in different years have appeared.

## If you searched for this

- how to upload a Korean HWP file to ChatGPT
- HWP table not readable
- how to open HWP on a Mac
- open HWP without Hancom Office
- upload HWP to ChatGPT, Claude or Gemini
- read HWP in Python, extract HWP text, extract HWP tables
- process HWP on a Linux server
- prepare HWP for an LLM or RAG pipeline, HWP MCP server
- parse HWPX and read OWPML XML
- HWP tables missing from fast text extraction, merged HWP table columns shifted

Implemented from the Hangul Word Processor File Format 5.0 specification published by Hancom.

## License

MIT
