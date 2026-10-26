"""Live percentage for long steps (closed model creation, CBCT segmentation).

* Panel: a progress bar with the percentage (``draw_bar``).
* Viewport: a step-by-step list with percentages in the bottom-left corner
  of every 3D view (POST_PIXEL draw handler).

Blocking work (one operator, e.g. the closed model) would not repaint until
it ends, so ``begin(..., blocking=True)`` makes every step force a window
redraw.  Asynchronous work (segmentation, driven by a timer) only tags the
areas for redraw.
"""
import time

import bpy

STATE = {'active': False, 'title': '', 'pct': 0.0, 'steps': [], 'result': '', 'ok': True,
         'handler': None, 'last_redraw': 0.0, 'started': 0.0, 'blocking': True}
HOLD_SECONDS = 5.0
MIN_REDRAW_INTERVAL = 0.05
MAX_LINES = 12


def active():
    return bool(STATE['active'])


def visible():
    return bool(STATE['active'] or STATE['result'])


def begin(context, title, blocking=True):
    try:
        if bpy.app.timers.is_registered(_clear):
            bpy.app.timers.unregister(_clear)
    except Exception:
        pass
    STATE.update(active=True, title=str(title), pct=0.0, steps=[], result='', ok=True,
                 started=time.perf_counter(), last_redraw=0.0, blocking=bool(blocking))
    _install()
    if blocking:
        try:
            context.window_manager.progress_begin(0, 100)
        except Exception:
            pass
    _redraw(force=True)


def step(pct, text, detail=''):
    """Start a new stage at ``pct`` percent."""
    if not STATE['active']:
        return
    pct = max(0.0, min(100.0, float(pct)))
    STATE['pct'] = pct
    STATE['steps'].append([pct, str(text), str(detail or '')])
    _after_change()


def update(pct, phase, detail=''):
    """Progress report: a new phase opens a step, the same phase only
    refreshes the percentage and its detail line."""
    if not STATE['active']:
        return
    phase = str(phase or '').strip() or 'Procesando'
    pct = max(STATE['pct'], max(0.0, min(100.0, float(pct))))
    STATE['pct'] = pct
    steps = STATE['steps']
    if steps and steps[-1][1] == phase:
        steps[-1][2] = str(detail or '')
    else:
        steps.append([pct, phase, str(detail or '')])
    _after_change()


def _after_change():
    pct = STATE['pct']
    current = STATE['steps'][-1] if STATE['steps'] else (pct, '', '')
    if STATE['blocking']:
        try:
            bpy.context.window_manager.progress_update(int(pct))
        except Exception:
            pass
        _status(f"{STATE['title']} · {pct:.0f} % · {current[1]}")
    _redraw(force=STATE['blocking'])


def end(ok, text=''):
    if not STATE['active']:
        return
    STATE['active'] = False
    STATE['ok'] = bool(ok)
    if STATE['steps']:
        STATE['steps'][-1][2] = ''
    if ok:
        STATE['pct'] = 100.0
        final = text or 'Completado'
        if not STATE['steps'] or STATE['steps'][-1][1] != final:
            STATE['steps'].append([100.0, final, ''])
    STATE['result'] = text or ('Completado' if ok else 'Error')
    if STATE['blocking']:
        try:
            bpy.context.window_manager.progress_end()
        except Exception:
            pass
        _status('')
    _redraw(force=STATE['blocking'])
    try:
        bpy.app.timers.register(_clear, first_interval=HOLD_SECONDS)
    except Exception:
        _clear()


def _clear():
    if STATE['active']:
        return None
    STATE.update(result='', steps=[], pct=0.0)
    _remove()
    _tag_redraw()
    return None


def draw_bar(layout):
    """Percentage bar for the panel; returns True when something was drawn."""
    if not visible():
        return False
    pct = float(STATE['pct'])
    current = STATE['steps'][-1][1] if STATE['steps'] else 'Iniciando…'
    text = f'{pct:.0f} % · {current}'
    if hasattr(layout, 'progress'):
        layout.progress(factor=pct / 100.0, type='BAR', text=text)
    else:
        layout.label(text=text, icon='TIME')
    return True


def _status(text):
    try:
        workspace = bpy.context.workspace
        if workspace is not None:
            workspace.status_text_set(text or None)
    except Exception:
        pass


