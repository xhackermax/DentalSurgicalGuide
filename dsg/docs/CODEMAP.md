# DSG 9.10.11 · Mapa del código

Guía para localizar cada área del addon y seguir un fallo desde el botón hasta el worker. Adaptada del mapa aportado para 9.10.9 y contrastada con las fuentes de esta entrega.

- [CODEMAP_INDEX.md](CODEMAP_INDEX.md): índice generado con AST, con funciones, clases, métodos, operadores y líneas exactas de las fuentes incluidas. No carga Blender ni ejecuta los módulos.
- [ARCHITECTURE_RATCHET.md](ARCHITECTURE_RATCHET.md): alcance de la primera fase de mejora arquitectónica y deuda pendiente.
- [INDEX.md](INDEX.md): resto de la documentación.

Desde la carpeta que contiene `dsg/`:

```powershell
python dsg/tools/gen_index.py dsg --write
python dsg/tools/gen_index.py dsg --check
python dsg/tools/check_quality.py
```

Los comandos requieren un Python compatible con las dependencias indicadas; el control de calidad necesita NumPy. Se ejecutan como herramientas de desarrollo, no como botones clínicos. El índice comprueba una huella de todas las fuentes productivas para detectar si quedó desactualizado.

Las rutas y nombres de símbolos son la referencia estable de este mapa. Las líneas y tamaños se consultan en el índice generado. La existencia de un motor en este mapa no demuestra que esté instalado o que sus pesos estén disponibles: eso se comprueba con el preflight real.

---

## 1. Vista general en 30 segundos

DSG tiene **tres etapas clínicas**, cada una con su módulo principal:

```
 DICOM / CBCT                 ALINEACIÓN                 GUÍA (DSG)
 dicom_module          ──►    alignment_module    ──►    guide_module
 (_dicom_parts/)              (_alignment_parts/)        (_guide_parts/)
      │                                                       │
      ├─ segmentación IA (proceso externo)                    └─ guide_export/ (control de calidad + STL)
      └─ cbct_dental_module (dientes FDI, revisión)

 core.py orquesta las etapas, las rutas (SIMPLE / IMMEDIATE) y el panel principal.
```

Además hay **dos rutas clínicas**, definidas en `core.py` (`ROUTE_SIMPLE`, `ROUTE_IMMEDIATE`):

- **Implante simple:** segmentación de arcadas y alineación con el IOS.
- **Implante inmediato:** dientes individualizados con FDI, selección de dientes a extraer, modelos alveolares e IOS postextracción.

Y el código corre en **tres tipos de proceso**:

| Proceso | Qué ejecuta | ¿Tiene Blender? |
|---|---|---|
| Blender (UI) | Operadores, paneles, timers e importación de resultados | Sí |
| Worker de inferencia | `cbct_pipeline_worker.run_request()` → `main()` → tareas | Usa Python del runtime IA; el launcher también admite Blender headless como fallback |
| Workers auxiliares | `segmentation_install_worker.py`, `cbct_post_smoothing_worker.py`, `cbct_surface_sidecar.py`, `engine_preflight.py`, `compute_probe.py` | No |

---

## 2. Cómo se carga el addon (lo primero que hay que entender)

### 2.1 `__init__.py`

1. Blender descubre `bl_info`; sus valores literales permiten inspeccionar el addon antes de cargarlo.
2. El paquete importa la versión y utilidades estándar. En 9.10.11 `bpy` se importa dentro de `_blender_api()` al utilizarlo. Por eso `import dsg.pipeline_core` funciona en Python independiente de Blender.
3. `register()` llama a `_load_modules()`: comprueba archivos obligatorios, limpia módulos cacheados y carga dependencias en orden. El orden clínico es `core` → `dicom_module` → `segmentation_engines` → `cbct_dental_module` → `runtime_bootstrap` → `alignment_module` → `guide_module`; después se cargan contexto, estructura y agente.
4. Comprueba que la versión de la guía coincida con `version.DSG_VERSION`, registra la suite y los módulos con UI y prepara inicialización diferida y el historial.

La importación diferida del bootstrap no convierte en puros los módulos clínicos: `core.py`, DICOM, alineación y guía siguen dependiendo de Blender. `_validate_installation()` comprueba un listado explícito, no todos los archivos del addon. Los módulos de historial y suavizado también se cargan mediante sus consumidores y el registro de la suite.

### 2.2 Los fragmentos (`_dicom_parts`, `_guide_parts`, `_alignment_parts`)

