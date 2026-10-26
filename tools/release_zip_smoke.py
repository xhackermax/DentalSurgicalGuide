"""Executed inside Blender with an isolated user profile."""
import hashlib
import json
import sys
from pathlib import Path
import addon_utils
import bpy

archive = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
source = Path(sys.argv[sys.argv.index('--') + 2]).resolve()  # repository dsg/ the ZIP was built from
assert bpy.app.version[:2] == (5, 2), bpy.app.version_string
assert bpy.ops.preferences.addon_install(filepath=str(archive), overwrite=True) == {'FINISHED'}
for _ in range(2):
    assert bpy.ops.preferences.addon_enable(module='dsg') == {'FINISHED'}
    assert addon_utils.check('dsg') == (True, True)
    import dsg
    assert tuple(dsg.bl_info['version']) == tuple(dsg.DSG_VERSION), (dsg.bl_info['version'], dsg.DSG_VERSION)
    root = Path(dsg.__file__).resolve().parent
    manifest = json.loads((root / 'BUILD_MANIFEST.json').read_text('utf-8'))
    assert manifest['version'] == dsg.DSG_VERSION_STR
    for entry in manifest['files']:
        installed = root / entry['path']
        assert hashlib.sha256(installed.read_bytes()).hexdigest() == hashlib.sha256((source / entry['path']).read_bytes()).hexdigest(), entry['path']
    assert bpy.ops.preferences.addon_disable(module='dsg') == {'FINISHED'}
print('DSG_ZIP_INSTALL_CYCLES_PASS', bpy.app.version_string, flush=True)
