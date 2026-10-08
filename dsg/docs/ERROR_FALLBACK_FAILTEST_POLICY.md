# DSG 9.10.0 · Política de ERROR, FALLBACK y FAILTEST

## Tres conceptos distintos

**ERROR** significa que DSG no puede garantizar un resultado coherente y detiene la acción. El usuario recibe un código estable `DSG-E###`, una explicación corta y una acción concreta. La excepción Python cruda no se muestra en la interfaz.

**FALLBACK** significa que la ruta preferida falló pero existe una alternativa explícitamente admitida. El proceso puede continuar, pero el evento debe quedar visible y registrado como `DSG-F###`. Un fallback nunca debe disfrazarse de ejecución normal.

**FAILTEST** es una prueba diseñada para hacer fallar el build cuando se rompe un contrato de seguridad. No recupera nada y no modifica casos clínicos. Su trabajo es detectar el problema antes de que llegue al usuario.

## Fallbacks críticos actuales

| Código | Ruta preferida | Fallback | Efecto esperado |
|---|---|---|---|
| `DSG-F201` | CUDA | CPU | mismo motor seleccionado, más lento |
| `DSG-F210` | Python directo | Blender 5.2 headless | mismo worker en proceso aislado |
| `DSG-F220` | child worker | supervisor | misma tarea numérica, ejecución inline |
| `DSG-F230` | motor geométrico preferido | alternativa validada | revisar quality gate final |

## Reglas de mensajes

1. Cada error terminal tiene código estable.
2. El texto al usuario explica **qué pasó + qué hacer**.
3. Nunca se muestra `str(exc)` directamente como mensaje principal.
4. Paths, correos e identificadores largos se redactan en la nueva infraestructura de logging.
5. Los datos del paciente no son material de diagnóstico técnico y no deben entrar en logs.
6. Un fallback debe persistir en el manifiesto cuando afecta al pipeline.
7. Un error inesperado termina en `DSG-E900`, no en silencio.

## Objetivos de failtests y comprobaciones disponibles

La lista siguiente recoge objetivos de la política; no certifica que todos estén implementados. `tools/run_failtests.py` no existe en esta entrega. `failtests.py` se ejecuta mediante `DSG_OT_RunSafetyFailtests` en Blender; la verificación real de motores requiere runtime y pesos disponibles. El comando `python dsg/tools/check_quality.py`, desde la carpeta padre del addon, comprueba métricas, dependencias de `pipeline_core`, pruebas puras y vigencia del índice. No instala ni verifica los pesos de los motores.

Objetivos:

- versión SSOT;
- contrato Blender 5.2;
- registro y verificación real de los tres motores de segmentación;
- catálogo de códigos;
- reducir las capturas silenciosas sin introducir nuevas regresiones; el ratchet aún permite la deuda existente, no garantiza cero;
- trazabilidad de fallbacks críticos;
- ausencia de `subprocess(..., shell=True)`;
- presencia de documentación/herramientas de seguridad.

Todo bug de producción corregido debe añadir un test de regresión. Si el bug puede volver por una modificación estructural, debe añadirse además un failtest de contrato.
