"""Integrity-checked loader for binary guide templates (drill, implant, microscrew).

The templates used to be ~700 KB of base85 text embedded in Python source.
They now live in ``resources/guide_assets/`` with SHA-256 hashes in
``manifest.json``; a corrupted or partial install fails fast with a clear
message instead of producing a wrong sleeve/drill geometry.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

ASSET_DIR = Path(__file__).resolve().parent / "resources" / "guide_assets"


class GuideAssetError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _manifest() -> dict:
    path = ASSET_DIR / "manifest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["files"]
    except (OSError, ValueError, KeyError) as exc:
        raise GuideAssetError(f"DSG guide asset manifest unreadable: {path}: {exc}") from exc


@lru_cache(maxsize=None)
def load_text(name: str) -> str:
    meta = _manifest().get(name)
    if meta is None:
        raise GuideAssetError(f"Unknown DSG guide asset: {name}")
    path = ASSET_DIR / name
    try:
        text = path.read_text(encoding="ascii")
    except OSError as exc:
        raise GuideAssetError(f"Missing DSG guide asset {path}; reinstall the complete add-on ZIP") from exc
    digest = hashlib.sha256(text.encode("ascii")).hexdigest()
    if digest != meta["sha256"]:
        raise GuideAssetError(f"DSG guide asset {name} is corrupted (sha256 {digest[:12]}… "
                              f"expected {meta['sha256'][:12]}…); reinstall the add-on")
    return text
