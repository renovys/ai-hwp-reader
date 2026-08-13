"""0.5 계열 실문서 의미 복원 계층.

정상 HWP/HWPX의 기존 fast path를 유지하면서 문단 번호·글머리표, 각주·미주,
하이퍼링크, 수식 스크립트, 글상자·이미지 참조처럼 AI가 문서 의미를 이해하는 데
필요한 구조를 추가로 보존한다.

포맷/동작 교차검증: edwardkim/rhwp, chrisryugj/kordoc (MIT).
"""

MAX_HWP_RECORDS = 500_000
MAX_HWP_STREAM_BYTES = 256 * 1024 * 1024
MAX_HWP_TOTAL_BYTES = 512 * 1024 * 1024
MAX_HWPX_SECTION_BYTES = 64 * 1024 * 1024
MAX_HWPX_TOTAL_XML_BYTES = 256 * 1024 * 1024
MAX_FEATURE_DEPTH = 8
MAX_HYPERLINK_LENGTH = 2_000

TAG_BIN_DATA = 0x12
TAG_NUMBERING = 0x17
TAG_BULLET = 0x18
TAG_DOC_PARA_SHAPE = 0x19
TAG_EQEDIT = 0x58
TAG_SHAPE_COMPONENT = 0x4C
TAG_SHAPE_COMPONENT_PICTURE = 0x55


def _cid(text):
    return int.from_bytes(text.encode("ascii"), "big")


CTRL_TBL = _cid("tbl ")
CTRL_GSO = _cid("gso ")
CTRL_EQED = _cid("eqed")
CTRL_HEAD = _cid("head")
CTRL_FOOT = _cid("foot")
CTRL_FN = _cid("fn  ")
CTRL_EN = _cid("en  ")
CTRL_ATNO = _cid("atno")
CTRL_NWNO = _cid("nwno")
CTRL_SECD = _cid("secd")
CTRL_OLE = _cid("ole ")
FIELD_HLK = _cid("%hlk")

KNOWN_CTRL_IDS = {
    CTRL_TBL, CTRL_GSO, CTRL_EQED, CTRL_HEAD, CTRL_FOOT,
    CTRL_FN, CTRL_EN, CTRL_ATNO, CTRL_NWNO, CTRL_SECD, CTRL_OLE,
}


def _swap32(value):
    return int.from_bytes(value.to_bytes(4, "little"), "big")


def _is_field_id(value):
    return ((value >> 24) & 0xFF) == 0x25


def _normalize_ctrl_id(value):
    if value in KNOWN_CTRL_IDS or _is_field_id(value):
        return value
    swapped = _swap32(value)
    if swapped in KNOWN_CTRL_IDS or _is_field_id(swapped):
        return swapped
    return value


def _records_limited(module, data):
    out = []
    pos, end = 0, len(data)
    while pos < end:
        if len(out) >= MAX_HWP_RECORDS:
            raise ValueError(f"손상된 HWP 레코드: {MAX_HWP_RECORDS}개 상한을 넘는다")
        if pos + 4 > end:
            raise ValueError("손상된 HWP 레코드: 헤더가 4바이트보다 짧다")
        header = module.struct.unpack_from("<I", data, pos)[0]
        tag = header & 0x3FF
        level = (header >> 10) & 0x3FF
        size = (header >> 20) & 0xFFF
        pos += 4
        if size == 0xFFF:
            if pos + 4 > end:
                raise ValueError("손상된 HWP 레코드: 확장 크기가 잘렸다")
            size = module.struct.unpack_from("<I", data, pos)[0]
            pos += 4
        if size > end - pos:
            raise ValueError("손상된 HWP 레코드: payload가 섹션 끝을 넘는다")
        out.append((tag, level, data[pos:pos + size]))
        pos += size
    return out


