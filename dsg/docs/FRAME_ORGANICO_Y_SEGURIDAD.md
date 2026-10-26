# Frame orgánico y cilindro invisible · DSG 9.15.5

## Frame

CREAR ESTRUCTURA utiliza el recorrido calculado sobre el modelo retentivo, en el orden de los puntos marcados. Los puntos del usuario, una vez proyectados a la superficie, son obligatorios y no se eliminan durante el suavizado.

La curva final es una Bézier cúbica con tangentes calculadas desde Catmull–Rom centrípeto. No se encadenan dos suavizados independientes. Se añaden controles donde la curva se aparta del recorrido o alarga excesivamente un tramo. El corredor permitido es de 0,04–0,15 mm según el radio del frame y la longitud evaluada de cada tramo no supera el 105 % de su referencia. Estas tolerancias conservan una proximidad controlada a la ruta; no implican que cada punto de la Bézier coincida exactamente con la superficie triangulada.

El radio del barrido permanece constante, incluido el paso por cada punto marcado. No se afina la sección para conseguir suavidad. La booleana final puede modificar la sección de la guía y conserva sus comprobaciones propias de exportación.

No se añade ningún botón: se sigue usando CREAR ESTRUCTURA.

## Halo de seguridad

El halo visible tiene **2 mm de altura**, orientados según el eje del implante, y se sitúa alrededor de su plataforma coronal. Conserva el radio correspondiente a la separación de seguridad.

Un segundo cilindro permanece oculto y sin selección. Su altura abarca la longitud completa del implante más el margen en ambos extremos; su radio incluye el margen de seguridad. Mover el implante mueve ambas representaciones.

La comprobación del cilindro completo incluye:

- Otros implantes de la escena.
- Dientes CBCT individualizados que se mantienen en boca.
- El nervio mandibular segmentado cuando está presente.

En la ruta inmediata, los FDI fijados para extracción se excluyen del conjunto de dientes conservados: permanecen como referencias del caso, pero su extracción está prevista en el flujo.

La intersección comprueba las caras triangulares, no solo sus vértices, e incluye el caso de un cilindro completamente contenido dentro de una malla cerrada. La confirmación de implantes se bloquea si encuentra contacto o si no puede verificar una geometría consultada. Las comprobaciones anteriores de distancia entre implantes y distancia exacta a dientes permanecen activas.

Durante la planificación, después de disponer de una posición libre de contacto, un movimiento que introduce colisión vuelve a la última posición libre conocida. Si un implante nace en una posición conflictiva, debe desplazarse a una libre antes de disponer de esa referencia de retorno. La comprobación de confirmación se ejecuta siempre, también al reabrir un caso.

Estas comprobaciones dependen de las estructuras disponibles en la segmentación. Las pruebas de esta versión utilizan geometrías sintéticas en Blender; no constituyen una evaluación clínica con un CBCT de paciente.
