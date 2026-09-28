"""Run every automated DSG release gate that does not need a human.

    python tools/run_checks.py            # compile + lint + tests (+ smoke if bpy)
    python tools/run_checks.py --no-smoke

Exit code 0 only if every gate passes. Mirrors specs/DSG_9.6/acceptance.md.
"""
from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ADDON = REPO / "dsg"
FRAGMENTS = "_guide_parts,_dicom_parts,_alignment_parts"


def _run(name: str, cmd: list[str]) -> bool:
    print(f"\n=== {name}: {' '.join(cmd)}", flush=True)
    ok = subprocess.run(cmd, cwd=REPO).returncode == 0
    print(f"=== {name}: {'PASS' if ok else 'FAIL'}", flush=True)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-smoke", action="store_true", help="skip the real-Blender smoke test")
    args = ap.parse_args()
    py = sys.executable
    results: dict[str, bool] = {}
    results["compileall"] = _run("compileall", [py, "-m", "compileall", "-q", str(ADDON)])
    ruff = shutil.which("ruff")
    if ruff:
        # Correctness rules only (undefined names, redefinitions, syntax).
        results["ruff"] = _run("ruff", [ruff, "check", "--select", "F821,F811,E9,F63,F7",
                                        "--exclude", FRAGMENTS, str(ADDON)])
    else:
        print("\n=== ruff: SKIPPED (pip install ruff)")
    results["pytest"] = _run("pytest", [py, "-m", "pytest"])
    if not args.no_smoke:
        if importlib.util.find_spec("bpy") is not None:
            results["blender_smoke"] = _run("blender_smoke", [py, str(REPO / "tools" / "blender_smoke.py")])
            results["install_smoke"] = _run("install_smoke", [py, str(REPO / "tools" / "install_smoke.py")])
        else:
            print("\n=== blender_smoke: SKIPPED (bpy not importable; use the bpy wheel or Blender)")
    print("\nSUMMARY:", ", ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in results.items()))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
