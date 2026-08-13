"""HWP 배포용 ViewText 읽기 지원. 표준 라이브러리만 사용한다.

알고리즘은 HWP 5 배포용 문서 규격과 rhwp/kordoc(MIT), FIPS-197을 교차검증했다.
"""
import struct
import zlib

TAG_DISTRIBUTE_DOC_DATA = 0x1C
S = bytes.fromhex("637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b27509832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cfd0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdbe0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9ee1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16")
IS = bytes.fromhex("52096ad53036a538bf40a39e81f3d7fb7ce339829b2fff87348e4344c4dee9cb547b9432a6c2233dee4c950b42fac34e082ea16628d924b2765ba2496d8bd12572f8f66486689816d4a45ccc5d65b6926c704850fdedb9da5e154657a78d9d8490d8ab008cbcd30af7e45805b8b34506d02c1e8fca3f0f02c1afbd0301138a6b3a9111414f67dcea97f2cfcef0b4e67396ac7422e7ad3585e2f937e81c75df6e47f11a711d29c5896fb7620eaa18be1bfc563e4bc6d279209adbc0fe78cd5af41fdda8338807c731b11210592780ec5f60517fa919b54a0d2de57a9f93c99cefa0e03b4dae2af5b0c8ebbb3c83539961172b047eba77d626e169146355210c7d")
RCON = (1, 2, 4, 8, 16, 32, 64, 128, 27, 54)

class ViewTextError(ValueError):
    pass

class _Lcg:
    def __init__(self, seed):
        self.seed = seed & 0xFFFFFFFF
    def rand(self):
        self.seed = (self.seed * 214013 + 2531011) & 0xFFFFFFFF
        return (self.seed >> 16) & 0x7FFF

def _unscramble(payload):
    if len(payload) < 256:
        raise ViewTextError("DISTRIBUTE_DOC_DATA가 256바이트보다 짧다")
    out = bytearray(payload[:256])
    random = _Lcg(struct.unpack_from("<I", out)[0])
    left = 0
    key = 0
    for index in range(256):
        if not left:
            key = random.rand() & 0xFF
            left = (random.rand() & 15) + 1
        if index >= 4:
            out[index] ^= key
        left -= 1
    return bytes(out)

def _mul(a, b):
    result = 0
    for _ in range(8):
        if b & 1:
            result ^= a
        a = ((a << 1) ^ 0x11B) if a & 0x80 else a << 1
        a &= 0xFF
        b >>= 1
    return result

def _round_keys(key):
    if len(key) != 16:
        raise ViewTextError("AES-128 키 길이가 16바이트가 아니다")
    words = [list(key[offset:offset + 4]) for offset in range(0, 16, 4)]
    for index in range(4, 44):
        temp = words[index - 1][:]
        if index % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [S[value] for value in temp]
            temp[0] ^= RCON[index // 4 - 1]
        words.append([words[index - 4][j] ^ temp[j] for j in range(4)])
    return [sum((words[rnd * 4 + j] for j in range(4)), []) for rnd in range(11)]

def _add_key(state, key):
    for index, value in enumerate(key):
        state[index] ^= value

def _decrypt_block(block, keys):
    state = list(block)
    _add_key(state, keys[10])
    for rnd in range(9, -1, -1):
        previous = state[:]
        for row in range(4):
            for col in range(4):
                state[col * 4 + row] = previous[((col - row) % 4) * 4 + row]
        state[:] = [IS[value] for value in state]
        _add_key(state, keys[rnd])
        if rnd:
            for col in range(4):
                pos = col * 4
                a = state[pos:pos + 4]
                state[pos] = _mul(a[0], 14) ^ _mul(a[1], 11) ^ _mul(a[2], 13) ^ _mul(a[3], 9)
                state[pos + 1] = _mul(a[0], 9) ^ _mul(a[1], 14) ^ _mul(a[2], 11) ^ _mul(a[3], 13)
                state[pos + 2] = _mul(a[0], 13) ^ _mul(a[1], 9) ^ _mul(a[2], 14) ^ _mul(a[3], 11)
                state[pos + 3] = _mul(a[0], 11) ^ _mul(a[1], 13) ^ _mul(a[2], 9) ^ _mul(a[3], 14)
    return bytes(state)

def aes128_ecb_decrypt(data, key):
    if not data or len(data) % 16:
        raise ViewTextError("AES 데이터 길이가 16바이트 배수가 아니다")
    keys = _round_keys(bytes(key))
    return b"".join(_decrypt_block(data[i:i + 16], keys) for i in range(0, len(data), 16))

def decrypt_viewtext_section(data, compressed, max_output=256 * 1024 * 1024):
    if len(data) < 4:
        raise ViewTextError("ViewText 첫 레코드 헤더가 잘렸다")
    header = struct.unpack_from("<I", data)[0]
    tag = header & 0x3FF
    size = (header >> 20) & 0xFFF
    header_size = 4
    if size == 0xFFF:
        if len(data) < 8:
            raise ViewTextError("ViewText 확장 레코드 헤더가 잘렸다")
        size = struct.unpack_from("<I", data, 4)[0]
        header_size = 8
    end = header_size + size
    if tag != TAG_DISTRIBUTE_DOC_DATA or size < 256 or end > len(data):
        raise ViewTextError("DISTRIBUTE_DOC_DATA 레코드가 올바르지 않다")
    payload = _unscramble(data[header_size:header_size + 256])
    offset = 4 + (payload[0] & 15)
    key = payload[offset:offset + 16]
    encrypted = data[end:]
    remainder = len(encrypted) % 16
    if remainder:
        if any(encrypted[-remainder:]):
            raise ViewTextError("ViewText 암호 데이터 끝이 블록 경계에서 잘렸다")
        encrypted = encrypted[:-remainder]
    plain = aes128_ecb_decrypt(encrypted, key)
    if not compressed:
        if len(plain) > max_output:
            raise ViewTextError("ViewText 본문이 처리 상한을 넘는다")
        return plain.rstrip(b"\0")
    decoder = zlib.decompressobj(-15)
    try:
        out = decoder.decompress(plain, max_output + 1)
        out += decoder.flush(max_output + 1 - len(out))
    except zlib.error as exc:
        raise ViewTextError("ViewText DEFLATE가 손상됐다") from exc
    if len(out) > max_output or not decoder.eof or decoder.unconsumed_tail:
        raise ViewTextError("ViewText 압축 해제 결과가 비정상적이다")
    return out