`dicom_module.py`, `guide_module.py` y `alignment_module.py` tienen 9–24 líneas. Lo único que hacen es llamar a `source_parts.exec_source_parts()`, que **ejecuta varios archivos en el mismo espacio de nombres**, por orden.

Consecuencias prácticas al corregir:

- **Una función de un fragmento puede usar cualquier nombre definido en un fragmento anterior sin importarlo.** Si ves un nombre que no se define en el archivo, búscalo en toda la carpeta del fragmento.
- **Renombrar o borrar una función puede romper otro fragmento** sin que el editor lo avise. Antes de cambiar un nombre, búscalo en la carpeta y en todo `dsg/`: otros módulos acceden con `dicom_module.nombre`.
- **El orden importa.** Un fragmento no puede usar a nivel de módulo algo definido en uno posterior; dentro de funciones sí, porque se resuelve al ejecutarlas.
- **Las trazas de error muestran el archivo y la línea reales del fragmento**, así que se pueden seguir sin problema.
- Desde fuera se accede siempre por el módulo anfitrión: `dicom_module.load_volume`, `guide_module.STEP_IMPLANT`, etc.

---

## 3. Flujo de segmentación, paso a paso

Este es el camino que recorre un CBCT desde que se elige el archivo hasta que aparecen los dientes. Es la primera referencia cuando “no segmenta”.

| # | Qué pasa | Dónde |
|---|---|---|
| 1 | El usuario elige el DICOM | `DICOMWIZARDPRO_OT_select_file` · `_dicom_parts/06_operators_a.py` |
| 2 | Se analiza la carpeta y la serie | `probe_source()` · `_dicom_parts/01_utils_dicom_io.py` |
| 3 | Se decodifica el volumen (pydicom → decoders alternativos → ITK/GDCM → `minidicom.py`) | `load_volume()` · `01_utils_dicom_io.py` |
| 4 | Se guarda una caché `.npy` para el worker | `_prepare_external_pipeline_cache()` · `01_utils_dicom_io.py` |
| 5 | El usuario pulsa “Segmentar todo” o “Segmentar DICOM” | `DICOMWIZARDPRO_OT_segment_all` / `_direct_dicom_to_surface` · `06_operators_b.py` |
| 6 | Se prepara la petición y se lanza el worker | `_start_async_full_segmentation()` · `06_operators_b.py` → `cbct_pipeline_client.start_full_pipeline()` |
| 7 | Si Python directo no arranca, se reintenta en Blender headless (`DSG-F210`) | `cbct_pipeline_client.py` · `_launch_blender_fallback` |
| 8 | `run_request()` valida el esquema y abre RunTrace; `main()` valida volumen, spacing y calibración antes de inferir | `cbct_pipeline_worker.py`; `pipeline_core/contracts.py`, `trace.py` |
| 9 | Inferencia según el motor; si falla CUDA, se reintenta en CPU | `infer_totalseg` · `infer_toothseg` · `infer_umamba2` |
| 10 | Se normalizan a labels compatibles, se deriva FDI y Labelmap valida dimensiones, dtype, labels y presencia de dientes | `cbct_pipeline_worker.py` · `_fdi_to_compat`, `_translate_totalseg` |
| 11 | Se generan las mallas por diente (VTK o scikit-image) | `cbct_pipeline_tasks.run_teeth_task` → `cbct_surface_meshing.py` |
| 12 | Escribe estado y manifest schema_version=1, run_id y contrato del labelmap | `atomic_json` · `cbct_pipeline_worker.py` |
| 13 | Blender consulta el estado con un timer | `_poll_async_segmentation()` · `06_operators_b.py` → `cbct_pipeline_client.state()` |
| 14 | ResultManifest verifica esquema/run_id; la UI verifica dimensiones/dtype y crea dientes por lotes | `consume_manifest()` → `cbct_dental_module.iter_build_universal_dentition()` |
| 15 | Se termina: revisión FDI y paso a alineación | `_finish_async_segmentation()` · `06_operators_b.py` |

**Archivos que deja cada ejecución:** carpeta del job con `request.json`, `status.json`, `manifest.json` y `pipeline.log`. `cbct_pipeline_client.snapshot_failure_diagnostics()` copia estos archivos cuando algo falla.

