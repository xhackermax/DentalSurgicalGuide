# DSG9.22.22 — evaluación de dientes suavizados

El exportador del optimizador rechazaba todos los modificadores activos, incluido el suavizado medido de DSG que usa el botón SÍ/NO. Ahora reconoce exclusivamente su grafo conocido de desplazamientos por vértice y exporta la misma superficie como arrays temporales. Funciona con anatomía visible u oculta, sin aplicar modificadores ni cambiar mallas o visibilidad. La suma conserva la precisión de coordenadas que utiliza Blender.

Se verifica la estructura exacta del grafo, sus conexiones y tipos, el atributo vectorial por vértice y el límite de desplazamiento. Otros modificadores activos y los modificadores del implante objetivo siguen requiriendo revisión. El estado del suavizado forma parte de la huella de la propuesta, por lo que cambiar la superficie invalida un resultado previo. La aceptación vuelve a exportar la geometría y repite las comprobaciones.

Verificación: superficie evaluada en Blender igual a la exportada; geometría oculta y visible iguales; fuente original conservada; edición de desplazamientos invalida la huella; modificadores desconocidos y grafos alterados rechazados. Pruebas de búsqueda, previsualización, aceptar/descartar y revalidación con una mandíbula que lleva este suavizado activo.

Se conservan los catálogos y la regla del seno de9.22.19, el suavizado corregido de9.22.20, la edición de vecinos de9.22.21 y los botones eliminados.
