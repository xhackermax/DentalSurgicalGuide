from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)
import time
import threading

from .version import DSG_VERSION_STR
import bpy
from bpy.types import Operator
from . import dicom_module
from . import totalseg_runtime

# A versioned, unique RNA id prevents Blender 5.2 from dispatching a stale
# operator class left alive after an add-on ZIP update.  The old v955 id was
# the reason a click could return FINISHED without starting a worker.
INSTALL_OPERATOR_ID = "dsg.install_totalseg"
_VERIFY={"running":False,"done":False,"ready":False,"error":""}
_INSTALL_UI_TIMER_ACTIVE = False


def _tag_all_view3d_redraw():
    try:
        wm = bpy.context.window_manager
        for window in getattr(wm, "windows", ()):
            screen = getattr(window, "screen", None)
            for area in getattr(screen, "areas", ()) if screen else ():
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _install_ui_timer():
    global _INSTALL_UI_TIMER_ACTIVE
    try:
        st = totalseg_runtime.install_state()
        _tag_all_view3d_redraw()
        # Keep repainting while a worker is alive.  The status JSON is polled
        # here, so the progress indicator advances even though the worker is
        # a separate Python process.
        if st.get("running"):
            return 0.35
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _INSTALL_UI_TIMER_ACTIVE = False
    return None


def _ensure_install_ui_timer():
    global _INSTALL_UI_TIMER_ACTIVE
    if _INSTALL_UI_TIMER_ACTIVE:
        return
    _INSTALL_UI_TIMER_ACTIVE = True
    try:
        bpy.app.timers.register(_install_ui_timer, first_interval=0.05)
    except Exception:
        _INSTALL_UI_TIMER_ACTIVE = False


def component_status():
    ts = totalseg_runtime.quick_status()
    d = dicom_module.dicom_preflight_report()
    numpy_ready = dicom_module.load_numpy() is not None
    dicom_reader = dicom_module.load_pydicom() is not None
    dicom_full = bool(d.get("standard_cbct_ready", False))
    base_ready = bool(numpy_ready and dicom_reader)
    ready = bool(base_ready and ts.dependencies_ready and ts.model_ready)
    return {
        "numpy": numpy_ready,
        "dicom_engine": dicom_full,
        "dicom_reader": dicom_reader,
        "dicom_standard_cbct_ready": dicom_full,
        "base_required_ready": base_ready,
        "ai_dependencies": ts.dependencies_ready,
        "semantic_model": ts.model_ready,
        "universal_model": ts.model_ready,
        "totalsegmentator": ts.dependencies_ready,
        "totalsegmentator_teeth": ts.model_ready,
        "device": ts.device,
        "all_required_ready": ready,
        "engine": "TotalSegmentator",
        "engine_version": ts.version,
        "error": ts.error,
    }


def ui_component_status(): return component_status()
def invalidate_ui_component_status(): return None
def ui_engines_ready(): return bool(component_status().get("all_required_ready"))
def verification_state(): return dict(_VERIFY)
def remote_install_state(): return totalseg_runtime.install_state()
def state(): return totalseg_runtime.install_state()
def all_required_ready(): return ui_engines_ready()


def _verify():
    _VERIFY.update(running=True,done=False,ready=False,error="")
    try:
        s=totalseg_runtime.quick_status(); ok=bool(s.dependencies_ready and s.model_ready)
        _VERIFY.update(running=False,done=True,ready=ok,error="" if ok else s.error)
    except Exception as exc:
        _VERIFY.update(running=False,done=True,ready=False,error=f"{type(exc).__name__}: {exc}")


def start_background_verification(force=False):
    if _VERIFY.get("running"): return False
    if _VERIFY.get("done") and not force: return False
    threading.Thread(target=_verify,daemon=True,name="DSG-TotalSeg-Verify").start(); return True


def ensure_first_run_install_started():
    s=totalseg_runtime.quick_status()
    if s.dependencies_ready and s.model_ready: start_background_verification(force=True)
    return False


def reset_auto_start_for_retry(): return None
def start_install_all(): return totalseg_runtime.start_install()


