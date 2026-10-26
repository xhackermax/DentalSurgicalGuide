"""Blender compatibility contract for DSG 9.10.11.

This build is intentionally scoped to the Blender 5.2 series. Runtime and
segmentation dependencies are never adopted from another Blender series.
"""
from __future__ import annotations

import logging

_LOG = logging.getLogger(__name__)

BLENDER_MIN = (5, 2, 0)
BLENDER_TARGET_SERIES = (5, 2)
PYTHON_TARGET = (3, 13)


def runtime_report() -> dict:
    import bpy
    import sys
    version = tuple(int(x) for x in bpy.app.version[:3])
    py = (sys.version_info.major, sys.version_info.minor)
    exact_series = version[:2] == BLENDER_TARGET_SERIES
    return {
        "blender": version,
        "blender_string": getattr(bpy.app, "version_string", ".".join(map(str, version))),
        "python": py,
        "minimum": BLENDER_MIN,
        "target_series": BLENDER_TARGET_SERIES,
        "python_target": PYTHON_TARGET,
        "supported": bool(exact_series and version >= BLENDER_MIN),
        "tested_series": exact_series,
    }


def assert_supported_runtime() -> dict:
    report = runtime_report()
    if not report["supported"]:
        have = ".".join(map(str, report["blender"]))
        raise RuntimeError(f"DSG 9.10.11 requiere Blender 5.2.x; detectado {have}.")
    if report["python"] != PYTHON_TARGET:
        _LOG.warning(
            "DSG runtime Python is %s.%s; Blender 5.2 target ABI is CPython %s.%s. "
            "The segmentation runtime will be created only for the active Blender 5.2 ABI.",
            *report["python"], *PYTHON_TARGET,
        )
    return report
