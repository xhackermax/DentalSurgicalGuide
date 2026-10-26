"""Evaluate modifiers on an object even while the workflow keeps it hidden.

Blender does not evaluate modifiers of objects disabled in the viewport or
hidden in the view layer: a Boolean added to such an object silently
returns the original mesh.  The extraction Booleans (IOS socket and bone
carve) run on hidden objects, so they reported success without cutting.
"""
from contextlib import contextmanager


@contextmanager
def visible(*objects):
    saved = []
    for obj in objects:
        if obj is None:
            continue
        saved.append((obj, obj.hide_viewport, obj.hide_get()))
        obj.hide_viewport = False
        try:
            obj.hide_set(False)
        except RuntimeError:
            pass  # not in the active view layer
    try:
        yield
    finally:
        for obj, disabled, hidden in saved:
            obj.hide_viewport = disabled
            try:
                obj.hide_set(hidden)
            except RuntimeError:
                pass
