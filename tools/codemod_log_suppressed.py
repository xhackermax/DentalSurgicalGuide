"""Codemod: replace ``except Exception: pass`` with a DEBUG log + traceback.

Idempotent. Only handlers catching ``Exception``/``BaseException`` whose body
is exactly ``pass`` are rewritten; narrow handlers (``except KeyError: pass``)
are intentional control flow and are left alone.

    python tools/codemod_log_suppressed.py dsg/            # rewrite
    python tools/codemod_log_suppressed.py dsg/ --check    # exit 1 if any remain
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

CALL = '_DSG_LOG.debug("suppressed exception", exc_info=True)'
HEADER = "import logging as _dsg_logging\n_DSG_LOG = _dsg_logging.getLogger(__name__)\n"
BROAD = {"Exception", "BaseException"}
# Fragment sets share one namespace: define the logger once, in the first part.
FRAGMENT_HEADS = {"_guide_parts": None,  # 00_a already defines _DSG_LOG ("dsg.guide")
                  "_dicom_parts": "00_constants_runtime_dependencies.py",
                  "_alignment_parts": "00_alignment_core.py"}


def _is_broad(handler: ast.ExceptHandler) -> bool:
    t = handler.type
    if t is None:
        return True
    names = t.elts if isinstance(t, ast.Tuple) else [t]
    return any(isinstance(n, ast.Name) and n.id in BROAD for n in names)


def targets(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _is_broad(node) \
                and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            yield node.body[0]


def _header_line(tree: ast.Module) -> int:
    """0-based line index after the docstring and ``from __future__`` imports."""
    line = 0
    for i, node in enumerate(tree.body):
        is_doc = i == 0 and isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant) \
            and isinstance(node.value.value, str)
        is_future = isinstance(node, ast.ImportFrom) and node.module == "__future__"
        if is_doc or is_future:
            line = node.end_lineno
        else:
            break
    return line


def needs_header(path: Path) -> bool:
    parent = path.parent.name
    if parent in FRAGMENT_HEADS:
        return FRAGMENT_HEADS[parent] == path.name
    return True


def rewrite(path: Path) -> int:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    passes = sorted(targets(tree), key=lambda n: (n.lineno, n.col_offset), reverse=True)
    lines = src.splitlines(keepends=True)
    for node in passes:
        i, c = node.lineno - 1, node.col_offset
        assert lines[i][c:c + 4] == "pass", (path, node.lineno)
        lines[i] = lines[i][:c] + CALL + lines[i][c + 4:]
    new = "".join(lines)
    has_logger = "_DSG_LOG =" in new or "_DSG_LOG=" in new
    fragment_set = path.parent.name in FRAGMENT_HEADS
    if (passes or (fragment_set and needs_header(path))) and not has_logger and needs_header(path):
        at = _header_line(ast.parse(new))
        lines = new.splitlines(keepends=True)
        lines.insert(at, ("\n" if at else "") + HEADER)
        new = "".join(lines)
    if new != src:
        ast.parse(new)
        path.write_text(new, encoding="utf-8")
    return len(passes)


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "dsg")
    check = "--check" in argv
    total = 0
    for path in sorted(root.rglob("*.py")):
        if check:
            n = sum(1 for _ in targets(ast.parse(path.read_text(encoding="utf-8"))))
            if n:
                print(f"{path}: {n}")
        else:
            n = rewrite(path)
        total += n
    print(f"{'remaining' if check else 'rewritten'}: {total}")
    return 1 if (check and total) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