**Diagnóstico en 9.10.11:** el cliente crea un `run_id` y conserva un JSON en `scripts/dsg_diagnostics/<run_id>.json`, fuera del job temporal. `RunTrace` registra etapas, duración, resultado y fallbacks controlados. `dsg.copy_pipeline_diagnostic`, en `cbct_dental_module.py`, permite copiar el último registro desde el panel DICOM. Copia el diagnóstico estructurado; los requests y logs operativos quedan separados porque pueden contener rutas privadas. No equivale a copiar todo `manifest.json` ni todo `pipeline.log`.

**Contratos:** `pipeline_core/contracts.py` define `VolumeInput`, `Labelmap`, `ResultManifest` y errores por etapa. Conserva dientes 1..32, mandíbula 53, maxila 54 y canal 55. `pipeline_core/trace.py` escribe la trazabilidad. El núcleo no importa Blender. No presupone HU absolutos para todos los CBCT.

**Instalación y comprobación de motores:** `segmentation_engines.py` (rutas, estado, `verify_engine`) · `segmentation_install_worker.py` (descargas y pip en proceso aparte) · `runtime_bootstrap.py` (estado en la UI y operadores de instalar y verificar) · `engine_preflight.py` (carga real de modelos).

---

## 4. Mapa por áreas

En la columna **Blender**: ✅ depende de su API; ❌ no importa directamente su API; la ausencia de imports directos no certifica pureza transitiva. El índice identifica imports diferidos y anfitriones de fragmentos.

### 4.1 Infraestructura y arranque

| Archivo | Qué hace | Blender |
|---|---|---|
| `__init__.py` | `bl_info`, carga ordenada, registro y limpieza; importación de bpy diferida a `_blender_api()` | Diferido |
| `version.py` | Versión única (SSOT): `DSG_VERSION` | ❌ |
| `source_parts.py` | Ejecuta los fragmentos en un espacio de nombres compartido | ❌ |
| `lifecycle.py` | Protege timers, handlers y modales durante la recarga o desactivación del addon | ✅ |
| `blender_compat.py` | Contrato de compatibilidad con Blender 5.2 | ✅ |
| `dsg_logging.py` | Log central con redacción de rutas y datos personales (`…/scripts/dsg_logs/dsg.log`) | ❌ |
| `error_handling.py` | Catálogo de códigos `DSG-E###` / `DSG-F###` / `DSG-W###`, `report()`, `log_fallback()`, `redact()` | ❌ |
| `failtests.py` | Comprobaciones de contrato invocadas por el operador de seguridad; no es el ratchet de métricas | ❌ |
| `pipeline_core/` | Contratos y trazabilidad puros del worker/cliente | ❌ |
| `tools/metrics.py`, `check_quality.py` | Línea base AST, reglas de dependencia, tests puros y vigencia del índice | ❌ |
| `tools/gen_index.py` | Genera y comprueba el índice de las fuentes mediante AST | ❌ |
| `installation_lock.py` | Bloqueo entre procesos para impedir dos instalaciones a la vez | ❌ |
| `workflow_history.py` | Ctrl+Z reversible: checkpoints `.blend` y arrays deduplicados en disco | ✅ |
| `ui_style.py`, `icon_manager.py`, `glyph_library.py` | Estilo de la UI, iconos y glifos para grabar texto | ✅ |

### 4.2 Orquestación clínica: `core.py`

| Zona | Qué contiene |
|---|---|
| Constantes al inicio | Constantes de rutas (`ROUTE_*`) y etapas (`STAGE_DICOM/ALIGNMENT/DSG`) |
| `infer_stage`, `set_stage`, `stage_is` | En qué etapa está la escena |
| `reconcile_workflow_after_undo`, `dsg_workflow_undo_post` | Reparación del estado tras Ctrl+Z |
| `DSGSuiteSettings` | Propiedades globales: ruta, FDI objetivo, idioma, carpeta del paciente |
| `DSG_SUITE_OT_ChoosePatientFolder`, `_LoadPatientCBCT` | Carpeta del paciente y autodetección de CBCT e IOS |
| `DSG_SUITE_OT_StartSimpleRoute` … `_ConfirmSimpleSTL` | Ruta de implante simple |
| `DSG_SUITE_OT_StartImmediateRoute` … `_ConfirmImmediateModels` | Ruta de implante inmediato: FDI, dientes a extraer y modelos alveolares |
| `DSG_SUITE_OT_PrepareIOSPostExtraction`, `_ConfirmIOSPostExtraction` | Recorte del IOS en los dientes a extraer y cierre local de la malla |
| `DSG_SUITE_OT_BackWorkflow`, `_Restart*` | Navegación hacia atrás y reinicios |
| `DSG_SUITE_PT_Main` | Panel principal con la barra vertical de etapas |
| `external_agent_execution_context`, `reject_external_agent_for_user_gate` | Impiden que un agente MCP salte las confirmaciones clínicas |

