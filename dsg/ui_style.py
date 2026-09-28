"""DSG UI hierarchy helpers.

The clinical workflow uses a restrained FIVE-tone blue hierarchy.  The tones
encode workflow priority and secondary-route depth, not decoration:

    PRIMARY        bright clinical cyan-blue -> next required action
    SECONDARY      deep route blue          -> first secondary route/action
    SECONDARY_ALT  medium blue              -> nested secondary route/action
    SECONDARY_SOFT soft sky blue            -> low-priority route/action
    TERTIARY       blue-gray                -> navigation/accessory action

Blender's native Python panel API does not expose an arbitrary background color
per operator button.  DSG therefore keeps the user's Blender theme untouched
and adds a small native color marker to each semantic action row while also
using size/placement to reinforce hierarchy.

`depress=True` remains reserved for true selected/toggled states.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import bpy

# Five semantic workflow tones. Blender does not expose arbitrary per-operator
# fills, so DSG pairs native hierarchy/scale with tiny original color swatches.
ACTION_PRIMARY_HEX = "#169FC5"
ACTION_PRIMARY = (22 / 255.0, 159 / 255.0, 197 / 255.0, 1.0)
ACTION_SECONDARY_HEX = "#2D78B7"
ACTION_SECONDARY = (45 / 255.0, 120 / 255.0, 183 / 255.0, 1.0)
ACTION_SECONDARY_ALT_HEX = "#4C8CC6"
ACTION_SECONDARY_ALT = (76 / 255.0, 140 / 255.0, 198 / 255.0, 1.0)
ACTION_SECONDARY_SOFT_HEX = "#75A9D3"
ACTION_SECONDARY_SOFT = (117 / 255.0, 169 / 255.0, 211 / 255.0, 1.0)
ACTION_TERTIARY_HEX = "#91AFC7"
ACTION_TERTIARY = (145 / 255.0, 175 / 255.0, 199 / 255.0, 1.0)

# Backward-compatible aliases for older modules that referenced the old teal
# vocabulary. They deliberately resolve to the new three-tone hierarchy.
DSG_TEAL_HEX = ACTION_PRIMARY_HEX
DSG_TEAL = ACTION_PRIMARY
DSG_TEAL_MUTED_HEX = ACTION_SECONDARY_HEX
DSG_INFO_HEX = ACTION_PRIMARY_HEX
DSG_EMPTY_HEX = ACTION_TERTIARY_HEX

# Status colors are not action/button hierarchy colors. They are retained only
# for existing non-button status assets and validation messages.
DSG_DANGER_HEX = "#D65353"
DSG_SUCCESS_HEX = "#42B883"
DSG_WARNING_HEX = "#E3A93B"

UI_SCALE_PRIMARY = 1.42
UI_SCALE_SECONDARY = 1.12
UI_SCALE_NORMAL = 0.98
UI_SCALE_COMPACT = 0.90
UI_SCALE_HEADER = 1.18

TURQUOISE = (0.025, 0.72, 0.74, 1.0)
TURQUOISE_TEXT = (0.015, 0.055, 0.065, 1.0)
_THEME_SNAPSHOT = {}


def _priority_marker(row, level: str) -> None:
    """Add a small original blue swatch without mutating the user's Blender theme."""
    try:
        from . import icon_manager
        icon = icon_manager.icon_id(f"tone_{str(level).lower()}")
        if icon:
            marker = row.row(align=True)
            marker.scale_x = 0.42
            marker.label(text="", icon_value=icon)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


class _PrimaryActionProxy:
    """Make the single clinical next-step visibly turquoise in native Blender.

    Blender exposes no per-button colour API.  A depressed operator uses the
    theme's selected colour, which DSG owns while enabled (turquoise), so this
    tiny proxy consistently gives *only* primary actions a coloured treatment.
    It otherwise forwards the complete UILayout API unchanged.
    """

    def __init__(self, layout):
        object.__setattr__(self, "_layout", layout)

    def __getattr__(self, name):
        return getattr(self._layout, name)

    def __setattr__(self, name, value):
        setattr(self._layout, name, value)

    def operator(self, operator, **kwargs):
        kwargs.setdefault("depress", True)
        return self._layout.operator(operator, **kwargs)


def primary_action(container, *, enabled: bool = True, align: bool = False):
    """Required next step: large turquoise action, visually a clear "next"."""
    row = container.row(align=align)
    row.scale_y = UI_SCALE_PRIMARY
    row.enabled = bool(enabled)
    _priority_marker(row, "primary")
    return _PrimaryActionProxy(row)


