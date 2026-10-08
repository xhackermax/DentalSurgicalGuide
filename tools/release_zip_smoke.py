"""Executed inside Blender with an isolated user profile."""
import hashlib
import json
import sys
from pathlib import Path
import addon_utils
import bpy

archive = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
assert bpy.app.version[:2] == (5, 2), bpy.app.version_string
assert bpy.ops.preferences.addon_install(filepath=str(archive), overwrite=True) == {'FINISHED'}
for _ in range(2):
    assert bpy.ops.preferences.addon_enable(module='dsg') == {'FINISHED'}
    assert addon_utils.check('dsg') == (True, True)
    import dsg
    assert dsg.DSG_VERSION == (9, 10, 11)
    root = Path(dsg.__file__).resolve().parent
    manifest = json.loads((root / 'BUILD_MANIFEST.json').read_text('utf-8'))
    for entry in manifest['files']:
        assert hashlib.sha256((root / entry['path']).read_bytes()).hexdigest() == entry['sha256']
    assert bpy.ops.preferences.addon_disable(module='dsg') == {'FINISHED'}
print('DSG_ZIP_INSTALL_CYCLES_PASS', bpy.app.version_string, flush=True)
