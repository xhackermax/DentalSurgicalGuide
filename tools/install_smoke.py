"""Install the built ZIP into an isolated Blender profile (legacy add-on and
Extension) and verify it registers. Needs ``bpy`` (Blender 5.2 or bpy wheel).

    python tools/install_smoke.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import build_addon_zip  # noqa: E402

_CHILD = r'''
import sys, bpy, addon_utils
mode, zp = sys.argv[-2], sys.argv[-1]
if mode == "upgrade":
    # What a user does: install an older DSG, enable it, then install the new
    # ZIP over it *in the same Blender session*. Blender reloads the package.
    old_zip, zp = zp.split(";")
    bpy.ops.preferences.addon_install(filepath=old_zip, overwrite=True)
    addon_utils.modules_refresh()
    addon_utils.enable("dsg", default_set=True)
    assert "dsg" in bpy.context.preferences.addons, "old build did not enable"
    bpy.ops.preferences.addon_install(filepath=zp, overwrite=True)
    addon_utils.modules_refresh()
    addon_utils.enable("dsg", default_set=True, handle_error=None)
    import dsg, dsg.version
    new_version = tuple(dsg.bl_info["version"])
    assert tuple(dsg.DSG_VERSION) == new_version == tuple(dsg.version.DSG_VERSION), (dsg.DSG_VERSION, new_version)
    name = "dsg"
elif mode == "legacy":
    bpy.ops.preferences.addon_install(filepath=zp, overwrite=True)
    addon_utils.modules_refresh()
    addon_utils.enable("dsg", default_set=True)
    name = "dsg"
else:
    bpy.context.preferences.system.use_online_access = False
    bpy.ops.extensions.package_install_files(filepath=zp, repo="user_default", enable_on_install=True)
    name = "bl_ext.user_default.dsg"
ok = name in bpy.context.preferences.addons
try:
    bpy.ops.dsg.export_guide_stl.get_rna_type()
except Exception:
    ok = False
print("INSTALL_SMOKE", mode, "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
'''


OLD_VERSION = (9, 7, 0)


def make_older_build(new_zip: Path, out: Path, version=OLD_VERSION) -> Path:
    """Copy of ``new_zip`` that reports an older DSG version (upgrade test)."""
    tup = "(" + ", ".join(map(str, version)) + ")"
    with zipfile.ZipFile(new_zip) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.endswith("dsg/version.py"):
                data = re.sub(rb"DSG_VERSION = \([^)]*\)", b"DSG_VERSION = " + tup.encode(), data)
            elif info.filename.endswith("dsg/__init__.py"):
                data = re.sub(rb'"version": \([^)]*\)', b'"version": ' + tup.encode(), data, count=1)
            dst.writestr(info, data)
    return out


def main() -> int:
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        child = tmp / "child.py"
        child.write_text(_CHILD, encoding="utf-8")
        zips = {
            "legacy": build_addon_zip.build(tmp / "dist", extension=False, license_id=None),
            # Placeholder licence only for this local install test.
            "extension": build_addon_zip.build(tmp / "dist", extension=True, license_id="SPDX:LicenseRef-DSG-TEST"),
        }
        zips["upgrade"] = f"{make_older_build(zips['legacy'], tmp / 'dsg_old.zip')};{zips['legacy']}"
        for mode, zp in zips.items():
            profile = tmp / f"profile_{mode}"
            profile.mkdir()
            env = dict(os.environ, BLENDER_USER_RESOURCES=str(profile))
            proc = subprocess.run([sys.executable, str(child), mode, str(zp)], env=env,
                                  capture_output=True, text=True, timeout=600)
            results[mode] = proc.returncode == 0
            if not results[mode]:
                print(proc.stdout[-3000:], proc.stderr[-3000:])
    print("INSTALL SMOKE:", ", ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in results.items()))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
