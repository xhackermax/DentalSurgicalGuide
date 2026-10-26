# DSG 9.22.2 · Cerrar agujeros

El botón podía mostrar `NameError: name _progress is not defined` después de procesar la malla, antes de completar la comprobación de anatomía. La referencia al indicador de progreso estaba importada dentro de otra función, por lo que no estaba disponible en esta ruta. La copia parcial podía quedar en la escena aunque la operación se anunciara como fallida.

Se importa el módulo de progreso localmente en `close_scanned_model_holes` y `_close_open_model_volumetric`, las dos funciones que lo utilizaban sin definirlo. No se modifica el algoritmo de cierre ni se relajan las comprobaciones geométricas.

La regresión se reprodujo antes del cambio y se verificó después en Blender: cierre real de un agujero secundario en un modelo sintético, abertura basal conservada, anatomía original preservada, segundo pase sin agujeros adicionales y resolución de la dependencia de progreso en el comienzo de la ruta volumétrica. Esta última prueba no equivale a validar toda la reconstrucción volumétrica.

Para usarlo, pulsa CERRAR AGUJEROS en el modelo alineado y continúa con el cierre basal habitual. Los agujeros secundarios y la abertura basal se tratan en pasos distintos. El carácter experimental de DSG se conserva.
