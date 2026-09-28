"""Regression tests for the defects fixed in DSG 9.7.0.

Each test names the defect it guards (AGENTS.md §1.11: every important fixed
bug gains a regression test).
"""
from __future__ import annotations

import ast
import collections
import importlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "dsg"
FRAGMENT_DIRS = ("_guide_parts", "_dicom_parts", "_alignment_parts")


# ── 1. EXACT implant/tooth clearance crashed with NameError: np ─────────────
def test_surgical_context_imports_numpy_for_exact_mode():
    tree = ast.parse((ROOT / "dental_mapping" / "surgical_context.py").read_text("utf-8"))
    imported = {
        (alias.asname or alias.name)
        for node in tree.body if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "np" in imported


def test_surgical_context_module_exposes_np_at_runtime():
    module = importlib.import_module("dsg.dental_mapping.surgical_context")
    assert getattr(module, "np", None) is not None


# ── 2. "REPAIR CUDA RUNTIME" pointed to a non-existent operator ─────────────
def test_cuda_repair_button_uses_force_reinstall():
    panel = (ROOT / "_dicom_parts" / "07_panels_registration.py").read_text("utf-8")
    assert "dsg.install_totalseg_v955" not in panel
    assert re.search(r'repair_op\s*=\s*cuda_row\.operator\(\s*"dsg\.install_totalseg"', panel)
    assert "repair_op.force = True" in panel
    bootstrap = (ROOT / "runtime_bootstrap.py").read_text("utf-8")
    assert "force: bpy.props.BoolProperty(" in bootstrap
    assert "and not self.force" in bootstrap


def test_operator_ids_are_stable_not_versioned():
    ids = []
    for path in ROOT.rglob("*.py"):
        ids += re.findall(r"bl_idname\s*=\s*[\"']([^\"']+)[\"']", path.read_text("utf-8"))
    ids += re.findall(r'INSTALL_OPERATOR_ID\s*=\s*"([^"]+)"', (ROOT / "runtime_bootstrap.py").read_text("utf-8"))
    versioned = sorted(i for i in ids if re.search(r"_v\d{3,}$", i))
    assert not versioned, versioned


# ── 3. STL export wrote "<name>DSG_ExportGuide_Work.stl" (use_batch=True) ───
def _guide_stl_export_kwargs() -> dict:
    src = (ROOT / "_guide_parts" / "08_export_final_ui_registration.py").read_text("utf-8")
    tree = ast.parse(src)
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == "DSG_OT_ExportGuideSTL":
            for node in ast.walk(cls):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "stl_export"):
                    return {kw.arg: ast.literal_eval(kw.value) for kw in node.keywords
                            if kw.arg != "filepath"}
    raise AssertionError("wm.stl_export call not found in DSG_OT_ExportGuideSTL")


def test_guide_export_does_not_use_batch_mode():
    assert _guide_stl_export_kwargs().get("use_batch") is False


@pytest.mark.requires_bpy
def test_guide_export_kwargs_write_exact_filename(tmp_path):
    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.name = "DSG_ExportGuide_Work"
    obj.select_set(True)
    target = tmp_path / "DSG_Guide_case.stl"
    bpy.ops.wm.stl_export(filepath=str(target), **_guide_stl_export_kwargs())
    assert target.is_file(), sorted(p.name for p in tmp_path.iterdir())


# ── 4. core.py used cbct_dental_module without importing it ─────────────────
def test_no_undefined_names_in_standalone_modules():
    ruff = shutil.which("ruff")
    if ruff is None:
        pytest.skip("ruff not installed")
    exclude = ",".join(FRAGMENT_DIRS)
    result = subprocess.run(
        [ruff, "check", "--select", "F821", "--exclude", exclude, "--output-format", "concise", str(ROOT)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout


# ── Source-fragment namespace guard ─────────────────────────────────────────
@pytest.mark.parametrize("fragment_dir", FRAGMENT_DIRS)
def test_fragments_never_redefine_a_top_level_symbol(fragment_dir):
    """Fragments share one namespace: a later redefinition silently wins."""
    seen = collections.defaultdict(list)
    for path in sorted((ROOT / fragment_dir).glob("*.py")):
        for node in ast.parse(path.read_text("utf-8")).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                seen[node.name].append(f"{path.name}:{node.lineno}")
    duplicates = {k: v for k, v in seen.items() if len(v) > 1}
    assert not duplicates, duplicates


# ── Package lazy loading: placeholders must not shadow submodules ──────────
def test_package_does_not_shadow_submodules_with_none():
    tree = ast.parse((ROOT / "__init__.py").read_text("utf-8"))
    shadowed = [
        t.id for node in tree.body if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant) and node.value.value is None
        for t in node.targets if isinstance(t, ast.Name) and (ROOT / f"{t.id}.py").exists()
    ]
    assert not shadowed, shadowed


# ── Packaging: install validator only requires files that ship ─────────────
def test_install_validator_required_files_exist():
    src = (ROOT / "__init__.py").read_text("utf-8")
    block = src[src.index("required = ("):src.index(")\n    base = _addon_dir()")]
    required = re.findall(r'"([^"]+)"', block)
    missing = [r for r in required if not (ROOT / r).is_file()]
    assert required and not missing, missing


def test_addon_package_ships_no_changelog_or_test_files():
    stray = [p.name for p in ROOT.iterdir() if p.suffix in {".md", ".txt"} and p.name != "THIRD_PARTY_MODEL_NOTICE.txt"]
    assert not stray, stray
    assert not (ROOT / "tests_pure").exists()


# ── 9.7.1: irrigation ───────────────────────────────────────────────────────
def test_link_tool_never_creates_a_link_of_a_link():
    """Links whose source is another Link were silently dropped by Apply Irrigation."""
    src = (ROOT / "_guide_parts" / "06_irrigation_b.py").read_text("utf-8")
    modal = src[src.index("class DSG_OT_LinkIrrigation"):src.index("class DSG_OT_RemoveLastIrrigation")]
    assert "if bool(source_entry.get('link', False)):" in modal
    assert "source_entry = trunk_entry" in modal


def test_seal_builder_no_longer_uses_create_circle_geom_key():
    """9.7.1: ret['geom'] was always empty in Blender 3+, so no seal was ever built."""
    for path in (ROOT / "_guide_parts").glob("*.py"):
        assert "ret.get('geom'" not in path.read_text("utf-8"), path.name


def test_direct_controls_resolve_their_own_sleeve():
    """9.7.2: DIRECT Link channels started inside the ACTIVE sleeve."""
    src = (ROOT / "_guide_parts" / "02_implant_animation_geometry_c.py").read_text("utf-8")
    body = src[src.index("def _normalize_direct_irrigation_controls"):src.index("def get_sleeve_lateral_port_geometry")]
    assert "get_nearest_implant_to_point(props, pts[0])" in body


def test_frangible_wall_is_100_microns():
    src = (ROOT / "_guide_parts" / "00_bootstrap_constants_assets_a.py").read_text("utf-8")
    assert re.search(r"IRRIGATION_FRANGIBLE_SEAL_CENTER_THICKNESS_MM_FIXED = 0\.10\b", src)
