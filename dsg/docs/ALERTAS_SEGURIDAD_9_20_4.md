# Alertas de contacto · DSG 9.20.4

Al detectar contacto del cilindro de seguridad con un diente vecino aparece **ALERTA DE SEGURIDAD**, con el número FDI de los dientes afectados. El panel conserva un botón rojo **CONTACTO DE SEGURIDAD**, que permite volver a consultar los contactos. Otros obstáculos conservan su nombre identificador. El halo recibe un color de aviso; su visualización depende del modo de color de la vista de Blender.

La ventana espera a que terminen los controles modales, incluidos **R** y **G**. No se repite para el mismo conjunto de contactos mientras persistan. Al resolverlo se elimina el aviso del panel y se permite que un contacto posterior avise de nuevo. No se calculan colisiones desde el dibujado del panel: se utilizan los resultados del comprobador diferido, conservando la mejora de rendimiento de 9.20.3.

Puedes cerrar la ventana y continuar ajustando el implante. La confirmación y la exportación siguen comprobando y bloqueando una posición inválida. Esta revisión no cambia los márgenes ni la geometría del caso.

Verificación: prueba Blender del etiquetado FDI, espera durante controles modales, ausencia de avisos duplicados, resolución y reentrada. También se vuelve a comprobar la prueba de movimiento nativo y los controles de confirmación/exportación. La documentación de 9.20.3 conserva las medidas de rendimiento y limitaciones del paquete base experimental.
