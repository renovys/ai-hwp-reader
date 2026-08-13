"""0.5 읽기 계층 설치 진입점."""
from ._parser_features import *
from ._parser_controls_text import control_effect, decode_para, paragraph_prefix
from ._viewtext import decrypt_viewtext_section

MAX_XML_DEPTH = 256
MAX_XML_NODES = 2_000_000
MAX_ZIP_RATIO = 1000
MAX_ARCHIVE_TOTAL_SIZE = 1024 * 1024 * 1024


def _parse_paragraph(module, records, start, end, docinfo, state):
    base = records[start][1]; payloads = []; controls = []; blocks = []; pos = start + 1
    while pos < end:
        tag, level, data = records[pos]
        if level == base + 1 and tag == module.HWPTAG_PARA_TEXT:
            payloads.append(data); pos += 1; continue
        if level == base + 1 and tag == module.HWPTAG_MEMO_LIST:
            memo, nxt = module._parse_memo(records, pos)
            if memo: blocks.append({"type": "memo", "text": memo})
            pos = max(pos + 1, nxt); continue
        if level == base + 1 and tag == module.HWPTAG_CTRL_HEADER:
            effect = control_effect(module, records, pos, end, docinfo, state)
            controls.append(effect); blocks.extend(effect["blocks"]); pos = max(pos + 1, effect["end"]); continue
        pos += 1
    text = decode_para(module, payloads, controls); prefix = paragraph_prefix(module, records[start], docinfo, state)
    if prefix: text = (prefix + " " + text).strip()
    out = [{"type": "text", "text": text}] if text else []; out.extend(blocks); return out


def _parse_hwp_section(module, records, docinfo, state):
    blocks = []; pos = 0
    while pos < len(records):
        tag, level, data = records[pos]
        if tag == module.HWPTAG_PARA_HEADER:
            end = pos + 1
            while end < len(records):
                ntag, nlevel, _ = records[end]
                if ntag == module.HWPTAG_PARA_HEADER and nlevel <= level: break
                end += 1
            blocks.extend(_parse_paragraph(module, records, pos, end, docinfo, state)); pos = end; continue
        if tag == module.HWPTAG_MEMO_LIST:
            memo, nxt = module._parse_memo(records, pos)
            if memo: blocks.append({"type": "memo", "text": memo})
            pos = max(pos + 1, nxt); continue
        if tag == module.HWPTAG_TABLE:
            table, nxt = module._parse_table(records, pos)
            if table.get("grid"): blocks.append({"type": "table", **table})
            pos = max(pos + 1, nxt); continue
        if tag == module.HWPTAG_PARA_TEXT:
            text = module._decode_text(data).strip()
            if text: blocks.append({"type": "text", "text": text})
        pos += 1
    return blocks


def _read_hwp(module, source, name=None):
    label = module._label(source, name)
    try: ole = module.OleFile(source)
    except ValueError as exc: raise ValueError(f"{label}: OLE HWP 파일이 아니다 ({exc})") from None
    if not ole.exists("FileHeader"): raise ValueError(f"{label}: FileHeader 스트림이 없다")
    head = ole.open("FileHeader")
    if len(head) < 40 or not head.startswith(module.HWP_SIGNATURE): raise ValueError(f"{label}: HWP 5.0 FileHeader가 아니다")
    flags = module.struct.unpack_from("<I", head, 36)[0]
    compressed, encrypted, distribution, drm = bool(flags & 1), bool(flags & 2), bool(flags & 4), bool(flags & 16)
    if drm: raise RuntimeError(f"{label}: DRM 보호 문서는 읽을 수 없다")
    if encrypted: raise RuntimeError(f"{label}: 열기 암호가 걸린 문서다. 암호를 풀고 다시 저장할 것")
    docinfo = _parse_docinfo(module, ole, compressed); prefix = "ViewText/Section" if distribution else "BodyText/Section"
    names = sorted((s for s in ole.listdir() if s.startswith(prefix)), key=module._section_number)
    if not names: raise ValueError(f"{label}: {'ViewText' if distribution else 'BodyText'} 섹션이 없다")
    state = {"numbering": _NumberingState(), "auto": {}, "outline": 0, "seen": set()}; blocks = []; total = 0
    for stream in names:
        data = decrypt_viewtext_section(ole.open(stream), compressed, MAX_HWP_STREAM_BYTES) if distribution else module._read_stream(ole, stream, compressed)
        total += len(data)
        if len(data) > MAX_HWP_STREAM_BYTES or total > MAX_HWP_TOTAL_BYTES: raise ValueError(f"{label}: HWP 본문이 처리 상한을 넘는다")
        blocks.extend(_parse_hwp_section(module, module._records(data), docinfo, state))
    if not distribution: blocks.extend(module._read_hwp_changes(ole, compressed))
    return blocks


