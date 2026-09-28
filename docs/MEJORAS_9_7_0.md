# DSG 9.7.0 — Mejoras de calidad, seguridad y mantenibilidad

**Base:** DSG 9.6.8 · **Objetivo:** Blender 5.2 · **Verificado con:** Blender 5.2.2 LTS (módulo `bpy` oficial) y Blender 5.0.1

Este documento recoge qué se ha cambiado respecto a la 9.6.8, por qué, cómo se ha verificado y qué queda pendiente. Sigue las reglas de `AGENTS.md`: especificación, luego implementación, luego tests y prueba real en Blender.

---

## 1. Resumen

| Área | Antes (9.6.8) | Ahora (9.7.0) |
|---|---|---|
| Errores detectados | 4 errores activos | Corregidos, cada uno con su test de regresión |
| Tests | 11 de 33 en rojo; no arrancaban sin Blender | 75 tests en verde con Blender 5.2.2 (66 + 9 omitidos sin Blender) |
| Prueba real en Blender | Manual | Automática: registro, dibujo de paneles, botones e instalación ZIP (add-on clásico y Extension) |
| Exportación STL | Nombre de archivo incorrecto; solo se comprobaba el sólido cerrado con sellos | Control de calidad completo e informe de trazabilidad JSON |
| Errores silenciados | 951 `except Exception: pass` | 0 silenciosos: todos se registran con traza completa |
| Logging | 0 usos de `logging`, 209 `print` | Logger `dsg.*` con archivo rotativo |
| Token del puente MCP | Se guardaba dentro del `.blend` | Solo en memoria del proceso |
| Plantillas 3D | ~700 KB en base85 dentro del código | Archivos en `resources/` verificados con SHA-256 |
| Paquete instalable | 134 changelogs y los tests dentro del add-on | Solo código y recursos; documentación en `docs/` |
| IDs de operador | Con versión (`_v968`, `_v955`), origen del botón muerto | Estables |
| Instalación como Extension | Imposible (dependía de `bl_info`) | Probada en Blender 5.2.2 |

---

## 2. Errores corregidos

### 2.1 La verificación EXACT de distancia implante–diente fallaba siempre

- **Archivo:** `dsg/dental_mapping/surgical_context.py`
- **Causa:** se usaba `np` sin `import numpy as np`.
- **Efecto:** el único modo considerado control definitivo (`hard_gate_eligible`) terminaba siempre en `NameError`. Fallaba de forma segura (no daba un "seguro" falso), pero la verificación exacta no existía en la práctica.
- **Tests:** `test_surgical_context_imports_numpy_for_exact_mode` y `test_surgical_context_module_exposes_np_at_runtime`.

### 2.2 El botón "REPARAR RUNTIME CUDA" no hacía nada

- **Archivos:** `dsg/_dicom_parts/07_panels_registration.py` y `dsg/runtime_bootstrap.py`
- **Causa:** apuntaba a `dsg.install_totalseg_v955`, un operador que no existe. Además, el instalador real no hacía nada si el runtime ya figuraba como listo, así que tampoco habría servido para reparar.
- **Solución:** el botón llama a `dsg.install_totalseg` con `force=True`. Esta nueva propiedad (oculta, `SKIP_SAVE`) salta la comprobación de "listo" y vuelve a extraer el runtime con PyTorch CUDA.
- **Tests:** `test_cuda_repair_button_uses_force_reinstall`, `test_custom_literal_operator_buttons_have_an_implementation` y la prueba en Blender (`tools/blender_smoke.py`), que comprueba que las 98 referencias de operador de la interfaz existen.

### 2.3 El STL se guardaba con otro nombre

- **Archivo:** `dsg/_guide_parts/08_export_final_ui_registration.py`
- **Causa:** `wm.stl_export(..., use_batch=True)`. En modo batch, Blender añade el nombre del objeto al archivo.
- **Evidencia en Blender 5.2:** se pedía `DSG_Guide_caso.stl` y se escribía `DSG_Guide_casoDSG_ExportGuide_Work.stl`, mientras el mensaje decía que se había exportado con el nombre pedido.
- **Solución:** `use_batch=False`, y `batch_mode='OFF'` en la ruta de compatibilidad.
- **Tests:** `test_guide_export_does_not_use_batch_mode`, y `test_guide_export_kwargs_write_exact_filename`, que reproduce la llamada exacta en Blender.

