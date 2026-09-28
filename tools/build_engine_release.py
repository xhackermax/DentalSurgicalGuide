"""Build and publish-ready packaging of DSG's prebuilt AI engine (run once per release).

Run it on the target platform with Blender's own Python (Windows example)::

    "C:\\Program Files\\Blender Foundation\\Blender 5.2\\5.2\\python\\bin\\python.exe" ^
        tools\\build_engine_release.py --out engine_release

What it does, per accelerator (cuda126, cpu):

1. installs PyTorch + TotalSegmentator with uv (pip fallback) into a clean folder;
2. checks the import in a separate process (and that CUDA builds really have CUDA);
3. writes a hash-locked requirements file (``dsg/engine_install/locks``) so
   future local builds skip dependency resolution;
4. packs two deterministic layers: ``torch`` (PyTorch + NVIDIA/Triton libs) and
   ``core`` (everything else, identical for CPU and CUDA → downloaded once);
5. splits every archive into parts < 2 GiB (GitHub Release limit);
6. downloads (or reuses) the two official dental weight archives and verifies them;
7. writes ``engines/manifest-v2.json`` with sizes, SHA-256 and mirrors:
   GitHub Release first, Google Drive second (``--drive-ids``).

Then upload ``<out>/upload/*`` to the GitHub Release (default tag engine-v2) and,
optionally, to Google Drive (share as "anyone with the link"), and commit the
manifest. ``--manifest-only --drive-ids ids.json`` re-writes the manifest after
the Drive upload without rebuilding.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "dsg"))
from engine_install import builder, download, identity, installer, manifest  # noqa: E402

DEFAULT_RELEASE = "https://github.com/xhackermax/DentalSurgicalGuide/releases/download/engine-v2"
PART_SIZE = 1900 * 1024 * 1024
TORCH_LAYER_PREFIXES = ("torch", "torchgen", "functorch", "nvidia", "triton", "cuda")
FIXED_DATE = (2026, 1, 1, 0, 0, 0)


def sha256(path: Path) -> str:
    return download.sha256_file(path)


def is_torch_layer(name: str) -> bool:
    low = name.lower()
    return any(low == p or low.startswith(p + "-") or low.startswith(p + "_") or low.startswith(p + ".")
               for p in TORCH_LAYER_PREFIXES)


def deterministic_zip(src: Path, members: list[Path], out: Path) -> None:
    """Same input → same bytes → same SHA (so the shared core layer dedupes)."""
    files = sorted({f for m in members for f in ([m] if m.is_file() else m.rglob("*")) if f.is_file()
                    and "__pycache__" not in f.parts and f.suffix not in (".pyc", ".pyo")})
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
        for f in files:
            info = zipfile.ZipInfo(f.relative_to(src).as_posix(), FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(f, "rb") as fh, zf.open(info, "w", force_zip64=True) as dst:
                shutil.copyfileobj(fh, dst, 8 * 1024 * 1024)


def split(path: Path, part_size: int) -> list[Path]:
    if path.stat().st_size <= part_size:
        return [path]
    parts = []
    with open(path, "rb") as fh:
        index = 1
        while True:
            block = fh.read(part_size)
            if not block:
                break
            part = path.with_name(f"{path.name}.part{index:03d}")
            part.write_bytes(block)
            parts.append(part)
            index += 1
    path.unlink()
    return parts


def asset_record(asset_id: str, install: str, whole_sha: str, parts: list[Path], urls_for, description: str):
    return manifest.Asset(
        asset_id, install, sum(p.stat().st_size for p in parts), whole_sha,
        tuple(manifest.Part(p.name, p.stat().st_size, sha256(p), tuple(urls_for(p.name))) for p in parts),
        description)


def run(cmd, env=None) -> int:
    print(">", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(list(map(str, cmd)), env=env).returncode


def build_accel(python: str, accel: str, work: Path, cache: Path) -> Path:
    site = work / f"build-{accel}" / "site-packages"
    shutil.rmtree(site.parent, ignore_errors=True)
    tool = builder.build_site_packages(python, site, accel, cache, lambda cmd, env: run(cmd, env))
    print(f"[{accel}] installed with {tool}")
    check = subprocess.run([python, "-c", "import torch,nnunetv2,totalsegmentator;"
                            "from totalsegmentator.registry import get_task_classes;"
                            "print(torch.__version__, torch.version.cuda, len(get_task_classes('teeth')))"],
                           env=dict(os.environ, PYTHONPATH=str(site), PYTHONNOUSERSITE="1"),
                           capture_output=True, text=True)
    print(f"[{accel}] import check:", check.stdout.strip() or check.stderr[-800:])
    if check.returncode != 0 or (accel == "cuda126" and " None " in f" {check.stdout} "):
        raise SystemExit(f"[{accel}] engine import check failed")
    return site


def write_lock(python: str, accel: str, cache: Path, ident: identity.RuntimeIdentity) -> Path | None:
    uv = builder.ensure_uv(python, cache, lambda cmd, env: run(cmd, env))
    if uv is None:
        print("uv unavailable: lock file skipped")
        return None
    locks = REPO / "dsg" / "engine_install" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    req = cache / f"req-{accel}.in"
    req.write_text("\n".join(builder.requirements(accel)) + "\n")
    out = locks / f"{ident.platform}-{ident.python_abi}-{accel}.txt"
    code = run([uv, "pip", "compile", str(req), "--python", python, "--generate-hashes",
                "--index-url", builder.TORCH_INDEXES[accel], "--extra-index-url", builder.PYPI_INDEX,
                "--index-strategy", "unsafe-best-match", "-o", out])
    return out if code == 0 else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--python", default=sys.executable, help="Blender's Python (defines ABI/platform)")
    ap.add_argument("--accel", nargs="+", default=["cuda126", "cpu"], choices=identity.ACCELERATORS)
    ap.add_argument("--out", default="engine_release")
    ap.add_argument("--release-base-url", default=DEFAULT_RELEASE)
    ap.add_argument("--drive-ids", help="JSON {file_name: google_drive_file_id} to add Drive mirrors")
    ap.add_argument("--weights-dir", help="folder with Dataset113_ToothFairy3.zip / Dataset115_mandible.zip")
    ap.add_argument("--part-size-mb", type=int, default=1900)
    ap.add_argument("--test-weights", action="store_true",
                    help="testing only: accept --weights-dir files whose hash is not the official one")
    ap.add_argument("--manifest-only", action="store_true", help="only rewrite the manifest from <out>/upload")
    ap.add_argument("--site", action="append", default=[], metavar="ACCEL=PATH",
                    help="package an already-built site-packages instead of building it")
    args = ap.parse_args(argv)

    out = Path(args.out).resolve()
    upload = out / "upload"
    cache = out / "cache"
    upload.mkdir(parents=True, exist_ok=True)
    drive = json.loads(Path(args.drive_ids).read_text()) if args.drive_ids else {}

    def urls_for(name: str) -> list[str]:
        urls = [f"{args.release_base_url.rstrip('/')}/{name}"]
        if name in drive:
            urls.append(f"gdrive:{drive[name]}")
        return urls

    state_file = out / "assets.json"
    state = json.loads(state_file.read_text()) if state_file.is_file() else {"assets": {}, "profiles": {}}

    if not args.manifest_only:
        probe = subprocess.run([args.python, "-c", "import sys;print(sys.version_info[0], sys.version_info[1], sys.platform)"],
                               capture_output=True, text=True, check=True).stdout.split()
        abi = f"cp{probe[0]}{probe[1]}"
        platform = "win_amd64" if probe[2].startswith("win") else ("macosx_arm64" if probe[2] == "darwin" else "linux_x86_64")
        weights_ids = []
        for w in installer.OFFICIAL_WEIGHTS:
            name = w.parts[0].name
            local = Path(args.weights_dir) / name if args.weights_dir else None
            if local and local.is_file():
                shutil.copy2(local, upload / name)
            else:
                download.download_assets([w], upload)
            whole = sha256(upload / name)
            if w.sha256 and whole != w.sha256 and not args.test_weights:
                raise SystemExit(f"{name}: SHA-256 differs from the official one")
            state["assets"][w.id] = {"install": "weights", "sha": whole, "parts": [name],
                                     "description": f"Official TotalSegmentator weights {name}"}
            weights_ids.append(w.id)
        for accel in args.accel:
            ident = identity.RuntimeIdentity(identity.TOTALSEG_VERSION, identity.TORCH_VERSION, accel, abi, platform)
            prebuilt = dict(item.split("=", 1) for item in args.site)
            if accel in prebuilt:
                site = Path(prebuilt[accel]).resolve()
            else:
                site = build_accel(args.python, accel, out, cache)
                write_lock(args.python, accel, cache, ident)
            entries = sorted(site.iterdir())
            layers = {"torch": [e for e in entries if is_torch_layer(e.name)],
                      "core": [e for e in entries if not is_torch_layer(e.name)]}
            ids = []
            for layer, members in layers.items():
                tmp = out / f"{layer}-{accel}.zip"
                deterministic_zip(site, members, tmp)
                whole = sha256(tmp)
                asset_id = f"{layer}-{platform}-{abi}" + (f"-{accel}" if layer == "torch" else "")
                if layer == "core" and asset_id in state["assets"] and state["assets"][asset_id]["sha"] == whole:
                    tmp.unlink()                            # identical core already packed for the other accel
                else:
                    if layer == "core" and asset_id in state["assets"]:
                        asset_id += f"-{accel}"             # core differs between accelerators
                    final = upload / f"dsg-{asset_id}-ts{identity.TOTALSEG_VERSION}.zip"
                    os.replace(tmp, final)
                    parts = split(final, args.part_size_mb * 1024 * 1024)
                    state["assets"][asset_id] = {"install": "site-packages", "sha": whole,
                                                 "parts": [p.name for p in parts],
                                                 "description": f"{layer} layer · {accel} · {abi} · {platform}"}
                ids.append(asset_id)
            state["profiles"].setdefault(platform, {}).setdefault(abi, {})[accel] = ids + weights_ids
            if accel not in prebuilt:
                shutil.rmtree(site.parent, ignore_errors=True)
        state_file.write_text(json.dumps(state, indent=2))

    assets = [asset_record(aid, rec["install"], rec["sha"], [upload / n for n in rec["parts"]], urls_for,
                           rec.get("description", "")) for aid, rec in state["assets"].items()]
    data = manifest.build({"totalseg": identity.TOTALSEG_VERSION, "torch": identity.TORCH_VERSION},
                          state["profiles"], assets)
    manifest.parse(data)                                    # self-check
    target = out / "manifest-v2.json"
    target.write_text(json.dumps(data, indent=2) + "\n")
    print(f"\nManifest: {target}\nUpload every file in {upload} to {args.release_base_url}")
    print("  e.g.  gh release create engine-v2 --repo xhackermax/DentalSurgicalGuide " + str(upload / "*"))
    print("Then copy the manifest to engines/manifest-v2.json in the GitHub repository.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
