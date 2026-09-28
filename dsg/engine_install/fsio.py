"""Windows-safe file replacement for the engine installer (no ``bpy``).

On Windows ``os.replace`` fails with ``PermissionError [WinError 5/32]`` while
another process has the destination open: Blender's UI polls
``install_status.json`` several times per second, and antivirus / search
indexers briefly lock freshly written files and folders. Those locks last
milliseconds, so the right answer is to retry, not to abort a multi-GB install.

* ``replace_with_retry`` – ``os.replace`` retried with back-off (~6 s total).
* ``write_json_atomic`` – unique temp file per writer + ``replace_with_retry``.
  With ``best_effort=True`` (progress/status files) it never raises: losing one
  progress update is harmless, killing the installation is not.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

_LOG = logging.getLogger("dsg.engine_install")

RETRY_DELAYS = (0.02, 0.05, 0.1, 0.1, 0.2, 0.25, 0.25, 0.5, 0.5, 0.5, 1.0, 1.0, 1.0, 1.0)
# Renaming a freshly extracted runtime folder (thousands of files) can stay
# blocked while Windows Defender scans it: allow ~30 s before giving up.
DIR_RETRY_DELAYS = RETRY_DELAYS + (2.0,) * 12


def _transient(exc: OSError) -> bool:
    if isinstance(exc, PermissionError):
        return True
    return getattr(exc, "winerror", None) in (5, 32, 33)   # access denied / sharing / lock violation


def replace_with_retry(src, dst, *, delays=None, sleep=None, replace=None) -> None:
    """``os.replace(src, dst)`` that tolerates short-lived Windows file locks."""
    replace = replace or os.replace
    sleep = sleep or time.sleep
    delays = RETRY_DELAYS if delays is None else delays
    for delay in (*delays, None):
        try:
            replace(src, dst)
            return
        except OSError as exc:
            if delay is None or not _transient(exc):
                raise
            sleep(delay)


def _unique_tmp(path: Path) -> Path:
    return path.with_name(f"{path.name}.{os.getpid()}-{threading.get_ident()}.tmp")


def write_json_atomic(path, data, *, best_effort: bool = False, indent=None,
                      delays=None, sleep=None, replace=None) -> bool:
    """Atomically write ``data`` as JSON. Returns ``True`` when the file was updated."""
    path = Path(path)
    tmp = _unique_tmp(path)
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, default=str, indent=indent), encoding="utf-8")
        replace_with_retry(tmp, path, delays=delays, sleep=sleep, replace=replace)
        return True
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        if not best_effort:
            raise
        _LOG.debug("status file %s not updated (locked by a reader)", path, exc_info=True)
        return False