### 2.4 Etiquetas FDI que nunca se ocultaban

- **Archivo:** `dsg/core.py`
- **Causa:** se usaba `cbct_dental_module` sin importarlo, y un `try/except` ocultaba el `NameError`. Las etiquetas del arco no usado seguían visibles durante el alineamiento.
- **Test:** `test_no_undefined_names_in_standalone_modules` (ruff F821 sobre todo el paquete).

### 2.5 Submódulos que se resolvían como `None` (encontrado al reparar los tests)

- **Archivo:** `dsg/__init__.py`
- **Causa:** el paquete declaraba `dental_assets = None`, `tooth_analysis = None`, etc. Con eso, `from . import dental_assets` devolvía `None` en lugar del módulo si se importaba fuera del orden de `register()`. Por eso fallaban 8 tests.
- **Solución:** se eliminan esos marcadores y se añade un `__getattr__` (PEP 562) que importa el submódulo a demanda. `_loaded(name)` consulta sin importar.
- **Test:** `test_package_does_not_shadow_submodules_with_none`.

---

## 3. Control de calidad y trazabilidad de la exportación

Es un nuevo paquete, `dsg/guide_export/`, integrado en `DSG_OT_ExportGuideSTL`.

### 3.1 Qué se comprueba

| Comprobación | Método | ¿Bloquea? | Cómo saltarla |
|---|---|---|---|
| **Piezas sueltas** (antes de la limpieza existente) | Componentes conexos y volumen con signo de cada pieza | Sí, si alguna pieza que se eliminaría supera 0,5 mm³ o 2000 caras (por ejemplo, un casquillo que perdió su conector) | Casilla "Confirm removal of detached pieces" |
| **Sólido cerrado** | Cada arista compartida por exactamente 2 triángulos, orientación coherente, sin triángulos degenerados | Sí | Casilla "Allow non-closed mesh" (desaconsejado) |
| **Grosor de pared** | Hasta 20.000 rayos desde el centro de las caras hacia dentro (BVH). Mínimo, percentiles 1 y 5, mediana y los 5 puntos más finos | No (aviso). Umbral configurable, 1,0 mm por defecto | Casilla "Check wall thickness" |
| **Distancia implante–conducto mandibular** | BVH: intersección exacta de triángulos y distancia bidireccional vértice–superficie (cota superior ajustada) | No (aviso). Margen configurable, 2,0 mm por defecto | — |
| **Resumen geométrico** | Triángulos, volumen y caja envolvente en mm | Informativo | — |

La distancia al conducto mandibular es una comprobación nueva: la 9.6.8 no calculaba en ningún sitio la distancia entre el implante y el conducto.

Rendimiento medido en Blender 5.2.2: todas las comprobaciones sobre una malla de 327.680 triángulos tardan unos 1,5 s.

### 3.2 Informe de trazabilidad

Al lado de cada STL se escribe `<nombre>.dsg-report.json` (esquema `dsg.guide_export_report.v1`, escritura atómica). Incluye:

- Versiones de DSG, Blender, Python y la plataforma.
- Caso y carpeta del paciente.
- **Entradas:** ruta y SHA-256 del DICOM (archivo o carpeta completa) y del escaneo intraoral (STL), y métricas del alineamiento (RMSE de landmarks, error, solapamiento y p95 del ICP).
- **Parámetros del plan:** casquillo, fresa, alivio, retención, márgenes.
- **Implantes:** FDI, diámetro, longitud, plataforma, eje y centro del casquillo.
- **Comprobaciones:** estado global PASS/WARN/FAIL y las métricas de cada una.
- SHA-256 del STL exportado.
- Aviso de responsabilidad clínica.

Si el informe no puede escribirse, el mensaje final lo dice claramente ("REPORT NOT WRITTEN"): nunca falla en silencio.

### 3.3 Diseño SOLID

```
DSG_OT_ExportGuideSTL  (operador: interfaz y flujo de la transacción)
        │  usa
        ▼
service.ExportGate     (orquesta; depende de abstracciones inyectables)
   │            │                 │
   ▼            ▼                 ▼
mesh_checks   report          blender_adapter   ← único módulo con bpy
(NumPy puro)  (JSON puro)     (arrays, BVHRayCaster, distancias, lectura del plan)
   ▲
policy.ExportPolicy (umbrales inmutables y validados)
```

