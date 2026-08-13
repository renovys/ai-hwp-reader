# hwp-reader — read HWP/HWPX in ChatGPT without Hancom Office

**Read Korean HWP and HWPX documents without Hancom Office. Keep merged table positions and hidden memos.**

[![PyPI](https://img.shields.io/pypi/v/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![Python](https://img.shields.io/pypi/pyversions/hwp-reader)](https://pypi.org/project/hwp-reader/)
[![tests](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/renovys/hwp-reader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[한국어](README.md)

## Use it in ChatGPT, Claude or Gemini without installing anything

1. Open [SKILL.md](SKILL.md) and **copy the whole file**.
2. Paste it into a chatbot conversation and upload an `.hwp` or `.hwpx` document.
3. Ask for the document or ask a question about it.

`SKILL.md` contains the complete zero-dependency parser plus explicit instructions to **execute it rather than merely explain the code**. The parser itself makes no network requests.

If a model cannot execute Python, it cannot actually run the parser. The skill explicitly tells the model not to pretend that it read the document when execution is unavailable.

Example output:

```text
| Item | Qty | Amount |
|---|---|---|
| Office chair | 12 | 1,944,000 |

[메모] Please update this using the latest material.
```

The standalone distribution, `skill/hwp_reader_single.py`, also accepts multiple documents at once.

```bash
python hwp_reader_single.py contract.hwp articles.hwp application.hwpx
```

## Why this exists

Korean government, school and company documents often place important content inside tables. A generic text extractor can appear to succeed while dropping the actual table contents, which is particularly dangerous for budgets, contracts and forms.

hwp-reader reconstructs the table grid from the row/column addresses and merge spans stored in the document.

## Features

- HWP 5.0 body text
- HWP tables with merged-cell coordinates
- HWP hidden memos/comments
- HWPX body text, tables and memos
- zero runtime dependencies for the base parser
- format detection even when `.hwp` and `.hwpx` extensions are wrong
- read-only operation
- about 0.1 second per typical document

## Limitations

| Item | Status |
|---|---|
| Password-protected documents | Not supported; remove the password first |
| Hancom equation objects | Not converted to text |
| Scanned images | OCR is not included |
| HWP 3.0 and older formats | Not supported |
| Editing/writing HWP files | Not supported by design |

## Install for Python/CLI use

```bash
pip install hwp-reader
```

The base package adds no runtime dependencies.

```bash
hwp-reader document.hwp
hwp-reader document.hwp --format md
hwp-reader document.hwp --tables-only
hwp-reader document.hwp --memos-only
hwp-reader ./folder -r
hwp-reader document.hwp --format json
```

Python API:

```python
from hwp_reader import read, render

blocks = read("document.hwp")
print(render(blocks, "md"))
```

`read()` returns ordered blocks:

```python
{"type": "text",  "text": "..."}
{"type": "table", "rows": 9, "cols": 5, "grid": [[...], ...], "cells": [...]}
{"type": "memo",  "text": "..."}
```

Each table cell records `row`, `col`, `rowspan`, `colspan` and `text`.

## Claude Desktop / Cursor MCP

Install the optional MCP integration only when you need it:

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

The MCP tools are read-only: `hwp_read`, `hwp_tables`, and `hwp_memos`.

## Correctness checks

The regression suite covers the failure modes that can produce plausible but wrong output: cell-coordinate offsets, control-character widths, residual C0 controls, UTF-16 surrogate pairs, numeric section ordering, HWPX merge fallback, duplicated table paragraphs, inline memo ordering, Markdown pipe escaping, truncated records, and synchronization of the generated single-file/skill artifacts.

CI runs on Python 3.9 through 3.13 across Linux, macOS and Windows.

Low-level format notes are in [docs/hwp-format.md](docs/hwp-format.md). Changes are tracked in [CHANGELOG.md](CHANGELOG.md).

## Development principles

- Read-only: no HWP writer/editor.
- Real confidential documents are never committed; test fixtures are generated from code.
- `hwp_reader/_ole.py` and `hwp_reader/parser.py` are the source of truth. `tools/build_single.py` generates `skill/hwp_reader_single.py` and the Python block inside `SKILL.md`.
- The parser itself performs no network calls.

## License

MIT
