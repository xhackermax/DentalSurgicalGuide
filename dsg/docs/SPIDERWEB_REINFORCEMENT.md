# Telaraña geodésica del frame

El paso de refuerzos usa `ADAPTIVE_SPIDERWEB_V1` automáticamente, sin controles nuevos. Los colores y Thin Wall existentes se conservan.

- Ramas desde puntos superiores reales y alejados del frame, priorizando recorridos útiles largos hacia paredes curvas del sleeve.
- Nodos independientes a distancias geodésicas comunes desde cada sleeve. No se fijan al mismo porcentaje de ramas de longitudes diferentes.
- Arcos sobre el IOS, sin diagonales obligatorias. Primero se reserva el corredor interior más estrecho y se intenta ampliar con otro nivel exterior.
- El frame evaluado puede cerrar el anillo exterior únicamente si su malla está cerrada, conectada y tiene un asa topológica real (característica de Euler <= 0). Un sólido sin agujero o una superficie abierta no sirven como anillo.
- Un sector válido puede contener un arco interior y el frame como anillo exterior. Se informan separadamente niveles interiores, anillo existente y anillos nuevos completos. No se presenta un sector como una telaraña circular de 360 grados.

Las ramas ya suavizadas se conservan exactamente al insertar nodos. Los arcos se suavizan y se comprueban después de cada ajuste: pliegues, apoyo en IOS, intersecciones, lumen, irrigación y apertura lateral. Las aristas del enrutador se contrastan con los tubos físicos mediante distancia exacta entre segmentos; los límites finales siguen siendo obligatorios.

## Comprobación nativa

El botón guarda una copia local del caso en la carpeta temporal del cálculo. El trabajador aislado construye y verifica las mallas de las ramas antes de seleccionarlas. Rechaza las que invaden la cara inferior del frame o incumplen cualquier control de malla; no puede recuperarlas por obtener una mejor puntuación de longitud.

También construye la telaraña completa antes de devolver un candidato. Un fallo de unión o de malla invalida esa distribución y continúa con las siguientes. La sesión activa vuelve a comprobar la propuesta al construir sus objetos visibles.

Se comprueban radio, cierre, auto-intersecciones, apoyo de todas las secciones, límites de entrada y tapas del sleeve y volúmenes protegidos. Se exige un testigo de volumen positivo en frame/sleeve para cada rama y en ambas ramas receptoras para cada arco. Los anclajes deben pertenecer al mismo componente real del frame. La guía, el IOS, los implantes y los soportes originales se preservan.

Un eje DSG_Axis oculto, sin padre ni restricciones, se lee desde su matriz base: Blender puede mantener matrix_world como identidad al cargar un objeto excluido del grafo de dependencias. Los ejes con padre o restricciones conservan su transformación mundial evaluada.

La propuesta sigue siendo reversible y pendiente de aceptación. Las comprobaciones de geometría no constituyen una evaluación de resistencia mecánica.

## Crecimiento orgánico adicional

La red radial certificada actúa como esqueleto inmutable. Se añaden ramas geodésicas entre el frame y las estaciones de las ramas, entre estaciones de ramas distintas y entre regiones del frame. Las ramas nuevas también pueden recibir bifurcaciones. Los puntos adicionales del frame se toman de vértices reales de sus caras superiores, sin mover ni remodelar el original.

Las ramas de crecimiento tienen menor radio que el esqueleto y sus uniones se resuelven con los mismos tubos de marcos de rotación mínima y transiciones Coons. La densidad es automática: no se añaden controles ni botones. Un enlace debe añadir material visible, no quedar enteramente enterrado en el frame. La comprobación contempla el radio completo de la sección.

Cada adición requiere dos extremos físicamente unidos y apoyo de las secciones en IOS/frame/ramas receptoras. Las intersecciones con otras ramas solo se permiten dentro de la unión local declarada; se rechazan contactos remotos. Un enlace rechazado restaura los nodos y conserva todas las curvas y mallas anteriores. Se vuelve a comprobar el grafo completo y la propuesta nativa final.

El objetivo de densidad está acotado por el espacio disponible y los volúmenes protegidos. No se eliminan límites de altura, superficies inferiores, tapas del sleeve ni lumen para obtener más conectores. La apariencia generativa no constituye un cálculo de resistencia ni una optimización por elementos finitos.

## Verificación

Pruebas de crecimiento sobre superficie, conservación exacta del esqueleto, rechazo de ramas huérfanas, radio, continuidad, restricciones y pruebas nativas de limpieza. Los ensayos reales se ejecutan sobre copias inmutables del caso. Tras un cambio de geometría o reinicio de Blender se toma una copia nueva y se recalcula; una propuesta de un caso anterior no se transfiere al nuevo.


## Axial radial web V2 (2026-10-21)

The Optimize Frame action now dispatches to `blender/axial_web_pipeline.py` for new snapshots. See `docs/AXIAL_RADIAL_WEB.md`. The V1 worker and review paths remain available for their original requests. `axial_radial_web.py` builds the shared distance graph, `blender/axial_design_sheet.py` constructs the IOS-guided extrados, `axial_capsule.py` and `blender/axial_implicit_web.py` form the shared volume, and `blender/axial_web_mesh.py` verifies the final geometry. `axial_web_contract.py` binds the inputs, artifacts and receipts.
