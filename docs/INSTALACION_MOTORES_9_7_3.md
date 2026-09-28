# DSG 9.7.3 — Instalación rápida de los motores de IA

## 1. Resumen

| Situación | Antes (9.6.8 – 9.7.2) | Ahora (9.7.3) |
|---|---|---|
| Actualizar DSG | Reinstalación completa (varios GB) cada vez que cambiaba la versión del runtime | **0 s**: el motor se reutiliza |
| Primera vez, motor precompilado | No existía: siempre se construía en el PC | Descarga paralela y reanudable, extracción y verificación. **79 s** con un motor real de 7,9 GB servido en local |
| Primera vez sin motor precompilado | `pip` más 2 compresiones ZIP más 1 descompresión | `uv` (3,6× más rápido) con los modelos descargándose en paralelo |
| PC sin NVIDIA | Se descargaba PyTorch con CUDA | PyTorch sin CUDA: **≈ 580 MB** de descarga en Windows |
| Carpetas antiguas | `dsg_ts965`, `dsg_ts967`, `dsg_ts968` se acumulaban (~6 GB cada una) | Se reutiliza la última y se borran las demás |
| Archivos descargados | Dentro de la carpeta del addon, así que se perdían al actualizar | En `…/scripts/dsg_runtime/cache` y se borran tras instalar (se liberan ~4 GB) |

## 2. Cómo decide DSG de dónde sale el motor

Por orden, del camino más rápido al más lento:

1. **Reutilizar:** ya está instalado exactamente este motor. Tarda 0 s.
2. **Adoptar:** una carpeta antigua (`dsg_ts968_py313`, …) contiene el mismo motor. Se **renombra**, no se reinstala.
3. **Paquete dentro del ZIP:** versiones "offline completas" para equipos sin Internet (`offline_totalseg/`).
4. **Precompilado:** se lee `engines/manifest-v2.json` del repositorio de GitHub y se descargan los paquetes:
   - Varias descargas a la vez (4 hilos).
   - Si se corta, continúa donde se quedó (`.part` con Range).
   - Cada archivo se comprueba con su SHA-256.
   - Se prueban espejos en orden: GitHub Release → Google Drive (`gdrive:<id>`) → URL oficial.
5. **Construcción local:** `uv` instala PyTorch y TotalSegmentator **en una sola resolución**, y usa un archivo de bloqueo con hashes si existe. Mientras tanto, los modelos se descargan en paralelo. Si `uv` falla, se usa `pip`.

Todo se instala primero en `_stage-<clave>`. Después se **verifica importándolo en un proceso aparte**: PyTorch, nnU-Net, TotalSegmentator, las 77 clases dentales, que la versión CUDA tenga CUDA de verdad y que estén los modelos Dataset113/115. Solo entonces se activa con un renombrado. Si algo falla, el motor que ya funcionaba no se toca.

**Clave del motor:** `ts2.18.0-torch2.8.0-cuda126-cp313-win_amd64`. Depende solo del contenido, nunca de la versión de DSG.

**Aceleración:**
- CUDA si `nvidia-smi` responde; si no, CPU.
- La variable de entorno `DSG_AI_ACCEL=cpu|cuda126` fuerza una u otra.
- "Reparar runtime CUDA" reinstala con `force=True`.

## 3. Publicar los motores precompilados (una vez por versión del motor)

La descarga de PyTorch con CUDA y de los modelos oficiales está bloqueada en el entorno donde se preparó esta versión. Por eso los paquetes se generan en tu PC Windows:

```bat
"C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe" ^
    tools\build_engine_release.py --out engine_release
```

La herramienta:

1. Construye los motores CUDA y CPU con `uv` y verifica que cargan.
2. Escribe los archivos de bloqueo con hashes en `dsg/engine_install/locks/`.
3. Empaqueta dos capas por motor:
   - **torch:** PyTorch y las librerías de NVIDIA.
   - **core:** el resto. Es idéntica para CPU y CUDA, así que solo se sube una vez.
4. Trocea cada archivo en partes de < 2 GiB, el límite de GitHub.
5. Descarga y verifica los dos modelos oficiales.
6. Genera `engine_release/manifest-v2.json`.

Después:

```bat
gh release create engine-v2 --repo xhackermax/DentalSurgicalGuide engine_release\upload\*
```

**Google Drive (espejo opcional):**

1. Sube los mismos archivos a una carpeta de Drive.
2. Compártelos como **"cualquier persona con el enlace"**.
3. Crea `ids.json` con `{"nombre_archivo": "id_de_drive"}`.
4. Regenera el manifest sin reconstruir:

```bat
python tools\build_engine_release.py --out engine_release --manifest-only --drive-ids ids.json
```

Por último, copia `engine_release/manifest-v2.json` a `engines/manifest-v2.json` en el repositorio.

Hasta que se publique, el manifest del repositorio solo lleva el modelo Dataset113 y DSG usa la construcción local con `uv`. Ya es más rápida que antes, pero no tanto como el paquete precompilado.

**Tamaños medidos** (motor TotalSegmentator 2.18 con PyTorch 2.8):

| Motor | Instalado | Descarga (capas ZIP) |
|---|---|---|
| Windows cp313 CPU | 2,4 GB | torch 241 MB + core 339 MB ≈ **580 MB** |
| Linux cp313 CUDA (PyPI, prueba) | 7,9 GB | torch 3,9 GB (2 partes) + core 475 MB |
| Windows cp313 CUDA 12.6 | ≈ 5–6 GB (estimado) | ≈ 2,5–3 GB (se mide al generarlo) |

## 4. Verificación

- **`tests/test_engine_install.py` (21 tests, sin Blender ni Internet).** Un servidor HTTP local hace de GitHub o Drive. Cubre:
  - Descarga que continúa donde se cortó y servidor que ignora Range.
  - Espejo caído (404), página HTML en lugar del archivo, o hash incorrecto → pasa al siguiente espejo.
  - Caché sin volver a descargar y archivos en varias partes.
  - Protección contra rutas peligrosas dentro de un ZIP (zip-slip).
  - Instalación precompilada y reutilización en 0 s.
  - Adopción de una carpeta antigua y borrado de las viejas.
  - Una petición de CPU no adopta un motor CUDA.
  - Una verificación fallida conserva el motor que funcionaba.
  - Construcción local con modelos en paralelo y paquete offline dentro del addon.
- **`tests/test_engine_install_blender.py` (Blender 5.2).** `start_install()` lanza el proceso instalador real, la interfaz sigue el progreso y `quick_status()` informa de que el motor está listo. La segunda vez usa reutilización.
- **Prueba real completa:**
  1. `uv` construyó un motor real de 7,9 GB (68 s).
  2. `build_engine_release.py` lo empaquetó (4,4 GB en 3 archivos).
  3. El instalador lo descargó de un servidor local, lo extrajo, **lo importó de verdad** (`torch 2.8.0`, 77 clases dentales) y lo activó en **79 s**.
  4. La segunda ejecución tardó 0 s.

```
SUMMARY: compileall=PASS, ruff=PASS, pytest=PASS (143), blender_smoke=PASS, install_smoke=PASS
```

## 5. Pendiente

- **Generar y subir los paquetes de Windows** (sección 3). Es lo que activa la instalación rápida para todos los usuarios.
- **Recortar dependencias que DSG no usa** (`fury`, `dipy`, `pyarrow`, …). Primero hay que validarlo con una segmentación real en Windows con NVIDIA.
- **macOS:** la identidad y el instalador ya lo contemplan (siempre CPU), pero no hay paquetes publicados.