def _inflate_raw_limited(module, raw, max_bytes, what):
    dec = module.zlib.decompressobj(-15)
    try:
        out = dec.decompress(raw, max_bytes + 1)
    except module.zlib.error as exc:
        raise ValueError(f"{what}: HWP 압축 스트림이 손상됐다") from exc
    if len(out) > max_bytes or dec.unconsumed_tail:
        raise ValueError(f"{what}: 압축 해제 결과가 {max_bytes}바이트 상한을 넘는다")
    try:
        out += dec.flush(max_bytes + 1 - len(out))
    except module.zlib.error as exc:
        raise ValueError(f"{what}: HWP 압축 스트림이 손상됐다") from exc
    if len(out) > max_bytes:
        raise ValueError(f"{what}: 압축 해제 결과가 {max_bytes}바이트 상한을 넘는다")
    if not dec.eof:
        raise ValueError(f"{what}: HWP 압축 스트림이 끝나기 전에 잘렸다")
    return out


def _hwp_string(module, data, offset):
    if offset + 2 > len(data):
        return "", len(data)
    length = module.struct.unpack_from("<H", data, offset)[0]
    start = offset + 2
    end = start + length * 2
    if end > len(data):
        raise ValueError("손상된 DocInfo: UTF-16 문자열이 레코드 끝을 넘는다")
    if not length:
        return "", start
    return module._decode_utf16(data[start:end], "HWP DocInfo"), end


def _parse_docinfo(module, ole, compressed):
    info = {"para_shapes": [], "numberings": [], "bullets": [], "bin_data": []}
    if not ole.exists("DocInfo"):
        return info
    records = module._records(module._read_stream(ole, "DocInfo", compressed))
    for tag, _level, data in records:
        if tag == TAG_DOC_PARA_SHAPE and len(data) >= 4:
            attr = module.struct.unpack_from("<I", data, 0)[0]
            info["para_shapes"].append({
                "head_type": (attr >> 23) & 0x03,
                "level": (attr >> 25) & 0x07,
                "numbering_id": module.struct.unpack_from("<H", data, 30)[0]
                if len(data) >= 32 else 0,
            })
        elif tag == TAG_BIN_DATA and len(data) >= 2:
            attr = module.struct.unpack_from("<H", data, 0)[0]
            kind = attr & 0x000F
            if kind == 0:
                info["bin_data"].append({"kind": "link", "storage_id": 0, "extension": ""})
            else:
                storage_id = module.struct.unpack_from("<H", data, 2)[0] if len(data) >= 4 else 0
                extension, _ = _hwp_string(module, data, 4)
                info["bin_data"].append({
                    "kind": "storage" if kind == 2 else "embed",
                    "storage_id": storage_id,
                    "extension": extension.strip(".\0"),
                })
        elif tag == TAG_NUMBERING and len(data) >= 14:
            formats, number_formats = [], []
            starts = [1] * 7
            offset = 0
            for _ in range(7):
                if offset + 12 > len(data):
                    formats.append("")
                    number_formats.append(0)
                    continue
                attr = module.struct.unpack_from("<I", data, offset)[0]
                number_formats.append((attr >> 5) & 0x0F)
                offset += 12
                value, offset = _hwp_string(module, data, offset)
                formats.append(value)
            base_start = 1
            if offset + 2 <= len(data):
                base_start = module.struct.unpack_from("<H", data, offset)[0] or 1
                offset += 2
            for level in range(7):
                if offset + 4 <= len(data):
                    starts[level] = module.struct.unpack_from("<I", data, offset)[0] or 1
                    offset += 4
                else:
                    starts[level] = base_start
            info["numberings"].append({
                "formats": formats, "number_formats": number_formats, "starts": starts,
            })
        elif tag == TAG_BULLET and len(data) >= 14:
            code = module.struct.unpack_from("<H", data, 12)[0]
            info["bullets"].append(chr(code) if code and code != 0xFFFF else "•")
    return info


