from __future__ import annotations

import base64
import zlib

import pytest

from dsg import guide_assets


@pytest.mark.parametrize("name", sorted(guide_assets._manifest()))
def test_asset_hash_verified_and_decodable(name):
    text = guide_assets.load_text(name)
    raw = base64.b85decode(text)
    assert len(raw) > 1000
    try:  # templates are zlib-compressed binary meshes
        zlib.decompress(raw)
    except zlib.error:
        pass


def test_corrupted_asset_fails_fast(tmp_path, monkeypatch):
    name = sorted(guide_assets._manifest())[0]
    (tmp_path / name).write_text("corrupted", encoding="ascii")
    monkeypatch.setattr(guide_assets, "ASSET_DIR", tmp_path)
    guide_assets.load_text.cache_clear()
    with pytest.raises(guide_assets.GuideAssetError, match="corrupted"):
        guide_assets.load_text(name)
    guide_assets.load_text.cache_clear()