### 4.3 DICOM / CBCT: `dicom_module` → `_dicom_parts/`

| Fragmento | Qué hace |
|---|---|
| `00_constants_runtime_dependencies.py` | Constantes, `VolumeRuntime` (estado del volumen en memoria), carga de pydicom, NumPy, SciPy, scikit-image, VTK y SimpleITK, e instalación del runtime DICOM |
| `01_utils_dicom_io.py` | Lectura DICOM: cabeceras, spacing, orientación, descubrimiento y recuperación de series, decodificación y `load_volume` |
| `02_volume_mpr_scene.py` | Previsualización VDB, cortes MPR (axial, coronal, sagital y oblicuo), muestreo de densidad y creación de la escena de visualización |
| `03_updates_segmentation.py` | Callbacks de propiedades (`on_*_change`), umbrales automáticos (Otsu, k-means), máscaras, canal mandibular, islas, huecos y transparencia |
| `04_hybrid_surface_preview.py` | Superficie previa en tiempo real, marching cubes nativo, superficies desde máscara, arcadas simples y **`DICOMWizardProProperties`** (todas las propiedades DICOM) |
| `05_realtime_mpr.py` | Handlers de depsgraph y undo/redo para mantener sincronizados los cortes |
| `06_operators_a.py` | Operadores de importación y navegación, y la vista MPR “segura” en cuádruple panel (`_safe_mpr_*`) |
| `06_operators_b.py` | Operadores de revisión y segmentación, **flujo asíncrono de segmentación** (`_start_async…`, `_poll_async…`, `_finish_async…`), STL DICOM y paso a alineación |
| `07_panels_registration.py` | Paneles `DICOMWIZARDPRO_PT_*` y `register()` / `unregister()` del módulo |

Módulos de apoyo: `minidicom.py` (lector mínimo de reserva), `dicom_probe.py` (prueba de códecs con píxeles sintéticos), `cbct_native_threshold.py` (superficie por umbral a resolución nativa), `anatomy_refine.py` (refinado de superficie guiado por el CBCT).

### 4.4 Motores de segmentación y workers

| Archivo | Qué hace | Blender |
|---|---|---|
| `segmentation_engines.py` | Rutas del runtime, estado de cada motor (`TOTALSEG`, `TOOTHSEG`, `UMAMBA2`), detección de CUDA y lanzamiento del instalador | Importación diferida |
| `segmentation_install_worker.py` | Instalación en proceso aparte: pip con restricciones, descargas, MD5 y verificación | ❌ |
| `runtime_bootstrap.py` | Estado de los motores en la UI, verificación en segundo plano y operadores de instalar, preflight y failtests | ✅ |
| `engine_preflight.py`, `compute_probe.py` | Comprueban en un Python externo los imports, la convolución 3D y la carga de modelos | ❌ |
| `cbct_pipeline_client.py` | Lanzar, consultar, cancelar, validar manifest/run_id, diagnóstico persistente y fallback headless | Importación diferida |
| `cbct_pipeline_worker.py` | **Worker de inferencia**: `run_request()`, `main()`, `infer_*`, normalización compatible y contratos | ❌ |
| `cbct_pipeline_tasks.py` | Postproceso dentro del worker: máscaras compactas, mallas por diente y arcadas simples | ❌ |
| `cbct_surface_meshing.py` | Extracción de superficies multietiqueta y binarias (VTK o scikit-image) | ❌ |
| `cbct_surface_sidecar.py`, `cbct_surface_worker_client.py` | Worker opcional de superficies | ❌ / ✅ |

### 4.5 Dentición CBCT, FDI y suavizado

| Archivo | Qué hace |
|---|---|
| `cbct_dental_module.py` | Crea un objeto por diente a partir del labelmap, etiquetas FDI 3D, corrección de espejo, revisión FDI (aceptar, editar, intercambiar arcadas, marcar ausente) y referencia dental para la alineación |
| `tooth_analysis.py` | Modelo de identidad dental: conversión universal ↔ FDI, arcadas y vecinos. Sin Blender |
| `cbct_post_smoothing.py` | Operadores “Suavizar dientes”: lanzamiento del worker, caché, restaurar originales e informe por diente |
| `cbct_post_smoothing_worker.py` | Worker de suavizado (Windowed Sinc o Surface Nets). Sin Blender |
| `surface_smoothing.py`, `surface_nets_geometry.py` | Algoritmos de suavizado medido y Surface Nets |

