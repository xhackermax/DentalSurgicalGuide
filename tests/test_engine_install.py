"""AI-engine installer: identity, manifest, downloads and orchestration.

Runs without Blender and without Internet: a local HTTP server (with Range
support) plays GitHub / Google Drive, and a tiny fake engine (torch,
nnunetv2, totalsegmentator stubs) is verified by the *real* import check.
"""
from __future__ import annotations

import hashlib
import http.server
import io
import json
import sys
import threading
import zipfile
from pathlib import Path

import pytest

ADDON = Path(__file__).resolve().parents[1] / "dsg"
sys.path.insert(0, str(ADDON))                      # import like the worker does (no bpy)

from engine_install import archive, builder, download, identity, installer, manifest  # noqa: E402


# ── fixtures ───────────────────────────────────────────────────────────────
class _Handler(http.server.BaseHTTPRequestHandler):
    files: dict[str, bytes] = {}
    html: set[str] = set()
    hits: dict[str, int] = {}
    no_range: set[str] = set()

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        type(self).hits[path] = type(self).hits.get(path, 0) + 1
        if path in self.html:
            body = b"<html>quota exceeded</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        data = self.files.get(path)
        if data is None:
            self.send_error(404)
            return
        rng = self.headers.get("Range")
        if rng and path not in self.no_range:
            start = int(rng.split("=")[1].split("-")[0])
            chunk = data[start:]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        else:
            chunk = data
            self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(chunk)))
        self.end_headers()
        self.wfile.write(chunk)


@pytest.fixture()
def server():
    _Handler.files, _Handler.html, _Handler.hits, _Handler.no_range = {}, set(), {}, set()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", _Handler
    httpd.shutdown()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


def fake_engine_zip(cuda: bool = True) -> bytes:
    cuda_value = "'12.6'" if cuda else "None"
    return zip_bytes({
        "torch/__init__.py": "from . import version\n__version__ = version.__version__\n",
        "torch/version.py": f"__version__ = '2.8.0'\ncuda = {cuda_value}\n",
        "nnunetv2/__init__.py": "",
        "totalsegmentator/__init__.py": "",
        "totalsegmentator/registry.py": "def get_task_classes(task):\n    return {i: f'c{i}' for i in range(77)}\n",
    })


def weights_zip(name: str) -> bytes:
    return zip_bytes({f"{name}/nnUNetTrainer__plans/fold_0/checkpoint_final.pth": "weights"})


def publish(server_url, handler, name: str, data: bytes) -> str:
    handler.files["/" + name] = data
    return f"{server_url}/{name}"


def manifest_for(server_url, handler, *, accel="cuda126", split_runtime=False, cuda=True) -> manifest.Manifest:
    ident = identity.desired_identity(accel)
    rt = fake_engine_zip(cuda=cuda)
    parts = []
    if split_runtime:
        half = len(rt) // 2
        for i, chunk in enumerate((rt[:half], rt[half:]), start=1):
            name = f"rt.zip.part{i:03d}"
            parts.append({"name": name, "size": len(chunk), "sha256": sha(chunk),
                          "urls": [publish(server_url, handler, name, chunk)]})
    else:
        parts.append({"name": "rt.zip", "size": len(rt), "sha256": sha(rt), "urls": [publish(server_url, handler, "rt.zip", rt)]})
    assets = {"rt": {"install": "site-packages", "size": len(rt), "sha256": sha(rt), "parts": parts}}
    for aid, wname in (("w113", "Dataset113_ToothFairy3"), ("w115", "Dataset115_mandible")):
        data = weights_zip(wname)
        assets[aid] = {"install": "weights", "size": len(data), "sha256": sha(data),
                       "parts": [{"name": f"{wname}.zip", "size": len(data), "sha256": sha(data),
                                  "urls": [publish(server_url, handler, f"{wname}.zip", data)]}]}
    return manifest.parse({
        "schema_version": 2, "engine": {"totalseg": "2.18.0", "torch": "2.8.0"},
        "profiles": {ident.platform: {ident.python_abi: {accel: ["rt", "w113", "w115"]}}},
        "assets": assets,
    })


