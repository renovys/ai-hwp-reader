# AI HWP Reader

## Your AI can now read HWP — and work with the document.

Give **ChatGPT, Claude or Gemini** the original Korean HWP/HWPX file. AI HWP Reader recovers the parts that matter for real work: **merged tables, tables inside tables, hidden comments, tracked changes, footnotes/endnotes, links, equation scripts, and image references**.

No Hancom Office · zero runtime dependencies for the core parser · read-only

[![PyPI](https://img.shields.io/pypi/v/ai-hwp-reader)](https://pypi.org/project/ai-hwp-reader/)
[![Python](https://img.shields.io/pypi/pyversions/ai-hwp-reader)](https://pypi.org/project/ai-hwp-reader/)
[![tests](https://github.com/renovys/ai-hwp-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/renovys/ai-hwp-reader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[한국어](README.md)

> HWP · HWPX · Hangul · Hancom · Arae-A Hangul → AI

## Install it once, then just attach documents

You do **not** need a terminal, Python knowledge, or `pip install`.

1. **[Download `ai-hwp-reader-skill.zip`](https://github.com/renovys/ai-hwp-reader/releases/latest/download/ai-hwp-reader-skill.zip)** — one click, saves straight to your machine.
2. Register it once with your AI:
   - **Claude** — Settings → Skills → create a skill and upload the zip as is.
   - **ChatGPT** — add `SKILL.md` and `scripts/hwp_reader_single.py` from the zip as files in a Project or a custom GPT.
3. From then on, just attach a `.hwp`, `.hwpx`, or `.zip` and ask for the work you want done.

Prefer not to install anything? Download [`SKILL.md`](https://github.com/renovys/ai-hwp-reader/releases/latest/download/SKILL.md) and attach it alongside your document each time.

Some models, Gemini among them, already read Hangul documents directly. Where this parser pulls ahead is complex tables — merged cells and two- or three-row headers, whose cell coordinates it restores instead of flattening.

`SKILL.md` contains the complete zero-dependency parser plus execution instructions. In an AI environment that can execute Python, the model runs the parser against the attached file and then uses the parsed result to continue the task.

```text
SKILL.md + agreement.hwp
→ “do it”
→ read the document → preserve tables/comments/revisions → summarize or review it
```

```text
SKILL.md + documents.zip
→ “compare these”
→ find every HWP/HWPX inside the ZIP → parse each file → compare them
```

The point is to remove the manual chain of opening HWP in Hancom Office, exporting PDF/text, repairing tables, and re-explaining the document to the AI.

## Reading HWP is not enough. The structure has to survive.

Important Korean business documents often place the actual facts inside tables. A flat text extractor can make a document look readable while silently losing amounts, ownership percentages, conditions, approval fields, or compliance results.

AI HWP Reader uses the stored cell coordinates and merge ranges instead of guessing the table layout.

It also preserves information that is easy to miss:

| Document structure | Support |
|---|---:|
| HWP 5.0 / HWPX body text | ✅ |
| Tables | ✅ |
| Merged cells and multi-row headers | ✅ |
| **Nested tables (table inside a cell)** | ✅ |
| Hidden comments / memos | ✅ |
| **HWP tracked insertions and deletions** | ✅ |
| **Footnotes / endnotes** | ✅ |
| **Hyperlinks** | ✅ |
| **Hancom equation scripts** | ✅ preserves source script |
| **Image references** | ✅ reference only, no OCR/binary extraction |
| **Text boxes** | ✅ |
| **Distribution HWP ViewText** | ✅ local decryption |
| Multiple sections in numeric order | ✅ |
| Wrong `.hwp` / `.hwpx` filename extension | ✅ content detection |
| **ZIP containing multiple HWP/HWPX files** | ✅ recursive member discovery |
| Password-protected documents | ❌ unlock first |
| Scanned-image OCR | ❌ |
| Full conversion of Hancom equation objects | ❌ |
| HWP 3.0 and older formats | ❌ |
| Writing or modifying HWP | ❌ read-only |

### Nested tables

A table cell may contain another table. AI HWP Reader keeps the parent-cell location and renders the inner table separately instead of dropping it.

```text
[table inside table · row 3 column 2]
| item | amount |
|---|---:|
| A | 100 |
```

### Hidden comments

Review comments stored outside ordinary body text are emitted separately:

```text
[메모] Replace this with the latest figure.
```

### Tracked changes

For HWP files with change tracking, the final `BodyText` remains the final document. Insert/delete ranges stored in `ViewText/Section#` are emitted separately:

```text
[변경추적 삭제] old wording
[변경추적 추가] revised wording
```

### ZIP archives

A ZIP can contain HWP/HWPX files in nested folders. `read_documents()` finds them without extracting the archive to a temporary directory and keeps file boundaries in the output.

## For developers

The PyPI package and CLI are `ai-hwp-reader`. The Python import stays `hwp_reader`, and the legacy `hwp-reader` command is still installed for compatibility.

```bash
pip install ai-hwp-reader
```

Core runtime dependencies: **0**.

### Python

```python
from hwp_reader import read, render

blocks = read("document.hwp")
print(render(blocks, "md"))
```

For a ZIP or a bundle of documents:

```python
from hwp_reader import read_documents, render_documents

documents = read_documents("bundle.zip")
print(render_documents(documents, "md"))
```

Block types include `text`, `table`, `memo`, `revision`, `note`, `link`, `equation`, `image`, and `textbox`. Tables expose their grid, cell coordinates, spans, and nested tables.

### CLI

```bash
ai-hwp-reader document.hwp --format md
ai-hwp-reader document.hwpx --format json
ai-hwp-reader bundle.zip --format md
ai-hwp-reader document.hwp --tables-only
ai-hwp-reader document.hwp --memos-only
ai-hwp-reader document.hwp --revisions-only
ai-hwp-reader ./folder -r
```

### MCP

```bash
pip install "ai-hwp-reader[mcp]"
```

The MCP tools are read-only as well.

## Accuracy philosophy

A parser that crashes is obvious. A parser that returns plausible-but-wrong values is more dangerous for AI workflows.

Regression tests therefore focus on silent-failure cases: cell coordinate offsets, row/column spans, multi-row headers, HWP control widths, surrogate pairs, section ordering, cells without explicit HWPX addresses, nested tables, hidden comments, tracked-change ranges, distribution ViewText, bounded DEFLATE output, XML DTD/entity rejection, ZIP limits/path normalization, Markdown escaping, malformed records/XML, oversized table allocation, and generated `SKILL.md` synchronization.

CI covers Python 3.9–3.13 on Linux, macOS, and Windows.

## Privacy and design constraints

- The core parser makes no network requests.
- Documents are read-only; it never rewrites HWP/HWPX.
- Real business documents may be used privately for regression validation but are never committed as test fixtures.
- `SKILL.md` and `skill/hwp_reader_single.py` are generated from the parser source by `tools/build_single.py`.

## License

MIT

Implemented from the published HWP 5.0 / OWPML document formats. Open-source cross-checks and license notices are documented in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