def secondary_action(container, *, enabled: bool = True, align: bool = False):
    """Optional/corrective action: muted slate-blue, subordinate to primary."""
    row = container.row(align=align)
    row.scale_y = UI_SCALE_SECONDARY
    row.enabled = bool(enabled)
    _priority_marker(row, "secondary")
    return row


def secondary_action_alt(container, *, enabled: bool = True, align: bool = False):
    """Second nested route level: medium clinical blue."""
    row = container.row(align=align)
    row.scale_y = UI_SCALE_SECONDARY
    row.enabled = bool(enabled)
    _priority_marker(row, "secondary_alt")
    return row


def secondary_action_soft(container, *, enabled: bool = True, align: bool = False):
    """Third nested route level: soft sky blue."""
    row = container.row(align=align)
    row.scale_y = UI_SCALE_NORMAL
    row.enabled = bool(enabled)
    _priority_marker(row, "secondary_soft")
    return row


def tertiary_action(container, *, enabled: bool = True, align: bool = True):
    """Review/navigation/accessory action: compact blue-gray."""
    row = container.row(align=align)
    row.scale_y = UI_SCALE_NORMAL
    row.enabled = bool(enabled)
    _priority_marker(row, "tertiary")
    return row


def compact_action(container, *, enabled: bool = True, align: bool = True):
    """Very low-priority inline tool, using the tertiary blue-gray tone."""
    row = container.row(align=align)
    row.scale_y = UI_SCALE_COMPACT
    row.enabled = bool(enabled)
    _priority_marker(row, "tertiary")
    return row


def destructive_action(container, *, enabled: bool = True, compact: bool = False, align: bool = True):
    """Discard/reset action. Keep it tertiary in hierarchy; confirmation owns risk."""
    row = container.row(align=align)
    row.scale_y = UI_SCALE_COMPACT if compact else UI_SCALE_NORMAL
    row.enabled = bool(enabled)
    _priority_marker(row, "tertiary")
    return row


def header_row(container, *, align: bool = True):
    row = container.row(align=align)
    row.scale_y = UI_SCALE_HEADER
    return row


def apply_dsg_theme() -> bool:
    """Restore the restrained 8.0 turquoise selected-state and roundness."""
    try:
        themes = bpy.context.preferences.themes
        ui = themes[0].user_interface if themes else None
    except Exception:
        ui = None
    if ui is None:
        return False
    for widget_name in ("wcol_tool", "wcol_regular"):
        widget = getattr(ui, widget_name, None)
        if widget is None:
            continue
        for attr, value in (
            ("inner_sel", TURQUOISE),
            ("text_sel", TURQUOISE_TEXT),
            ("roundness", 0.48),
        ):
            if not hasattr(widget, attr):
                continue
            key = (widget_name, attr)
            current = getattr(widget, attr)
            if key not in _THEME_SNAPSHOT:
                try:
                    _THEME_SNAPSHOT[key] = tuple(current)
                except TypeError:
                    _THEME_SNAPSHOT[key] = current
            try:
                fitted = tuple(value[:len(current)]) if isinstance(value, tuple) else value
                setattr(widget, attr, fitted)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    for widget_name in ("wcol_box", "wcol_option", "wcol_num", "wcol_menu", "wcol_pulldown"):
        widget = getattr(ui, widget_name, None)
        if widget is None or not hasattr(widget, "roundness"):
            continue
        key = (widget_name, "roundness")
        if key not in _THEME_SNAPSHOT:
            _THEME_SNAPSHOT[key] = getattr(widget, "roundness")
        try:
            widget.roundness = 0.32
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    _redraw_all()
    return True


def restore_dsg_theme() -> None:
    """Restore every Blender theme value captured by :func:`apply_dsg_theme`."""
    try:
        themes = bpy.context.preferences.themes
        ui = themes[0].user_interface if themes else None
    except Exception:
        ui = None
    if ui is not None:
        for (widget_name, attr), value in list(_THEME_SNAPSHOT.items()):
            widget = getattr(ui, widget_name, None)
            if widget is not None and hasattr(widget, attr):
                try:
                    setattr(widget, attr, value)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
    _THEME_SNAPSHOT.clear()
    _redraw_all()


def _redraw_all() -> None:
    try:
        windows = list(bpy.context.window_manager.windows)
    except Exception:
        windows = []
    for window in windows:
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in screen.areas:
            try:
                area.tag_redraw()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
