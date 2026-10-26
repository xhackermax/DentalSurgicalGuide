"""Model-free Blender checks in isolated profiles; no real CBCT inference."""
import argparse
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Model-free Blender 5.2 cases that do not need an installed AI runtime.
TESTS = ('test_runtime_status.py', 'test_pipeline_diagnostic.py',
         'test_post_segmentation_smoothing.py', 'test_async_smoothing_undo.py',
         'test_surface_smoothing.py')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--blender', required=True)
    parser.add_argument('--logs', default='dist/blender-checks')
    parser.add_argument('--vtk-site-packages', help='compatible VTK libraries for Blender Python; no models required')
    parser.add_argument('--case', help='run only this named case')
    args = parser.parse_args()
    logs = (REPO / args.logs).resolve()
    logs.mkdir(parents=True, exist_ok=True)
    import build_addon_zip
    archive = build_addon_zip.build(logs / 'zip', extension=False, license_id=None)
    cases = [('zip_install', REPO / 'tools/release_zip_smoke.py', str(archive), str(REPO / 'dsg')),
             ('operators', REPO / 'tools/blender_smoke.py', str(REPO))]
    cases += [(Path(name).stem, REPO / 'dsg/tests_blender' / name, str(REPO)) for name in TESTS]
    if args.case:
        cases = [case for case in cases if case[0] == args.case]
        if not cases:
            parser.error('unknown case')
    failed = []
    with tempfile.TemporaryDirectory(prefix='dsg-checks-', ignore_cleanup_errors=True) as temp:
        for name, script, *arguments in cases:
            profile = Path(temp) / name
            env = dict(os.environ, BLENDER_USER_RESOURCES=str(profile),
                       BLENDER_USER_SCRIPTS=str(profile / 'scripts'))
            log = logs / (name + '.log')
            command = [args.blender, '--background', '--factory-startup', '--python-exit-code', '1']
            if args.vtk_site_packages:
                library_path = str(Path(args.vtk_site_packages).resolve())
                command += ['--python-expr', 'import sys; sys.path.append(' + repr(library_path) + ')']
            command += ['--python', str(script), '--', *arguments]
            with log.open('w', encoding='utf-8') as stream:
                process = subprocess.run(command,
                    cwd=REPO, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=600)
            print(f"{name}: {'PASS' if process.returncode == 0 else 'FAIL'} ({log})", flush=True)
            if process.returncode:
                failed.append(name)
    if failed:
        raise SystemExit('BLENDER_CHECKS_FAILED: ' + ', '.join(failed))
    print(f'DSG_BLENDER_RELEASE_CHECKS_PASS: {len(cases)} model-free cases; no real CBCT inference', flush=True)

if __name__ == '__main__':
    main()
