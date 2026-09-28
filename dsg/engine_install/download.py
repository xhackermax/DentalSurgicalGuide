"""Parallel, resumable, hash-verified downloads with mirror fallback (stdlib only)."""
from __future__ import annotations

import hashlib
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable

from .manifest import Asset, Part, expand_url
from .fsio import replace_with_retry

CHUNK = 1024 * 1024
USER_AGENT = "DSG-engine-installer/2"
ProgressFn = Callable[[int, int, str], None]      # (done_bytes, total_bytes, label)


class DownloadError(RuntimeError):
    pass


def sha256_file(path: Path, chunk: int = 8 * CHUNK) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _verified_marker(path: Path) -> Path:
    return path.with_name(path.name + ".verified")


def _is_verified(path: Path, sha: str) -> bool:
    """Cache hit without re-hashing GBs: marker stores sha + size + mtime."""
    marker = _verified_marker(path)
    try:
        st = path.stat()
        return marker.read_text(encoding="utf-8").strip() == f"{sha}:{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        return False


def _mark_verified(path: Path, sha: str) -> None:
    st = path.stat()
    _verified_marker(path).write_text(f"{sha}:{st.st_size}:{int(st.st_mtime)}", encoding="utf-8")


class _Counter:
    def __init__(self, total: int):
        self.total = int(total)
        self.done = 0
        self._lock = threading.Lock()

    def add(self, n: int) -> int:
        with self._lock:
            self.done += n
            return self.done


def _open(url: str, offset: int, timeout: float):
    headers = {"User-Agent": USER_AGENT}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout)


def fetch_part(part: Part, dest_dir: Path, *, counter: _Counter | None = None,
               progress: ProgressFn | None = None, timeout: float = 60.0,
               retries_per_url: int = 3, cancel: threading.Event | None = None) -> Path:
    """Download one part (resuming ``.part`` files) and verify its SHA-256."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / part.name
    if part.sha256 and final.is_file() and (_is_verified(final, part.sha256) or sha256_file(final) == part.sha256):
        if not _is_verified(final, part.sha256):
            _mark_verified(final, part.sha256)
        if counter:
            done = counter.add(final.stat().st_size)
            if progress:
                progress(done, counter.total, f"{part.name} (cache)")
        return final
    tmp = dest_dir / (part.name + ".part")
    errors = []
    counted = 0                                   # bytes of this part reflected in ``counter``

    def account(total_for_part: int, label: str) -> None:
        nonlocal counted
        if counter is None:
            return
        done = counter.add(total_for_part - counted)
        counted = total_for_part
        if progress:
            progress(done, counter.total, label)

    for raw_url in part.urls:
        url = expand_url(raw_url)
        for attempt in range(retries_per_url):
            if cancel is not None and cancel.is_set():
                raise DownloadError("cancelled")
            offset = tmp.stat().st_size if tmp.is_file() else 0
            if part.size and offset > part.size:
                tmp.unlink()
                offset = 0
            try:
                with _open(url, offset, timeout) as resp:
                    ctype = str(resp.headers.get("Content-Type", "")).lower()
                    if "text/html" in ctype:
                        raise DownloadError(f"{url}: got an HTML page instead of the file (quota/permissions?)")
                    if offset and getattr(resp, "status", 200) != 206:   # server ignored Range
                        offset = 0
                    written = offset
                    account(written, part.name)
                    with open(tmp, "ab" if offset else "wb") as fh:
                        while True:
                            if cancel is not None and cancel.is_set():
                                raise DownloadError("cancelled")
                            block = resp.read(CHUNK)
                            if not block:
                                break
                            fh.write(block)
                            written += len(block)
                            account(written, part.name)
                if part.size and tmp.stat().st_size != part.size:
                    raise DownloadError(f"{part.name}: size {tmp.stat().st_size} != {part.size} from {url}")
                if part.sha256 and sha256_file(tmp) != part.sha256:
                    tmp.unlink()
                    account(0, part.name)
                    raise DownloadError(f"{part.name}: SHA-256 mismatch from {url}")
                replace_with_retry(tmp, final)
                if part.sha256:
                    _mark_verified(final, part.sha256)
                return final
            except DownloadError as exc:
                errors.append(str(exc))
                if "cancelled" in str(exc):
                    raise
                if "HTML page" in str(exc) or "SHA-256" in str(exc) or "size" in str(exc):
                    break                                   # bad mirror: try the next one
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                errors.append(f"{url}: {exc}")
                time.sleep(min(8.0, 0.25 * 2 ** attempt))
    raise DownloadError(f"{part.name}: every mirror failed: " + " | ".join(errors[-4:]))


def assemble(asset: Asset, part_paths: list[Path], dest_dir: Path) -> Path:
    """Join multi-part assets and verify the whole-file SHA-256 (cached)."""
    if len(part_paths) == 1:
        path = part_paths[0]
        if not asset.sha256:                      # built-in fallback without a published hash
            return path
        if not (_is_verified(path, asset.sha256) or sha256_file(path) == asset.sha256):
            raise DownloadError(f"{asset.id}: SHA-256 mismatch")
        _mark_verified(path, asset.sha256)
        return path
    target = dest_dir / asset.filename
    if asset.sha256 and target.is_file() and _is_verified(target, asset.sha256):
        return target
    h = hashlib.sha256()
    tmp = dest_dir / (asset.filename + ".joining")
    with open(tmp, "wb") as out:
        for path in part_paths:
            with open(path, "rb") as fh:
                for block in iter(lambda: fh.read(8 * CHUNK), b""):
                    h.update(block)
                    out.write(block)
    if asset.sha256 and h.hexdigest() != asset.sha256:
        tmp.unlink()
        raise DownloadError(f"{asset.id}: SHA-256 mismatch after joining {len(part_paths)} parts")
    replace_with_retry(tmp, target)
    if asset.sha256:
        _mark_verified(target, asset.sha256)
    for path in part_paths:                                 # free disk: parts are no longer needed
        for p in (path, _verified_marker(path)):
            try:
                p.unlink()
            except OSError:
                pass
    return target


def download_assets(assets: Iterable[Asset], dest_dir: Path, *, workers: int = 4,
                    progress: ProgressFn | None = None,
                    cancel: threading.Event | None = None) -> dict[str, Path]:
    """Download every part of every asset in parallel; returns {asset_id: file}."""
    assets = list(assets)
    dest_dir = Path(dest_dir)
    jobs = [(a, i, p) for a in assets for i, p in enumerate(a.parts)]
    counter = _Counter(total=sum(p.size for _a, _i, p in jobs))
    results: dict[tuple[str, int], Path] = {}
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futures = {pool.submit(fetch_part, p, dest_dir, counter=counter, progress=progress, cancel=cancel): (a.id, i)
                   for a, i, p in jobs}
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
    return {a.id: assemble(a, [results[(a.id, i)] for i in range(len(a.parts))], dest_dir) for a in assets}