def make_installer(tmp_path, mf, *, accel="cuda126", force=False, allow_build=False, runner=None, events=None):
    events = events if events is not None else []
    req = installer.InstallRequest(base_dir=tmp_path / "dsg_runtime", python=sys.executable, accel=accel,
                                   force=force, allow_build=allow_build, workers=4)
    return installer.Installer(req, lambda *a, **k: events.append(a), runner=runner,
                               manifest_loader=lambda urls: mf, log=lambda *_: None)


# ── identity ───────────────────────────────────────────────────────────────
def test_runtime_key_does_not_depend_on_the_dsg_version():
    ident = identity.RuntimeIdentity("2.18.0", "2.8.0", "cuda126", "cp313", "win_amd64")
    assert ident.key == "ts2.18.0-torch2.8.0-cuda126-cp313-win_amd64"
    assert "9.7" not in ident.key and "968" not in ident.key


def test_accelerator_choice(monkeypatch):
    monkeypatch.delenv("DSG_AI_ACCEL", raising=False)
    monkeypatch.setattr(identity, "current_platform", lambda: "win_amd64")
    assert identity.choose_accelerator(True) == "cuda126"
    assert identity.choose_accelerator(False) == "cpu"
    monkeypatch.setenv("DSG_AI_ACCEL", "cpu")
    assert identity.choose_accelerator(True) == "cpu"
    monkeypatch.delenv("DSG_AI_ACCEL")
    monkeypatch.setattr(identity, "current_platform", lambda: "macosx_arm64")
    assert identity.choose_accelerator(True) == "cpu"


def test_installed_torch_accel_parses_real_torch_version_files(tmp_path):
    rt = tmp_path / "rt"
    (rt / "site-packages" / "torch").mkdir(parents=True)
    vf = rt / "site-packages" / "torch" / "version.py"
    vf.write_text("__version__ = '2.8.0+cu126'\ncuda: Optional[str] = '12.6'\nhip = None\n")
    assert identity.installed_torch_accel(rt) == "cuda126"
    vf.write_text("__version__ = '2.8.0+cpu'\ncuda: Optional[str] = None\n")
    assert identity.installed_torch_accel(rt) == "cpu"


# ── manifest ───────────────────────────────────────────────────────────────
def test_manifest_requires_hashes_and_known_targets():
    good = {"schema_version": 2, "engine": {}, "profiles": {}, "assets": {"a": {
        "install": "weights", "sha256": "0" * 64, "parts": [{"name": "a.zip", "urls": ["x"]}]}}}
    assert manifest.parse(good).assets["a"].install == "weights"
    for mutate in (lambda d: d["assets"]["a"].update(sha256=""),
                   lambda d: d["assets"]["a"].update(install="elsewhere"),
                   lambda d: d["assets"]["a"]["parts"][0].update(urls=[]),
                   lambda d: d.update(schema_version=1)):
        bad = json.loads(json.dumps(good))
        mutate(bad)
        with pytest.raises(manifest.ManifestError):
            manifest.parse(bad)


def test_google_drive_ids_expand_to_direct_downloads():
    assert manifest.expand_url("gdrive:ABC123") == \
        "https://drive.usercontent.google.com/download?id=ABC123&export=download&confirm=t"
    assert manifest.expand_url("https://x/y.zip") == "https://x/y.zip"


def test_missing_profile_is_reported():
    mf = manifest.parse({"schema_version": 2, "engine": {}, "profiles": {}, "assets": {}})
    with pytest.raises(manifest.ManifestError):
        mf.assets_for("win_amd64", "cp313", "cpu")


# ── downloads ──────────────────────────────────────────────────────────────
def test_download_resumes_a_partial_file(server, tmp_path):
    url, h = server
    data = bytes(range(256)) * 20000
    part = manifest.Part("big.bin", len(data), sha(data), (publish(url, h, "big.bin", data),))
    (tmp_path / "big.bin.part").write_bytes(data[:100000])
    out = download.fetch_part(part, tmp_path)
    assert out.read_bytes() == data


