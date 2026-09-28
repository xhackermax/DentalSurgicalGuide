# DSG 9.5.8 transitional namespace-preserving source split.
from .source_parts import exec_source_parts as _exec_source_parts

_PARTS = (
    '00_alignment_core.py',
    '01_alignment_operators_ui.py',
)
_exec_source_parts(globals(), __file__, '_alignment_parts', _PARTS)
del _exec_source_parts, _PARTS
