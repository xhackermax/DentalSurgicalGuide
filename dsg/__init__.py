import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)
# Keep this metadata self-contained.  Blender discovers legacy add-ons by
# parsing ``bl_info`` with ``ast.literal_eval`` before it imports the package;
# values such as ``DSG_VERSION`` are therefore not valid here.
# ``version`` MUST equal ``version.DSG_VERSION`` (enforced by
# tests/test_version_ssot.py and by the runtime check in register()).
bl_info = {
    "name": "DSG Dental Surgical Guide",
    "author": "Max Tiburcio",
    "version": (9, 7, 5),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > DSG (MCP: separate DSG MCP tab)",
    "description": "Dental surgical guide planning: DICOM/CBCT + IOS, implants, sleeves and guide export",
    "warning": "",
    "category": "3D View",
}


def _purge_stale_child_modules() -> None:
    """Forget ``dsg.*`` modules cached from a previously installed version.

    Installing a DSG ZIP over an enabled DSG makes Blender *reload* this
    package in the same process.  A reload re-executes this file, but relative
    imports such as ``from .version import …`` are answered from
    ``sys.modules`` — i.e. by the OLD version's modules, so the package
    reported the old version while ``guide_module`` (loaded fresh) reported
    the new one and the mixed-build guard refused to start.
    Purging before the first relative import guarantees every child module is
    read from the files on disk.  On a first import nothing is cached, so this
    is a no-op.
    """
    import sys as _sys

    prefix = f"{__name__}."
    for cached_name in [n for n in _sys.modules if n.startswith(prefix)]:
        _sys.modules.pop(cached_name, None)


_purge_stale_child_modules()

from .version import DSG_VERSION, DSG_VERSION_STR  # noqa: E402  (after the purge on purpose)


"""DSG package bootstrap.

DSG deliberately does *not* import the clinical modules while this package
is itself being initialized.  Blender may keep add-on modules in ``sys.modules``
when an add-on is updated/re-enabled in the same process.  Importing a module
such as ``alignment_module`` or ``roadmap_module`` from here while ``dsg`` is
still only partially initialized can therefore make their relative
``from . import dicom_module`` imports resolve against a half-built package and
raise the misleading circular-import error seen in Blender 5.1.

Blender first imports this file completely and only then calls ``register()``.
We take advantage of that contract: all DSG submodules are loaded lazily from
``register()`` in a strict dependency order.  The package is fully initialized
by then, so cross-module relative imports are safe.
"""

import importlib
import importlib.util
import sys
import traceback
from pathlib import Path

import bpy

# Child modules are bound as package globals by ``_load_modules()`` during
# register().  They are intentionally *not* pre-declared as ``None``: a
# ``name = None`` placeholder shadows the submodule, so ``from . import
# dental_assets`` inside another DSG module (or a test) would silently receive
# ``None`` instead of importing it.  Before register(), attribute access falls
# back to a normal lazy import through the PEP 562 ``__getattr__`` below.
_LAZY_SUBMODULES = frozenset({
    "lifecycle",
    "core",
    "ui_style",
    "icon_manager",
    "glyph_library",
    "dental_assets",
    "dental_asset_blender",
    "dental_mapping",
    "tooth_analysis",
    "dicom_module",
    "cbct_ai_runtime",
    "totalseg_runtime",
    "cbct_dental_module",
    "alignment_module",
    "guide_module",
    "roadmap_module",
    "clinical_core",
    "clinical_context",
    "evidence_core",
    "evidence_context",
    "frame_structural_core",
    "frame_fem_core",
    "frame_structural",
    "agent_core",
    "agent_scene_graph",
    "agent_facade",
    "runtime_bootstrap",
})


def __getattr__(name):
    if name in _LAZY_SUBMODULES:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _loaded(name):
    """Return an already loaded child module or ``None`` (never imports)."""
    return globals().get(name)


