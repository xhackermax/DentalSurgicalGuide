# Un solo botón de mejora — DSG 9.15.3

En la primera revisión después de segmentar aparece una única acción: **MEJORAR DIENTES**. No se repite en el panel DICOM ni en el de alineación.

El botón prepara los dientes disponibles, utiliza el refinado contra el CBCT si el volumen y las etiquetas originales están cargados, repara con remesh únicamente las superficies que no estén cerradas y calcula el acabado con el worker existente. Los parámetros se eligen internamente: no muestra selectores de suavizado, tamaño de vóxel, mejora del diente activo ni botones adicionales de resultados/restauración.

Durante el cálculo, el mismo botón cambia a **CANCELAR MEJORA**. Al terminar desaparece y queda un texto de estado. No aparece en selección de dientes para extracción, revisión de arcadas inmediata, alineación ni diseño de la guía. La ruta simple usa la misma acción para sus arcadas, sin inventar identidades FDI.

Una nueva segmentación restablece su disponibilidad en esa primera revisión. Si se cancela o falla, conserva los datos anteriores y permite reintentar. Si se avanza mientras calcula, cancela el trabajo antes de preparar las referencias de alineación. Un resultado de un paso anterior no se aplica en el siguiente.

Conserva nombres, identidades dentales y transformaciones, así como la malla CBCT original usada por la alineación numérica. Los resultados que no pasan los controles de acabado conservan su geometría anterior. No inicia otra inferencia ni certifica un aumento de precisión anatómica.

Esta actualización mantiene la edición manual del IOS, el cierre cóncavo y la booleana del diente CBCT inmediatamente después de ese cierre en la ruta de implante inmediato.
