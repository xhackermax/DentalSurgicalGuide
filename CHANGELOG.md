# Changelog

## Sin publicar

### Tests
- `test_surface_smoothing` buscaba el antiguo botón `dsg.cbct_post_smooth_teeth` en la revisión FDI inmediata y en la alineación. Desde la serie 9.2x ese botón se sustituyó por **MEJORAR DIENTES** (`dsg.finish_segmented_teeth`), que solo aparece en la primera revisión (`dsg/docs/MEJORA_UNICA_DIENTES.md`). El test comprueba ahora ese contrato: el botón aparece una vez en la revisión FDI inmediata, no aparece en la alineación y el botón antiguo no vuelve. No cambia el código del addon.

## 9.24.17 — versión instalada en Blender 5.2

El repositorio pasa de 9.10.11 a la copia de DSG instalada en Blender 5.2 del autor (`%APPDATA%\Blender Foundation\Blender\5.2\scripts\addons\dsg`, 20 de octubre de 2026). El historial 9.11–9.24 está en `dsg/docs/CHANGELOG.md` y en las notas de cada versión dentro de `dsg/docs/`.

### Instalación de motores en Blender 5.2
- Comprobado con los registros reales del equipo del autor (Windows, Blender 5.2, Python 3.13.13, RTX 2070): TotalSegmentator 2.18.0 y ToothSeg cargan sus checkpoints y hacen una pasada en GPU con PyTorch 2.14.1+cu126; DICOM y PyTorch quedan listos.
- Corregido: en Windows, «DICOM + motores» terminaba siempre como `PARTIAL` con error porque intentaba U-Mamba2, que no puede instalarse en Windows. Ahora U-Mamba2 se marca `UNSUPPORTED` y la instalación termina `DONE`. En Linux no cambia nada.

### Corregido
- `bl_info` declaraba 9.24.14 mientras `version.py` decía 9.24.17. Blender mostraba una versión equivocada en Preferencias. `tests/test_version_ssot.py` lo detecta.

### Comprobaciones del repositorio
- `tools/verify_release.py` comprueba la versión y `dsg/BUILD_MANIFEST.json` en lugar del ZIP 9.10.11. Los archivos que difieren del manifest se listan como `DSG_MANIFEST_DRIFT`. En esta copia difieren 7 archivos de la celosía axial y `__init__.py`, `segmentation_install_worker.py` y `tests_pure/test_installer.py` (cambios de esta versión); hay 6 archivos nuevos que el manifest no lista.
- `tools/run_checks.py` ejecuta los tests puros de `dsg/tests_pure` (uno por proceso) y el test de versión.
- `tools/run_blender_release_checks.py` construye el ZIP desde el árbol y ejecuta los casos de Blender que no necesitan runtime IA. `tools/blender_smoke.py` ejecuta la inicialización diferida antes de buscar operadores sin registrar.

### Pendiente (no forma parte de este cambio)
- En Blender 5.2.3 (bpy, Linux) fallan 24 de 89 tests de `dsg/tests_blender`. Unos dependen de Windows o de tener los motores instalados (`test_engine_models`, `test_immediate_gate`); otros son de geometría o interfaz.
- `tests/` (raíz) conserva tests de 9.7 que importan módulos ya retirados (`engine_install`, `irrigation_network`).

## 9.10.11 — contratos y diagnóstico del pipeline

Actualización desde el ZIP original del autor (8 de octubre de 2026).

- Contratos de volumen, calibración, spacing, labelmap y manifest con `schema_version=1` y `run_id`.
- Diagnóstico persistente con etapas, duración, estado y fallbacks; botón **Copiar diagnóstico**.
- Núcleo comprobable sin Blender, 20 tests puros, control de métricas e índice de código regenerable.
- Conserva labels anatómicos, motores, suavizado, geometría e historial Ctrl+Z.
- Incluye manual en español, explicación de funcionamiento, verificación y hoja de ruta.

