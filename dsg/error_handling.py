"""DSG safety/error/fallback contract.

This module is deliberately Blender-free so workers, tests and Blender UI code
can share the same error language. User-visible errors use stable codes and
never expose raw exception strings or patient paths. Technical evidence is
redacted before it reaches the log.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
import traceback
from typing import Any, Mapping

LOG = logging.getLogger(__name__)

@dataclass(frozen=True)
class MessageSpec:
    code: str
    level: str
    title: str
    message: str
    action: str
    recoverable: bool = False

# Stable codes. Do not silently recycle a code for a different meaning.
CATALOG: dict[str, MessageSpec] = {
    "DSG-E100": MessageSpec("DSG-E100", "ERROR", "Faltan datos", "No están disponibles todos los datos necesarios para esta acción.", "Revisa el paso anterior y vuelve a intentarlo."),
    "DSG-E110": MessageSpec("DSG-E110", "ERROR", "Estado no válido", "La acción no es válida en el estado actual del caso.", "Vuelve al último paso válido y repite la acción."),
    "DSG-E120": MessageSpec("DSG-E120", "ERROR", "CBCT fuera del rango del motor", "El campo de visión supera el límite admitido por la ruta optimizada del motor seleccionado.", "Usa la ruta completa o recorta el CBCT a la región dentomaxilofacial y vuelve a segmentar."),
    "DSG-E200": MessageSpec("DSG-E200", "ERROR", "Motor IA no disponible", "El runtime de segmentación no está listo o está incompleto.", "Pulsa COMPROBAR MOTORES y, si sigue pendiente, REPARAR MOTORES.", True),
    "DSG-E210": MessageSpec("DSG-E210", "ERROR", "Worker IA no arrancó", "El proceso aislado de segmentación no pudo iniciarse.", "Reintenta. Si persiste, revisa el log DSG y ejecuta el failtest de runtime.", True),
    "DSG-E220": MessageSpec("DSG-E220", "ERROR", "Instalación del motor fallida", "No se pudo completar la instalación o reparación del motor IA.", "Reintenta REPARAR MOTORES. DSG conservará cualquier runtime válido previo.", True),
    "DSG-E230": MessageSpec("DSG-E230", "ERROR", "Segmentación fallida", "La segmentación no terminó correctamente.", "Revisa el diagnóstico guardado y vuelve a intentarlo; los datos originales no se modifican.", True),
    "DSG-E240": MessageSpec("DSG-E240", "ERROR", "Resultado del worker inválido", "El worker terminó, pero su manifiesto de resultados no es válido.", "No uses ese resultado. Ejecuta de nuevo la segmentación y conserva el diagnóstico.", True),
    "DSG-E300": MessageSpec("DSG-E300", "ERROR", "DICOM no válido", "El estudio DICOM no contiene la información necesaria o está incompleto.", "Selecciona una serie CBCT válida y vuelve a importarla."),
    "DSG-E400": MessageSpec("DSG-E400", "ERROR", "Geometría no válida", "La geometría no cumple los requisitos para continuar de forma segura.", "Corrige la malla indicada y repite la comprobación."),
    "DSG-E410": MessageSpec("DSG-E410", "ERROR", "Exportación bloqueada", "La guía no supera el control de calidad requerido para exportar.", "Corrige los fallos señalados. No ignores un bloqueo clínico sin revisión explícita."),
    "DSG-E500": MessageSpec("DSG-E500", "ERROR", "Incompatibilidad con Blender", "La operación usa un estado o API de Blender que DSG no puede resolver de forma segura.", "Guarda el caso, reinicia Blender 5.2 LTS y ejecuta el failtest de compatibilidad."),
    "DSG-E900": MessageSpec("DSG-E900", "ERROR", "Error interno inesperado", "DSG detuvo la acción para evitar continuar con un estado incierto.", "No repitas pasos destructivos. Conserva el log y ejecuta los failtests.", True),
    "DSG-F201": MessageSpec("DSG-F201", "WARNING", "Fallback CUDA → CPU", "La ejecución por CUDA falló; DSG continuará automáticamente en CPU.", "No necesitas intervenir. El cálculo puede tardar más.", True),
    "DSG-F205": MessageSpec("DSG-F205", "WARNING", "Fallback de ruta optimizada", "La ruta rápida del motor no pudo utilizarse; DSG continuará con su ruta completa validada.", "No necesitas intervenir. El cálculo puede tardar más.", True),
    "DSG-F210": MessageSpec("DSG-F210", "WARNING", "Fallback Python → Blender", "El worker Python directo no arrancó; DSG continuará en un Blender headless aislado.", "No necesitas intervenir salvo que el segundo intento falle.", True),
    "DSG-F220": MessageSpec("DSG-F220", "WARNING", "Fallback worker → supervisor", "Un worker de postproceso no respondió; DSG ejecutará esa tarea en el supervisor.", "No necesitas intervenir. El evento quedará registrado.", True),
    "DSG-F230": MessageSpec("DSG-F230", "WARNING", "Fallback geométrico", "El motor geométrico preferido falló y DSG está usando una ruta alternativa validada.", "Revisa el informe final antes de exportar.", True),
    "DSG-F301": MessageSpec("DSG-F301", "WARNING", "Lectura DICOM tolerante", "La cabecera DICOM no usó el formato habitual y DSG la abrió en modo compatible.", "No necesitas intervenir.", True),
    "DSG-F302": MessageSpec("DSG-F302", "WARNING", "Decoder DICOM alternativo", "El decoder DICOM preferido falló y DSG probó otra ruta compatible.", "No necesitas intervenir.", True),
    "DSG-F303": MessageSpec("DSG-F303", "WARNING", "Fallback DICOM ITK/GDCM", "Los decoders DICOM principales fallaron y DSG utilizó el lector ITK/GDCM disponible.", "No necesitas intervenir.", True),
    "DSG-F304": MessageSpec("DSG-F304", "WARNING", "Serie DICOM recuperada", "Los cortes de la misma serie estaban repartidos en varias carpetas y DSG los reunió automáticamente.", "No necesitas intervenir.", True),
    "DSG-W100": MessageSpec("DSG-W100", "WARNING", "Resultado degradado", "La operación terminó usando una ruta de recuperación.", "Revisa los avisos y confirma el resultado antes de continuar.", True),
}

_PATH_WIN = re.compile(r"(?i)(?:[A-Z]:\\[^\s\n\r\t\"']+)")
_PATH_UNIX = re.compile(r"(?<![\w:])/(?:[^\s\n\r\t\"']+/)+[^\s\n\r\t\"']+")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_LONG_ID = re.compile(r"\b\d{8,}\b")


def spec(code: str) -> MessageSpec:
    return CATALOG.get(code, CATALOG["DSG-E900"])


def redact(value: Any, *, limit: int = 12000) -> str:
    """Best-effort privacy redaction for technical logs.

    It removes home paths, generic absolute paths, e-mail-like strings and very
    long numeric identifiers. It is intentionally conservative: DSG should log
    technical state, not patient identity.
    """
    text = str(value or "")
    home = str(Path.home())
    if home:
        text = text.replace(home, "<HOME>")
    text = _PATH_WIN.sub("<PATH>", text)
    text = _PATH_UNIX.sub("<PATH>", text)
    text = _EMAIL.sub("<EMAIL>", text)
    text = _LONG_ID.sub("<ID>", text)
    return text[:limit]


def user_message(code: str, *, extra: str = "") -> str:
    item = spec(code)
    base = f"[{item.code}] {item.message} {item.action}".strip()
    # Extra is for controlled, non-sensitive context only, never raw exceptions.
    if extra:
        base += f" · {str(extra).strip()}"
    return base[:500]


def log_exception(logger: logging.Logger, code: str, exc: BaseException, *, context: Mapping[str, Any] | None = None) -> None:
    item = spec(code)
    tb = redact("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    ctx = redact(dict(context or {}))
    logger.error("%s %s | context=%s | traceback=%s", item.code, item.title, ctx, tb)


def log_fallback(logger: logging.Logger, code: str, *, reason: Any = "", context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    item = spec(code)
    event = {
        "code": item.code,
        "level": item.level,
        "title": item.title,
        "message": item.message,
        "action": item.action,
        "reason": redact(reason, limit=1200),
        "context": {str(k): redact(v, limit=500) for k, v in dict(context or {}).items()},
    }
    logger.warning("%s %s | reason=%s | context=%s", item.code, item.title, event["reason"], event["context"])
    return event


def report(operator: Any, code: str, *, extra: str = "", technical: BaseException | None = None, context: Mapping[str, Any] | None = None) -> str:
    """Report a stable user message through a Blender operator when available."""
    item = spec(code)
    message = user_message(code, extra=extra)
    if technical is not None:
        log_exception(LOG, code, technical, context=context)
    try:
        level = {"ERROR"} if item.level == "ERROR" else {"WARNING"} if item.level == "WARNING" else {"INFO"}
        operator.report(level, message)
    except Exception as exc:  # reporting must never replace the original failure
        log_exception(LOG, "DSG-E900", exc, context={"during": "operator.report", "original_code": code})
    return message


def error_payload(code: str, *, detail: Any = "", context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    item = spec(code)
    return {
        "ok": False,
        "code": item.code,
        "level": item.level,
        "title": item.title,
        "message": user_message(code),
        "recoverable": bool(item.recoverable),
        "technical_detail": redact(detail, limit=2000),
        "context": {str(k): redact(v, limit=500) for k, v in dict(context or {}).items()},
    }
