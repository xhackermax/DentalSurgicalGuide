# DSG 9.22.24: protección de deshacer

Antes de Ctrl+Z o rehacer, DSG detiene la búsqueda del optimizador, cancela sus temporizadores y libera las referencias temporales a la escena. No modifica las mallas dentro de esa preparación.

La limpieza de propuestas restauradas y la reconstrucción de la vista se realizan después, consultando de nuevo los objetos que Blender acaba de restaurar. Una propuesta pendiente se descarta sin aplicarse al implante original.

Se añade una prueba que detectaba temporizadores activos durante deshacer y ahora comprueba su cancelación, la liberación de referencias y la recuperación posterior. Las pruebas con una copia del caso incluyen deshacer y rehacer con ventana.

El cierre nativo registrado en `deg_eval_copy_is_expanded / build_empty_object` no se ha reproducido exactamente. Esta versión corrige riesgos comprobados en la integración con deshacer; no demuestra por sí sola que todas las causas de ese cierre estén resueltas.
