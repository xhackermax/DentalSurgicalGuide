# Búsqueda geométrica por secciones · 9.22.16

## Uso

Seleccionar implante → biblioteca → revisión del CBCT → **BUSCAR PROPUESTA**. El cálculo usa la orientación colocada por el usuario y busca medidas y traslaciones locales. La propuesta cian sigue al MPR; el original conserva malla y posición hasta aceptar. Aceptar exige revisión clínica del perfil/tejidos/límites protésicos y una revalidación con geometría actual. Descartar restaura el original. Ninguna propuesta se aplica automáticamente.

## Elementos analizados

- Hueso segmentado del maxilar o mandíbula activos: secciones con contornos exteriores e interiores y medición separada del hueso realmente segmentado.
- Raíces vecinas conservadas, implantes y microtornillos: zonas protegidas con sus márgenes, incluidas geometrías ocultas.
- Alvéolo del diente extraído: espacio distinto del hueso nativo; no se confunde con ausencia de hueso ni se suma al soporte nativo.
- Senos maxilares: hasta2mm de penetración con alerta, según configuración solicitada; más profundidad o profundidad no verificable se rechazan.
- Cavidades nasales:0mm de margen adicional y sin penetración.
- Conducto dentario: mantiene mínimo2mm y márgenes más estrictos del caso. Dientes1,5mm e implantes3mm como mínimos; no se rebajan sus reglas.

Las estructuras lejanas se descartan del mapa local mediante cajas envolventes; las comprobaciones 3D finales conservan las estructuras protegidas originales. La malla activa y sus superficies son la fuente geométrica; los cortes no son capturas de pantalla.

## Método y relación con el texto matemático aportado

Se transforma la geometría al eje del implante y se calculan cortes paralelos cada0,25mm. Se intersectan triángulos y planos y se rellenan los contornos mediante paridad, conservando huecos y componentes separados. Se usa una región local que cubre todos los tamaños/traslaciones considerados y sus márgenes.

El espacio disponible de cada corte se erosiona con un disco del radio del implante: un centro es utilizable si la sección circular cabe en él. La intersección de esos conjuntos a lo largo de su longitud aproxima el espacio de configuraciones del cilindro. Es más informativo que comparar volúmenes o cajas. La búsqueda conserva el eje; no estudia la trayectoria de inserción.

Las máscaras de obstáculos se expanden usando distancia euclídea a través de la pila, no solo dentro de un plano. La incertidumbre de muestreo se hace explícita: media diagonal de un voxel de0,25mm, aproximadamente0,217mm. Pequeñas estructuras entre planos pueden no aparecer en el raster y deben ser detectadas por la comprobación 3D final.

Los volúmenes se estiman sumando área por espesor de corte. Se muestran por separado hueso segmentado, alvéolo, espacio permitido del seno y espacio sin clasificar. Rellenar un contorno para describir su envolvente no convierte ese espacio en hueso. Si la región ocupada bajo la banda cervical contiene espacio sin clasificar, la referencia requiere revisión.

## Elección y comprobaciones

Se buscan centros en una rejilla lateral de0,5mm dentro de3mm y cuatro profundidades entre0 y1,5mm hacia apical, con medidas disponibles del catálogo. El orden es mayor longitud, después diámetro; la intersección superficial con hueso y menor movimiento desempatan. El tamaño del catálogo elegido corresponde al modelo nominal DSG, no al CAD exacto de roscas/cuello comercial.

El soporte se describe por la fracción del anillo superficial en hueso segmentado y el tramo consecutivo en el que al menos el50% del área de la sección intersecta hueso segmentado. Se conserva3mm como heurística técnica para el tramo; NO es un umbral universal de consenso ni predice torque/estabilidad primaria. Este criterio sustituye, en esta ruta, la antigua envolvente expandida1,6mm; no se muestra como si se hubiese medido aquella reserva. La pared vestibular direccional sigue requiriendo revisión del CBCT/MPR.

Se priorizan las combinaciones en el mapa y se realizan hasta24 comprobaciones completas de estructuras protegidas sobre las mallas 3D. Además se muestrea la superficie 3D del candidato respecto a la unión de hueso/alvéolo/seno permitido bajo la banda cervical; una separación mayor que la resolución del mapa exige revisión. El seno conserva su comprobación 3D de profundidad. Al aceptar se reconstruye el mapa desde una instantánea nueva y se repiten las comprobaciones.

Una propuesta significa encaje geométrico según estas comprobaciones. No certifica viabilidad clínica. La búsqueda es finita, en una región y eje concretos, no un óptimo global; si se agota el presupuesto se indica que quedan candidatos sin verificar. Una referencia con contorno, soporte o clasificación no resueltos se muestra en ámbar, sin aceptación habilitada. Los rechazos de estructuras protegidas conservan su estado.

Si faltan dependencias científicas o el mapa no puede construirse, se utiliza la búsqueda3D anterior y se informa del respaldo. Los catálogos de CAD personalizados mantienen la ruta3D, porque no se asume que tengan sección cilíndrica nominal.

## Pruebas

Contornos exteriores/interiores y componentes separados; elección de la medida mayor que cabe; hueso/alvéolo/aire separados; invasión del seno hasta2mm y rechazo superior; obstáculo fino entre planos rechazado en3D; nueva estructura invalida la revalidación; visualización sin atribuir una reserva no medida. Se mantienen pruebas de aceptación, descarte, MPR y rollback.

## Referencia clínica y límites

El ITI respalda la evaluación tridimensional del sitio mediante CBCT y las medidas en cortes, con errores posibles de medida. Reducir cálculos mediante cortes no elimina la revisión volumétrica ni la incertidumbre de segmentación.
https://academy.iti.org/academy/consensus-database/consensus-statement/-/consensus/accuracy-of-linear-measurements-on-cbct-images-related-to-presurgical-implant-treatment-planning/1819
