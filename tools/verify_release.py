"""Verify source correspondence to the original versioned ZIP."""
import ast
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]

def main():
    provenance = json.loads((REPO / 'docs/DSG_9_10_11_PROVENANCE.json').read_text('utf-8'))
    archive = REPO / 'releases/v9.10.11' / provenance['source']
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == provenance['sha256']
    with zipfile.ZipFile(archive) as source:
        assert source.testzip() is None
        manifest = json.loads(source.read('dsg/BUILD_MANIFEST.json'))
        assert manifest['version'] == provenance['version'] == '9.10.11'
        assert manifest['file_count'] == len(manifest['files']) == 426
        assert manifest['weights_bundled'] is False
        assert manifest['segmentation_engines'] == ['TOTALSEG', 'TOOTHSEG', 'UMAMBA2']
        expected = {'dsg/BUILD_MANIFEST.json'}
        for entry in manifest['files']:
            relative = PurePosixPath(entry['path'])
            assert not relative.is_absolute() and '..' not in relative.parts
            name = 'dsg/' + relative.as_posix()
            data = source.read(name)
            assert len(data) == entry['bytes'], name
            assert hashlib.sha256(data).hexdigest() == entry['sha256'], name
            assert (REPO / name).read_bytes() == data, 'Source differs from ZIP: ' + name
            expected.add(name)
        assert len(source.namelist()) == len(expected) and set(source.namelist()) == expected
        assert (REPO / 'dsg/BUILD_MANIFEST.json').read_bytes() == source.read('dsg/BUILD_MANIFEST.json')
        actual = {'dsg/' + p.relative_to(REPO / 'dsg').as_posix()
                  for p in (REPO / 'dsg').rglob('*') if p.is_file()
                  and '__pycache__' not in p.parts and p.suffix not in {'.pyc', '.pyo'}}
        assert actual == expected, 'Missing or obsolete addon files'
        tree = ast.parse(source.read('dsg/version.py'))
        version = next(ast.literal_eval(node.value) for node in tree.body
                       if isinstance(node, ast.Assign)
                       and any(getattr(t, 'id', '') == 'DSG_VERSION' for t in node.targets))
        assert version == (9, 10, 11)
    print('DSG_RELEASE_PROVENANCE_PASS: 426 hashes, exact source, CRC, version, model scope')

if __name__ == '__main__':
    main()