Actualización acumulada desde 9.7.5: motores de la serie 9.10 y registro DICOM (9.10.0–1), reparación Windows/DICOM/CUDA/SciPy (9.10.2–4), suavizado reversible (9.10.5–9) e historial de etapas (9.10.9–10). No se atribuyen estos cambios previos a 9.10.11.

Detalle: [mejoras](docs/MEJORAS_9_10_11.md), [changelog del paquete](dsg/docs/CHANGELOG.md) y [limitaciones de pruebas](docs/VERIFICACION_9_10_11.md).

## Historial anterior del repositorio

## 9.7.5 — instalación de motores en Windows

### Corregido
- En Windows la instalación del motor se cortaba con `PermissionError: [WinError 5] Acceso denegado: …\\dsg_runtime\\install_status.json.tmp`. El instalador reemplaza el archivo de progreso varias veces por segundo mientras Blender lo lee, y Windows no permite reemplazar un archivo abierto por otro proceso. Un fallo al escribir el progreso abortaba toda la instalación.
  - Nuevo `engine_install/fsio.py`: reemplazo con reintentos ante bloqueos breves (Blender, antivirus, indexador) y archivo temporal propio para cada escritor.
  - El progreso es "best effort": si una actualización no se puede escribir, se descarta y la instalación continúa.
  - La activación del motor (renombrar carpetas), el puntero `active_runtime.json` y las descargas usan el mismo reemplazo con reintentos.
  - El instalador borra los `.tmp` que dejó una instalación interrumpida.

### Añadido
- `tests/test_engine_install_windows_locks.py`: emula el bloqueo de Windows (`WinError 5`) en cualquier sistema. Sin la corrección, reproduce el fallo.

## 9.7.4 — actualización sin reiniciar Blender

### Corregido
- Instalar el ZIP nuevo encima de un DSG ya activo fallaba con "DSG internal version mismatch … package=(9, 7, 0) guide_module=(9, 7, 3)". Al recargar el paquete, Blender reutilizaba el `dsg/version.py` antiguo que seguía en memoria. Ahora `dsg/__init__.py` descarta los submódulos en caché antes del primer import, así que todo se lee de los archivos nuevos.
- El mensaje del control de versiones propone primero reiniciar Blender.

### Añadido
- `tools/install_smoke.py` tiene un modo `upgrade`: instala una versión anterior, la activa e instala la nueva encima en la misma sesión. Reproduce el fallo sin la corrección.

## 9.7.3 — instalación rápida de motores

Detalle: [`docs/INSTALACION_MOTORES_9_7_3.md`](docs/INSTALACION_MOTORES_9_7_3.md).

### Añadido
- Paquete `engine_install`: identidad del motor independiente de la versión de DSG, manifest v2 (GitHub Release + Google Drive), descargas paralelas/reanudables/verificadas, instalación en staging con verificación real y activación atómica.
- Adopción de runtimes antiguos (`dsg_tsNNN`) sin reinstalar y limpieza de los sobrantes.
- PyTorch CPU en equipos sin NVIDIA (≈ 580 MB en Windows en lugar de varios GB).
- Construcción local con `uv` (3,6× más rápida que pip) y modelos descargados en paralelo.
- `tools/build_engine_release.py`: construye, empaqueta en capas, trocea (< 2 GiB) y genera `engines/manifest-v2.json`.

### Cambiado
- La caché de descargas vive fuera del addon y se borra tras instalar.
- Sonda `nvidia-smi` cacheada (antes se ejecutaba en cada redibujado del panel).

### Eliminado
- `totalseg_bootstrap_worker.py`, `totalseg_install_worker.py`, `build_windows_full_offline.py` y su `.bat` (doble ZIP + descompresión).

## 9.7.2 — paredes frangibles y marcas de perforación

Detalle: [`docs/PAREDES_FRANGIBLES_9_7_2.md`](docs/PAREDES_FRANGIBLES_9_7_2.md).