def _tag_redraw():
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
    except Exception:
        pass


def _redraw(force=False):
    now = time.perf_counter()
    if not force and now - STATE['last_redraw'] < MIN_REDRAW_INTERVAL:
        return
    STATE['last_redraw'] = now
    _tag_redraw()
    if force:
        try:
            # Repaint now, while the operator is still running.
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass


def _install():
    if STATE['handler'] is None:
        STATE['handler'] = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_PIXEL')


def _remove():
    handler = STATE['handler']
    STATE['handler'] = None
    if handler is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handler, 'WINDOW')
        except Exception:
            pass


def _elapsed():
    seconds = int(max(0.0, time.perf_counter() - STATE['started']))
    return f'{seconds // 60}:{seconds % 60:02d}'


def _lines():
    lines = []
    steps = STATE['steps']
    title = f"{STATE['title']} · {STATE['pct']:.0f} %"
    if STATE['active']:
        title += f'  ({_elapsed()})'
    elif not STATE['ok']:
        title = f"{STATE['title']} · error"
    lines.append((title, (1.0, 1.0, 1.0, 1.0)))
    shown = steps[-MAX_LINES:]
    if len(steps) > len(shown):
        lines.append((f'… {len(steps) - len(shown)} pasos anteriores', (0.6, 0.6, 0.6, 1.0)))
    for index, (pct, text, detail) in enumerate(shown):
        last = index == len(shown) - 1
        if last and STATE['active']:
            mark, color = '▶', (0.35, 0.85, 1.0, 1.0)
        else:
            mark, color = '✓', (0.55, 0.9, 0.55, 1.0)
        line = f'{mark} {pct:>3.0f} %  {text}'
        if detail and last and STATE['active']:
            line += ' · ' + detail
        lines.append((line[:110], color))
    if not STATE['active'] and not STATE['ok'] and STATE['result']:
        lines.append(('✗ ' + STATE['result'][:100], (1.0, 0.4, 0.35, 1.0)))
    return lines


def _draw():
    if not visible():
        return
    try:
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader
        context = bpy.context
        region = context.region
        if region is None:
            return
        scale = context.preferences.system.ui_scale
        size = 12.0 * scale
        pad = 10.0 * scale
        spacing = size * 1.55
        font = 0
        lines = _lines()
        blf.size(font, size)
        width = max(blf.dimensions(font, text)[0] for text, _c in lines) + 2 * pad
        height = spacing * len(lines) + 2 * pad - (spacing - size)
        left = 0.0
        area = context.area
        if area is not None and context.preferences.system.use_region_overlap:
            for other in area.regions:  # toolbar drawn over the view
                if other.type == 'TOOLS' and other.width > 1 and other.x < area.x + area.width / 2:
                    left = float(other.width)
        x0 = left + 14.0 * scale
        y0 = 14.0 * scale
        coords = ((x0, y0), (x0 + width, y0), (x0 + width, y0 + height), (x0, y0 + height))
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        shader.bind()
        shader.uniform_float('color', (0.08, 0.09, 0.11, 0.85))
        batch_for_shader(shader, 'TRI_FAN', {'pos': coords}).draw(shader)
        # Thin bar with the percentage along the bottom of the box.
        bar_h = 3.0 * scale
        fill = width * max(0.0, min(1.0, STATE['pct'] / 100.0))
        bar = ((x0, y0), (x0 + fill, y0), (x0 + fill, y0 + bar_h), (x0, y0 + bar_h))
        shader.uniform_float('color', (0.2, 0.75, 0.95, 1.0) if STATE['ok'] else (1.0, 0.35, 0.3, 1.0))
        batch_for_shader(shader, 'TRI_FAN', {'pos': bar}).draw(shader)
        gpu.state.blend_set('NONE')
        y = y0 + height - pad - size
        for text, color in lines:
            blf.position(font, x0 + pad, y, 0)
            blf.color(font, *color)
            blf.draw(font, text)
            y -= spacing
    except Exception:
        pass


def unregister():
    try:
        if bpy.app.timers.is_registered(_clear):
            bpy.app.timers.unregister(_clear)
    except Exception:
        pass
    STATE.update(active=False, result='', steps=[])
    _remove()
