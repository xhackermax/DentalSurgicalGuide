"""Run scene changes outside Panel.draw.

Blender forbids writing to ID data while a panel is drawn ("Writing to ID
classes in this context is not allowed").  The exception aborts the rest of
the panel, so every button drawn after the offending call disappears.  Panels
call ``run_later`` instead; the change runs on the next timer tick, once.
"""
import bpy

_PENDING = set()


def run_later(key, function):
    if key in _PENDING:
        return
    _PENDING.add(key)

    def _tick():
        _PENDING.discard(key)
        try:
            function(bpy.context)
        except Exception as exc:  # a failed visual sync must never break the UI
            print(f'[DSG] deferred {key}: {exc}')
        return None

    bpy.app.timers.register(_tick, first_interval=0.0)


def assign(target, attribute, value):
    """Set an RNA attribute only when it changes (avoids redraw loops)."""
    if target.path_resolve(attribute) != value:
        setattr(target, attribute, value)
        return True
    return False


def assign_key(target, key, value):
    if target.get(key) != value:
        target[key] = value
        return True
    return False


def set_hidden(obj, hidden):
    changed = assign(obj, 'hide_viewport', hidden)
    try:
        if obj.hide_get() != hidden:
            obj.hide_set(hidden)
            changed = True
    except RuntimeError:
        pass  # object not in the active view layer
    return changed
