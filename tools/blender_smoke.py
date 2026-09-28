"""Real-Blender smoke test for DSG (register → introspect → unregister).

Run with Blender:   blender --background --factory-startup --python tools/blender_smoke.py
or with the bpy wheel: python tools/blender_smoke.py

Exit code 0 = PASS. It verifies that:
  * the add-on registers and unregisters cleanly (twice, to catch leaks),
  * every operator id referenced from UI code exists after registration,
  * the DSG panels draw without raising in an empty scene.
"""
from __future__ import annotations

import ast
import re
import sys
import traceback
from pathlib import Path

import bpy
import addon_utils

REPO = Path(__file__).resolve().parents[1]
ADDON = "dsg"
_OP_CALL = re.compile(r"\.operator\(\s*['\"]([a-z0-9_]+\.[a-z0-9_]+)['\"]")


def _referenced_operator_ids() -> set[str]:
    ids: set[str] = set()
    for path in (REPO / ADDON).rglob("*.py"):
        ids.update(_OP_CALL.findall(path.read_text(encoding="utf-8")))
    return ids


def _registered(op_id: str) -> bool:
    cat, name = op_id.split(".", 1)
    try:
        getattr(getattr(bpy.ops, cat), name).get_rna_type()
        return True
    except Exception:
        return False


DRAWN: list[str] = []


def _draw_panels() -> list[str]:
    errors: list[str] = []

    class _FakeLayout:
        def __getattr__(self, _n):
            return self._any

        def _any(self, *a, **k):
            return self

        def __bool__(self):
            return True

    for cls in list(bpy.types.Panel.__subclasses__()):
        if not getattr(cls, "bl_category", "").upper().startswith(("DSG", "DICOM", "DENTAL")) and "DSG" not in cls.__name__.upper() and "DICOM" not in cls.__name__.upper():
            continue
        import types as _types
        panel = _types.SimpleNamespace(layout=_FakeLayout(), bl_idname=getattr(cls, "bl_idname", cls.__name__))
        for _name in dir(cls):
            if not _name.startswith("__") and callable(getattr(cls, _name, None)) and _name not in ("draw", "poll"):
                try:
                    setattr(panel, _name, getattr(cls, _name).__get__(panel))
                except Exception:
                    pass
        ctx = bpy.context
        try:
            poll = getattr(cls, "poll", None)
            if poll is None or poll(ctx):
                cls.draw(panel, ctx)
                DRAWN.append(cls.__name__)
        except Exception as exc:  # noqa: BLE001 - collected and reported
            errors.append(f"{cls.__name__}: {type(exc).__name__}: {exc}")
    return errors


def main() -> int:
    sys.path.insert(0, str(REPO))
    failures: list[str] = []
    for cycle in (1, 2):
        mod = addon_utils.enable(ADDON, default_set=True, handle_error=lambda e: failures.append(f"enable[{cycle}]: {e!r}\n{traceback.format_exc()}"))
        if mod is None:
            failures.append(f"enable[{cycle}] returned None")
            break
        missing = sorted(i for i in _referenced_operator_ids() if not _registered(i) and not i.startswith(("wm.", "screen.", "object.", "mesh.", "view3d.", "ed.", "sculpt.", "transform.", "import_", "export_", "preferences.")))
        if missing:
            failures.append(f"cycle {cycle}: dead operator references: {missing}")
        if cycle == 1:
            failures.extend(f"draw: {e}" for e in _draw_panels())
        addon_utils.disable(ADDON, default_set=True, handle_error=lambda e: failures.append(f"disable[{cycle}]: {e!r}"))
    if failures:
        print("DSG SMOKE: FAIL")
        for f in failures:
            print("  -", f)
        return 1
    print(f"DSG SMOKE: PASS · Blender {bpy.app.version_string} · "
          f"{len(_referenced_operator_ids())} UI operator refs resolved · panels drawn: {', '.join(DRAWN) or 'none'}")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.exit(code)
