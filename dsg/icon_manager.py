"""DSG professional clinical icon registry.

Custom icons are original assets shipped with DSG.  The icon set has dark- and
light-theme raster variants generated from the same SVG source language.  DSG
never changes Blender's theme; it only selects the most legible preview asset at
draw time.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import os
import bpy
import bpy.utils.previews

_PREVIEWS = None


def _relative_luma(rgb) -> float:
    try:
        r, g, b = (float(rgb[0]), float(rgb[1]), float(rgb[2]))
    except Exception:
        return 0.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _theme_variant() -> str:
    """Return ``light`` or ``dark`` without mutating user preferences."""
    try:
        themes = bpy.context.preferences.themes
        if not themes:
            return 'dark'
        ui = themes[0].user_interface
        # Regular widget fill is available across supported Blender 5.x themes
        # and tracks the overall UI brightness well enough for icon contrast.
        rgb = getattr(getattr(ui, 'wcol_regular', None), 'inner', None)
        if rgb is not None and _relative_luma(rgb) >= 0.48:
            return 'light'
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return 'dark'


def register():
    global _PREVIEWS
    if _PREVIEWS is not None:
        return
    previews = bpy.utils.previews.new()
    icon_dir = os.path.join(os.path.dirname(__file__), 'icons')
    png_files = sorted(
        filename for filename in os.listdir(icon_dir)
        if filename.lower().endswith('.png'))
    stems = {os.path.splitext(filename)[0] for filename in png_files}
    for filename in png_files:
        name = os.path.splitext(filename)[0]
        # Every current DSG icon has dark/light variants. Keep the base PNG in
        # the distribution for backwards compatibility, but do not allocate a
        # third Blender preview when variants are present.
        if not name.endswith(('_dark', '_light')):
            if f'{name}_dark' in stems or f'{name}_light' in stems:
                continue
        try:
            previews.load(name, os.path.join(icon_dir, filename), 'IMAGE')
        except Exception as exc:
            print(f'[DSG Icons] Could not load {filename}: {exc}')
    _PREVIEWS = previews


def unregister():
    global _PREVIEWS
    if _PREVIEWS is None:
        return
    try:
        bpy.utils.previews.remove(_PREVIEWS)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _PREVIEWS = None


def icon_id(name: str) -> int:
    if _PREVIEWS is None:
        return 0
    try:
        variant_key = f'{name}_{_theme_variant()}'
        if variant_key in _PREVIEWS:
            return int(_PREVIEWS[variant_key].icon_id)
        if name in _PREVIEWS:
            return int(_PREVIEWS[name].icon_id)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return 0
