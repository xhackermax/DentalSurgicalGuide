# Prioridad de anclaje al sleeve · 9.24.17

Los refuerzos principales buscan unirse directamente al sleeve. El generador ya no se detiene en las dos primeras ramas válidas: compara conjuntos de rutas compatibles, prioriza el número de apoyos con conexión directa y después la diversidad de puntos de unión y la longitud. El presupuesto se reparte por sleeve y se prueban los primeros puertos de cada origen antes de agotar alternativas de un solo apoyo.

La selección trabaja sobre un conjunto finito de rutas y tiene presupuesto explícito. No afirma un óptimo mecánico ni una búsqueda exhaustiva de toda la anatomía. Se mantiene un mínimo de dos conexiones desde apoyos distintos por sleeve. Las rutas y el suavizado siguen apoyados sobre el IOS.

La celosía secundaria se intenta después de asegurar los anclajes. Si no caben enlaces transversales válidos, se conserva la red directa al sleeve y se identifica como refuerzos, sin afirmar que la celosía está completa. No se añaden cruces inválidos ni puentes aéreos para forzar el patrón.

## Unión geométrica real

Cada rama principal debe compartir volumen con la malla real del sleeve. Se busca un punto estrictamente interior a ambos sólidos, se comprueba su número de enrollamiento y su distancia positiva a las dos superficies. El simple contacto tangencial no basta. Esta comprobación demuestra una unión geométrica positiva, no su resistencia mecánica.

Las huellas del caso incluyen ahora las mallas fuente de los sleeves. Cambiar su geometría invalida la propuesta. Al aceptar también se verifica la identidad y el rol de cada rama y que su prueba de unión siga intacta.

## Uso

En el paso Refuerzos, pulsa OPTIMIZAR FRAME y revisa las ramas naranjas que llegan al sleeve. Cuando haya celosía completa aparecerá USAR CELOSÍA; si el resultado es una red directa sin enlaces secundarios, aparecerá USAR REFUERZOS. Descartar restaura los originales. La propuesta no se acepta automáticamente.

Siguen pendientes la evaluación mecánica y la validación de espesor después de la booleana final.
