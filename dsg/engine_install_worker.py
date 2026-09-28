"""External AI-engine installer process (runs with Blender's Python, no ``bpy``).

    python engine_install_worker.py <request.json>

The request is written by ``totalseg_runtime.start_install``; progress goes to
``<base>/install_status.json`` (same keys the Blender UI already polls).
"""
from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from pathlib import Path


def _atomic_write(path: Path, data: dict) -> None:
    """Progress is best effort: a status file locked by Blender's UI poll
    (Windows) must never abort the installation."""
    from engine_install.fsio import write_json_atomic
    write_json_atomic(path, data, best_effort=True)


def main(argv: list[str]) -> int:
    request_path = Path(argv[-1]).resolve()
    q = json.loads(request_path.read_text(encoding="utf-8"))
    addon_dir = Path(q["addon_dir"]).resolve()
    sys.path.insert(0, str(addon_dir))             # import engine_install without the dsg package (bpy)
    from engine_install.installer import Installer, InstallRequest

    base = Path(q["base_dir"])
    base.mkdir(parents=True, exist_ok=True)
    status_path = base / "install_status.json"
    for stale in base.glob("install_status.json*.tmp"):   # left by an interrupted/older installer
        try:
            stale.unlink()
        except OSError:
            pass
    state = {"running": True, "done": False, "progress": 0.01, "phase": "BOOT",
             "message": "Instalador de motores iniciado", "error": "", "heartbeat": time.time()}
    lock = threading.Lock()
    stop = threading.Event()

    def emit(phase, message, progress, **extra):
        with lock:
            state.update(phase=phase, message=message, progress=float(progress), heartbeat=time.time(), **extra)
            state.setdefault("running", True)
            _atomic_write(status_path, state)
        print(f"[{phase}] {message}", flush=True)

    def heartbeat():
        while not stop.wait(2.0):
            with lock:
                state["heartbeat"] = time.time()
                _atomic_write(status_path, state)

    threading.Thread(target=heartbeat, daemon=True).start()
    emit("BOOT", "Instalador de motores iniciado", 0.01)
    try:
        request = InstallRequest(
            base_dir=base,
            python=str(q.get("python") or sys.executable),
            accel=str(q["accel"]),
            force=bool(q.get("force", False)),
            manifest_urls=tuple(q.get("manifest_urls") or ()) or InstallRequest.__dataclass_fields__["manifest_urls"].default,
            offline_payload_dir=Path(q["offline_payload_dir"]) if q.get("offline_payload_dir") else None,
            locks_dir=Path(q["locks_dir"]) if q.get("locks_dir") else None,
            workers=int(q.get("workers", 4)),
            allow_build=bool(q.get("allow_build", True)),
        )
        result = Installer(request, emit).run()
        with lock:
            state.update(running=False, done=True, progress=1.0, phase="READY", error="",
                         source=result.source, key=result.key, seconds=round(result.seconds, 1),
                         details=result.details, heartbeat=time.time())
            _atomic_write(status_path, state)
        return 0
    except Exception as exc:                        # noqa: BLE001 - reported to the UI
        with lock:
            state.update(running=False, done=True, phase="ERROR", message="Instalación de motores fallida",
                         error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc()[-6000:],
                         heartbeat=time.time())
            _atomic_write(status_path, state)
        traceback.print_exc()
        return 1
    finally:
        stop.set()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
