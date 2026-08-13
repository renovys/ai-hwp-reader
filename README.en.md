# AI HWP Reader

### Your AI can now read HWP/HWPX — and actually work with the **tables, numbers and hidden comments inside.**

**An AI-native HWP/HWPX reader for ChatGPT, Claude and Gemini.**  
No Hancom Office · zero runtime dependencies · read-only

[![PyPI](https://img.shields.io/pypi/v/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![Python](https://img.shields.io/pypi/pyversions/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![tests](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[한국어](README.md)

> The goal is not merely to parse Korea's HWP (Hangul / Hancom / Arae-A Hangul) format in Python. The goal is to let an AI execute the parser itself, recover the document structure, and then use that structure to do real work.

## Let the AI work with the HWP, not just “open” it

The old workflow looks like this:

```text
HWP → open in Hancom Office → export to PDF/text → upload again → ask the AI
```

AI HWP Reader is built for this workflow instead:

```text
HWP/HWPX → AI runs parser → text + tables + comments → analyze, review, summarize
```

In an AI environment that can execute Python, paste `SKILL.md`, upload the document, and ask for the work you want done. The parser uses only the Python standard library and makes no network requests.

Examples:

```text
Extract fund size, requested commitment, term, management fee and carry from this proposal.
Find only the investment restriction risks in this compliance checklist.
Compare transfer restrictions, ROFR and tag-along provisions in this agreement.
Recalculate the totals in this budget table and flag suspicious cells.
Show me only the reviewer comments hidden in the HWP file.
```

## Three steps, no installation

1. Open [SKILL.md](SKILL.md) and **copy the whole file**.
2. Paste it into a code-executing ChatGPT, Claude or Gemini conversation, then upload `.hwp` or `.hwpx` files.
3. Ask for the result or the task: **“show me this”**, **“summarize it”**, **“check the numbers”**.

`SKILL.md` contains both the zero-dependency parser and explicit instructions telling the model to **run the parser instead of merely explaining the code**. If the environment cannot execute Python, the skill tells the model not to pretend that it read the document.

Multiple files can be processed in one run:

```bash
python hwp_reader_single.py contract.hwp articles.hwp application.hwpx
```

## Why tables matter for AI

Korean government, school and corporate documents often place their critical information inside tables: investment proposals, compliance checklists, budgets, quotations, agreements and application forms.

A text-only extraction path can appear successful while silently dropping the values the AI actually needs:

```text
◎ Investment overview
<table>

◎ Key terms
<table>
```

If that is all the model receives, amounts, ownership percentages, conditions, dates and review results may be gone.

AI HWP Reader restores the grid from the row/column addresses and merge spans stored in the document:

```text
| Item | Spec | Qty | List price | Discount | Supply amount | VAT |
|---|---|---|---|---|---|---|
| Office chair | KS-320 | 12 | 180,000 | 162,000 | 1,944,000 | 194,400 |
```

Hidden reviewer comments are emitted separately:

```text
[메모] Please update this using the latest data.
```

## Preserve the structures AI is most likely to lose

| Problem | AI HWP Reader |
|---|---|
| Multi-row merged headers | Restores positions from `row`, `col`, `rowspan`, `colspan` |
| Tables inside table cells | Keeps nested table contents with a `[중첩표]` marker and retains the nested structure |
| Hidden HWP comments | Extracts both the location marker and comment text |
| Multiple sections | Sorts section numbers numerically, not lexicographically |
| Wrong `.hwp` / `.hwpx` extension | Detects the actual container instead of trusting the filename |
| Corrupted documents | Fails explicitly instead of returning a plausible partial result |
| `|` inside Markdown cells | Escapes the delimiter so columns do not shift |
| Original document | **Read-only** — never rewrites the HWP/HWPX |

The base parser even includes its own HWP 5.0 OLE/CFB reader, so it has **zero runtime dependencies** outside the Python standard library.

## Designed for AI input, not feature count

The priority is the quality of the document representation handed to the model:

- **Preserve structure** — table columns must not silently shift.
- **Avoid omissions** — hidden comments and nested tables should not disappear.
- **Keep document order** — context depends on where content appears.
- **Fail loudly** — an explicit error is safer than a convincing partial parse.
- **Run offline** — chatbot sandboxes may not have internet or package installation.
- **Stay read-only** — parsing should never damage the source document.

## Support matrix

| Feature | Support |
|---|---|
| HWP 5.0 text | ✅ |
| HWP 5.0 tables / merged cells | ✅ |
| HWP comments | ✅ |
| HWPX text / tables | ✅ |
| HWPX nested table contents | ✅ |
| HWPX comments | ✅ |
| Detect mismatched `.hwp` / `.hwpx` extensions | ✅ |
| Encrypted documents | ❌ decrypt and resave first |
| Full text recovery for Hancom equation objects | ❌ |
| OCR for scanned images | ❌ |
| HWP 3.0 and other legacy formats | ❌ |
| Writing / editing documents | ❌ |

## For developers

The project brand is **AI HWP Reader**. For compatibility, the PyPI package, Python import and CLI keep their existing names: `hwp-reader` / `hwp_reader`.

### Install

```bash
pip install hwp-reader
```

### Python

```python
from hwp_reader import read, render

blocks = read("document.hwp")
print(render(blocks, "md"))
```

`read()` returns blocks in document order:

```python
{"type": "text",  "text": "..."}
{"type": "table", "rows": 9, "cols": 5, "grid": [[...], ...], "cells": [...]}
{"type": "memo",  "text": "Please update this."}
```

Each table cell includes `row`, `col`, `rowspan`, `colspan`, and `text`. HWPX cells containing nested tables also expose `nested_tables`.

### CLI

```bash
hwp-reader document.hwp
hwp-reader document.hwp --format md
hwp-reader document.hwp --tables-only
hwp-reader document.hwp --memos-only
hwp-reader ./folder -r
hwp-reader ./folder --format md -o ./out
hwp-reader document.hwp --format json
```

## Claude Desktop / Cursor MCP

Install the optional MCP extra if you want a local AI client to read paths directly:

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

All MCP tools are read-only.

| Tool | Result |
|---|---|
| `hwp_read` | text, tables and comments in document order |
| `hwp_tables` | table grids as JSON |
| `hwp_memos` | hidden comments only |

## Validation philosophy: “no exception” is not enough

The dangerous failure mode in HWP parsing is a result that **looks reasonable but is wrong**. An AI can confidently reason over a missing amount or a shifted table column.

Regression tests therefore target:

- HWP cell offsets and merge spans
- HWP control-code widths and residual C0 controls
- UTF-16 surrogate pairs
- the real HWP FileHeader signature
- numeric section ordering in HWP and HWPX
- merged-cell fallback when HWPX cell addresses are omitted
- HWPX nested-table preservation
- duplicate text prevention inside tables
- inline comment ordering
- Markdown cell escaping
- explicit failure on truncated records and pathological table dimensions
- synchronization of generated `skill/hwp_reader_single.py` and `SKILL.md`

CI runs on Python 3.9–3.13 across Linux, macOS and Windows.

## Performance

Typical business documents are read in roughly **0.1 seconds per document**.

## Project principles

- **Read-only**: no HWP/HWPX writing or editing.
- **No private fixtures in the repo**: real business files are used only for local regression checks.
- **One source of truth**: `skill/hwp_reader_single.py` and `SKILL.md` are generated by `tools/build_single.py`.
- **Offline parser**: no network requests.
- **AI-input quality first**: preserving tables, comments and ordering matters more than adding unrelated features.

See [docs/hwp-format.md](docs/hwp-format.md) for low-level format notes and [CHANGELOG.md](CHANGELOG.md) for release history.

## License

MIT
