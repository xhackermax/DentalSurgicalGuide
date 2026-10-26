from __future__ import annotations

import json
import logging
import threading

import bpy
from bpy.types import Operator

from .version import DSG_VERSION_STR
from . import dicom_module, segmentation_engines, failtests, error_handling

_LOG = logging.getLogger(__name__)
INSTALL_OPERATOR_ID = "dsg.install_segmentation_engines_910"
_VERIFY = {"running": False, "done": False, "ready": False, "error": ""}
_INSTALL_UI_TIMER_ACTIVE = False


def _tag_all_view3d_redraw():
    try:
        for window in getattr(bpy.context.window_manager, "windows", ()):
            screen = getattr(window, "screen", None)
            for area in getattr(screen, "areas", ()) if screen else ():
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except Exception:
        _LOG.debug("redraw failed", exc_info=True)


def _install_ui_timer():
    global _INSTALL_UI_TIMER_ACTIVE
    try:
        state = segmentation_engines.install_state()
        _tag_all_view3d_redraw()
        if state.get("running"):
            return 0.35
    except Exception:
        _LOG.debug("install timer failed", exc_info=True)
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


def _selected_engine(context=None):
    context = context or bpy.context
    try:
        return str(context.scene.dicom_wizard_pro.ai_segmentation_engine or segmentation_engines.ENGINE_TOTALSEG).upper()
    except Exception:
        return segmentation_engines.ENGINE_TOTALSEG


def component_status():
    engine = _selected_engine()
    selected = segmentation_engines.verify_engine(engine, force=False)
    all_status = segmentation_engines.verify_all(force=False)
    d = dicom_module.dicom_preflight_report()
    numpy_ready = dicom_module.load_numpy() is not None
    dicom_reader = dicom_module.load_pydicom() is not None
    dicom_full = bool(d.get("standard_cbct_ready", False))
    base_ready = bool(numpy_ready and dicom_full)
    compute = segmentation_engines.runtime_compute_status()
    return {
        "numpy": numpy_ready,
        "dicom_engine": dicom_full,
        "dicom_reader": dicom_reader,
        "dicom_standard_cbct_ready": dicom_full,
        "base_required_ready": base_ready,
        "ai_dependencies": selected.dependencies_ready,
        "semantic_model": selected.model_ready,
        "universal_model": selected.model_ready,
        "totalsegmentator": all_status[segmentation_engines.ENGINE_TOTALSEG].ready,
        "toothseg": all_status[segmentation_engines.ENGINE_TOOTHSEG].ready,
        "umamba2": all_status[segmentation_engines.ENGINE_UMAMBA2].ready,
        "device": compute.get("device", "CPU"),
        "compute_ready": bool(compute.get("ready", False)),
        "all_required_ready": bool(base_ready and selected.ready and compute.get("ready", False)),
        "engine": selected.label,
        "engine_id": selected.engine,
        "engine_version": DSG_VERSION_STR,
        "error": selected.error,
    }


def ui_component_status(): return component_status()
def invalidate_ui_component_status(): segmentation_engines.invalidate_cache()
def ui_engines_ready(): return bool(component_status().get("all_required_ready"))
def verification_state(): return dict(_VERIFY)
def remote_install_state(): return segmentation_engines.install_state()
def state(): return segmentation_engines.install_state()
def all_required_ready(): return ui_engines_ready()


def _verify():
    _VERIFY.update(running=True, done=False, ready=False, error="")
    try:
        segmentation_engines.refresh_runtime_compute_status()
        status = segmentation_engines.verify_engine(_selected_engine(), force=True)
        complete = component_status()
        _VERIFY.update(running=False, done=True, ready=complete["all_required_ready"], error=status.error or ("Runtime DICOM/PyTorch incompleto" if not complete["all_required_ready"] else ""))
    except Exception as exc:
        _VERIFY.update(running=False, done=True, ready=False, error=f"{type(exc).__name__}: {exc}")


def start_background_verification(force=False):
    if _VERIFY.get("running"):
        return False
    if _VERIFY.get("done") and not force:
        return False
    threading.Thread(target=_verify, daemon=True, name="DSG-Segmentation-Verify").start()
    return True


