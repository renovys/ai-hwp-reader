"""시험용 HWPX 문서를 만든다.

실무 문서는 전부 사내 자료라 저장소에 넣을 수 없다. 대신 병합 헤더가 있는 표와
메모가 든 HWPX를 규격대로 생성해서 쓴다. HWPX는 ZIP + XML이라 이게 가능하다.
"""

import zipfile

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS = "http://www.hancom.co.kr/hwpml/2011/section"


def _tc(col, row, colspan, rowspan, text, addr=True):
    span = f'<hp:cellSpan colSpan="{colspan}" rowSpan="{rowspan}"/>'
    where = f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/>' if addr else ""
    return (f"<hp:tc>{where}{span}<hp:subList><hp:p><hp:run>"
            f"<hp:t>{text}</hp:t></hp:run></hp:p></hp:subList></hp:tc>")


def _tbl(rows, n_rows, n_cols):
    body = "".join(f"<hp:tr>{''.join(r)}</hp:tr>" for r in rows)
    return f'<hp:tbl rowCnt="{n_rows}" colCnt="{n_cols}">{body}</hp:tbl>'


def budget_table(addr=True):
    """README에 실린 그 표. 2단 헤더에 병합이 걸려 있다."""
    return _tbl([
        [_tc(0, 0, 7, 1, "(단위: 원)", addr)],
        [_tc(0, 1, 1, 2, "품목", addr), _tc(1, 1, 1, 2, "규격", addr),
         _tc(2, 1, 1, 2, "수량", addr), _tc(3, 1, 2, 1, "단가", addr),
         _tc(5, 1, 2, 1, "금액", addr)],
        [_tc(3, 2, 1, 1, "정가", addr), _tc(4, 2, 1, 1, "할인가", addr),
         _tc(5, 2, 1, 1, "공급가", addr), _tc(6, 2, 1, 1, "부가세", addr)],
        [_tc(0, 3, 1, 1, "사무용 의자", addr), _tc(1, 3, 1, 1, "KS-320", addr),
         _tc(2, 3, 1, 1, "12", addr), _tc(3, 3, 1, 1, "180,000", addr),
         _tc(4, 3, 1, 1, "162,000", addr), _tc(5, 3, 1, 1, "1,944,000", addr),
         _tc(6, 3, 1, 1, "194,400", addr)],
    ], 4, 7)


def section_xml(addr=True, memo=True):
    memo_xml = ("<hp:memogroup><hp:memo><hp:p><hp:run>"
                "<hp:t>최신 자료 기준으로 업데이트해주세요.</hp:t>"
                "</hp:run></hp:p></hp:memo></hp:memogroup>") if memo else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}">'
        "<hp:p><hp:run><hp:t>◎ 예산 집행 내역</hp:t></hp:run></hp:p>"
        f"<hp:p><hp:run>{budget_table(addr)}</hp:run></hp:p>"
        "<hp:p><hp:run><hp:t>이상.</hp:t></hp:run></hp:p>"
        f"{memo_xml}"
        "</hs:sec>"
    )


def write_hwpx(path, addr=True, memo=True):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("version.xml", '<?xml version="1.0"?><hv:HCFVersion/>')
        z.writestr("Contents/section0.xml", section_xml(addr, memo))
    return str(path)