_MODULES = ()
_REGISTERED = []
_DEFERRED_INIT_ATTEMPTS = 0
_MODULES_LOADED = False


def _addon_dir() -> Path:
    return Path(__file__).resolve().parent


def _ensure_package_path():
    """Guarantee that Blender treats ``dsg`` as a real package.

    Some legacy add-on reload paths can leave the package without a usable
    ``__path__`` even though ``__init__.py`` was loaded correctly.  Standard
    relative imports then misleadingly report ``No module named
    dsg.dicom_module``.  Pin the package search path to the physical add-on
    directory before any clinical module is loaded.
    """
    pkg_dir = str(_addon_dir())
    path_obj = globals().get("__path__")
    if path_obj is None:
        globals()["__path__"] = [pkg_dir]
        return
    try:
        if pkg_dir not in path_obj:
            path_obj.append(pkg_dir)
    except Exception:
        globals()["__path__"] = [pkg_dir]


def _validate_installation():
    """Fail early with a precise message if Blender kept a partial install."""
    required = (
        "version.py", "source_parts.py", "dsg_logging.py",
        "lifecycle.py", "ui_style.py", "icon_manager.py", "glyph_library.py",
        "dental_assets.py", "dental_asset_blender.py", "tooth_analysis.py", "anatomy_refine.py",
        "dental_mapping/__init__.py", "dental_mapping/service.py", "dental_mapping/library.py",
        "dental_mapping/registration.py", "dental_mapping/landmark_transfer.py",
        "dental_mapping/landmark_refine.py", "dental_mapping/validation.py",
        "dental_mapping/derived_geometry.py", "dental_mapping/anatomic_fit.py",
        "dental_mapping/proximal_fit.py", "dental_mapping/occlusal_fit.py",
        "dental_mapping/emergence.py", "dental_mapping/scoring.py", "dental_mapping/surgical_context.py", "dental_mapping/mesh_distance_core.py", "dental_mapping/eoff.py", "dental_mapping/eoff_core.py", "dental_mapping/migration.py",
        "core.py", "common_surface_match.py", "dental_surface_geometry.py", "dicom_module.py", "runtime_bootstrap.py",
        "cbct_ai_runtime.py", "totalseg_runtime.py", "engine_install_worker.py", "engine_install/__init__.py", "engine_install/identity.py", "engine_install/manifest.py", "engine_install/download.py", "engine_install/archive.py", "engine_install/builder.py", "engine_install/installer.py", "cbct_dental_module.py", "alignment_module.py",
        "guide_module.py", "irrigation_network.py", "frangible_seal.py", "_guide_parts/06_irrigation_d_frangible.py", "_guide_parts/06_irrigation_c_sequential.py", "guide_assets.py", "resources/guide_assets/manifest.json", "resources/guide_assets/drill_visual_template.b85", "resources/guide_assets/implant_template.b85", "resources/guide_assets/microscrew_visual_template.b85", "guide_export/__init__.py", "guide_export/policy.py", "guide_export/mesh_checks.py", "guide_export/report.py", "guide_export/blender_adapter.py", "guide_export/service.py", "frame_structural_core.py", "frame_fem_core.py", "frame_structural.py", "roadmap_module.py", "agent_core.py", "agent_scene_graph.py", "agent_facade.py", "clinical_core.py", "clinical_context.py", "evidence_core.py", "evidence_context.py",
        "resources/dental_assets/asset_contract_v1.json",
        "resources/clinical/source_registry.json",
        "resources/clinical/patient_context_schema_v1.json",
        "resources/evidence/manifest.json", "resources/evidence/references.json",
        "resources/evidence/rules.json", "resources/evidence/journals.json",
        "resources/evidence/expert_watchlist.json", "resources/evidence/search_queries.json",
        "resources/frame/frame_structural_contract_v1.json",
        "resources/specs/DSG_v9_2_1_PATIENT_FIRST_WORKFLOW.json",
        "resources/runtime/OFFLINE_RUNTIME_MANIFEST.json",
        "THIRD_PARTY_MODEL_NOTICE.txt",
    )
    base = _addon_dir()
    missing = [name for name in required if not (base / name).is_file()]
    if missing:
        raise RuntimeError(
            "DSG installation incomplete. Missing files in "
            f"{base}: {', '.join(missing)}. Remove the old dsg folder and "
            "install the complete DSG ZIP again."
        )