class DSG_OT_InstallTotalSeg(Operator):
    """Stable TotalSegmentator installer operator.

    ``force=True`` re-extracts the runtime even when it already reports READY.
    It is the repair path used by "REPAIR CUDA RUNTIME" when an NVIDIA driver
    is present but the installed Torch build is CPU-only.
    Stale-module safety no longer depends on versioned ids: ``dsg.__init__``
    purges every cached ``dsg.*`` module before registration.
    """
    bl_idname=INSTALL_OPERATOR_ID
    bl_label=f"Instalar TotalSegmentator {DSG_VERSION_STR}"
    bl_description="Instala/prepara TotalSegmentator para DSG y muestra un diagnóstico persistente desde el primer clic."
    bl_options={"REGISTER"}

    force: bpy.props.BoolProperty(
        name="Force reinstall",
        description="Re-extract the runtime even if it is already reported as ready (CUDA repair)",
        default=False,
        options={"HIDDEN", "SKIP_SAVE"},
    )

    def execute(self, context):
        click_id = f"{time.time():.6f}"
        try:
            context.scene["DSG_totalseg_install_click"] = click_id
            context.scene["DSG_totalseg_install_operator"] = INSTALL_OPERATOR_ID
            context.scene.dicom_wizard_pro.status = f"DSG {DSG_VERSION_STR} · clic recibido · comprobando instalador…"
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            totalseg_runtime.record_install_click(click_id=click_id, operator_id=INSTALL_OPERATOR_ID)
            totalseg_runtime.mark_install_requested(f"DSG {DSG_VERSION_STR} · clic recibido · localizando Python de Blender…")
        except Exception as exc:
            msg=f"No se pudo inicializar el instalador {DSG_VERSION_STR}: {type(exc).__name__}: {exc}"
            try: self.report({"ERROR"}, msg[:240])
            except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
            return {"CANCELLED"}
        _tag_all_view3d_redraw()
        # Start the repaint loop immediately so REQUESTED/BOOT is visible on
        # the first click rather than waiting for process creation to finish.
        _ensure_install_ui_timer()

        s = totalseg_runtime.quick_status()
        if s.dependencies_ready and s.model_ready and not self.force:
            self.report({"INFO"}, f"TotalSegmentator {s.version} ya está listo · {s.device}")
            return {"FINISHED"}
        try:
            started = totalseg_runtime.start_install(force=bool(self.force))
        except Exception as exc:
            msg = f"TotalSegmentator {DSG_VERSION_STR}: {type(exc).__name__}: {exc}"
            totalseg_runtime.mark_install_error(msg)
            try:
                context.scene.dicom_wizard_pro.status = msg[:240]
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            _tag_all_view3d_redraw()
            self.report({"ERROR"}, msg[:240])
            return {"CANCELLED"}

        st=totalseg_runtime.install_state()
        if st.get("error"):
            msg=str(st.get("error"))
            self.report({"ERROR"}, msg[:240])
            return {"CANCELLED"}
        if not started:
            self.report({"INFO"}, f"La instalación TotalSegmentator {DSG_VERSION_STR} ya está en curso")
        else:
            self.report({"INFO"}, f"DSG {DSG_VERSION_STR} · instalando motor de IA ({totalseg_runtime.desired_accelerator().upper()})")
        return {"FINISHED"}


class DSG_OT_InstallAllTotalSeg(DSG_OT_InstallTotalSeg):
    bl_idname="dsg.install_all_totalseg"
    bl_label=f"Instalar todo TotalSegmentator {DSG_VERSION_STR}"


class DSG_OT_RuntimePreflight(Operator):
    bl_idname="dsg.runtime_preflight"
    bl_label=f"Comprobar TotalSegmentator {DSG_VERSION_STR}"
    bl_options={"REGISTER"}
    def execute(self,context):
        start_background_verification(force=True)
        s=totalseg_runtime.quick_status()
        self.report({"INFO"} if s.dependencies_ready and s.model_ready else {"WARNING"}, f"TotalSegmentator {'listo' if s.dependencies_ready and s.model_ready else 'pendiente'} · {s.error or s.device}")
        return {"FINISHED"}


CLASSES=(DSG_OT_InstallTotalSeg,DSG_OT_InstallAllTotalSeg,DSG_OT_RuntimePreflight)


def register():
    # Do NOT swallow registration errors. A dead install button is worse than a visible add-on error.
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        try:bpy.utils.unregister_class(c)
        except Exception:_DSG_LOG.debug("suppressed exception", exc_info=True)