def test_download_restarts_when_the_server_ignores_range(server, tmp_path):
    url, h = server
    data = b"x" * 300000
    h.no_range.add("/norange.bin")
    part = manifest.Part("norange.bin", len(data), sha(data), (publish(url, h, "norange.bin", data),))
    (tmp_path / "norange.bin.part").write_bytes(b"x" * 1000)
    assert download.fetch_part(part, tmp_path).read_bytes() == data


def test_mirror_fallback_on_404_html_and_bad_hash(server, tmp_path):
    url, h = server
    data = b"good" * 1000
    h.files["/corrupt.bin"] = b"evil" * 1000
    h.html.add("/quota.bin")
    part = manifest.Part("m.bin", len(data), sha(data),
                         (f"{url}/missing.bin", f"{url}/quota.bin", f"{url}/corrupt.bin", publish(url, h, "good.bin", data)))
    assert download.fetch_part(part, tmp_path).read_bytes() == data


def test_cached_download_is_not_fetched_again(server, tmp_path):
    url, h = server
    data = b"cached" * 1000
    part = manifest.Part("c.bin", len(data), sha(data), (publish(url, h, "c.bin", data),))
    download.fetch_part(part, tmp_path)
    download.fetch_part(part, tmp_path)
    assert h.hits["/c.bin"] == 1


def test_multipart_assets_are_joined_and_verified(server, tmp_path):
    url, h = server
    data = b"0123456789" * 50000
    halves = (data[:250000], data[250000:])
    parts = tuple(manifest.Part(f"j.part{i}", len(c), sha(c), (publish(url, h, f"j{i}", c),)) for i, c in enumerate(halves))
    asset = manifest.Asset("joined", "weights", len(data), sha(data), parts)
    events = []
    out = download.download_assets([asset], tmp_path, progress=lambda d, t, n: events.append((d, t)))
    assert out["joined"].read_bytes() == data
    assert events[-1][0] == events[-1][1] == len(data)


