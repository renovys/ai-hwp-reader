"""생성 단일 파일의 0.5 기능 smoke test."""

import importlib.util
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SINGLE = ROOT / "skill" / "hwp_reader_single.py"
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS = "http://www.hancom.co.kr/hwpml/2011/section"


def test_단일파일도_0_5_의미복원기능을_실행한다():
    name = "single_v05_smoke"
    spec = importlib.util.spec_from_file_location(name, SINGLE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    sys.modules.pop(name, None)

    xml = (
        f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}">'
        '<hp:p><hp:run><hp:t>본문 </hp:t>'
        '<hp:footNote><hp:p><hp:run><hp:t>각주 내용</hp:t></hp:run></hp:p></hp:footNote>'
        '<hp:equation><hp:script><hp:t>x+y</hp:t></hp:script></hp:equation>'
        '<hp:hyperlink href="https://example.com"><hp:t>링크</hp:t></hp:hyperlink>'
        '<hp:pic binaryItemIDRef="BIN0001"/>'
        '</hp:run></hp:p></hs:sec>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", xml)

    rendered = module.render(module.read(buf.getvalue(), name="meaning.hwpx"), "md")
    assert "본문" in rendered
    assert "[수식: x+y]" in rendered
    assert "[각주] 각주 내용" in rendered
    assert "[하이퍼링크] https://example.com" in rendered
    assert "[이미지 · BIN0001]" in rendered