def ensure_first_run_install_started():
    return False


def reset_auto_start_for_retry():
    return None


def start_install_all():
    return segmentation_engines.start_install("ALL")


class DSG_OT_InstallSegmentationEngines910(Operator):
    bl_idname = INSTALL_OPERATOR_ID
    bl_label = f"Instalar motores IA {DSG_VERSION_STR}"
    bl_description = "Instala/verifica TotalSegmentator, ToothSeg o U-Mamba2 en el runtime exclusivo de Blender 5.2"
    bl_options = {"REGISTER"}

    engine: bpy.props.EnumProperty(
        name="Motor",
        items=[
            ("ALL", "DICOM + motores", "Repara DICOM, PyTorch y motores; U-Mamba2 necesita Linux/CUDA y checkpoint final"),
            ("TOTALSEG", "TotalSegmentator", "TotalSegmentator 2.18 + task=teeth"),
            ("TOOTHSEG", "ToothSeg", "Código oficial + checkpoints Zenodo"),
            ("UMAMBA2", "U-Mamba2", "Código/kernels; checkpoint final ToothFairy3 se valida aparte"),
        ],
        default="ALL",
    )
    force: bpy.props.BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        engine = str(self.engine or "ALL").upper()
        if engine != "ALL":
            current = segmentation_engines.verify_engine(engine, force=True)
            compute = segmentation_engines.runtime_compute_status()
            prepared = dicom_module.dicom_standard_cbct_ready() and compute.get("ready") and (compute.get("cuda") or not segmentation_engines._nvidia_driver_present())
            if current.ready and prepared and not self.force:
                self.report({"INFO"}, f"{current.label} ya está READY")
                return {"FINISHED"}
        try:
            started = segmentation_engines.start_install(engine, force=bool(self.force))
        except Exception as exc:
            error_handling.log_exception(_LOG, "DSG-E220", exc, context={"engine": engine})
            self.report({"ERROR"}, str(exc)[:240])
            return {"CANCELLED"}
        _ensure_install_ui_timer()
        if started:
            self.report({"INFO"}, f"Instalador {engine} iniciado")
        else:
            self.report({"INFO"}, "Ya hay una instalación en curso")
        return {"FINISHED"}


class DSG_OT_RuntimePreflight(Operator):
    bl_idname = "dsg.runtime_preflight"
    bl_label = f"Comprobar motores {DSG_VERSION_STR}"
    bl_options = {"REGISTER"}

    def execute(self, context):
        segmentation_engines.invalidate_cache()
        statuses = segmentation_engines.verify_all(force=True)
        ready = [v.label for v in statuses.values() if v.ready]
        pending = [v.label for v in statuses.values() if not v.ready]
        text = "READY: " + (", ".join(ready) if ready else "ninguno")
        if pending:
            text += " · PENDIENTES: " + ", ".join(pending)
        self.report({"INFO" if ready else "WARNING"}, text[:240])
        return {"FINISHED"}


class DSG_OT_RunSafetyFailtests(Operator):
    bl_idname = "dsg.run_safety_failtests"
    bl_label = "Ejecutar failtests DSG"
    bl_description = "Ejecuta comprobaciones de seguridad de solo lectura; no modifica el caso clínico"
    bl_options = {"REGISTER"}

    def execute(self, context):
        results = failtests.run_all()
        payload = [r.__dict__ for r in results]
        try:
            context.scene["DSG_failtest_report"] = json.dumps(payload, ensure_ascii=False)
        except Exception:
            pass
        failed = [r for r in results if r.status == "FAIL"]
        if failed:
            self.report({"ERROR"}, "Failtests: " + ", ".join(r.name for r in failed[:3]))
            return {"CANCELLED"}
        self.report({"INFO"}, f"DSG failtests PASS · {len(results)} comprobaciones")
        return {"FINISHED"}


CLASSES = (DSG_OT_InstallSegmentationEngines910, DSG_OT_RuntimePreflight, DSG_OT_RunSafetyFailtests)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            _LOG.debug("unregister failed", exc_info=True)