class _NumberingState:
    def __init__(self):
        self.current = 0
        self.counters = [0] * 7
        self.history = {}

    def advance(self, numbering_id, level):
        level = min(max(level, 0), 6)
        if self.current != numbering_id:
            if self.current:
                self.history[self.current] = self.counters[:]
            if numbering_id in self.history:
                self.counters = self.history[numbering_id][:]
            else:
                old = self.counters
                self.counters = [0] * 7
                for i in range(level):
                    self.counters[i] = old[i]
            self.current = numbering_id
        self.counters[level] += 1
        for i in range(level + 1, 7):
            self.counters[i] = 0
        return self.counters[:]


def _roman(number):
    if number <= 0 or number > 3999:
        return str(number)
    pairs = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
             (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
             (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
    out = []
    for value, glyph in pairs:
        while number >= value:
            number -= value
            out.append(glyph)
    return "".join(out)


def _latin(number, upper=True):
    if number <= 0:
        return str(number)
    out = ""
    base = 65 if upper else 97
    while number:
        number -= 1
        out = chr(base + number % 26) + out
        number //= 26
    return out


def _east_asian(number, digits, units, zero):
    if number == 0:
        return zero
    if number < 0 or number > 99999:
        return str(number)
    result, unit = "", 0
    while number:
        digit = number % 10
        if digit:
            d = "" if digit == 1 and unit else digits[digit]
            result = d + units[unit] + result
        number //= 10
        unit += 1
    return result


def _format_number(number, code, auto=False):
    if code == 1:
        return chr(0x2460 + number - 1) if 1 <= number <= 20 else str(number)
    if code == 2:
        return _roman(number)
    if code == 3:
        return _roman(number).lower()
    if code == 4:
        return _latin(number, True)
    if code == 5:
        return _latin(number, False)
    ganada_code = 6 if auto else 8
    hangul_code = 7 if auto else 12
    hanja_code = 8 if auto else 13
    if code == ganada_code:
        table = "가나다라마바사아자차카타파하"
        return table[number - 1] if 1 <= number <= len(table) else str(number)
    if not auto and code == 10:
        table = "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ"
        return table[number - 1] if 1 <= number <= len(table) else str(number)
    if code == hangul_code:
        return _east_asian(number,
                           ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"],
                           ["", "십", "백", "천", "만"], "영")
    if code == hanja_code:
        return _east_asian(number,
                           ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"],
                           ["", "十", "百", "千", "萬"], "零")
    return str(number)


def _expand_numbering(fmt, counters, numbering):
    out, i = [], 0
    while i < len(fmt):
        if fmt[i] == "^" and i + 1 < len(fmt) and fmt[i + 1] in "1234567":
            idx = int(fmt[i + 1]) - 1
            count = counters[idx] if idx < len(counters) else 0
            start = numbering["starts"][idx] if idx < len(numbering["starts"]) else 1
            number = start - 1 + count if count else start
            code = numbering["number_formats"][idx] if idx < len(numbering["number_formats"]) else 0
            out.append(_format_number(number, code))
            i += 2
        else:
            out.append(fmt[i])
            i += 1
    return "".join(out)


__all__ = [
    "MAX_HWP_RECORDS", "MAX_HWP_STREAM_BYTES", "MAX_HWP_TOTAL_BYTES",
    "MAX_HWPX_SECTION_BYTES", "MAX_HWPX_TOTAL_XML_BYTES", "MAX_FEATURE_DEPTH",
    "MAX_HYPERLINK_LENGTH", "TAG_BIN_DATA", "TAG_NUMBERING", "TAG_BULLET",
    "TAG_DOC_PARA_SHAPE", "TAG_EQEDIT", "TAG_SHAPE_COMPONENT",
    "TAG_SHAPE_COMPONENT_PICTURE", "CTRL_TBL", "CTRL_GSO", "CTRL_EQED",
    "CTRL_HEAD", "CTRL_FOOT", "CTRL_FN", "CTRL_EN", "CTRL_ATNO",
    "CTRL_NWNO", "CTRL_SECD", "CTRL_OLE", "FIELD_HLK",
    "_normalize_ctrl_id", "_records_limited", "_parse_docinfo",
    "_NumberingState", "_format_number", "_expand_numbering",
]
