# DSG 9.21.16 · Barra de inclinación del MPR del implante

Selecciona un implante o su control de emergencia. En su revisión MPR aparece **Inclinación MPR**, con recorrido de −180° a +180°. La barra gira el plano radiográfico alrededor del eje longitudinal del implante. El corte sigue pasando por ese eje; no mueve ni inclina el implante.

El ángulo se expresa respecto a la orientación base mesiodistal o vestibulolingual. Cambiar entre estas dos orientaciones restablece el ajuste a 0°. Cada plano conserva su propio valor al cambiar de implante y al guardar/abrir el .blend. Los planos existentes se incorporan sin cambiar su orientación inicial.

El ajuste actualiza la geometría del plano inmediatamente y solicita el recálculo de su imagen con una espera de 0,12 s para agrupar cambios. Necesita el CBCT cargado para actualizar la imagen; si falta, conserva el aviso de CBCT no cargado. No repite la segmentación.

El marco permanece gris neutro, sin selector de color ni botón Rehacer. Se mantienen los controles de visibilidad y la orientación base. Los colores anatómicos no se modifican.

Verificación: prueba en Blender con dos implantes y planos independientes, ángulos entre −180° y +180°, eje contenido en el corte, centro alineado, posición del implante invariable, regreso a 0°, recálculo solicitado y persistencia al guardar/abrir un archivo sintético. Una prueba falló antes de implementar la propiedad y pasó después.

Este ajuste es visual y no modifica los cálculos ni las limitaciones de seguridad previamente documentados. El paquete conserva su carácter experimental.
