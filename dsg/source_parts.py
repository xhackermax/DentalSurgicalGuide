"""Ordered source-fragment loader used by DSG's transitional refactor.

The heavy Blender modules historically lived in single generated files. During
9.5.8 they are split into domain-sized source fragments while deliberately
executing in one module namespace. This preserves every public symbol and avoids
circular-import regressions while making each domain independently editable and
reviewable. Fragments can become true modules after their boundaries gain
integration-test coverage.
"""
from __future__ import annotations

import __future__
from pathlib import Path
from typing import Iterable, MutableMapping


def exec_source_parts(
    module_globals: MutableMapping[str, object],
    module_file: str,
    parts_dir: str,
    parts: Iterable[str],
    *,
    future_annotations: bool = False,
) -> None:
    root = Path(module_file).resolve().parent / parts_dir
    flags = __future__.annotations.compiler_flag if future_annotations else 0
    for part_name in parts:
        path = root / part_name
        source = path.read_text(encoding="utf-8")
        code = compile(source, str(path), "exec", flags=flags, dont_inherit=True)
        exec(code, module_globals, module_globals)
