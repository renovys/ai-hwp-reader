"""HWP 0.5 문단·컨트롤 의미 복원."""
from ._parser_features import *

_EXTENDED = set(range(1, 4)) | set(range(11, 13)) | set(range(14, 19)) | set(range(21, 24))
_INLINE = set(range(4, 10)) | set(range(19, 21))


def _field_url(command):
    out, escaped = [], False
    for ch in command:
        if escaped: out.append(ch); escaped = False
        elif ch == "\\": escaped = True
        elif ch == ";": break
        else: out.append(ch)
    value = "".join(out).strip()
    return value if value and len(value) <= MAX_HYPERLINK_LENGTH and value.lower().startswith(("http://", "https://", "mailto:", "#")) else ""


def _field_command(module, data):
    if len(data) < 11: return ""
    length = module.struct.unpack_from("<H", data, 9)[0]
    end = 11 + length * 2
    return module._decode_utf16(data[11:end], "HWP 하이퍼링크 필드").rstrip("\0") if length and end <= len(data) else ""


def _child_end(records, index, end):
    level = records[index][1]; pos = index + 1
    while pos < end and records[pos][1] > level: pos += 1
    return pos


def _child_text(module, records, start, end):
    parts = []
    for tag, _level, data in records[start:end]:
        if tag == module.HWPTAG_PARA_TEXT:
            text = module._decode_text(data).strip()
            if text: parts.append(text)
    return " ".join(parts)


def _child_text_without_tables(module, records, start, end):
    """머리말/꼬리말의 표 셀 문자를 평문과 중복시키지 않는다."""
    parts = []; pos = start
    while pos < end:
        tag, _level, data = records[pos]
        if tag == module.HWPTAG_CTRL_HEADER and len(data) >= 4:
            ctrl = _normalize_ctrl_id(module.struct.unpack_from("<I", data)[0])
            if ctrl == CTRL_TBL:
                pos = _child_end(records, pos, end)
                continue
        if tag == module.HWPTAG_PARA_TEXT:
            text = module._decode_text(data).strip()
            if text: parts.append(text)
        pos += 1
    return " ".join(parts)


def _child_tables(module, records, start, end):
    tables = []; pos = start
    while pos < end:
        tag, _level, data = records[pos]
        if tag == module.HWPTAG_CTRL_HEADER and len(data) >= 4:
            ctrl = _normalize_ctrl_id(module.struct.unpack_from("<I", data)[0])
            if ctrl == CTRL_TBL:
                finish = _child_end(records, pos, end)
                for i in range(pos + 1, finish):
                    if records[i][0] == module.HWPTAG_TABLE:
                        table, _ = module._parse_table(records, i)
                        if table.get("grid"): tables.append(table)
                        break
                pos = finish
                continue
        pos += 1
    return tables


def _table_identity(table):
    return (
        table.get("rows", 0), table.get("cols", 0),
        tuple((c.get("row"), c.get("col"), c.get("rowspan", 1), c.get("colspan", 1), c.get("text", ""))
              for c in table.get("cells", [])),
    )


def _equation(module, records, start, end):
    for tag, _level, data in records[start:end]:
        if tag == TAG_EQEDIT and len(data) >= 6:
            length = module.struct.unpack_from("<H", data, 4)[0]; stop = 6 + length * 2
            if length and stop <= len(data):
                return module._decode_utf16(data[6:stop], "HWP 수식").replace("\0", "").strip()
    return ""


def _image_name(module, data, docinfo):
    if len(data) < 73: return ""
    ident = module.struct.unpack_from("<H", data, 71)[0]
    if not ident: return ""
    items = docinfo.get("bin_data", []); item = items[ident - 1] if ident <= len(items) else None
    if item and item.get("kind") == "link": return f"외부연결:{ident}"
    storage = (item.get("storage_id", 0) if item else ident) or ident
    ext = (item.get("extension") or "bin") if item else "bin"
    return f"BIN{storage:04X}.{ext}"


