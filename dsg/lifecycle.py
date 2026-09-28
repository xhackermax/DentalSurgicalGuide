"""Small lifecycle guard for Blender callbacks, timers and modal operators.

Blender can keep Python timer closures alive briefly while an add-on is being
reloaded or disabled.  Those callbacks must stop before RNA classes and scene
properties are removed, otherwise they can touch invalid StructRNA references.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import traceback

import bpy

_ACTIVE = False
_EPOCH = 0
_TIMER_WRAPPERS: set[object] = set()
_TIMER_BY_CALLBACK: dict[object, set[object]] = {}


def activate() -> int:
    """Start a fresh add-on lifecycle generation."""
    global _ACTIVE, _EPOCH
    cancel_all_timers()
    _EPOCH += 1
    _ACTIVE = True
    return _EPOCH


def deactivate() -> None:
    """Stop callbacks first, before modules remove RNA classes/properties."""
    global _ACTIVE, _EPOCH
    _ACTIVE = False
    _EPOCH += 1
    cancel_all_timers()


def is_active(epoch: int | None = None) -> bool:
    if not _ACTIVE:
        return False
    return epoch is None or int(epoch) == _EPOCH


def current_epoch() -> int:
    return int(_EPOCH)


def _forget_wrapper(wrapper, callback=None) -> None:
    _TIMER_WRAPPERS.discard(wrapper)
    if callback is None:
        return
    wrappers = _TIMER_BY_CALLBACK.get(callback)
    if wrappers is None:
        return
    wrappers.discard(wrapper)
    if not wrappers:
        _TIMER_BY_CALLBACK.pop(callback, None)


def register_timer(callback, *, first_interval: float = 0.0, persistent: bool = False):
    """Register a timer that automatically dies after add-on reload/unregister."""
    if not callable(callback):
        raise TypeError("Timer callback must be callable")

    epoch = current_epoch()

    def guarded_callback():
        if not is_active(epoch):
            _forget_wrapper(guarded_callback, callback)
            return None
        try:
            result = callback()
        except (ReferenceError, RuntimeError) as exc:
            print(f"[DSG] Timer stopped safely: {type(exc).__name__}: {exc}")
            result = None
        except Exception as exc:
            print(f"[DSG] Timer callback failed and was stopped: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            result = None
        if result is None:
            _forget_wrapper(guarded_callback, callback)
        return result

    guarded_callback.__name__ = f"dsg_guarded_{getattr(callback, '__name__', 'timer')}"
    guarded_callback.__module__ = getattr(callback, "__module__", __name__)
    _TIMER_WRAPPERS.add(guarded_callback)
    _TIMER_BY_CALLBACK.setdefault(callback, set()).add(guarded_callback)
    try:
        bpy.app.timers.register(
            guarded_callback,
            first_interval=max(0.0, float(first_interval)),
            persistent=bool(persistent),
        )
    except Exception:
        _forget_wrapper(guarded_callback, callback)
        raise
    return guarded_callback


def unregister_timer(callback) -> None:
    for wrapper in list(_TIMER_BY_CALLBACK.get(callback, ())):
        try:
            if bpy.app.timers.is_registered(wrapper):
                bpy.app.timers.unregister(wrapper)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        _forget_wrapper(wrapper, callback)


def cancel_module_timers(module_name: str) -> None:
    wanted = str(module_name)
    for callback, wrappers in list(_TIMER_BY_CALLBACK.items()):
        if getattr(callback, "__module__", "") != wanted:
            continue
        for wrapper in list(wrappers):
            try:
                if bpy.app.timers.is_registered(wrapper):
                    bpy.app.timers.unregister(wrapper)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            _forget_wrapper(wrapper, callback)


def cancel_all_timers() -> None:
    for wrapper in list(_TIMER_WRAPPERS):
        try:
            if bpy.app.timers.is_registered(wrapper):
                bpy.app.timers.unregister(wrapper)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        _TIMER_WRAPPERS.discard(wrapper)
    _TIMER_BY_CALLBACK.clear()
