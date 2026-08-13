"""0.5 의미 복원 계층을 기존 단일 파일 생성물에 합친다."""
import hashlib
import re
from pathlib import Path
import build_single as legacy

ROOT = Path(__file__).resolve().parents[1]
MODULES = [
    ROOT / "hwp_reader" / "_ole_compat.py",
    ROOT / "hwp_reader" / "_ole_fallback.py",
    ROOT / "hwp_reader" / "_parser_features.py",
    ROOT / "hwp_reader" / "_parser_controls_text.py",
    ROOT / "hwp_reader" / "_viewtext.py",
    ROOT / "hwp_reader" / "_reader_v05.py",
    ROOT / "hwp_reader" / "_v05_enable.py",
]
RELATIVE_IMPORTS = (
    "from ._ole import DIFSECT, ENDOFCHAIN, FATSECT, FREESECT, NOSTREAM, OleFile",
    "from ._ole import OleFile as StrictOleFile",
    "from ._ole_compat import CompatOleFile",
    "from ._parser_features import *",
    "from ._parser_controls_text import control_effect, decode_para, paragraph_prefix",
    "from ._viewtext import decrypt_viewtext_section",
    "from . import _parser_core",
    "from ._ole_fallback import FallbackOleFile, current_compat_warnings",
    "from ._reader_v05 import install",
)


def _extra_source():
    parts = []
    for path in MODULES:
        text = path.read_text(encoding="utf-8").rstrip()
        for line in RELATIVE_IMPORTS:
            text = text.replace(line, "")
        if path.name == "_ole_fallback.py":
            # 패키지에서는 `from ._ole import OleFile as StrictOleFile`이 담당한다.
            # 한 파일로 펼칠 때는 같은 별칭을 직접 만든다.
            text = "StrictOleFile = OleFile\n\n" + text
        if path.name == "_v05_enable.py":
            renames = {
                "_base_read_hwpx": "_single_base_read_hwpx",
                "_base_read_hwp": "_single_base_read_hwp",
                "_base_render": "_single_base_render",
                "_validate_blocks": "_single_validate_blocks",
                "_validate_table": "_single_validate_table",
                "_read_hwpx": "_single_post_read_hwpx",
                "_read_hwp": "_single_post_read_hwp",
                "_render": "_single_post_render",
            }
            for old, new in renames.items():
                pattern = r"(?<![A-Za-z0-9_])" + re.escape(old) + r"(?![A-Za-z0-9_])"
                text = re.sub(pattern, new, text)
            text = text.replace("_parser_core", "sys.modules[__name__]")
        parts.append(text)
    return "\n\n".join(parts)


def build_source():
    base = legacy.build_source()
    marker = 'if __name__ == "__main__":'
    if base.count(marker) != 1:
        raise RuntimeError("기존 단일 파일 main 경계를 찾지 못했다")
    before, main = base.split(marker, 1)
    combined = before.rstrip() + "\n\n" + _extra_source() + "\n\n" + marker + main
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]
    return re.sub(r"source-sha256:[0-9a-f]{16}", f"source-sha256:{digest}", combined, count=1)


def build_skill(single):
    prefix = legacy.SKILL_PREFIX.replace(
        "핵심 내용·표·메모·변경추적을 정리한다.",
        "핵심 내용·표·메모·변경추적·각주·링크를 정리한다.",
    )
    suffix = """

## 0.5 지원 범위
- HWP 5.0 / HWPX 본문, 병합·중첩 표, 빈 행, 숨은 메모, 변경 내용 추적
- 각주·미주, 하이퍼링크, 수식 스크립트, 이미지 참조, 글상자 텍스트
- HWP 배포용 문서(ViewText), strict 실패 시 제한적 비표준 CFB 호환 읽기
- 여러 문서가 든 ZIP, XML/ZIP/레코드/압축 해제 자원 상한, DTD/ENTITY 차단
- 외부 런타임 의존성 0개, 네트워크 요청 없음, 읽기 전용

지원하지 않음: 열기 암호·DRM, OCR, HWP 3.0, 문서 쓰기·수정.
이미지는 바이너리를 기본 추출하거나 OCR하지 않고 문서 내부 참조를 보존한다.
"""
    return prefix.rstrip() + "\n\n```python\n" + single + "\n```\n" + suffix


def main():
    single = build_source()
    legacy.SINGLE_SOURCE.write_text(single, encoding="utf-8")
    legacy.SKILL_SOURCE.write_text(build_skill(single), encoding="utf-8")
    print("generated: skill/hwp_reader_single.py")
    print("generated: SKILL.md")


if __name__ == "__main__":
    main()