def _import_submodule(name: str):
    """Load a DSG submodule from its exact file path.

    This deliberately does not depend on Blender's transient package search
    state during add-on reloads.  The module is registered in ``sys.modules``
    *before* execution, and also exposed on the ``dsg`` package, so ordinary
    relative imports such as ``from . import dicom_module`` resolve to the
    already-loaded module without creating a circular bootstrap.
    """
    _ensure_package_path()
    fq_name = f"{__name__}.{name}"
    module_path = _addon_dir() / f"{name}.py"
    package_dir = _addon_dir() / name
    is_package = False
    if not module_path.is_file():
        package_init = package_dir / "__init__.py"
        if package_init.is_file():
            module_path = package_init
            is_package = True
        else:
            raise ModuleNotFoundError(
                f"Required DSG module/package is missing: {module_path} / {package_init}"
            )

    # Blender keeps imported Python modules alive across add-on ZIP updates.
    # Reusing one here can execute an older guide_module.py even after the
    # physical dsg folder has been replaced. A registration always loads the
    # current on-disk DSG child module.
    cached = sys.modules.pop(fq_name, None)
    if cached is not None:
        try:
            if sys.modules[__name__].__dict__.get(name) is cached:
                delattr(sys.modules[__name__], name)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    spec = importlib.util.spec_from_file_location(
        fq_name,
        module_path,
        submodule_search_locations=[str(package_dir)] if is_package else None,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create import spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[fq_name] = module
    setattr(sys.modules[__name__], name, module)
    try:
        spec.loader.exec_module(module)
    except Exception:
        # Do not leave a poisoned half-initialized module behind.
        sys.modules.pop(fq_name, None)
        if sys.modules[__name__].__dict__.get(name) is module:
            delattr(sys.modules[__name__], name)
        raise
    return module


def _load_modules():
    """Load DSG modules once, in dependency order, after ``dsg`` is ready."""
    global _MODULES_LOADED, _MODULES
    global lifecycle, core, ui_style, icon_manager, glyph_library
    global dental_assets, dental_asset_blender, dental_mapping, tooth_analysis
    global dicom_module, cbct_ai_runtime, totalseg_runtime, cbct_dental_module, runtime_bootstrap
    global alignment_module, guide_module, frame_structural_core, frame_fem_core, frame_structural, roadmap_module, agent_core, agent_scene_graph, agent_facade, clinical_core, clinical_context, evidence_core, evidence_context

    if _MODULES_LOADED:
        return

    _ensure_package_path()
    _validate_installation()

    # Purge every cached DSG child module once per package registration. This
    # prevents mixed-version sessions after installing a newer ZIP in Blender.
    prefix = f"{__name__}."
    for cached_name in list(sys.modules):
        if cached_name.startswith(prefix):
            sys.modules.pop(cached_name, None)

    # Foundation modules first.  They do not depend on the clinical modules.
    lifecycle = _import_submodule("lifecycle")
    ui_style = _import_submodule("ui_style")
    icon_manager = _import_submodule("icon_manager")
    glyph_library = _import_submodule("glyph_library")
    dental_assets = _import_submodule("dental_assets")
    tooth_analysis = _import_submodule("tooth_analysis")
    core = _import_submodule("core")
    dental_asset_blender = _import_submodule("dental_asset_blender")
    dental_mapping = _import_submodule("dental_mapping")

    # DICOM is the root of the clinical workflow.  Load it before modules that
    # intentionally reference it at module scope (Alignment/Roadmap).
    dicom_module = _import_submodule("dicom_module")
    cbct_ai_runtime = _import_submodule("cbct_ai_runtime")
    totalseg_runtime = _import_submodule("totalseg_runtime")
    cbct_dental_module = _import_submodule("cbct_dental_module")
    runtime_bootstrap = _import_submodule("runtime_bootstrap")
    alignment_module = _import_submodule("alignment_module")
    guide_module = _import_submodule("guide_module")
    try:
        loaded_guide_version = tuple(guide_module.bl_info.get("version", ()))
    except Exception:
        loaded_guide_version = ()
    if loaded_guide_version != tuple(DSG_VERSION):
        raise RuntimeError(
            "DSG internal version mismatch in the installed files: "
            f"package={DSG_VERSION} guide_module={loaded_guide_version}. "
            "Restart Blender and enable DSG again; if it persists, remove the existing "
            "dsg add-on folder and install one complete DSG ZIP. "
            "This guard prevents Blender from running a partially mixed clinical build."
        )
    frame_structural_core = _import_submodule("frame_structural_core")
    frame_fem_core = _import_submodule("frame_fem_core")
    frame_structural = _import_submodule("frame_structural")
    clinical_core = _import_submodule("clinical_core")
    clinical_context = _import_submodule("clinical_context")
    evidence_core = _import_submodule("evidence_core")
    evidence_context = _import_submodule("evidence_context")
    roadmap_module = _import_submodule("roadmap_module")
    agent_core = _import_submodule("agent_core")
    agent_scene_graph = _import_submodule("agent_scene_graph")
    agent_facade = _import_submodule("agent_facade")

    _MODULES = (
        dicom_module,
        cbct_dental_module,
        runtime_bootstrap,
        alignment_module,
        guide_module,
        frame_structural,
        clinical_context,
        evidence_context,
        roadmap_module,
        agent_facade,
    )
    _MODULES_LOADED = True


def _quiesce_legacy_handlers():
    """Remove callbacks left by older DSG versions before RNA registration."""
    names = {
        "dicom_wizard_pro_depsgraph_update",
        "_dsg_update_dicom_measurements_handler",
        "_dsg_restore_implant_step_after_undo",
        "dicom_wizard_pro_undo_pre",
        "dicom_wizard_pro_undo_post",
        "dicom_wizard_pro_redo_pre",
        "dicom_wizard_pro_redo_post",
        "_dsg_migrate_irrigation_outlet_to_1mm",
    }
    for group_name in (
        "depsgraph_update_post",
        "undo_pre",
        "undo_post",
        "redo_pre",
        "redo_post",
        "load_post",
    ):
        handlers = getattr(bpy.app.handlers, group_name, None)
        if handlers is None:
            continue
        for handler in list(handlers):
            if getattr(handler, "__name__", "") not in names:
                continue
            try:
                handlers.remove(handler)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

    for module in (_loaded("dicom_module"), _loaded("guide_module")):
        if module is None:
            continue
        callback = getattr(module, "pre_register_quiesce", None)
        if callable(callback):
            try:
                callback()
            except Exception as exc:
                print(f"[DSG] Pre-register quiesce warning in {module.__name__}: {exc}")


def _configure_panels():
    # One sidebar tab and one parent panel. Only the active workflow stage is visible.
    for cls in getattr(dicom_module, "PANEL_CLASSES", ()):
        try:
            cls.bl_category = "DSG"
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    dicom_module.DICOMWIZARDPRO_PT_main.bl_parent_id = core.DSG_SUITE_PT_Main.bl_idname
    dicom_module.DICOMWIZARDPRO_PT_main.bl_label = "DICOM"
    dicom_module.DICOMWIZARDPRO_PT_main.bl_options = {"HIDE_HEADER"}
    dicom_module.DICOMWIZARDPRO_PT_main.poll = classmethod(
        lambda cls, context: core.stage_is(context, core.STAGE_DICOM)
    )

    alignment_module.DICP_PT_Main.bl_category = "DSG"
    alignment_module.DICP_PT_Main.bl_parent_id = core.DSG_SUITE_PT_Main.bl_idname
    alignment_module.DICP_PT_Main.bl_label = "Alignment"
    alignment_module.DICP_PT_Main.bl_options = {"HIDE_HEADER"}
    alignment_module.DICP_PT_Main.poll = classmethod(
        lambda cls, context: core.stage_is(context, core.STAGE_ALIGNMENT)
    )

    guide_module.DSG_PT_Main.bl_category = "DSG"
    guide_module.DSG_PT_Main.bl_parent_id = core.DSG_SUITE_PT_Main.bl_idname
    guide_module.DSG_PT_Main.bl_label = "DSG"
    guide_module.DSG_PT_Main.bl_options = {"HIDE_HEADER"}
    guide_module.DSG_PT_Main.poll = classmethod(
        lambda cls, context: core.stage_is(context, core.STAGE_GUIDE)
    )

    roadmap_module.DSG_PT_MCPRoadmap.bl_category = "DSG MCP"
    roadmap_module.DSG_PT_MCPRoadmap.bl_parent_id = ""
    roadmap_module.DSG_PT_MCPRoadmap.bl_options = {"DEFAULT_CLOSED"}
    roadmap_module.DSG_PT_MCPRoadmap.poll = classmethod(
        lambda cls, context: getattr(context, "scene", None) is not None
    )


def _normal_data_available():
    try:
        return (
            getattr(bpy.data, "objects", None) is not None
            and getattr(bpy.data, "scenes", None) is not None
        )
    except Exception:
        return False


def _deferred_initialize():
    """Initialize scene/object handoff only after _RestrictData is gone."""
    global _DEFERRED_INIT_ATTEMPTS
    _DEFERRED_INIT_ATTEMPTS += 1

    if not _normal_data_available():
        return 0.20 if _DEFERRED_INIT_ATTEMPTS < 50 else None

    try:
        for scene in bpy.data.scenes:
            if core.SUITE_LANGUAGE_KEY not in scene:
                scene[core.SUITE_LANGUAGE_KEY] = "ES"
            if core.SUITE_STAGE_KEY not in scene:
                core.set_stage(scene, core.infer_stage(scene))
            dental_mapping.migrate_scene_compatibility(scene)

        cbct_ready = bool(cbct_dental_module.deferred_post_register())
        dicom_ready = bool(dicom_module.deferred_post_register())
        guide_ready = bool(guide_module.deferred_post_register())
        if not (cbct_ready and dicom_ready and guide_ready):
            return 0.20 if _DEFERRED_INIT_ATTEMPTS < 50 else None

        scene = getattr(bpy.context, "scene", None)
        dsg_props = getattr(scene, "dsg_props", None) if scene is not None else None
        if (
            scene is not None
            and core.infer_stage(scene) == core.STAGE_GUIDE
            and dsg_props is not None
            and int(getattr(dsg_props, "current_step", 0)) == 0
        ):
            core.prepare_guide_entry_view(bpy.context)

        # First-run dependency bootstrap.  This is deliberately deferred until
        # Blender/Mixar has left _RestrictData and all DSG modules are registered.
        runtime_bootstrap.ensure_first_run_install_started()
        # v9.2.17: verify the complete DICOM/AI stack at startup, but keep the
        # minimal panel clean. Diagnostics live in the scene and Blender status bar.
        try:
            import json as _json
            _health = runtime_bootstrap.component_status()
            if scene is not None:
                scene["DSG_runtime_preflight"] = _json.dumps(_health, ensure_ascii=False, default=str)
            _missing = [k for k in ("dicom_engine", "ai_dependencies", "semantic_model", "universal_model") if not _health.get(k)]
            _text = "DSG listo · DICOM + segmentación verificados" if not _missing else "DSG preflight · falta: " + ", ".join(_missing)
            try:
                bpy.context.workspace.status_text_set(_text)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    except Exception as exc:
        print(f"[DSG] Deferred initialization warning: {type(exc).__name__}: {exc}")
        return 0.35 if _DEFERRED_INIT_ATTEMPTS < 50 else None

    print("[DSG] Deferred scene/object initialization completed")
    return None


def _register_deferred_initializer():
    global _DEFERRED_INIT_ATTEMPTS
    _DEFERRED_INIT_ATTEMPTS = 0
    lifecycle.unregister_timer(_deferred_initialize)
    lifecycle.register_timer(_deferred_initialize, first_interval=0.10)


def _unregister_deferred_initializer():
    if _loaded("lifecycle") is not None:
        _loaded("lifecycle").unregister_timer(_deferred_initialize)


def register():
    global _REGISTERED
    if _REGISTERED:
        return

    try:
        from . import dsg_logging
        _log_path = dsg_logging.configure()
        if _log_path:
            print(f"[DSG] log file: {_log_path}")
    except Exception as exc:  # logging must never prevent registration
        print(f"[DSG] logging setup warning: {exc}")

    try:
        _load_modules()
    except Exception as exc:
        print(f"[DSG] Module bootstrap failed: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        raise

    _REGISTERED = []
    icons_registered = False
    lifecycle_active = False
    _quiesce_legacy_handlers()
    try:
        lifecycle.activate()
        lifecycle_active = True
        icon_manager.register()
        icons_registered = True
        ui_style.apply_dsg_theme()
        core.register()
        _REGISTERED.append(core)
        _configure_panels()
        for module in _MODULES:
            module.register()
            _REGISTERED.append(module)
        _register_deferred_initializer()
        print(f"[DSG] REGISTERED v{DSG_VERSION_STR} | {__file__}")
    except Exception:
        _unregister_deferred_initializer()
        for module in reversed(_REGISTERED):
            try:
                module.unregister()
            except Exception as rollback_exc:
                print(f"[DSG] Registration rollback warning in {module.__name__}: {rollback_exc}")
        _REGISTERED = []
        if icons_registered:
            try:
                icon_manager.unregister()
            except Exception as rollback_exc:
                print(f"[DSG] Icon rollback warning: {rollback_exc}")
        if lifecycle_active:
            lifecycle.deactivate()
        try:
            ui_style.restore_dsg_theme()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        raise


def unregister():
    global _REGISTERED
    if not _MODULES_LOADED:
        return

    # Stop DSG 9.3 direct-Python pipeline before unloading modules.
    try:
        from . import cbct_pipeline_client
        cbct_pipeline_client.cleanup_artifacts()
    except Exception as exc:
        print(f"[DSG] Pipeline shutdown warning: {exc}")

    # Stop the persistent background Blender before unloading DSG modules.
    try:
        if _loaded("cbct_ai_runtime") is not None:
            shutdown = getattr(_loaded("cbct_ai_runtime"), "shutdown_persistent_worker", None)
            if callable(shutdown):
                shutdown()
    except Exception as exc:
        print(f"[DSG] AI worker shutdown warning: {exc}")

    _unregister_deferred_initializer()
    for module in reversed(list(_REGISTERED)):
        try:
            module.unregister()
        except Exception as exc:
            print(f"[DSG] Unregister warning in {module.__name__}: {exc}")
    _REGISTERED = []
    try:
        icon_manager.unregister()
    except Exception as exc:
        print(f"[DSG] Icon unregister warning: {exc}")
    try:
        ui_style.restore_dsg_theme()
    except Exception as exc:
        print(f"[DSG] UI theme restore warning: {exc}")
    lifecycle.deactivate()
    try:
        from . import dsg_logging
        dsg_logging.unconfigure()
    except Exception as exc:
        print(f"[DSG] logging teardown warning: {exc}")
