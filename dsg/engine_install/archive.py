"""Safe archive extraction (zip-slip protected) with byte progress."""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Callable


class ArchiveError(RuntimeError):
    pass


def safe_extract(archive: Path, dest: Path, progress: Callable[[int, int], None] | None = None) -> int:
    """Extract ``archive`` into ``dest``; returns the number of files written."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        members = zf.infolist()
        for m in members:
            target = (dest / m.filename).resolve()
            if target != root and root not in target.parents:
                raise ArchiveError(f"unsafe path in {Path(archive).name}: {m.filename}")
        total = sum(m.file_size for m in members) or 1
        done = files = 0
        for m in members:
            if m.is_dir():
                (dest / m.filename).mkdir(parents=True, exist_ok=True)
                continue
            out = dest / m.filename
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(m) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst, 4 * 1024 * 1024)
            files += 1
            done += m.file_size
            if progress:
                progress(done, total)
    return files


def flatten_single_root(dest: Path, expected: str) -> None:
    """If an archive wrapped everything in ``<expected>/``, lift its content one level."""
    inner = Path(dest) / expected
    if inner.is_dir() and len(list(Path(dest).iterdir())) == 1:
        for item in list(inner.iterdir()):
            shutil.move(str(item), str(Path(dest) / item.name))
        inner.rmdir()
