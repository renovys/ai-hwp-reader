"""strict CFB 우선, 알려진 비표준 할당표에만 호환 재시도를 적용한다."""

from contextvars import ContextVar

from ._ole import OleFile as StrictOleFile
from ._ole_compat import CompatOleFile

_COMPAT = ContextVar("ai_hwp_reader_compat_cfb", default=None)


def current_compat_warnings():
    """현재 읽기 호출에서 호환 CFB가 쓰였다면 경고 목록을 반환한다."""
    return _COMPAT.get()


class FallbackOleFile:
    """정상 문서는 strict 경로 하나만 타는 OLE 팩토리."""

    def __new__(cls, source):
        _COMPAT.set(None)
        try:
            ole = StrictOleFile(source)
            ole.compat_mode = False
            ole.compat_warnings = []
            return ole
        except ValueError as strict_error:
            try:
                ole = CompatOleFile(source)
            except ValueError:
                raise strict_error
            ole.compat_mode = True
            ole.strict_error = str(strict_error)
            warnings = tuple(ole.compat_warnings) or ("비표준 CFB 할당표를 호환 모드로 읽었다",)
            _COMPAT.set(warnings)
            return ole
