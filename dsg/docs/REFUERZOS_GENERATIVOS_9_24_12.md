# Refuerzos de superficie · DSG 9.24.12

El botón **OPTIMIZAR FRAME** propone refuerzos sin cambiar el contorno dibujado. Está disponible también cuando existen refuerzos anteriores. El cálculo se realiza en un proceso separado y mantiene el modelo original.

1. Abre el paso de refuerzos y pulsa **OPTIMIZAR FRAME**.
2. Espera a la generación de rutas. Las conexiones parten de candidatos del contorno, incluyendo esquinas que coinciden con apoyos.
3. Revisa la propuesta cian. Los refuerzos anteriores se ocultan mientras la comparas, pero siguen conservados.
4. Pulsa **USAR REFUERZOS** para sustituirlos o **Descartar refuerzos** para recuperar la vista anterior. Si cambia el caso antes de aceptar, hay que repetir el cálculo.

El algoritmo usa la superficie pasiva ya preparada por DSG. Las caras de área nula se excluyen únicamente de la copia analítica, con registro y remapeo de sus índices; no modifica el IOS ni rellena huecos. Busca rutas con restricciones de superficie, grosor y acceso al sleeve. Una ruta bloqueada no se sustituye por una barra recta que cruce el modelo.

Esta primera entrega genera y comprueba candidatos geométricos. No predice rigidez ni demuestra que dos refuerzos sean suficientes bajo las cargas reales. La unión final al sleeve, el lumen tras la booleana y las secciones fabricables siguen requiriendo validación posterior. Los botones de investigación FEM permanecen identificados como experimentales.

Arquitectura: `ios_surface.py` conserva contratos y procedencia; `geodesic_router.py` calcula alternativas; `frame_generator.py` conserva el perímetro y construye conexiones; `frame_optimizer.py` evalúa la geometría. El adaptador Blender controla instantáneas, cálculo, revisión y aplicación reversible.

La revisión bloquea propuestas incompletas o alteradas y detecta cambios en la malla evaluada, las claves de forma y los modificadores. Los volúmenes de irrigación requieren identificación de tipo, guía propietaria y cobertura de cada conducto; una estructura distinta no sustituye un volumen ausente. Las trayectorias se suavizan y reproyectan dentro de su corredor de superficie, con comprobación posterior de distancia a la superficie, obstáculos y cruces propios. Si el suavizado falla, se conserva la ruta de superficie verificada.

En el caso abierto de prueba se han usado cinco apoyos, un sleeve y dos puertos accesibles: 18 rutas admisibles, dos refuerzos propuestos, radio nominal de 1,25 mm y longitud conjunta de 54,63 mm. La previsualización y su descarte conservaron la geometría original. El cálculo tardó 26,4 s en esta máquina; no es una garantía de rendimiento para otras mallas.

Pendiente menor: añadir orígenes en el centro de vanos largos. Esta entrega usa los apoyos existentes; el caso heredado no conserva una línea central verificable del contorno. No se inventan puntos de unión sobre un polígono aproximado. La siguiente etapa deberá recuperar esa línea del frame real antes de incorporar dichos orígenes.
