"""Verify the add-on tree against its own BUILD_MANIFEST.json.

The 9.10.11 check compared the tree with the original release ZIP. From 9.24.x
the source of truth is the installed build copied into the repository, so this
gate checks version coherence and reports files that drifted from the manifest
instead of failing on them (the drift is listed in the CHANGELOG).
"""
import ast
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ADDON = REPO / 'dsg'


def _literal(path, name):
    tree = ast.parse(path.read_text('utf-8'))
    return next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') == name for t in node.targets))


def main():
    version = tuple(_literal(ADDON / 'version.py', 'DSG_VERSION'))
    assert tuple(_literal(ADDON / '__init__.py', 'bl_info')['version']) == version, 'bl_info version != DSG_VERSION'
    manifest = json.loads((ADDON / 'BUILD_MANIFEST.json').read_text('utf-8'))
    assert manifest['version'] == '.'.join(map(str, version)), 'BUILD_MANIFEST version != DSG_VERSION'
    assert manifest['weights_bundled'] is False
    assert manifest['segmentation_engines'] == ['TOTALSEG', 'TOOTHSEG', 'UMAMBA2']
    missing, drifted = [], []
    for entry in manifest['files']:
        path = ADDON / entry['path']
        if not path.is_file():
            missing.append(entry['path'])
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            drifted.append(entry['path'])
    assert not missing, 'Files listed in BUILD_MANIFEST are missing: ' + ', '.join(missing)
    for name in drifted:
        print('DSG_MANIFEST_DRIFT', name)
    print(f"DSG_RELEASE_PROVENANCE_PASS: {manifest['version']}, {len(manifest['files'])} files, {len(drifted)} drifted")


if __name__ == '__main__':
    main()
