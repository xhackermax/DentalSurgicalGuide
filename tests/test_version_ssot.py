from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1] / "dsg"

def _tuple_assignment(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} tuple not found in {path.name}")

def _bl_info(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "bl_info" for t in node.targets):
            # Blender parses bl_info with literal_eval before importing: it must stay literal.
            return ast.literal_eval(node.value)
    raise AssertionError("bl_info not found")

def test_version_file_is_single_source_of_truth():
    version_file = ROOT / "version.py"
    assert version_file.is_file()
    version = _tuple_assignment(version_file, "DSG_VERSION")
    assert isinstance(version, tuple) and len(version) == 3

def test_bl_info_is_literal_and_matches_version_file():
    info = _bl_info(ROOT / "__init__.py")
    assert tuple(info["version"]) == _tuple_assignment(ROOT / "version.py", "DSG_VERSION")
    assert tuple(info["blender"]) >= (5, 2, 0)

def test_package_imports_version_ssot():
    package = (ROOT / "__init__.py").read_text(encoding="utf-8")
    assert "from .version import DSG_VERSION, DSG_VERSION_STR" in package
    assert "DSG_VERSION = (" not in package

def test_no_hardcoded_build_version_in_python_sources():
    import re
    version = ".".join(map(str, _tuple_assignment(ROOT / "version.py", "DSG_VERSION")))
    pattern = re.compile(r"[\"'][^\"'\n]*" + re.escape(version))
    offenders = [
        f"{p.relative_to(ROOT)}"
        for p in ROOT.rglob("*.py")
        if p.name != "version.py" and "__init__" != p.stem
        and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, offenders

def test_guide_reuses_package_bl_info_not_duplicate_version():
    guide = (ROOT / "_guide_parts" / "00_bootstrap_constants_assets_a.py").read_text(encoding="utf-8")
    # The guide derives its version from version.py; it must never import the
    # package bl_info (absent for Extensions) nor hard-code a version tuple.
    assert "from .version import DSG_VERSION" in guide
    assert "bl_info as bl_info" not in guide
    assert '"version": DSG_VERSION' in guide
    assert "DSG_VERSION = (" not in guide

def test_install_validator_requires_version_file():
    package = (ROOT / "__init__.py").read_text(encoding="utf-8")
    assert '"version.py"' in package

def test_core_can_replace_stale_previous_install_rna():
    core = (ROOT / "core.py").read_text(encoding="utf-8")
    assert "_core_remove_stale_scene_pointer()" in core
    assert "_core_unregister_stale_classes()" in core
    assert "Disable the previous DSG version first" not in core
