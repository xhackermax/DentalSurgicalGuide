# Dental Surgical Guide — DSG 9.10.11

Complemento de planificación dental y maxilofacial para **Blender 5.2**: importa CBCT/DICOM, prepara anatomía, alinea escaneados intraorales (IOS) y acompaña el diseño y la exportación de guías quirúrgicas.

Esta actualización incorpora el ZIP `DSG_v9_10_11_BLENDER_5_2_PIPELINE_CONTRACTS_DIAGNOSTICS.zip` facilitado por el autor. El código de `dsg/` conserva exactamente el paquete y su manifiesto de hashes. Los documentos 9.6/9.7 permanecen como historial; las guías actuales están enlazadas abajo.

## Descarga e instalación

- [Versión 9.10.11](https://github.com/xhackermax/DentalSurgicalGuide/releases/tag/v9.10.11).
- [ZIP original](releases/v9.10.11/DSG_v9_10_11_BLENDER_5_2_PIPELINE_CONTRACTS_DIAGNOSTICS.zip) y [SHA-256](releases/v9.10.11/DSG_v9_10_11_BLENDER_5_2_PIPELINE_CONTRACTS_DIAGNOSTICS.zip.sha256).
- En Blender 5.2: **Edit → Preferences → Add-ons → Install from Disk**, selecciona el ZIP, activa DSG y abre **N → DSG** en la vista 3D.
- Guarda el caso, cancela trabajos pendientes y reinicia Blender después de sustituir una versión anterior. Inicia una ejecución nueva.

**Los pesos IA no están incluidos.** En DICOM, **INSTALAR / REPARAR MOTORES** prepara el entorno y **REVISAR** comprueba su disponibilidad. READY exige código, dependencias y checkpoints válidos. U-Mamba2 requiere Linux/CUDA y un checkpoint final ToothFairy3; esta versión no ofrece instalación nativa Windows para ese motor.

## Documentación

| Necesidad | Documento |
|---|---|
| Qué mejora y qué cambios vienen de versiones anteriores | [Mejoras](docs/MEJORAS_9_10_11.md) |
| Instalación, motores, segmentación, alineación, guía y resolución de problemas | [Manual de instrucciones](docs/MANUAL_9_10_11.md) |
| Cómo se comunican Blender, workers, resultados y diagnósticos | [Funcionamiento](docs/FUNCIONAMIENTO_9_10_11.md) |
| Próximas mejoras propuestas y criterios de aceptación | [Hoja de ruta](docs/FUTURAS_MEJORAS.md) |
| Pruebas ejecutadas y limitaciones | [Verificación](docs/VERIFICACION_9_10_11.md) |
| Módulos y símbolos para desarrollo | [Mapa del código](dsg/docs/CODEMAP.md), [índice generado](dsg/docs/CODEMAP_INDEX.md) |

## Novedades principales

9.10.11 valida volumen, spacing, calibración, labelmap y manifest en las fronteras del pipeline. Identifica cada ejecución con `run_id`, rechaza resultados incompatibles y guarda un diagnóstico de etapas, tiempos y fallbacks. **Copiar diagnóstico** permite recuperar ese informe después de limpiar los temporales. Añade pruebas del núcleo y un control que impide empeorar su línea base de deuda técnica.

La actualización desde 9.7.5 también incorpora selección de motores, reparación de operadores DICOM, suavizado reversible bajo demanda e historial Ctrl+Z de segmentación, alineación y etapas DSG. Estos cambios preceden a 9.10.11 y se distinguen en el [changelog](CHANGELOG.md).

Las pruebas de instalación y geometría sintética no establecen la precisión de una segmentación clínica. ToothSeg ofrece dientes/FDI y no sustituye a un motor con maxilares y canal cuando la ruta los exige. Surface Nets sigue experimental y conserva originales cuando rechaza un resultado.

## Desarrollo y comprobaciones

Lee [AGENTS.md](AGENTS.md) antes de modificar código. El alcance sigue siendo dental/maxilofacial y el manifest es el contrato de los resultados del worker.

```bash
python -m pip install numpy
python tools/run_checks.py --no-smoke
python tools/run_checks.py --blender "/ruta/a/blender"
python tools/build_addon_zip.py --out dist
```

Las comprobaciones actuales validan el ZIP original y su correspondencia con el código, compilan el addon, ejecutan sus 20 tests puros y comprueban las métricas y el índice. Con `--blender` se añade instalación/registro y pruebas sin modelos en perfiles aislados.

La prueba geométrica de suavizado requiere VTK compatible con el Python de Blender. Si está en un runtime separado, añade `--vtk-site-packages "/ruta/al/runtime/site-packages"`; no instala ni modifica modelos.

`tests/` conserva la suite histórica 9.7 y **no es la suite de aceptación de 9.10.11**: contiene imports de módulos retirados. `python -m pytest tests` permite auditarla y actualmente falla al recoger cinco módulos; ese resultado no se presenta como aprobado. Su migración está documentada en la hoja de ruta.

```text
dsg/                 contenido exacto del ZIP 9.10.11
  pipeline_core/     contratos y diagnóstico independientes de Blender
  tests_pure/        pruebas actuales sin Blender
  tests_blender/     pruebas actuales con Blender
  docs/              mapa de código y documentación del paquete
docs/                manual actual, novedades, roadmap e historial
tools/               comprobaciones y empaquetado
releases/v9.10.11/    ZIP original y checksum
tests/               suite histórica 9.7 pendiente de migración
```
