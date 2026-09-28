from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1] / "dsg"


def _sources():
    return {p:p.read_text("utf-8",errors="ignore") for p in ROOT.rglob("*.py")}


def test_custom_literal_operator_buttons_have_an_implementation():
    sources=_sources(); all_text="\n".join(sources.values())
    # Include direct bl_idname strings and constant-backed installer id.
    ids=set(re.findall(r"\bbl_idname\s*=\s*[\"']([^\"']+)",all_text))
    constants=dict(re.findall(r"\b([A-Z][A-Z0-9_]+)\s*=\s*[\"']([^\"']+)[\"']",all_text))
    for const in re.findall(r"\bbl_idname\s*=\s*([A-Z][A-Z0-9_]+)",all_text):
        if const in constants: ids.add(constants[const])
    refs=set(re.findall(r"\.operator\(\s*[\"']([^\"']+)",all_text))
    custom={x for x in refs if x.startswith(("dsg.","dsg_suite.","dicom_wizard_pro.","dicp.","dct."))}
    assert not sorted(custom-ids), sorted(custom-ids)


def test_class_bl_idname_button_references_resolve_to_a_defined_class():
    sources=_sources(); all_text="\n".join(sources.values())
    classes=set(re.findall(r"\bclass\s+(\w+)\s*\(",all_text))
    refs=set(re.findall(r"\.operator\(\s*(\w+)\.bl_idname",all_text))
    # Cross-module CBCT operator is intentionally referenced by imported symbol.
    allowed={"DSG_OT_CBCTAcceptFDI"}
    assert not sorted(refs-classes-allowed), sorted(refs-classes-allowed)



def test_custom_button_operator_classes_are_in_a_registration_contract():
    import ast
    sources = _sources()
    all_text = "\n".join(sources.values())
    id_to_class = {}
    for text in sources.values():
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.Assign, ast.AnnAssign)):
                        targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                        if not any(isinstance(t, ast.Name) and t.id == "bl_idname" for t in targets):
                            continue
                        value = item.value
                        if isinstance(value, ast.Constant) and isinstance(value.value, str):
                            id_to_class[value.value] = node.name
                        elif isinstance(value, ast.Name):
                            # Resolve module-level string constants below.
                            pass
    constants = dict(re.findall(r"\b([A-Z][A-Z0-9_]+)\s*=\s*[\"']([^\"']+)[\"']", all_text))
    for text in sources.values():
        try: tree = ast.parse(text)
        except SyntaxError: continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "bl_idname" for t in item.targets):
                        if isinstance(item.value, ast.Name) and item.value.id in constants:
                            id_to_class[constants[item.value.id]] = node.name

    refs = set(re.findall(r"\.operator\(\s*[\"']([^\"']+)", all_text))
    custom = {x for x in refs if x.startswith(("dsg.", "dsg_suite.", "dicom_wizard_pro.", "dicp.", "dct."))}

    registered_names = set()
    for text in sources.values():
        try: tree = ast.parse(text)
        except SyntaxError: continue
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if not any(isinstance(t, ast.Name) and t.id.endswith("CLASSES") for t in targets):
                continue
            value = node.value
            if isinstance(value, (ast.List, ast.Tuple)):
                for elt in value.elts:
                    if isinstance(elt, ast.Name):
                        registered_names.add(elt.id)

    missing = []
    for op_id in sorted(custom):
        cls = id_to_class.get(op_id)
        if cls is None:
            continue
        if cls not in registered_names:
            missing.append((op_id, cls))
    assert not missing, missing