def _xml_guard(module, raw, section):
    if len(raw) > MAX_HWPX_SECTION_BYTES: raise ValueError(f"{section}: HWPX XML이 처리 상한을 넘는다")
    head = raw[:65536].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head: raise ValueError(f"{section}: DTD/ENTITY가 있는 XML은 거부한다")
    try: root = module.ElementTree.fromstring(raw)
    except module.ElementTree.ParseError as exc: raise ValueError(f"손상된 HWPX XML ({section})") from exc
    stack = [(root, 1)]; nodes = 0
    while stack:
        node, depth = stack.pop(); nodes += 1
        if nodes > MAX_XML_NODES: raise ValueError(f"{section}: XML 노드가 처리 상한을 넘는다")
        if depth > MAX_XML_DEPTH: raise ValueError(f"{section}: XML 깊이가 처리 상한을 넘는다")
        stack.extend((child, depth + 1) for child in node)
    return root


def _hwpx_ref(module, node):
    for item in node.iter():
        for key in ("binaryItemIDRef", "href"):
            value = item.get(key)
            if value: return value
    return ""


def _hwpx_para(module, para, blocks):
    buf = []; extras = []; deleted = [0]
    def flush():
        text = module.re.sub(r"[ \t]+", " ", "".join(buf)).strip(); buf.clear()
        if text: blocks.append({"type": "text", "text": text})
    def walk(node, depth=0):
        if depth > MAX_XML_DEPTH: raise ValueError("HWPX 문단 중첩 깊이가 처리 상한을 넘는다")
        for child in node:
            local = module._hwpx_local(child.tag)
            if local == "deleteBegin": deleted[0] += 1; continue
            if local == "deleteEnd": deleted[0] = max(0, deleted[0] - 1); continue
            if local in ("insertBegin", "insertEnd", "hiddenComment", "shapeComment"): continue
            if local == "tbl":
                flush(); table = module._hwpx_table(child)
                if table.get("grid"): blocks.append({"type": "table", **table})
                continue
            if local in ("memo", "memogroup"): flush(); module._hwpx_append_memos(child, blocks); continue
            if local in ("footNote", "endNote", "fn", "en"):
                text = module._hwpx_text_of(child).strip()
                if text: extras.append({"type": "note", "kind": "각주" if local in ("footNote", "fn") else "미주", "text": text})
                continue
            if local == "equation":
                script = next((n for n in child.iter() if module._hwpx_local(n.tag) == "script"), None); text = module._hwpx_text_of(script) if script is not None else ""
                if text: buf.append(f" [수식: {text}] ")
                continue
            if local == "hyperlink":
                url = child.get("url") or child.get("href") or ""
                if url and len(url) <= MAX_HYPERLINK_LENGTH: extras.append({"type": "hyperlink", "url": url})
                walk(child, depth + 1); continue
            if local == "fieldBegin":
                for item in child.iter():
                    if module._hwpx_local(item.tag) == "stringParam" and item.get("name") == "Path":
                        url = (item.text or "").strip()
                        if url and len(url) <= MAX_HYPERLINK_LENGTH: extras.append({"type": "hyperlink", "url": url})
                        break
                continue
            if local in ("pic", "shape", "drawingObject"):
                ref = _hwpx_ref(module, child)
                if ref: extras.append({"type": "image", "name": ref})
                draw = next((n for n in child.iter() if module._hwpx_local(n.tag) == "drawText"), None)
                text = module._hwpx_text_of(draw) if draw is not None else ""
                if text: extras.append({"type": "textbox", "text": text})
                continue
            if local == "t" and child.text and not deleted[0]: buf.append(child.text); walk(child, depth + 1); continue
            if local == "tab" and not deleted[0]: buf.append("\t"); continue
            if local in ("br", "lineBreak") and not deleted[0]: buf.append("\n"); continue
            if local in ("fwSpace", "hwSpace") and not deleted[0]: buf.append(" "); continue
            walk(child, depth + 1)
    walk(para); flush(); blocks.extend(extras)


def _hwpx_walk(module, node, blocks):
    for child in node:
        local = module._hwpx_local(child.tag)
        if local == "tbl":
            table = module._hwpx_table(child)
            if table.get("grid"): blocks.append({"type": "table", **table})
        elif local in ("memo", "memogroup"): module._hwpx_append_memos(child, blocks)
        elif local == "p": _hwpx_para(module, child, blocks)
        else: _hwpx_walk(module, child, blocks)


