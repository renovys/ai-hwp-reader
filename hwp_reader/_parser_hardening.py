"""0.4 계열의 파싱 정확성 보강.

기존 파서의 공개 API는 그대로 두고, 형식이 모호하거나 손상된 입력을 조용히
보정해 정상 문서처럼 보이게 만들 수 있는 내부 경로만 교체한다.
"""


def install(module):
    """파서 코어 모듈에 정확성 보강 함수를 설치한다."""

    def _validate_cells(cells, n_rows, n_cols, what="표"):
        seen = set()
        for cell in cells:
            row = cell["row"]
            col = cell["col"]
            rowspan = cell["rowspan"]
            colspan = cell["colspan"]

            if row < 0 or col < 0:
                raise ValueError(f"손상된 {what}: 셀 주소가 음수다")
            if rowspan <= 0 or colspan <= 0:
                raise ValueError(f"손상된 {what}: 셀 병합 크기가 0 이하이다")
            if row + rowspan > n_rows or col + colspan > n_cols:
                raise ValueError(
                    f"손상된 {what}: 셀 범위가 표 격자를 벗어난다 "
                    f"(row={row}, col={col}, rowspan={rowspan}, colspan={colspan})"
                )
            key = (row, col)
            if key in seen:
                raise ValueError(
                    f"손상된 {what}: 같은 셀 주소가 중복됐다 ({row}, {col})"
                )
            seen.add(key)

    def _decode_utf16(raw, what):
        try:
            return raw.decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"손상된 {what}: UTF-16LE 문자열이 깨졌다"
            ) from exc

    def _decode_text(payload):
        """PARA_TEXT의 글자와 제어문자를 경계 손실 없이 분리한다."""
        if len(payload) % 2:
            raise ValueError(
                "손상된 HWP PARA_TEXT: UTF-16LE 바이트 수가 홀수다"
            )

        out, run = [], bytearray()
        i, n = 0, len(payload) // 2

        def flush():
            if run:
                out.append(_decode_utf16(bytes(run), "HWP PARA_TEXT"))
                run.clear()

        while i < n:
            code = module.struct.unpack_from("<H", payload, i * 2)[0]
            if code in module.WIDE_CTRL:
                flush()
                if i + 8 > n:
                    raise ValueError(
                        "손상된 HWP PARA_TEXT: 8워드 제어문자가 잘렸다"
                    )
                i += 8
                continue
            if code in module.CHAR_CTRL:
                flush()
                out.append(" ")
                i += 1
                continue
            run += payload[i * 2:i * 2 + 2]
            i += 1

        flush()
        text = "".join(out)
        return "".join(
            " " if ord(ch) < 0x20 or ord(ch) == 0x7F else ch
            for ch in text
        )

    def _decode_change_range(payload, start, end):
        """범위가 문단 밖이면 잘라 맞추지 않고 변경 텍스트로 채택하지 않는다."""
        if len(payload) % 2:
            return ""
        units = len(payload) // 2
        if start < 0 or end < start or start >= units or end >= units:
            return ""

        codes = [
            module.struct.unpack_from("<H", payload, i * 2)[0]
            for i in range(start, end + 1)
        ]
        if any(code < 0x20 for code in codes):
            return ""

        raw = payload[start * 2:(end + 1) * 2]
        try:
            text = raw.decode("utf-16-le")
        except UnicodeDecodeError:
            return ""
        return module.re.sub(r"\s+", " ", text).strip()

    def _read_stream(ole, name, compressed):
        raw = ole.open(name)
        if not compressed:
            return raw
        try:
            return module.zlib.decompress(raw, -15)
        except module.zlib.error as exc:
            raise ValueError(
                f"{name}: HWP 압축 스트림이 손상됐다"
            ) from exc

    def _grid(cells, n_rows, n_cols):
        """빈 행도 원래 행 좌표의 일부이므로 삭제하지 않는다."""
        module._validate_table_shape(n_rows, n_cols)
        _validate_cells(cells, n_rows, n_cols)
        grid = [["" for _ in range(n_cols)] for _ in range(n_rows)]
        for cell in cells:
            grid[cell["row"]][cell["col"]] = cell["text"]
        return grid

    def _parse_table(records, idx):
        """HWP TABLE과 셀 좌표/병합 크기를 보수적으로 복원한다."""
        _, level, payload = records[idx]
        if len(payload) < 8:
            raise ValueError(
                "손상된 HWP 표: TABLE payload가 8바이트보다 짧다"
            )
        n_rows, n_cols = module.struct.unpack_from("<HH", payload, 4)
        module._validate_table_shape(n_rows, n_cols, "HWP 표")

        cells, nested, cur = [], [], None
        i = idx + 1
        while i < len(records):
            tag, lv, data = records[i]
            if lv < level:
                break
            if (
                tag in (module.HWPTAG_CTRL_HEADER, module.HWPTAG_TABLE)
                and lv <= level
            ):
                break

            if tag == module.HWPTAG_TABLE and lv > level:
                table, next_i = _parse_table(records, i)
                if table["grid"]:
                    nested.append({
                        "row": cur["row"] if cur else None,
                        "col": cur["col"] if cur else None,
                        "table": table,
                    })
                    if cur is not None:
                        cur["text"] = (
                            cur["text"] + " ⟨표 안의 표⟩"
                        ).strip()
                i = next_i
                continue

            if (
                tag == module.HWPTAG_CTRL_HEADER
                and cur is not None
                and data[:4][::-1] == b"%unk"
            ):
                cur["text"] = (cur["text"] + " ⟨메모⟩").strip()

            if tag == module.HWPTAG_LIST_HEADER and lv == level:
                if len(data) < module.CELL_OFFSET + 8:
                    raise ValueError(
                        "손상된 HWP 표: LIST_HEADER 셀 정보가 잘렸다"
                    )
                col, row, cspan, rspan = module.struct.unpack_from(
                    "<4H", data, module.CELL_OFFSET
                )
                cur = {
                    "row": row,
                    "col": col,
                    "rowspan": rspan,
                    "colspan": cspan,
                    "text": "",
                }
                cells.append(cur)
            elif tag == module.HWPTAG_PARA_TEXT and cur is not None:
                piece = _decode_text(data).strip()
                if piece:
                    cur["text"] = (
                        cur["text"] + " " + piece
                    ).strip()
            i += 1

        _validate_cells(cells, n_rows, n_cols, "HWP 표")
        return {
            "rows": n_rows,
            "cols": n_cols,
            "cells": cells,
            "grid": _grid(cells, n_rows, n_cols),
            "nested_tables": nested,
        }, i

    def _hwpx_int(node, *names):
        if node is None:
            return None
        for name in names:
            value = node.get(name)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"손상된 HWPX: {name} 값이 정수가 아니다 ({value!r})"
                ) from exc
        return None

    def _hwpx_table(node):
        """HWPX 표의 선언 크기와 실제 셀 좌표가 서로 맞는지 확인한다."""
        cells, nested = [], []
        rows = [
            tr for tr in node
            if module._hwpx_local(tr.tag) == "tr"
        ]
        cursor = {}

        for r, tr in enumerate(rows):
            for tc in tr:
                if module._hwpx_local(tc.tag) != "tc":
                    continue

                addr = next(
                    (
                        c for c in tc
                        if module._hwpx_local(c.tag) == "cellAddr"
                    ),
                    None,
                )
                span = next(
                    (
                        c for c in tc
                        if module._hwpx_local(c.tag) == "cellSpan"
                    ),
                    None,
                )

                colspan = _hwpx_int(span, "colSpan", "colspan")
                rowspan = _hwpx_int(span, "rowSpan", "rowspan")
                colspan = 1 if colspan is None else colspan
                rowspan = 1 if rowspan is None else rowspan
                if colspan <= 0 or rowspan <= 0:
                    raise ValueError(
                        "손상된 HWPX 표: 셀 병합 크기가 0 이하이다"
                    )

                col = _hwpx_int(addr, "colAddr", "col")
                row = _hwpx_int(addr, "rowAddr", "row")
                if addr is not None and ((col is None) != (row is None)):
                    raise ValueError(
                        "손상된 HWPX 표: 셀 주소의 행·열 중 하나만 있다"
                    )
                if (
                    (col is not None and col < 0)
                    or (row is not None and row < 0)
                ):
                    raise ValueError(
                        "손상된 HWPX 표: 셀 주소가 음수다"
                    )

                if col is None or row is None:
                    row = r
                    col = cursor.get(r, 0)
                    while any(
                        c["row"] <= row < c["row"] + c["rowspan"]
                        and c["col"] <= col < c["col"] + c["colspan"]
                        for c in cells
                    ):
                        col += 1
                    cursor[r] = col + colspan

                nested_nodes = module._direct_nested_tables(tc)
                text = module._hwpx_text_of(tc)
                if nested_nodes:
                    text = (
                        text + " ⟨표 안의 표⟩"
                    ).strip()

                cells.append({
                    "row": row,
                    "col": col,
                    "rowspan": rowspan,
                    "colspan": colspan,
                    "text": text,
                })

                for nested_node in nested_nodes:
                    table = _hwpx_table(nested_node)
                    if table["grid"]:
                        nested.append({
                            "row": row,
                            "col": col,
                            "table": table,
                        })

        declared_rows = _hwpx_int(node, "rowCnt", "rowcnt")
        declared_cols = _hwpx_int(node, "colCnt", "colcnt")
        if declared_rows is not None and declared_rows < 0:
            raise ValueError("손상된 HWPX 표: rowCnt가 음수다")
        if declared_cols is not None and declared_cols < 0:
            raise ValueError("손상된 HWPX 표: colCnt가 음수다")

        actual_rows = max(
            [c["row"] + c["rowspan"] for c in cells] or [0]
        )
        actual_cols = max(
            [c["col"] + c["colspan"] for c in cells] or [0]
        )
        if declared_rows is not None and actual_rows > declared_rows:
            raise ValueError(
                "손상된 HWPX 표: 셀 범위가 선언된 rowCnt를 넘는다"
            )
        if declared_cols is not None and actual_cols > declared_cols:
            raise ValueError(
                "손상된 HWPX 표: 셀 범위가 선언된 colCnt를 넘는다"
            )

        n_rows = actual_rows if declared_rows is None else declared_rows
        n_cols = actual_cols if declared_cols is None else declared_cols
        module._validate_table_shape(n_rows, n_cols, "HWPX 표")
        _validate_cells(cells, n_rows, n_cols, "HWPX 표")
        return {
            "rows": n_rows,
            "cols": n_cols,
            "cells": cells,
            "grid": _grid(cells, n_rows, n_cols),
            "nested_tables": nested,
        }

    module._validate_cells = _validate_cells
    module._decode_utf16 = _decode_utf16
    module._decode_text = _decode_text
    module._decode_change_range = _decode_change_range
    module._read_stream = _read_stream
    module._grid = _grid
    module._parse_table = _parse_table
    module._hwpx_int = _hwpx_int
    module._hwpx_table = _hwpx_table

    return module
