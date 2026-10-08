# Mejoras de DSG 9.10.11

Actualización: 8 de octubre de 2026. La rama anterior publicaba 9.7.5; el paquete recibido contiene 9.10.11. Conviene distinguir las novedades de esta revisión de los cambios acumulados.

## Novedades específicas de 9.10.11

| Mejora | Cómo funciona | Beneficio |
|---|---|---|
| Contratos de entrada | Valida dimensiones, dtype, spacing y metadatos de calibración antes de procesar | Localiza datos incompatibles en su etapa |
| Contrato de etiquetas | Comprueba el labelmap; conserva dientes 1–32, mandíbula 53, maxila 54 y canal 55 | Evita interpretar anatomía como dientes |
| Manifest versionado | Cliente y worker exigen `schema_version=1` y el mismo `run_id` | Rechaza resultados de otra ejecución o protocolo |
| Diagnóstico persistente | Guarda etapas, duración, estado y fallbacks de lanzamiento/CUDA | Permanece después de limpiar temporales |
| Copiar diagnóstico | Recupera el informe estructurado desde DICOM | No copia peticiones privadas ni logs libres |
| Núcleo comprobable | `pipeline_core` permite pruebas fuera de Blender | Detecta fallos de datos sin abrir la interfaz |
| Control de deuda técnica | Compara métricas con una referencia que no se actualiza automáticamente | Impide aceptar regresiones regenerando la línea base |
| Índice de código generado | Inventario AST de funciones, clases y operadores con líneas reales | `--check` detecta un índice obsoleto |

El recuento publicado baja de 1775 a 1768 capturas amplias de excepciones y de 170 a 164 capturas silenciosas; las otras métricas no aumentan respecto a la referencia incluida. Es un análisis automático, no una revisión manual de cada excepción.

La normalización no recorta una etiqueta inválida convirtiéndola en diente. Los contratos tampoco presuponen HU absolutos para todos los CBCT.

## Cambios acumulados de la serie 9.10

- **9.10.0–9.10.1:** selección TotalSegmentator/ToothSeg/U-Mamba2, worker externo, salida normalizada y restauración de tres operadores DICOM con prueba de registro.
- **9.10.2–9.10.4:** reparaciones de instalación Windows, checkpoints, codecs DICOM, comprobaciones CUDA y acceso a SciPy del runtime privado. La disponibilidad depende del entorno instalado.
- **9.10.5–9.10.9:** suavizado reversible bajo demanda, cálculo externo, cancelación, caché y restauración con DIENTES ORIGINALES. La referencia numérica de alineación se conserva.
- **9.10.9–9.10.10:** historial de segmentación, alineación y etapas DSG. Recupera geometría, propiedades, FDI, etiquetas y máscaras; cancela pendientes y evita avanzar automáticamente después de Ctrl+Z.

## Límites

9.10.11 no cambia los modelos ni acelera por sí sola la inferencia. No sustituye los fragmentos DICOM ni todo el estado global por sesiones de escena. U-Mamba2 requiere un entorno compatible y un checkpoint final; los pesos SSL no bastan.

**Fiel a la segmentación / Surface Nets** sigue experimental: conserva originales si un diente o su grupo de contacto falla los controles. No ofrece una garantía general de ausencia de autointersecciones ni solapamiento cero. Véanse [manual](MANUAL_9_10_11.md), [pruebas](VERIFICACION_9_10_11.md) y [futuras mejoras](FUTURAS_MEJORAS.md).
