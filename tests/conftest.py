"""Test bootstrap.

* Puts the repository root on ``sys.path`` so ``import dsg.<module>`` works.
* If the real ``bpy`` module is unavailable (plain CPython CI), installs a
  permissive stub so *pure* modules can be imported. Tests that need real
  Blender behaviour live in ``tools/blender_smoke.py`` and are marked
  ``requires_bpy`` here.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

HAS_REAL_BPY = importlib.util.find_spec("bpy") is not None


class _Anything(types.ModuleType):
    """Module/attribute stand-in: every attribute access returns another stub."""

    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        value = _Anything(f"{self.__name__}.{name}")
        setattr(self, name, value)
        return value

    def __call__(self, *args, **kwargs):
        return _Anything(f"{self.__name__}()")

    def __mro_entries__(self, bases):  # allow ``class X(bpy.types.Operator)``
        return (object,)

    def __iter__(self):
        return iter(())


if not HAS_REAL_BPY:
    for _name in ("bpy", "bpy.types", "bpy.props", "bpy.app", "bpy.app.handlers",
                  "bpy.utils", "bpy_extras", "bpy_extras.io_utils", "bmesh",
                  "mathutils", "mathutils.bvhtree", "mathutils.kdtree", "gpu",
                  "gpu_extras", "gpu_extras.batch", "blf"):
        sys.modules.setdefault(_name, _Anything(_name))


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_bpy: needs the real Blender bpy module")


def pytest_collection_modifyitems(config, items):
    if HAS_REAL_BPY:
        return
    skip = pytest.mark.skip(reason="real bpy not available (run with Blender or the bpy wheel)")
    for item in items:
        if "requires_bpy" in item.keywords:
            item.add_marker(skip)