### Corregido
- La pared frangible flotaba dentro del hueco de la fresa y no sellaba; en modo C las dos salidas quedaban abiertas.
- La diana Ø2,5 mm nunca se grababa; la cruz (0,05 × 0,025 mm) no era imprimible.
- Modo directo: las ramas vinculadas arrancaban dentro del sleeve activo y su sleeve nunca se abría.
- STL con aristas compartidas por 3+ triángulos tras booleanas exactas (triangulación BEAUTY + separación de aristas pellizcadas).
- Cortador de cifras no manifold (píxeles en diagonal).

### Añadido
- Membrana por salida (0,10 mm centro / 0,25 mm borde) 0,30 mm detrás del hueco, avellanado de 0,20 mm y número de orden grabado junto al sleeve.
- Botón "Ver paredes y marcas" (previsualización no destructiva).

## 9.7.1 — irrigación con apertura secuencial

Detalle: [`docs/IRRIGACION_SECUENCIAL_9_7_1.md`](docs/IRRIGACION_SECUENCIAL_9_7_1.md).

### Añadido
- "Vincular seleccionados": une varios implantes al conducto principal con colocación automática de las Y.
- Apertura secuencial: cilindro inicial abierto, vinculados con pared frangible de 0,10 mm marcada y numerada por orden de perforación.
- Estrechamientos (gargantas) en el tronco hacia el cilindro inicial, dimensionados por Poiseuille para que el cilindro recién perforado reciba ≥ 75 % del agua (ajustable).
- Diseño de la red en la guía (`DSG_irrigation_network_json`) y en el informe de exportación.

### Corregido
- Las paredes frangibles no se construían (`create_circle` → `ret['geom']` vacío); toda exportación con sello se cancelaba.
- Un Link sobre otro Link desaparecía en "Aplicar irrigación"; ahora se une al tronco principal.
- `deselect_all_objects` con objetos `None` tras borrados.
- Los Links no recibían el sello automático; el mensaje de "Aplicar irrigación" describía boquillas desactivadas.

## 9.7.0 — calidad, seguridad y mantenibilidad

Detalle completo, motivos y verificación: [`docs/MEJORAS_9_7_0.md`](docs/MEJORAS_9_7_0.md).

### Corregido
- La verificación EXACT de distancia implante–diente fallaba con `NameError: np`.
- "REPARAR RUNTIME CUDA" apuntaba a un operador inexistente y ahora fuerza la reinstalación.
- El STL se guardaba como `<nombre>DSG_ExportGuide_Work.stl` (`use_batch=True`).
- `core.py` usaba `cbct_dental_module` sin importarlo (las etiquetas FDI no se ocultaban).
- Los marcadores `None` del paquete ocultaban submódulos en `from . import X`.

### Añadido
- Control de calidad de exportación: piezas sueltas, sólido cerrado, grosor de pared, distancia implante–conducto mandibular.
- Informe de trazabilidad `<stl>.dsg-report.json` (entradas con SHA-256, plan, versiones, comprobaciones).
- Logging central `dsg.*` con archivo rotativo; `DSG_LOG_LEVEL=DEBUG` registra los errores tolerados.
- `tools/run_checks.py`, `blender_smoke.py`, `install_smoke.py`, `build_addon_zip.py` y CI de GitHub.
- Instalación como Extension de Blender (`build_addon_zip.py --extension --license …`).

### Cambiado
- IDs de operador estables (sin `_v968`/`_v955`).
- Token del puente MCP solo en memoria (antes se guardaba en el `.blend`).
- Plantillas 3D en `resources/guide_assets/` con SHA-256 (antes ~700 KB de base85 en el código).
- Documentación, tests y herramientas fuera del paquete del add-on.
- `bl_info`: `blender = (5, 2, 0)` y descripción real.

## Versiones anteriores

Notas históricas originales (9.0 – 9.6.8) en [`docs/history/`](docs/history/).