### 4.6 Alineación CBCT ↔ IOS: `alignment_module` → `_alignment_parts/`

| Fragmento | Qué hace |
|---|---|
| `00_alignment_core.py` | Detección de modelos, marcadores y zonas, grafos de malla, registro global automático (hipótesis por PCA y desambiguación anatómica) e ICP robusto (Huber, punto a plano) |
| `01_alignment_operators_ui.py` | Evaluación de parches comunes, validación de puntos, operadores `DICP_OT_*` (importar STL, marcar zonas, alinear, revisar, enviar a DSG) y panel `DICP_PT_Main` |

Apoyo: `common_surface_match.py` (superficie común IOS–CBCT en casos inmediatos), `dental_surface_geometry.py` (geometría dental compartida).

### 4.7 Diseño de la guía: `guide_module` → `_guide_parts/`

El flujo de la guía tiene 10 pasos (`STEP_*` en `01_workflow_state_mpr_objects_a.py`):

| Paso | Constante | Etiqueta en la UI |
|---|---|---|
| 0 | `STEP_MODEL` / `STEP_AXIS` / `STEP_BLOCKOUT` | Modelo retentivo |
| 1 | `STEP_IMPLANT` | Planificación de implantes |
| 2 | `STEP_CONTOUR` | Contorno |
| 3 | `STEP_FRAME` | Microtornillo ⚠️ la constante se llama FRAME |
| 4 | `STEP_SLEEVE` | Cilindros |
| 5 | `STEP_IRRIGATION` | Irrigación |
| 6 | `STEP_REINFORCEMENT` | Refuerzos |
| 7 | `STEP_DRILL` | Canales de fresado |
| 8 | `STEP_FINAL_CUT` | Corte final |
| 9 | `STEP_NAME` / `STEP_DONE` | Nombre y exportación |

| Fragmento | Qué hace |
|---|---|
| `00_bootstrap_constants_assets_a/b` | Iconos y **todas las constantes numéricas** (mm, ángulos, tolerancias) de la guía |
| `01_workflow_state_mpr_objects_a` | Pasos, checkpoints por paso, invalidación al cambiar el modelo, visibilidad y MPR centrado en implante o microtornillo |
| `01_workflow_state_mpr_objects_b` | Colecciones DSG, guardas de operadores, borrado seguro de objetos, booleanas y voxel remesh, y blockout pasivo |
| `02_implant_animation_geometry_a` | Eje de inserción, mallas de implante, fresa y microtornillo desde plantillas, y animaciones de fresado, implante y extracción |
| `02_implant_animation_geometry_b` | Control de malla cerrada (manifold), perímetro de la base, cierre de agujeros del escaneado |
| `02_implant_animation_geometry_c` | Cierre de la base del modelo, preflight de booleanas, booleanas exactas, cortadores de fresa y protección de la pared del cilindro |
| `03_blockout_frame_geometry_a` | Diferencias manifold, protección de la inserción de la fresa, análisis de retención y blockout, y utilidades de implantes |
| `03_blockout_frame_geometry_b` | Seguridad entre implantes y entre implante y diente, tubos de emergencia, paralelismo, sellos de irrigación y rutas geodésicas del frame |
| `03_blockout_frame_geometry_c` | Rutas del frame con anchura preservada, curvas TCB y Catmull-Rom, tubos de irrigación, curva de contorno y dibujo en GPU |
| `04_properties_clinical_operators` | **`DSG_Props`** (todas las propiedades de la guía), raycast, medidas sobre el DICOM, grabado del nombre y operadores de los pasos 0–1 |
| `05_frame_microscrews_sleeves_drill` | Frame tubular, microtornillos (anclaje inteligente y soporte), cilindros y ventana lateral |
| `06_irrigation_a` | Geometría de irrigación: arco en C, lumen, venturi, red en Y y equilibrado de boquillas |
| `06_irrigation_b` | Operadores de irrigación (dibujar, enlazar, sellar, confirmar) y simulación visual del flujo |
| `07_reinforcement_animation` | Conectores de refuerzo y animación secuencial de tornillo, fresa e implante |
| `08_export_final_ui_registration` | Grabado del nombre, limpieza de fragmentos, **exportar STL**, corte final booleano, **panel `DSG_PT_Main` y dibujo de cada paso (`_draw_step_*`)**, implante inmediato y `register()` |

