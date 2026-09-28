"""End-to-end: Blender launches the external installer worker (bpy 5.2).

A local HTTP server publishes a schema-2 manifest and a tiny fake engine;
``totalseg_runtime.start_install()`` must install it, and ``quick_status``
must report the engine ready from the identity-named runtime folder.
"""
from __future__ import annotations

import json
import time

import pytest

from test_engine_install import _Handler, manifest_for, server  # noqa: F401  (fixture reuse)

pytestmark = pytest.mark.requires_bpy


def test_blender_installs_prebuilt_engine_via_worker(server, tmp_path, monkeypatch):  # noqa: F811
    import importlib

    import bpy
    import addon_utils
    from engine_install import identity, manifest

    url, handler = server
    mf = manifest_for(url, handler, accel="cpu", cuda=False)
    handler.files["/manifest-v2.json"] = json.dumps(
        manifest.build({"totalseg": "2.18.0", "torch": "2.8.0"}, mf.profiles, mf.assets.values())).encode()
    monkeypatch.setenv("DSG_TOTALSEG_RUNTIME_ROOT", str(tmp_path / "dsg_runtime"))
    monkeypatch.setenv("DSG_ENGINE_MANIFEST_URL", f"{url}/manifest-v2.json")
    monkeypatch.setenv("DSG_AI_ACCEL", "cpu")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    assert addon_utils.enable("dsg", default_set=True) is not None
    try:
        ts = importlib.import_module("dsg.totalseg_runtime")
        assert not ts.quick_status().dependencies_ready
        assert ts.start_install() is True
        deadline = time.time() + 120
        state = {}
        while time.time() < deadline:
            state = ts.install_state()
            if state.get("done"):
                break
            time.sleep(0.2)
        assert state.get("phase") == "READY", state
        assert state.get("source") == "prebuilt"
        status = ts.quick_status()
        assert status.dependencies_ready and status.model_ready
        key = identity.desired_identity("cpu").key
        assert status.runtime_dir.endswith(key)
        # Second request: nothing to download, reuse in well under a second of work.
        assert ts.start_install() is True
        while not ts.install_state().get("done"):
            time.sleep(0.1)
        assert ts.install_state().get("source") == "reuse"
    finally:
        addon_utils.disable("dsg", default_set=True)
