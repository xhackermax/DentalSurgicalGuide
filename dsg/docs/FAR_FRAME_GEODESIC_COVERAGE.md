# Optimización geodésica desde los puntos alejados del frame

La política interna `FAR_FRAME_GEODESIC_LATTICE_V2` utiliza el botón existente. No añade controles.

- Lee hasta 24 orígenes distribuidos sobre el frame conservado y prioriza los más alejados del sleeve. Selecciona hasta tres ramas principales por sleeve; no intenta unir todo el frame al sleeve.
- Prefiere recorridos geodésicos largos y útiles sobre el IOS. La puntuación limita la recompensa de rodeos artificiales.
- Busca cobertura de ambos lados de las aperturas guardadas. La cobertura es una preferencia de diseño: las zonas pendientes se muestran explícitamente y no se presentan como reforzadas. Los volúmenes de irrigación, apertura y paso de la fresa siguen siendo restricciones físicas obligatorias.
- Exige una red conectada y triangulada de conexiones geodésicas entre las ramas. Las ramas aisladas no se presentan como una celosía.
- Certifica el cuerpo central sobre el IOS y comprueba por separado que los cuellos finales se apoyan en los sólidos reales del frame y del sleeve. Una exclusión de cuello nunca autoriza un hueco interior sin apoyo.
- La comprobación de superficie incluye caras grandes cercanas aunque sus centroides estén lejos. Mantiene las mismas tolerancias geométricas.
- Las intersecciones de la malla final conservan sus comprobaciones exactas. Solo se descartan antes las parejas demostrablemente separadas por cajas y planos.
- Los informes de cada intento son copias independientes para poder serializar el resultado válido sin referencias circulares.

Las propuestas son reversibles y requieren la acción existente «Usar celosía» para aceptarlas. No se demuestra resistencia mecánica, optimalidad global ni aprobación clínica mediante estas comprobaciones geométricas.

## Evidencia de la regresión

La copia del caso que fallaba completó una propuesta de dos ramas principales y tres conexiones secundarias. Las cinco mallas finales superaron las verificaciones de apoyo, radio e invasión de volúmenes protegidos. El archivo de prueba guardado se volvió a abrir correctamente. Quedó un lado de la apertura sin cobertura, expresamente registrado como pendiente.

La prueba del botón real sobre la sesión actual se registra por separado en `outputs/optimizer_live_button_test.json`. No se debe confundir una prueba de rutas o una simulación sintética con la malla final verificada en Blender.

Validación ampliada: 94 pruebas pasan en cada copia (desarrollo e instalación). En una copia guardada se probaron tanto aceptar como descartar la propuesta, conservando la geometría clínica original. La validación física del caso de regresión bajó de 204 s a 41 s en las ejecuciones registradas (la primera incluía guardado); las mismas cinco piezas mantuvieron todos los certificados.

## Corrección del collar y verificación en la sesión actual

La unión Coons permitía que un control Bézier del collar atravesara el plano del aro del tubo y entrara en el cuerpo nominal. La regularización no originaba el defecto: el primer impacto radial ya detectaba el collar dentro del tubo antes del remallado. El control del apoyo se acorta en su misma dirección tangente para mantener el casco convexo del collar en el lado del soporte. La huella y el aro permanecen fijos. La opción interna se activa solo para la celosía automática; el comportamiento manual conserva su valor por defecto.

El caso actual del botón real produjo dos ramas y tres conexiones. Tras corregir el collar se reanudó su construcción nativa con el mismo resultado del worker y la misma huella del caso, sin recalcular ni sustituir la geometría clínica. Las cinco piezas quedaron visibles y pendientes de aceptar en la sesión abierta. Radios mínimos medidos: principales 1.2437/1.2442 mm (nominal 1.25 mm); secundarios 0.8674/0.8682/0.8676 mm (nominal 0.875 mm). Se mantuvieron las tolerancias y las verificaciones finales de apoyo, volúmenes protegidos y unión física al sleeve.

Este estado actual no contiene recortes guardados de apertura lateral ni irrigación: no constituye una nueva validación de esas zonas. El caso anterior con ambos recortes permanece como regresión independiente.

## Salidas superiores y contacto cilíndrico del sleeve

La restricción `FRAME_ABOVE_SIDEWALL_ONLY_V1` toma el lado superior hacia la entrada clínica de la fresa. Los orígenes se obtienen en caras superiores del frame evaluado, con normal en ese sentido; los puntos semánticos se llevan mediante rayos a esa superficie real. Después las rutas siguen siendo geodésicas sobre el IOS. No se fuerza una plataforma plana ni se inventan conexiones entre los puntos semánticos.

El radio completo de cada rama y conexión queda por debajo del plano superior del sleeve. La malla final, incluidos los collares, no puede cruzar ninguna de sus caras planas: se recortan los triángulos contra la banda de cada plano y se comprueba la intersección con el disco, incluso si los vértices están fuera. El contacto físico con el sleeve solo es admisible en la pared cilíndrica.

La cara inferior del frame se exporta como barrera orientada independiente de los volúmenes cerrados de irrigación y apertura. Guía la búsqueda y permite comprobar barridos exactos de las trayectorias centrales. Los cuellos terminales siguen sujetos a la validación de su malla Coons real; no se confunden con un tubo circular virtual. La malla final completa tampoco puede atravesar caras inferiores del frame. Cambiar el eje clínico invalida una propuesta pendiente.

Las cinco piezas de la propuesta anterior se rechazan con estos límites. Las pruebas de origen superior, planos del sleeve y barrera inferior son independientes de la prueba completa del caso abierto, registrada en `outputs/upper_frame_live_test.json`.

El cálculo conserva tanto los corredores guiados por costes como las alternativas sin esa penalización: ambas pasan los mismos límites exactos. La selección de alternativas distribuye el presupuesto entre parejas distintas de orígenes/puertos antes de repetir variantes geométricas casi iguales. Los intentos de celosía se interrumpen cuando falta una arista obligatoria; añadir aristas posteriores no puede completar ese mismo intento.

Se añade una separación de 0.05 mm respecto a la cara inferior del frame durante el barrido previo para evitar que una pequeña variación de la piel final regularizada produzca un contacto inferior. La malla final sigue siendo la comprobación decisiva. Validación: 107 pruebas puras por copia y cuatro pruebas geométricas de contacto superior/cambio de eje. Las exportaciones reales comprueban los orígenes contra el BVH del frame y conservan los volúmenes funcionales guardados.

Resultado final de esta sesión con las restricciones nuevas: `NO_VALID_SLEEVE_ANCHORED_LATTICE` tras 16 distribuciones y sus controles geométricos. La propuesta anterior está retirada; frame, guía e IOS conservan sus hashes y guía/IOS permanecen visibles. Se muestra el motivo en el mismo panel, sin controles nuevos. Esta búsqueda acotada no demuestra imposibilidad geométrica global. La generación de una celosía completa para este caso sigue pendiente; no se declara resuelta por tener las pruebas unitarias pasando.
