# Changelog

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