### 4.8 Exportación con control de calidad: `guide_export/`

Es el mejor ejemplo de la arquitectura objetivo: separa el núcleo puro del adaptador de Blender.

| Archivo | Qué hace | Blender |
|---|---|---|
| `policy.py` | Umbrales de calidad (configuración pura) | ❌ |
| `mesh_checks.py` | Análisis de malla con NumPy | ❌ |
| `service.py` | Orquesta el control de calidad que usa `DSG_OT_ExportGuideSTL` | ❌ |
| `report.py` | Informe de trazabilidad junto a cada STL | ❌ |
| `blender_adapter.py` | Única frontera con `bpy` | ✅ |

### 4.9 Biblioteca y mapeo dental: `dental_mapping/`

Plantilla de corona → fantasma → paciente. `service.py` es la API de alto nivel. `registration.py` registra superficies; `landmark_*` transfiere y refina puntos de referencia; `anatomic_fit`, `proximal_fit` y `occlusal_fit` hacen el ajuste anatómico, proximal y oclusal; `emergence.py` calcula el perfil de emergencia; `validation.py` hace las comprobaciones fail-fast; `surgical_context.py` orquesta con CBCT e implantes; `library.py` accede a la biblioteca `.blend`; `eoff_core.py` y `mesh_distance_core.py` son puros. Contrato de activos: `dental_assets.py` (puro) y `dental_asset_blender.py` (adaptador).

### 4.10 Módulos auxiliares (contexto clínico, evidencia, estructura, agente)

| Archivo | Qué hace |
|---|---|
| `clinical_core.py` / `clinical_context.py` | Contexto clínico del paciente (puro) y su UI y persistencia para MCP |
| `evidence_core.py` / `evidence_context.py` | Repositorio offline de evidencia científica (`resources/evidence/`) y su UI |
| `frame_structural_core.py`, `frame_fem_core.py` / `frame_structural.py` | Comprobación estructural y FEM del frame (puro) y su adaptador |
| `frame_surface_corridor.py` | Corredores de superficie para el trazado del frame |
| `roadmap_module.py` | Hoja de ruta clínica y puente MCP local |
| `agent_core.py`, `agent_scene_graph.py`, `agent_facade.py` | Runtime del agente local: políticas, grafo semántico de la escena y fachada por capacidades |
| `guide_assets.py` | Carga con verificación de integridad las plantillas binarias de fresa, implante y microtornillo (`resources/guide_assets/*.b85`) |

### 4.11 Tests y recursos

| Ruta | Contenido | Cómo se ejecuta |
|---|---|---|
| `tests_pure/test_*.py` | 20 pruebas: instalador, contratos, worker con motor simulado, trazabilidad y métricas | `python dsg/tools/check_quality.py` |
| `tests_blender/*.py` | 16 scripts: superficies, historial, registro, diagnóstico, estado de motores y ruta inmediata; tienen requisitos distintos | `blender -b --factory-startup --python-exit-code 1 --python dsg/tests_blender/<test>.py -- <carpeta_padre_de_dsg>` |
| `failtests.py` | 11 contratos | Desde Blender: operador `DSG_OT_RunSafetyFailtests` |
| `resources/` | Plantillas, contratos JSON, evidencia y especificación de motores | — |
| `offline_runtime/` | Ruedas de pydicom y códecs para Windows/Python 3.13 y requisitos | — |

---

## 5. ¿Dónde corrijo…?

