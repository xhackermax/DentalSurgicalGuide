"""Windows file-lock behaviour of the engine installer (reported on Windows 11).

On Windows ``os.replace`` raises ``PermissionError: [WinError 5] Acceso
denegado`` while another process (Blender polling ``install_status.json``,
antivirus, the search indexer) has the destination open. The user saw::

    InstallError: no installation source succeeded: build: PermissionError:
    [WinError 5] Acceso denegado: '…\\dsg_runtime\\install_status.json.tmp'

These tests emulate that lock semantics on any OS.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ADDON = Path(__file__).resolve().parents[1] / "dsg"
sys.path.insert(0, str(ADDON))

from engine_install import fsio, identity, installer  # noqa: E402
from test_engine_install import make_installer, manifest_for, server  # noqa: E402,F401


def _win_denied(path):
    exc = PermissionError(13, "Acceso denegado", str(path))
    exc.winerror = 5
    return exc


class LockedFor:
    """``os.replace`` stand-in: destination 'open by a reader' for N attempts."""

    def __init__(self, attempts: int, real=os.replace):
        self.left, self.real, self.calls = attempts, real, 0

    def __call__(self, src, dst):
        self.calls += 1
        if self.left > 0:
            self.left -= 1
            raise _win_denied(src)
        return self.real(src, dst)


def test_replace_retries_through_a_short_lock(tmp_path):
    src, dst = tmp_path / "a.tmp", tmp_path / "a.json"
    src.write_text("new")
    dst.write_text("old")
    fake = LockedFor(5)
    fsio.replace_with_retry(src, dst, replace=fake, sleep=lambda s: None)
    assert dst.read_text() == "new" and fake.calls == 6


def test_replace_gives_up_on_a_permanent_lock_and_other_errors_are_not_retried(tmp_path):
    src = tmp_path / "a.tmp"
    src.write_text("x")
    with pytest.raises(PermissionError):
        fsio.replace_with_retry(src, tmp_path / "b", replace=LockedFor(10**6), sleep=lambda s: None)
    calls = []

    def missing(s, d):
        calls.append(1)
        raise FileNotFoundError(s)
    with pytest.raises(FileNotFoundError):
        fsio.replace_with_retry(src, tmp_path / "b", replace=missing, sleep=lambda s: None)
    assert len(calls) == 1


def test_best_effort_status_write_never_raises_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "install_status.json"
    path.write_text('{"phase": "OLD"}')
    ok = fsio.write_json_atomic(path, {"phase": "NEW"}, best_effort=True,
                                replace=LockedFor(10**6), sleep=lambda s: None)
    assert ok is False
    assert json.loads(path.read_text())["phase"] == "OLD"            # previous status intact
    assert list(tmp_path.iterdir()) == [path]                           # no *.tmp litter
    with pytest.raises(PermissionError):
        fsio.write_json_atomic(path, {"phase": "NEW"}, replace=LockedFor(10**6), sleep=lambda s: None)


def test_concurrent_writers_use_distinct_temp_files(tmp_path):
    names = {fsio._unique_tmp(tmp_path / "s.json").name}
    import threading
    t = threading.Thread(target=lambda: names.add(fsio._unique_tmp(tmp_path / "s.json").name))
    t.start()
    t.join()
    assert len(names) == 2


def test_worker_status_writer_survives_a_locked_status_file(tmp_path, monkeypatch):
    import engine_install_worker as worker
    monkeypatch.setattr(os, "replace", LockedFor(10**6))
    monkeypatch.setattr(fsio, "RETRY_DELAYS", (0.0,))
    worker._atomic_write(tmp_path / "install_status.json", {"phase": "BUILD"})   # must not raise


def test_install_succeeds_when_progress_reporting_fails(server, tmp_path):  # noqa: F811
    url, h = server
    mf = manifest_for(url, h, cuda=False, accel="cpu")

    def broken_emit(*a, **k):                       # every status write hits the lock
        raise _win_denied("install_status.json.tmp")
    req = installer.InstallRequest(base_dir=tmp_path / "dsg_runtime", python=sys.executable,
                                   accel="cpu", allow_build=False, workers=4)
    result = installer.Installer(req, broken_emit, manifest_loader=lambda urls: mf,
                                 log=lambda *_: None).run()
    assert result.source == "prebuilt" and identity.runtime_ready(result.runtime)


def test_activation_and_active_pointer_survive_transient_locks(server, tmp_path, monkeypatch):  # noqa: F811
    url, h = server
    mf = manifest_for(url, h, cuda=False, accel="cpu")
    fake = LockedFor(3)
    monkeypatch.setattr(os, "replace", fake)
    monkeypatch.setattr(fsio.time, "sleep", lambda s: None)
    result = make_installer(tmp_path, mf, accel="cpu").run()
    assert result.source == "prebuilt" and identity.runtime_ready(result.runtime)
    assert identity.read_active(tmp_path / "dsg_runtime")["key"] == result.key
    assert fake.calls > 3
