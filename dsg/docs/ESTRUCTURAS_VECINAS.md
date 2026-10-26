# Estructuras vecinas y seguridad · DSG 9.15.9

La planificación mantiene dos funciones independientes para los dientes CBCT:

- **Extracción / booleana:** los FDI fijados con FIJAR DIENTES en la ruta inmediata. Se utilizan para modificar el IOS y no se muestran como dientes que permanecerán en boca.
- **Vecinos protegidos:** las otras mallas dentales segmentadas, incluidas sus raíces. Sirven de referencia visual y se comprueban frente al cilindro completo de seguridad del implante.

En planificación de implantes, pulsa **ELEGIR DIENTES VECINOS**. Aparece una lista por FDI con casillas para elegir qué vecinos visualizar. **MOSTRAR TODOS LOS VECINOS** recupera la visualización de todos los dientes conservados. La elección se guarda con la escena y no modifica los FDI de extracción, la booleana ni la geometría de las raíces.

Ocultar un vecino despeja la vista, pero no elimina su segmentación ni desactiva su comprobación de contacto. Esta separación evita que una preferencia de visualización deje una raíz sin protección. Se utilizan las mallas CBCT disponibles, no representaciones ficticias de las raíces.

En planificación inferior se mantienen visibles los nervios mandibulares segmentados, incluso si están separados en objetos izquierdo y derecho. Todos esos objetos participan en la comprobación del cilindro invisible. Si no hay una segmentación del nervio, la interfaz indica que falta: la herramienta no inventa ni genera el nervio por cambiar de etapa.

El halo visible conserva su altura de **2 mm**. El cilindro oculto abarca la longitud completa del implante y los márgenes de seguridad, y comprueba dientes conservados, otros implantes y los nervios disponibles. Las comprobaciones existentes de distancia exacta entre implante y dientes también se mantienen.

Al regresar a la planificación desde otro paso, DSG restaura la selección de raíces visibles y los nervios. Una nueva segmentación reinicia la selección de vecinos para evitar trasladar preferencias a un conjunto de estructuras diferente.

Las pruebas incluyen tres FDI con roles distintos, dos canales mandibulares, visualización selectiva y contacto con una raíz oculta, utilizando geometrías sintéticas en Blender.