| Síntoma | Dónde mirar primero |
|---|---|
| El DICOM no abre o faltan cortes | `01_utils_dicom_io.py`: `probe_source`, `_discover_series`, `_recover_image_source`, `_decode_pixel_array`. Avisos `DSG-F301…F304` |
| Spacing u orientación incorrectos | `01_utils_dicom_io.py`: `pixel_spacing`, `slice_spacing`, `image_orientation`, `_orientation_matrix`; `02_volume_mpr_scene.apply_patient_orientation` |
| Los cortes MPR no se actualizan o se desincronizan | `03_updates_segmentation.py` (`on_*_change`, `_refresh_all_aligned_planes`); `05_realtime_mpr.py` |
| La vista de revisión en cuádruple panel se rompe | `06_operators_a.py`: funciones `_safe_mpr_*` |
| **No segmenta o se queda colgado** | Copiar diagnóstico y seguir la etapa/error; después `cbct_pipeline_client.state()` → `cbct_pipeline_worker.run_request()`/`main()` → `infer_*`. Consultar `pipeline.log` local si hace falta, evitando compartir datos del paciente |
| El motor aparece como “no listo” | `segmentation_engines.verify_engine` / `_*_status`; `runtime_bootstrap.component_status` |
| Falla la instalación de motores | `segmentation_install_worker.py` (`install_*`, `_pip`, `_download`); log de instalación en el runtime |
| Va por CPU teniendo GPU | `segmentation_engines.runtime_compute_status`, `_nvidia_driver_present`; fallback en `cbct_pipeline_worker.infer_totalseg` |
| FDI incorrecto o arcadas invertidas | `cbct_pipeline_worker._fdi_to_compat`, `_toothseg_class_to_fdi`, `_translate_totalseg`; `cbct_dental_module.correct_universal_semantics` / `_mirroring`; `tooth_analysis.universal_to_fdi` |
| Dientes con mala malla | `cbct_pipeline_tasks.run_teeth_task`; `cbct_surface_meshing.extract_multilabel_surface`; `cbct_dental_module._prepare_mesh_from_label` |
| Suavizado incorrecto o no reversible | `cbct_post_smoothing.py`, `cbct_post_smoothing_worker.py`, `surface_smoothing.py` |
| La alineación CBCT–IOS falla | `_alignment_parts/00_alignment_core.py`: `_automatic_global_registration`, `_point_to_plane_huber_transform`; validación en `01_…`: `_validate_landmark_geometry` |
| Ctrl+Z deja la escena inconsistente | `workflow_history.py`; `core.reconcile_workflow_after_undo`; `_guide_parts/01_…_a._reconcile_workflow_after_undo`; `05_realtime_mpr.py` |
| Un paso de la guía no deja avanzar | `_guide_parts/01_…_a`: `_workflow_requirement_report`, `_require_workflow_stage`, `_set_workflow_gate` |
| Botón o texto de un paso de la guía | `_guide_parts/08_…`: `_draw_step_<paso>()` |
| Una medida (mm, ángulo, tolerancia) de la guía | `_guide_parts/00_bootstrap_constants_assets_a.py` |
| Booleana fallida o malla no manifold | `_guide_parts/02_…_c` (`apply_boolean_*`, `run_boolean_preflight`); `03_…_a` (`apply_difference_manifold_checked`) |
| Problemas de irrigación | Geometría: `_guide_parts/06_irrigation_a.py`. Operadores y UI: `06_irrigation_b.py`. Rutas: `03_…_c` |
| Microtornillos o frame | `_guide_parts/05_frame_microscrews_sleeves_drill.py`; rutas del frame en `03_…_b/c` |
| La exportación STL se bloquea | `guide_export/service.py` y `policy.py`; operador `DSG_OT_ExportGuideSTL` en `_guide_parts/08_…` |
| Mensaje de error o código `DSG-E###` | `error_handling.CATALOG`; errores de contrato por etapa en `pipeline_core/contracts.py` |
| Manifest rechazado o resultado de otro job | `pipeline_core.ResultManifest`; `cbct_pipeline_client.state()` / `consume_manifest()` |
| No se puede copiar diagnóstico | `DSG_OT_CopyPipelineDiagnostic`, `cbct_pipeline_client.diagnostic_text()`, `pipeline_core/trace.py` |
| El addon no carga o da error al recargar | `__init__.py`: `_validate_installation`, `_load_modules`, `_quiesce_legacy_handlers`; `lifecycle.py` |

---

## 6. Mantenimiento del mapa y del código

Estas recomendaciones describen cómo mantener esta documentación; no son instrucciones del usuario ni una afirmación de que toda la deuda heredada esté resuelta.

1. Buscar el `bl_idname` o símbolo en el índice y seguir sus llamadas desde `execute()`; en los fragmentos buscar en toda la carpeta antes de cambiar nombres.
2. Mantener los contratos puros sin dependencias de Blender. Los workers deben poder ejecutar sus tareas en el Python del runtime.
3. Al corregir fallos, usar errores por etapa y códigos estables; registrar fallbacks previstos. El ratchet impide aumentar las capturas amplias o silenciosas según su definición AST, pero no elimina automáticamente las existentes.
4. Ejecutar `python dsg/tools/gen_index.py dsg --write` después de cambios y `python dsg/tools/check_quality.py` antes de empaquetar. La comprobación falla si el índice quedó obsoleto o si empeoran las métricas.
5. Ejecutar las pruebas Blender afectadas con el runtime necesario. Los scripts de motores dependen de instalaciones/pesos reales; un test con FakeEngine no acredita inferencia clínica. Los failtests se invocan desde su operador, no desde una herramienta inexistente.
6. Al añadir un archivo obligatorio, revisar `_validate_installation()` y el manifest de build. Actualizar este mapa si cambian responsabilidades; regenerar el índice si cambia cualquier fuente productiva.

