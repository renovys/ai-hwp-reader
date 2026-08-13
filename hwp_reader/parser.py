"""AI HWP Reader 파서 공개 진입점."""

from . import _parser_core as _core
from ._parser_hardening import install as _install

_install(_core)

ARCHIVE_EXTS = _core.ARCHIVE_EXTS
CELL_OFFSET = _core.CELL_OFFSET
CHAR_CTRL = _core.CHAR_CTRL
HWPTAG_BEGIN = _core.HWPTAG_BEGIN
HWPTAG_CTRL_HEADER = _core.HWPTAG_CTRL_HEADER
HWPTAG_LIST_HEADER = _core.HWPTAG_LIST_HEADER
HWPTAG_MEMO_LIST = _core.HWPTAG_MEMO_LIST
HWPTAG_PARA_HEADER = _core.HWPTAG_PARA_HEADER
HWPTAG_PARA_RANGE_TAG = _core.HWPTAG_PARA_RANGE_TAG
HWPTAG_PARA_TEXT = _core.HWPTAG_PARA_TEXT
HWPTAG_TABLE = _core.HWPTAG_TABLE
HWP_SIGNATURE = _core.HWP_SIGNATURE
MAX_ARCHIVE_DOCUMENTS = _core.MAX_ARCHIVE_DOCUMENTS
MAX_ARCHIVE_MEMBER_SIZE = _core.MAX_ARCHIVE_MEMBER_SIZE
MAX_TABLE_CELLS = _core.MAX_TABLE_CELLS
TRACK_DELETE = _core.TRACK_DELETE
TRACK_INSERT = _core.TRACK_INSERT
WIDE_CTRL = _core.WIDE_CTRL
_section_number = _core._section_number
_validate_table_shape = _core._validate_table_shape
_records = _core._records
_decode_text = _core._decode_text
_decode_change_range = _core._decode_change_range
_read_stream = _core._read_stream
_grid = _core._grid
_parse_table = _core._parse_table
_parse_memo = _core._parse_memo
_parse_change_ranges = _core._parse_change_ranges
_read_hwp_changes = _core._read_hwp_changes
_hwp_flags = _core._hwp_flags
_hwpx_local = _core._hwpx_local
_hwpx_int = _core._hwpx_int
_hwpx_text_of = _core._hwpx_text_of
_direct_nested_tables = _core._direct_nested_tables
_hwpx_table = _core._hwpx_table
_hwpx_append_memos = _core._hwpx_append_memos
_hwpx_walk = _core._hwpx_walk
_hwpx_paragraph = _core._hwpx_paragraph
_zip_handle = _core._zip_handle
_is_zip = _core._is_zip
_is_hwpx = _core._is_hwpx
read_hwp = _core.read_hwp
read_hwpx = _core.read_hwpx
read = _core.read
read_documents = _core.read_documents
_md_cell = _core._md_cell
_render_table = _core._render_table
render = _core.render
render_documents = _core.render_documents
_validate_cells = _core._validate_cells
_decode_utf16 = _core._decode_utf16

del _install
