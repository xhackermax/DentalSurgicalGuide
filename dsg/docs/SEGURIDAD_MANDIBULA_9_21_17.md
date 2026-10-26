# DSG 9.21.17 · Seguridad de la mandíbula

Al seleccionar un implante inferior, o su control de emergencia, el apartado de seguridad muestra **ZONAS DE PELIGRO · mandíbula** e identifica el **Nervio dentario inferior (canal mandibular)**. El panel superior de senos/cavidad nasal se oculta. Al seleccionar un implante superior vuelve ese panel, aunque haya otros implantes inferiores en la escena.

Se utiliza el FDI o la arcada almacenada en el implante seleccionado. Si no hay un implante identificable, se conservan las referencias generales de la escena. La selección se utiliza también para decidir la arcada mostrada en la vista radiográfica. No se cambian las posiciones, las etiquetas de arcada ni la geometría de los implantes.

El cálculo neural existente se conserva: margen independiente de 2 a 10 mm respecto a la superficie del canal segmentado, comprobación lateral y apical, inclusión/intersección, canales bilaterales incluso ocultos y bloqueo si falta segmentación inferior o no puede verificarse la distancia. No se confunde con la tolerancia de penetración configurada para los senos.

El panel muestra el resultado ya calculado, sin ejecutar mediciones durante su dibujo. Si aún no existe informe indica pendiente; si falta el canal lo identifica expresamente; si el margen está invadido muestra el mensaje de riesgo. Una separación calculada como límite inferior se presenta con ≥, no como una distancia exacta.

Verificado en Blender: margen neural independiente, distancia lateral y apical, canales ocultos/bilaterales, ausencia de canal, selección entre implantes de ambas arcadas y selección de su control de emergencia. La sesión real abierta durante esta verificación corresponde al maxilar superior; las pruebas de mandíbula se ejecutaron en una escena sintética aparte.

Este cambio identifica y presenta la protección neural. No supone una nueva validación clínica de la segmentación o de la guía y conserva el carácter experimental del paquete.