- **S (responsabilidad única):** cada módulo hace una sola cosa. `policy` configura, `mesh_checks` mide, `report` documenta, `blender_adapter` traduce desde Blender, `service` orquesta.
- **O (abierto/cerrado):** una comprobación nueva es una función más que devuelve `CheckResult`. No hay que tocar las existentes ni el formato del informe.
- **L (sustitución de Liskov):** `NumpyRayCaster` (tests) y `BVHRayCaster` (Blender) cumplen el mismo protocolo `RayCaster` y son intercambiables. Un test comprueba que dan el mismo resultado.
- **I (segregación de interfaces):** `RayCaster` expone un solo método `cast()`. `ExportGate` recibe tres funciones pequeñas (`arrays`, `caster_factory`, `clearance`) en lugar de un objeto grande.
- **D (inversión de dependencias):** `ExportGate` depende de esas abstracciones. Las implementaciones de Blender se inyectan por defecto y los tests inyectan versiones puras.

Lo mismo se aplica a `dsg_logging.py` (solo configuración de logs) y a `guide_assets.py` (solo carga y verificación de plantillas).

---

## 4. Observabilidad: logging en lugar de errores silenciados

- **`dsg/dsg_logging.py`:** logger raíz `dsg` con archivo rotativo (5 MB × 3) en `<scripts de usuario de Blender>/dsg_logs/dsg.log` y consola a partir de WARNING. Es idempotente: no duplica handlers al volver a registrar el add-on, y se configura y retira en `register()`/`unregister()`.
- **`tools/codemod_log_suppressed.py`:** transforma los 951 `except Exception: pass` en `_DSG_LOG.debug("suppressed exception", exc_info=True)`. No cambia el comportamiento, pero ahora cada fallo tolerado queda con su traza completa.
- **Nivel DEBUG:** para registrar esos fallos, arrancar Blender con `DSG_LOG_LEVEL=DEBUG`. `DSG_LOG_DIR` cambia la carpeta.
- **Regla permanente:** `test_no_silent_broad_except_pass_left` impide que vuelva a aparecer un `except Exception: pass`.

---

## 5. Seguridad del puente MCP

El token de acceso se guardaba en `scene.dsg_roadmap_props.bridge_token`, así que quedaba dentro de cada `.blend` guardado o compartido. Ahora vive solo en la memoria del proceso (`roadmap_module._BRIDGE_TOKEN`), cambia en cada activación y se borra al detener el puente. El test `test_mcp_bridge_token_is_never_saved_in_blend` arranca el puente en Blender, guarda un `.blend` y comprueba que el token no aparece en sus bytes.

---

## 6. Mantenibilidad y empaquetado

- **IDs de operador estables:**

  | Antes | Ahora |
  |---|---|
  | `dsg_suite.install_engines_core_v968` | `dsg_suite.install_engines_core` |
  | `dsg.install_totalseg_v965` | `dsg.install_totalseg` |
  | `dsg.install_all_totalseg_v955` | `dsg.install_all_totalseg` |
  | `dsg.runtime_preflight_v955` | `dsg.runtime_preflight` |

  El riesgo de ejecutar módulos viejos ya lo cubre la purga de `sys.modules` en `register()`. Un test prohíbe nuevos IDs con sufijo de versión.
- **Versión única:** `dsg/version.py` es la única fuente. Los mensajes de la interfaz y los labels usan `DSG_VERSION_STR` en lugar de "9.6.8" escrito a mano, y un test prohíbe versiones literales en el código. `bl_info` (que tiene que ser literal) se valida contra `version.py`.
- **Plantillas 3D fuera del código:** `resources/guide_assets/*.b85` más `manifest.json` con SHA-256, cargadas por `guide_assets.py`. Si faltan o están dañadas, el add-on se detiene con un mensaje claro (`GuideAssetError`). Los fragmentos `00_bootstrap_*` pasan de ~800 KB a 48 KB.
- **Paquete limpio:**
  - Historial (115 archivos) → `docs/history/`.
  - Especificaciones → `docs/specs/`.
  - Tests → `tests/`.
  - Herramientas → `tools/`.
  - El validador de instalación ya no exige archivos de changelog.
