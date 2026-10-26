"""Hide Blender's dashed parent lines in the 3D views.

Every FDI label is parented to its tooth so it follows the tooth, but the
segmented teeth keep their origin at the CBCT root (world centre).  With
the "Relationship Lines" overlay on, Blender draws a dashed line from each
number to that centre, which clutters the dentition view.
"""
import bpy
from bpy.app.handlers import persistent


def hide_all():
    """Turn the relationship-line overlay off in every 3D view of every screen."""
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for space in area.spaces:
                if space.type == 'VIEW_3D' and space.overlay.show_relationship_lines:
                    space.overlay.show_relationship_lines = False


def _deferred():
    hide_all()
    return None


@persistent
def on_load(_dummy=None):
    bpy.app.timers.register(_deferred, first_interval=0.1)


def register():
    if on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load)
    bpy.app.timers.register(_deferred, first_interval=0.5)


def unregister():
    while on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load)
    if bpy.app.timers.is_registered(_deferred):
        bpy.app.timers.unregister(_deferred)
