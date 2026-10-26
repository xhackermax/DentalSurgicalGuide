from __future__ import annotations

"""Read-only safety checks for the DSG 9.10.11 Blender 5.2 segmentation build."""

from dataclasses import dataclass
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class FailtestResult:
    name: str
    status: str
    detail: str


def _ok(name, cond, detail_ok, detail_fail):
    return FailtestResult(name, "PASS" if cond else "FAIL", detail_ok if cond else detail_fail)


def run_all():
    results = []
    init = (ROOT / "__init__.py").read_text(encoding="utf-8")
    version = (ROOT / "version.py").read_text(encoding="utf-8")
    engines = (ROOT / "segmentation_engines.py").read_text(encoding="utf-8")
    installer = (ROOT / "segmentation_install_worker.py").read_text(encoding="utf-8")
    worker = (ROOT / "cbct_pipeline_worker.py").read_text(encoding="utf-8")

    results.append(_ok("version_9_10_10", "DSG_VERSION = (9, 22, 16)" in version and '"version": (9, 22, 16)' in init,
                       "Versión coherente 9.22.16", "Versiones internas no coinciden"))
    results.append(_ok("blender_5_2_only", '"blender": (5, 2, 0)' in init and '(major, minor) != (5, 2)' in engines,
                       "Build limitada a Blender 5.2", "No está aplicado el gate exclusivo de Blender 5.2"))
    results.append(_ok("three_engines", all(token in engines for token in ('ENGINE_TOTALSEG', 'ENGINE_TOOTHSEG', 'ENGINE_UMAMBA2')),
                       "Tres motores registrados", "Falta uno de los tres motores"))
    legacy = [name for name in ("densevnet_engine.py", "cbct_ai_runtime.py", "totalseg_runtime.py", "offline_model_pack.py") if (ROOT / name).exists()]
    results.append(_ok("legacy_runtime_removed", not legacy, "Runtimes legacy eliminados", "Persisten: " + ", ".join(legacy)))
    results.append(_ok("real_checkpoint_gate", '_contains_checkpoint' in engines and 'st_size >= 1_000_000' in engines,
                       "READY exige checkpoint real", "READY no valida checkpoints reales"))
    results.append(_ok("umamba_ssl_not_ready", 'SSL pretraining weights as a final segmenter' in engines or 'pesos SSL de preentrenamiento no se marcan' in engines,
                       "U-Mamba2 no confunde SSL con checkpoint final", "U-Mamba2 podría dar falso READY"))
    results.append(_ok("toothseg_official_weights", 'zenodo.org/records/14893540/files/ToothSeg.zip' in installer and '5d8dd061cce9529943567aeba3271143' in installer,
                       "ToothSeg usa paquete oficial + MD5", "Falta verificación del paquete oficial ToothSeg"))
    dicom_parts = "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "_dicom_parts").glob("*.py")))
    op_source = (ROOT / "_dicom_parts/06_operators_b.py").read_text(encoding="utf-8")
    classes_match = re.search(r"CLASSES\s*=\s*\((.*?)\)\s*\n\n# Preserve", op_source, flags=re.S)
    registered_names = [] if classes_match is None else [
        line.strip().rstrip(",") for line in classes_match.group(1).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    missing_registered = [name for name in registered_names if not re.search(rf"class\s+{re.escape(name)}\b|\b{re.escape(name)}\s*=", dicom_parts)]
    results.append(_ok("dicom_registered_symbols_defined", not missing_registered,
                       "Todos los operadores DICOM registrados están definidos",
                       "Operadores registrados no definidos: " + ", ".join(missing_registered)))
    results.append(_ok("external_worker", 'subprocess.Popen' in (ROOT / "cbct_pipeline_client.py").read_text(encoding="utf-8") and 'PIPELINE_EXTERNAL' in (ROOT / "_dicom_parts/06_operators_b.py").read_text(encoding="utf-8"),
                       "Inferencia aislada del hilo UI", "La inferencia externa no está cableada"))
    results.append(_ok("normalized_contract", 'normalized_labels_path' in worker and '_fdi_to_compat' in worker,
                       "Contrato de salida normalizado activo", "Falta normalización común de etiquetas"))
    forbidden = re.findall(r'5\.[01].*dsg_runtime|dsg_runtime.*5\.[01]', engines, flags=re.I)
    results.append(_ok("no_old_blender_runtime_adoption", not forbidden,
                       "No se adoptan runtimes de versiones Blender anteriores", "Se detectó adopción de runtime antiguo"))
    return results
