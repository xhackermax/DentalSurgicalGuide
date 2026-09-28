"""Build the installable DSG ZIP from the repository.

    python tools/build_addon_zip.py --out dist
    python tools/build_addon_zip.py --out dist --extension --license SPDX:GPL-3.0-or-later

* Only ``dsg/`` is packaged (no tests, docs, caches, VCS files).
* The version comes from ``dsg/version.py`` (single source of truth).
* ``--extension`` adds a generated ``blender_manifest.toml`` so the ZIP can be
  installed through Blender's Extensions system (Blender ≥ 4.2). The licence is
  a legal decision of the author, so it must be passed explicitly.
* A ``.sha256`` file is written next to the ZIP and the archive is re-opened
  and tested (acceptance gate "ZIP integrity").
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ADDON = REPO / "dsg"
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".tmp", ".log"}


def addon_version() -> tuple[int, int, int]:
    tree = ast.parse((ADDON / "version.py").read_text("utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "DSG_VERSION" for t in node.targets):
            return tuple(ast.literal_eval(node.value))
    raise SystemExit("DSG_VERSION not found in dsg/version.py")


def manifest_toml(version: str, license_id: str) -> str:
    return f'''schema_version = "1.0.0"

id = "dsg"
version = "{version}"
name = "DSG Dental Surgical Guide"
tagline = "Dental surgical guide planning from CBCT and intraoral scans"
maintainer = "Max Tiburcio"
type = "add-on"
tags = ["3D View", "Mesh"]
blender_version_min = "5.2.0"
license = ["{license_id}"]

[permissions]
files = "Read DICOM/STL inputs, write guide STL, reports and the AI runtime cache"
network = "Optional download of the dental AI runtime and model weights"
'''


def iter_files():
    for path in sorted(ADDON.rglob("*")):
        rel = path.relative_to(ADDON)
        if path.is_dir() or any(part in EXCLUDE_DIRS for part in rel.parts) or path.suffix in EXCLUDE_SUFFIXES:
            continue
        yield path, rel


def build(out_dir: Path, *, extension: bool, license_id: str | None) -> Path:
    version = ".".join(map(str, addon_version()))
    out_dir.mkdir(parents=True, exist_ok=True)
    kind = "extension" if extension else "addon"
    target = out_dir / f"DSG_v{version.replace('.', '_')}_{kind}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path, rel in iter_files():
            # Legacy add-ons need the top-level "dsg/" folder; extensions are flat.
            arc = rel.as_posix() if extension else f"dsg/{rel.as_posix()}"
            zf.write(path, arc)
        if extension:
            if not license_id:
                raise SystemExit("--extension requires --license (e.g. SPDX:GPL-3.0-or-later)")
            zf.writestr("blender_manifest.toml", manifest_toml(version, license_id))
    with zipfile.ZipFile(target) as zf:
        bad = zf.testzip()
        if bad:
            raise SystemExit(f"ZIP integrity failure: {bad}")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    print(f"built {target} ({target.stat().st_size / 1e6:.1f} MB) sha256={digest[:16]}…")
    return target


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist")
    ap.add_argument("--extension", action="store_true")
    ap.add_argument("--license", dest="license_id")
    args = ap.parse_args(argv)
    build(REPO / args.out, extension=args.extension, license_id=args.license_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