def control_effect(module, records, index, end, docinfo, state):
    data = records[index][2]; finish = _child_end(records, index, end)
    if len(data) < 4: return {"inline": "", "blocks": [], "end": finish}
    ctrl = _normalize_ctrl_id(module.struct.unpack_from("<I", data)[0]); blocks = []; inline = ""
    if ctrl == CTRL_EQED:
        value = _equation(module, records, index + 1, finish)
        if value: inline = f"[수식: {value}]"
    elif ctrl in (CTRL_FN, CTRL_EN):
        kind = "각주" if ctrl == CTRL_FN else "미주"; typ = 1 if ctrl == CTRL_FN else 2
        number = state["auto"].get(typ, 1); state["auto"][typ] = number + 1
        value = _child_text(module, records, index + 1, finish); inline = f"[{kind} {number}]"
        if value: blocks.append({"type": "note", "kind": kind, "number": number, "text": value})
    elif ctrl in (CTRL_HEAD, CTRL_FOOT):
        kind = "header" if ctrl == CTRL_HEAD else "footer"
        value = _child_text_without_tables(module, records, index + 1, finish)
        if value:
            key = kind + "\0" + value
            if key not in state["seen"]: state["seen"].add(key); blocks.append({"type": kind, "text": value})
        for table in _child_tables(module, records, index + 1, finish):
            key = (kind, "table", _table_identity(table))
            if key not in state["seen"]:
                state["seen"].add(key)
                blocks.append({"type": "table", "context": kind, **table})
    elif ctrl == CTRL_ATNO and len(data) >= 8:
        attr = module.struct.unpack_from("<I", data, 4)[0]; typ = attr & 15; fmt = (attr >> 4) & 255
        number = state["auto"].get(typ, 1); state["auto"][typ] = number + 1
        pre = module.struct.unpack_from("<H", data, 12)[0] if len(data) >= 14 else 0
        post = module.struct.unpack_from("<H", data, 14)[0] if len(data) >= 16 else 0
        inline = (chr(pre) if pre else "") + _format_number(number, fmt, auto=True) + (chr(post) if post else "")
    elif ctrl == CTRL_NWNO and len(data) >= 10:
        attr = module.struct.unpack_from("<I", data, 4)[0]; number = module.struct.unpack_from("<H", data, 8)[0]
        if number: state["auto"][attr & 15] = number
    elif ctrl == CTRL_SECD and len(data) >= 20: state["outline"] = module.struct.unpack_from("<H", data, 18)[0]
    elif ctrl == FIELD_HLK:
        url = _field_url(_field_command(module, data))
        if url: blocks.append({"type": "hyperlink", "url": url})
    elif ctrl == CTRL_TBL:
        for pos in range(index + 1, finish):
            if records[pos][0] == module.HWPTAG_TABLE:
                table, _ = module._parse_table(records, pos)
                if table.get("grid"): blocks.append({"type": "table", **table})
                break
    elif ctrl == CTRL_GSO:
        value = _child_text(module, records, index + 1, finish)
        if value: blocks.append({"type": "textbox", "text": value})
        for tag, _level, payload in records[index + 1:finish]:
            if tag == TAG_SHAPE_COMPONENT_PICTURE:
                name = _image_name(module, payload, docinfo)
                if name: blocks.append({"type": "image", "name": name})
    return {"inline": inline, "blocks": blocks, "end": finish}


def decode_para(module, payloads, controls):
    out, ctrl_index = [], 0
    for data in payloads:
        if len(data) % 2: raise ValueError("손상된 HWP PARA_TEXT: UTF-16LE 바이트 수가 홀수다")
        pos, units = 0, len(data) // 2
        while pos < units:
            code = module.struct.unpack_from("<H", data, pos * 2)[0]
            if code >= 32:
                start = pos
                while pos < units and module.struct.unpack_from("<H", data, pos * 2)[0] >= 32: pos += 1
                out.append(module._decode_utf16(data[start * 2:pos * 2], "HWP PARA_TEXT")); continue
            if code in _EXTENDED or code in _INLINE:
                if pos + 8 > units: raise ValueError("손상된 HWP PARA_TEXT: 8워드 제어문자가 잘렸다")
                if code in _EXTENDED:
                    if ctrl_index < len(controls) and controls[ctrl_index].get("inline"): out.append(controls[ctrl_index]["inline"])
                    ctrl_index += 1
                elif code == 9: out.append("\t")
                pos += 8; continue
            if code in (0, 10): out.append("\n")
            elif code == 24: out.append("-")
            elif code == 30: out.append("\u00a0")
            elif code == 31: out.append(" ")
            pos += 1
    return "".join(out).replace("\x7f", " ").strip()


def paragraph_prefix(module, header, docinfo, state):
    data = header[2]
    if len(data) < 10: return ""
    shape_id = module.struct.unpack_from("<H", data, 8)[0]; shapes = docinfo.get("para_shapes", [])
    if shape_id >= len(shapes): return ""
    shape = shapes[shape_id]; typ = shape.get("head_type", 0); level = min(shape.get("level", 0), 6); ident = shape.get("numbering_id", 0)
    if typ in (1, 2):
        if typ == 1 and not ident: ident = state.get("outline", 0)
        defs = docinfo.get("numberings", [])
        if not ident or ident > len(defs): return ""
        definition = defs[ident - 1]; counters = state["numbering"].advance(ident, level)
        fmt = definition["formats"][level] if level < len(definition["formats"]) else ""
        return _expand_numbering(fmt, counters, definition).strip()
    if typ == 3:
        bullets = docinfo.get("bullets", [])
        if ident and ident <= len(bullets): return bullets[ident - 1]
    return ""