def _zip_guard(zf, label):
    infos = zf.infolist(); seen = set(); total = 0
    for info in infos:
        if info.filename in seen: raise ValueError(f"{label}: ZIP 경로가 중복됐다: {info.filename}")
        seen.add(info.filename); total += info.file_size
        if total > MAX_ARCHIVE_TOTAL_SIZE: raise ValueError(f"{label}: ZIP 전체 압축 해제 크기가 처리 상한을 넘는다")
        if info.compress_size and info.file_size > 1024 * 1024 and info.file_size / info.compress_size > MAX_ZIP_RATIO: raise ValueError(f"{label}: 비정상 압축률의 ZIP 멤버다: {info.filename}")
    return infos


def _read_hwpx(module, source, name=None):
    label = module._label(source, name)
    if not module._is_zip(source): raise ValueError(f"{label}: HWPX가 아니다(ZIP 컨테이너가 아님)")
    blocks = []
    with module.zipfile.ZipFile(module._zip_handle(source)) as zf:
        infos = _zip_guard(zf, label)
        sections = sorted((i for i in infos if module.re.match(r"Contents/section\d+\.[Xx][Mm][Ll]$", i.filename)), key=lambda i: module._section_number(i.filename))
        if not sections: raise ValueError(f"{label}: Contents/sectionN.xml을 찾지 못했다")
        total = 0
        for info in sections:
            total += info.file_size
            if info.file_size > MAX_HWPX_SECTION_BYTES or total > MAX_HWPX_TOTAL_XML_BYTES: raise ValueError(f"{label}: HWPX XML이 처리 상한을 넘는다")
            _hwpx_walk(module, _xml_guard(module, zf.read(info), info.filename), blocks)
    return blocks


def _read_documents(module, source):
    label = module._label(source)
    if not module._is_zip(source) or module._is_hwpx(source): return [{"file": module.os.path.basename(label), "blocks": module.read(source)}]
    documents = []
    with module.zipfile.ZipFile(module._zip_handle(source)) as zf:
        infos = _zip_guard(zf, label); members = [i for i in infos if not i.is_dir() and not i.filename.startswith("__MACOSX/") and i.filename.lower().endswith(module.ARCHIVE_EXTS)]
        if not members: raise ValueError(f"{label}: ZIP 안에 HWP/HWPX가 없다")
        if len(members) > module.MAX_ARCHIVE_DOCUMENTS: raise ValueError(f"{label}: ZIP 안 문서가 {module.MAX_ARCHIVE_DOCUMENTS}개를 넘는다")
        for info in members:
            if info.file_size > module.MAX_ARCHIVE_MEMBER_SIZE: documents.append({"file": info.filename, "error": "ZIP 멤버가 처리 상한을 넘는다"}); continue
            try: documents.append({"file": info.filename, "blocks": module.read(zf.read(info), name=info.filename)})
            except Exception as exc: documents.append({"file": info.filename, "error": str(exc)})
    return documents


def _render(module, blocks, fmt="text", tables_only=False):
    lines = []
    for block in blocks:
        kind = block.get("type")
        if kind == "memo": lines.append("[메모] " + block["text"])
        elif kind == "revision": lines.append(f"[변경추적 {'추가' if block['kind'] == 'insert' else '삭제'}] {block['text']}")
        elif kind == "note": lines.append(f"[{block.get('kind','주석')}{' ' + str(block['number']) if block.get('number') is not None else ''}] {block.get('text','')}".rstrip())
        elif kind == "hyperlink": lines.append(f"[하이퍼링크] {block.get('url','')}")
        elif kind == "image": lines.append(f"[이미지 · {block.get('name','참조')}]")
        elif kind == "textbox": lines.append(f"[글상자] {block.get('text','')}")
        elif kind == "header": lines.append(f"[머리말] {block.get('text','')}")
        elif kind == "footer": lines.append(f"[꼬리말] {block.get('text','')}")
        elif kind == "text" and not tables_only: lines.append(block["text"])
        elif kind == "table": module._render_table(block, fmt, lines)
    return "\n".join(lines)


def _render_documents(module, documents, fmt="md"):
    chunks = []
    for doc in documents:
        chunks.append(f"\n{'=' * 70}\n{doc['file']}\n{'=' * 70}\n")
        chunks.append("[실패] " + doc["error"] if doc.get("error") else module.render(doc.get("blocks", []), fmt))
    return "\n".join(chunks).strip()


def install(module):
    module._records = lambda data: _records_limited(module, data)
    module.read_hwp = lambda source, name=None: _read_hwp(module, source, name)
    module.read_hwpx = lambda source, name=None: _read_hwpx(module, source, name)
    module.read_documents = lambda source: _read_documents(module, source)
    module.render = lambda blocks, fmt="text", tables_only=False: _render(module, blocks, fmt, tables_only)
    module.render_documents = lambda documents, fmt="md": _render_documents(module, documents, fmt)
    return module