def test_zip_slip_is_rejected(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(zip_bytes({"../escape.txt": "x"}))
    with pytest.raises(archive.ArchiveError):
        archive.safe_extract(bad, tmp_path / "out")


# ── builder commands ───────────────────────────────────────────────────────
def test_build_uses_one_resolution_with_pinned_cuda_torch(tmp_path):
    cmd = builder.uv_command(Path("uv"), "python", tmp_path, "cuda126", tmp_path)
    assert "torch==2.8.0+cu126" in cmd and "TotalSegmentator==2.18.0" in cmd
    assert cmd[cmd.index("--index-url") + 1].endswith("/cu126")
    pip = builder.pip_command("python", tmp_path, "cpu", tmp_path)
    assert "torch==2.8.0" in pip and pip.count("install") == 1


def test_build_falls_back_to_pip_when_uv_fails(tmp_path):
    calls = []

    def runner(cmd, env):
        calls.append(cmd)
        if "uv==" in " ".join(cmd):                       # bootstrap uv
            (tmp_path / "cache" / "uv-tool" / "bin").mkdir(parents=True)
            (tmp_path / "cache" / "uv-tool" / "bin" / "uv").write_text("")
            return 0
        return 1 if cmd[0].endswith("uv") else 0
    assert builder.build_site_packages("python", tmp_path / "site", "cpu", tmp_path / "cache", runner, log=lambda *_: None) == "pip"
    assert calls[-1][1:3] == ["-m", "pip"]


# ── orchestration ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("split", [False, True])
def test_prebuilt_install_then_reuse(server, tmp_path, split):
    url, h = server
    mf = manifest_for(url, h, split_runtime=split)
    events = []
    result = make_installer(tmp_path, mf, events=events).run()
    assert result.source == "prebuilt" and identity.runtime_ready(result.runtime)
    assert result.details["verify"]["teeth_classes"] == 77
    assert identity.read_active(tmp_path / "dsg_runtime")["key"] == result.key
    assert [e[0] for e in events][-1] == "READY"
    assert not (tmp_path / "dsg_runtime" / "cache" / "downloads").exists()   # ~4 GB freed after install
    again = make_installer(tmp_path, mf).run()
    assert again.source == "reuse" and again.seconds < 2.0


def test_legacy_runtime_is_adopted_not_reinstalled_and_old_ones_removed(server, tmp_path):
    url, h = server
    base = tmp_path / "dsg_runtime"
    py = identity.current_python_abi()[2:]
    legacy = base / f"dsg_ts968_py{py}"
    older = base / f"dsg_ts965_py{py}"
    archive.safe_extract(_write(tmp_path / "e.zip", fake_engine_zip()), legacy / "site-packages")
    for w in ("Dataset113_ToothFairy3", "Dataset115_mandible"):
        (identity.weights_dir(legacy) / w).mkdir(parents=True)
    older.mkdir(parents=True)
    result = make_installer(tmp_path, None).run()
    assert result.source == "adopted" and identity.runtime_ready(result.runtime)
    assert not legacy.exists() and not older.exists()


def test_cpu_request_does_not_adopt_a_cuda_runtime(server, tmp_path):
    url, h = server
    base = tmp_path / "dsg_runtime"
    legacy = base / f"dsg_ts968_py{identity.current_python_abi()[2:]}"
    archive.safe_extract(_write(tmp_path / "e.zip", fake_engine_zip(cuda=True)), legacy / "site-packages")
    for w in ("Dataset113_ToothFairy3", "Dataset115_mandible"):
        (identity.weights_dir(legacy) / w).mkdir(parents=True)
    mf = manifest_for(url, h, accel="cpu", cuda=False)
    assert make_installer(tmp_path, mf, accel="cpu").run().source == "prebuilt"


def test_failed_verification_keeps_the_working_runtime(server, tmp_path):
    url, h = server
    good = make_installer(tmp_path, manifest_for(url, h)).run()
    marker = good.runtime / "site-packages" / "torch" / "KEEP"
    marker.write_text("x")
    broken = manifest_for(url, h, cuda=False)            # CPU torch although CUDA requested
    with pytest.raises(installer.InstallError):
        make_installer(tmp_path, broken, force=True).run()
    assert marker.is_file() and identity.runtime_ready(good.runtime)


def test_local_build_downloads_weights_in_parallel(server, tmp_path):
    url, h = server
    mf = manifest_for(url, h)
    mf.profiles = {}                                     # no prebuilt for this machine
    started = threading.Event()

    def runner(cmd, env):
        started.set()
        if "--target" in cmd and ("pip" in cmd[1:3] or cmd[0].endswith("uv")) and "uv==" not in " ".join(cmd):
            target = Path(cmd[cmd.index("--target") + 1])
            archive.safe_extract(_write(tmp_path / "b.zip", fake_engine_zip()), target)
            return 0
        return 1                                         # uv bootstrap fails → pip path
    result = make_installer(tmp_path, mf, allow_build=True, runner=runner).run()
    assert result.source == "build" and started.is_set() and identity.runtime_ready(result.runtime)


def test_offline_payload_inside_the_addon_is_used_first(tmp_path):
    payload = tmp_path / "offline_totalseg"
    files = {"runtime_archive": ("payload/runtime/rt.zip", fake_engine_zip()),
             "dataset113": ("payload/weights/Dataset113_ToothFairy3.zip", weights_zip("Dataset113_ToothFairy3")),
             "dataset115": ("payload/weights/Dataset115_mandible.zip", weights_zip("Dataset115_mandible"))}
    rec = {}
    for key, (rel, data) in files.items():
        _write(payload / rel, data)
        rec[key] = {"path": rel, "size": len(data), "sha256": sha(data)}
    (payload / "OFFLINE_PAYLOAD_MANIFEST.json").write_text(json.dumps(
        {"schema_version": 1, "python_abi": identity.current_python_abi().replace("cp", "py"), "files": rec}))
    req = installer.InstallRequest(base_dir=tmp_path / "rt", python=sys.executable, accel="cuda126",
                                   offline_payload_dir=payload, allow_build=False)
    result = installer.Installer(req, lambda *a, **k: None, manifest_loader=lambda u: None, log=lambda *_: None).run()
    assert result.source == "offline"


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