## 7. Evaluación del ZIP de referencia y límites actuales

El mapa recibido es una buena guía de navegación: divide las tres etapas, explica correctamente el namespace compartido de los fragmentos y sigue la frontera cliente/worker. Se conserva ese enfoque. Su índice era una instantánea de 9.10.9 y no debe usarse como referencia de líneas para 9.10.11.

Correcciones incorporadas:

- El bootstrap actual importa `bpy` de forma diferida y el núcleo `pipeline_core` se importa fuera de Blender. La advertencia de que ningún módulo `dsg.x` se puede importar ya no describe esta entrega.
- El pipeline incorpora contratos, `run_id` y diagnóstico persistente; el mapa anterior no los incluía.
- Hay 20 pruebas puras y 16 scripts Blender, no solo las seis del instalador y once scripts de la instantánea. Esto cuenta casos unitarios y archivos respectivamente; no implica que todos los motores reales se hayan ejecutado.
- El índice nuevo incluye métodos y definiciones anidadas. Detecta cambios por una huella del conjunto de fuentes y no usa la ausencia de un import directo como prueba de pureza.
- Se corrigió el comentario del bootstrap que citaba `tests_pure/test_version_ssot.py`, inexistente. La comprobación de versión en registro y las pruebas Blender siguen siendo las referencias disponibles.

Deuda y diferencias que siguen siendo reales:

- `docs/ERROR_FALLBACK_FAILTEST_POLICY.md` era una política aspiracional: citaba `tools/run_failtests.py`, que no existe, y prometía cero capturas silenciosas. Se aclara su alcance y el comando disponible. `failtests.py` no ejecuta el ratchet de métricas.
- El ratchet actual cuenta 1768 capturas amplias, 164 capturas silenciosas de una sentencia, 95 declaraciones global, 1332 usos de getattr/hasattr, un exec y 126 imports Blender fuera de una carpeta llamada blender. Los valores de 217 silenciosos/936 DEBUG del ZIP usan otra clasificación o instantánea; no se presentan como métricas actuales. La línea base y la metodología están en `tools/metrics_baseline.json` y `tools/metrics.py`.
- `STEP_FRAME` sigue nombrando el paso de microtornillos en la UI.
- El registro lazy y el listado de instalación no son inventarios completos de dependencias. Los nuevos archivos `pipeline_core` se añaden al control de instalación; los consumidores importan otros módulos auxiliares.
- Persisten fragmentos ejecutados con `exec`, RUNTIME y registros globales; no se han sustituido por sesiones de escena ni adaptadores independientes para cada motor. Ver [ARCHITECTURE_RATCHET.md](ARCHITECTURE_RATCHET.md).

## 8. Ctrl+Z y suavizado: puntos de mantenimiento

`workflow_history.py` integra checkpoints del flujo con el undo nativo. El suavizado prepara el resultado en un worker y publica la geometría en Blender; los callbacks asíncronos necesitan inicio, commit y cancelación del historial. También se restauran estados DICOM y dependencias externas a la malla. Revisar `test_async_smoothing_undo.py`, `test_all_stage_history.py`, `test_modal_history.py`, `test_history_beyond_native_limit.py` y `test_mpr_image_history.py` al cambiar esos recorridos.

El historial archivado requiere modo Object y una única escena; Edit y varias escenas usan el historial nativo. Instalar paquetes o exportar archivos externos no se deshace con Ctrl+Z. La recuperación no recrea estados anteriores a la instalación de esta función. Los checkpoints y arrays se guardan en `scripts/dsg_history`; ver el README antes de mover un caso a otro equipo.

Los algoritmos de suavizado y sus parámetros no se cambian por añadir este mapa. La geometría suavizada y la original se gestionan en `cbct_post_smoothing.py`; el cálculo vive en `cbct_post_smoothing_worker.py`, `surface_smoothing.py` y `surface_nets_geometry.py`.
