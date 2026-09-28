"""Static regression checks for the 9.5.8 heavy-module source split."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "dsg"


def _parts_from_facade(name: str):
    tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_PARTS":
                    return list(ast.literal_eval(node.value))
    raise AssertionError(f"_PARTS not found in {name}")


def test_heavy_facades_are_small_and_all_parts_exist():
    cases = (
        ("guide_module.py", "_guide_parts"),
        ("dicom_module.py", "_dicom_parts"),
        ("alignment_module.py", "_alignment_parts"),
    )
    for facade, folder in cases:
        assert len((ROOT / facade).read_text(encoding="utf-8").splitlines()) < 80
        parts = _parts_from_facade(facade)
        assert parts
        for part in parts:
            path = ROOT / folder / part
            assert path.is_file(), path
            compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_no_refactor_fragment_exceeds_5000_lines():
    for folder in ("_guide_parts", "_dicom_parts", "_alignment_parts"):
        for path in (ROOT / folder).glob("*.py"):
            assert len(path.read_text(encoding="utf-8").splitlines()) <= 5000, path


def test_source_part_loader_uses_explicit_future_flag_not_source_rewriting():
    source = (ROOT / "source_parts.py").read_text(encoding="utf-8")
    assert "__future__.annotations.compiler_flag" in source
    assert "dont_inherit=True" in source