- **`bl_info` corregido:** `blender: (5, 2, 0)` y una descripción real del producto en lugar de una línea de changelog.
- **Compatible con Extensions:** el módulo de guía ya no importa `bl_info` del paquete (Blender lo elimina en las Extensions). `tools/build_addon_zip.py --extension --license <SPDX>` genera `blender_manifest.toml`. Instalación probada en Blender 5.2.2 en ambos modos.
- **Imports sin usar:** se han eliminado 22. Se conservan a propósito:
  - Las reexportaciones públicas de `dental_mapping/__init__.py`.
  - Los imports de verificación de `totalseg_install_worker.py`.
  - Los imports de orden de carga de `roadmap_module.py`.

---

## 7. Tests, CI y puertas de publicación

| Comando | Qué hace |
|---|---|
| `python tools/run_checks.py` | compileall, ruff (reglas de corrección), pytest, prueba en Blender e instalación del ZIP |
| `python tools/blender_smoke.py` | Registra y desregistra 2 veces, comprueba las referencias de operador y dibuja los paneles |
| `python tools/install_smoke.py` | Construye los ZIP y los instala en un perfil aislado (add-on clásico y Extension) |
| `python tools/build_addon_zip.py --out dist` | ZIP instalable, `.sha256` y comprobación de integridad |
| `.github/workflows/ci.yml` | Todo lo anterior en cada push o PR, con `bpy==5.2.2` sobre Python 3.13 |

Para ejecutarlo en local sin Blender instalado:

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install "bpy==5.2.2" pytest ruff numpy scipy
python tools/run_checks.py
```

Sin `bpy`, `tests/conftest.py` sustituye Blender por un stub y omite (no falla) los tests marcados `requires_bpy`.

Tests nuevos:

- `test_regressions_970.py`: errores corregidos, IDs estables, fragmentos sin redefiniciones, validador de instalación.
- `test_guide_export_checks.py`: 13 tests de geometría e informe, sin Blender.
- `test_export_integration.py`: exportación de extremo a extremo en Blender (nombre exacto, piezas sueltas, malla abierta, BVH frente a NumPy, plantillas, token MCP).
- `test_logging.py` y `test_guide_assets.py`.

Resultado final (Blender 5.2.2 LTS):

```
SUMMARY: compileall=PASS, ruff=PASS, pytest=PASS (75), blender_smoke=PASS, install_smoke=PASS
```

---

## 8. Pendiente (no hecho a propósito, con motivo)

1. **Convertir los fragmentos `exec()` en módulos reales** (`_guide_parts`, `_dicom_parts`, `_alignment_parts`).
   - Son unas 1.700 funciones en un mismo espacio de nombres. Hacerlo sin cubrir cada flujo clínico con tests de integración rompería cosas, y `REFACTOR_ARCHITECTURE_9_5_8.md` exige esos tests antes.
   - Ya existen la infraestructura (`blender_smoke`, tests con `bpy`) y una protección (`test_fragments_never_redefine_a_top_level_symbol`).
   - Siguiente paso: extraer primero los dominios con menos dependencias (por ejemplo `07_reinforcement_animation`), cada uno con su test de flujo.
2. **Traducciones con `bpy.app.translations`.** Las unas 500 llamadas `_dw_t(props, en, es)` siguen el selector de idioma propio de DSG (ES/EN/FR), no el de Blender. Migrarlas cambia el comportamiento y necesita decidir antes qué idioma manda.
3. **Revisar uno a uno los 1.799 `except Exception`.** Ya no son silenciosos, pero conviene revisar primero alineamiento, generación de casquillos y booleanos, para que avisen al usuario o se detengan en lugar de solo registrar.
4. **Umbrales clínicos.** Los 1,0 mm de pared y 2,0 mm al conducto son valores por defecto configurables. Deben fijarse según la resina, la impresora y el protocolo de la clínica; si se quiere, `ExportPolicy(block_thin_walls=True)` convierte el aviso en bloqueo.
5. **Licencia.** Para publicar como Extension hace falta elegir una licencia SPDX. El autor debe decidirla (la herramienta la pide explícitamente).
6. **Regulación.** Un software que diseña guías quirúrgicas puede ser producto sanitario bajo el reglamento europeo MDR. El informe de trazabilidad ayuda, pero no sustituye un sistema de gestión de calidad ni la documentación técnica correspondiente.
7. **Distancia al conducto:** es una cota superior basada en vértices. Con mallas del conducto muy poco densas puede sobrestimar la distancia en décimas de mm. Si se quiere un valor exacto, se puede reutilizar el barrido triángulo–triángulo de `mesh_distance_core` (ya usado en el modo EXACT).
