"""Run current release gates; historical 9.7 tests are separately auditable."""
import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-smoke', action='store_true', help='portable gates only')
    parser.add_argument('--blender', help='real Blender 5.2 executable')
    parser.add_argument('--vtk-site-packages', help='compatible VTK libraries for Blender Python')
    args = parser.parse_args()
    commands = [[sys.executable, 'tools/verify_release.py'],
                [sys.executable, '-m', 'compileall', '-q', 'dsg'],
                [sys.executable, 'dsg/tools/check_quality.py']]
    if args.blender and not args.no_smoke:
        commands.append([sys.executable, 'tools/run_blender_release_checks.py', '--blender', args.blender])
        if args.vtk_site_packages:
            commands[-1] += ['--vtk-site-packages', args.vtk_site_packages]
    elif not args.no_smoke:
        parser.error('specify --blender for real Blender gates, or --no-smoke for portable gates')
    for command in commands:
        subprocess.run(command, cwd=REPO, check=True)
    print('DSG_REPOSITORY_CHECKS_PASS' + (' (portable gates; Blender not run)' if args.no_smoke else ''))

if __name__ == '__main__':
    main()
