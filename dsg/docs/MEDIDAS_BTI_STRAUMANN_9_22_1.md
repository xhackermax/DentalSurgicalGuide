# DSG 9.22.1 · Medidas BTI y Straumann

El optimizador de tamaño incorpora la matriz aportada por el usuario. En **Biblioteca**, elige **BTI CORE-X**, **Straumann Standard Plus** o **Catálogo con mallas reales**. Posición conserva el tamaño y sigue siendo una búsqueda independiente.

## Selección del mayor tamaño admisible

Se evalúan las combinaciones concretas del catálogo, sin crear el producto de todos los diámetros por todas las longitudes. Primero se descartan las opciones que incumplen las restricciones. Entre las que pasan, se elige mayor diámetro y, a igualdad de diámetro, mayor longitud. La puntuación de soporte solo desempata medidas iguales; una puntuación alta no permite ignorar un margen.

El diámetro queda condicionado por los dientes vecinos y el hueso remanente. La longitud queda condicionada por el soporte óseo apical y la separación al seno, cavidad nasal o canal mandibular. El eje y la referencia coronal permanecen fijos durante esta búsqueda; si no hay combinación admisible, es necesario revisar la posición, no reducir automáticamente los márgenes.

Para tamaño se añade una comprobación del volumen del cuerpo dentro del hueso nativo cerrado, con reserva lateral y apical. La reserva usa una expansión conservadora por los ejes locales y una envolvente convexa; puede descartar opciones que una comprobación más precisa admitiera, especialmente en hueso cóncavo o superficies oblicuas. La parte coronal es una frontera libre: en la comprobación de apoyo se excluye una banda numérica de hasta 0,05 mm para admitir una referencia a nivel de la cresta. **Las comprobaciones frente a dientes, seno y nervio utilizan toda la geometría**, sin esa exclusión. Esta prueba geométrica no predice remodelado, calidad ósea ni estabilidad primaria.

## Datos de la matriz

Origen: `matrices_implantes_BTI_COREX_y_Straumann_Standard_Plus.xlsx`.

| Familia | Combinaciones habilitadas | Fuera de la selección automática |
|---|---:|---|
| BTI CORE-X | 45 marcadas ✔ | 39 «Por verificar» y 68 no listadas |
| Straumann Standard Plus | 12 marcadas ✔ | Dos combinaciones de 6 mm con ✔* y 43 no listadas |

Las combinaciones de 6 mm de Standard Plus necesitan confirmar la variante; no se activan por interpretar el asterisco como disponibilidad general. Los diámetros BTI 4,0 y 4,75 mm pendientes tampoco se ofrecen automáticamente. «Listada» significa marcada así en el archivo aportado, no una verificación actual de existencias, referencia comercial o autorización del fabricante.

El JSON incluido conserva el valor original de cada celda, hoja, coordenada y huella del archivo. No se modifica el Excel original.

## Medidas nominales y perfil real

La hoja aporta diámetro y longitud, pero no mallas comerciales, geometría de rosca, cuello ni referencias exactas por variante. Las bibliotecas integradas generan un **cuerpo cilíndrico nominal** circunscrito para preseleccionar medidas. Su referencia superior representa la cima del cuerpo intraóseo. No se presenta como un modelo CAD del fabricante ni como una envolvente certificada del implante completo.

La preselección aparece en alambre y muestra la medida elegida. **No se puede aplicar** con APLICAR PROPUESTA: faltan los perfiles reales y sus referencias cervicales. El bloqueo existe en la interfaz, en la validación del proceso de cálculo y en la aplicación final. La opción **Catálogo con mallas reales** mantiene la previsualización, revalidación y aplicación ya existentes cuando se dispone de un catálogo compatible. No se convierte una malla genérica en un BTI o Straumann cambiando sus medidas.

Esta distinción afecta especialmente a Standard Plus: la documentación oficial describe un cuello liso de 1,8 mm y plataformas RN de 4,8 mm o WN de 6,5 mm, diferentes del diámetro intraóseo. Hace falta identificar la variante y su geometría para comprobar el implante completo. [Descripción oficial Standard Plus](https://www.straumann.com/content/dam/media-center/straumann/en/documents/smart/490.191-Smart1-Standard-Plus-Implant-en.pdf).

## Verificación

Pruebas con la matriz completa, exclusión de medidas pendientes/condicionales y selección por tamaño aunque otra opción tenga más puntuación. En Blender, una escena de ensayo a nivel de la cresta limita el diámetro por hueso y la longitud por un margen de 2 mm a una cavidad: de las 45 medidas BTI elige 4,5 × 7,5 mm. Repetir el obstáculo como canal mandibular mantiene el límite longitudinal; añadir una raíz vecina reduce el diámetro elegido a 3,75 mm. Son casos sintéticos, no resultados del paciente abierto.

Se comprueban plataforma y eje fijos, bloqueo de aplicación nominal, catálogo de mallas reales, cancelación y rechazo de resultados caducados. El carácter experimental y los límites del [manual 9.22.0](OPTIMIZADORES_9_22_0.md) se conservan; para disponibilidad, orden de selección y bibliotecas integradas prevalece esta actualización.
