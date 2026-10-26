# Margen del nervio dentario · DSG 9.20.5

## Fundamento y alcance

El [consenso ITI de 2018 sobre precisión de medidas CBCT](https://academy.iti.org/academy/consensus-database/consensus-statement/-/consensus/accuracy-of-linear-measurements-on-cbct-images-related-to-presurgical-implant-treatment-planning/1819) recomienda considerar un margen mínimo de 2 mm respecto a estructuras anatómicas relevantes y explica que el error de las mediciones puede superar 1 mm en algunos casos. La [posición AAOMR sobre planificación de implantes](https://aaomr.org/common/Uploaded%20files/Position%20Papers/aaomr_implants_position_paper.pdf) señala la importancia de identificar el canal mandibular y el foramen mentoniano mediante imágenes transversales.

DSG aplica un **margen inicial de 2 mm**, ampliable hasta 10 mm, como decisión de planificación conservadora. El cálculo 3D que sigue es la implementación de DSG, no un algoritmo clínico validado por esos documentos. La referencia es la **superficie del canal mandibular segmentado**, no su línea central ni la distancia al eje del implante. El dato segmentado no representa necesariamente los límites microscópicos reales del nervio.

Un margen digital de 2 mm no garantiza por sí solo la ausencia de lesión. El control depende de la segmentación y alineación y no incorpora una longitud adicional de la fresa ni todas las desviaciones de ejecución quirúrgica. Se conserva el canal experimental del paquete base.

## Diferencia respecto al diente

- Dientes: conservan el cilindro de seguridad y su margen dental.
- Canal mandibular: se comprueba la separación euclídea respecto a toda la superficie del implante, incluidos extremo apical, laterales e inclinación. Reducir el margen dental no reduce el neural. El margen equivale a una zona de exclusión alrededor del canal, sin deformar ni reemplazar su segmentación.
- Se consideran todos los canales disponibles, aunque estén ocultos. Si existe segmentación del canal, se verifica cualquier implante próximo. En planificación inferior sin esa segmentación se bloquea la confirmación. Un caso superior sin canal mandibular no exige generarlo.
- Los microtornillos utilizan también esta comprobación independiente sobre su geometría.

## Uso y avisos

En mandíbula aparece **Margen nervio · mm**. Cambiarlo solicita una nueva comprobación diferida. Si se invade el margen, la alerta indica **Nervio dentario**, la separación acotada y el margen requerido. Puedes seguir usando R y G para ajustar; confirmar o exportar una posición inválida permanece bloqueado. El margen del diálogo de exportación, si es mayor, refuerza el control y nunca reduce el de la escena.

La comprobación obtiene límites matemáticos sobre las caras completas, no solo sus vértices. Usa la propiedad de que la distancia a una superficie cambia como máximo lo que cambia el punto consultado. Subdivide las caras próximas al umbral cuando hace falta. Una distancia indicada como **≤** es un límite superior y una marcada **≥** es un límite inferior; no se presenta como una medición exacta. El intervalo numérico de 0,02 mm se trata conservadoramente: una posición en el límite queda bloqueada. Esto es tolerancia de cálculo, no precisión del CBCT.

Se detectan intersección y contención, incluso entre componentes desconectados. Si el canal no está cerrado o la medición falla, aparece un estado no verificable y se bloquea. Para un STL de implante abierto se usa una envolvente convexa exterior solo para la comprobación; el aviso lo identifica como **envolvente conservadora**. Puede rechazar posiciones que la superficie original permitiría, pero no elimina metal ni modifica el implante. No se utiliza una envolvente convexa para reconstruir un canal incompleto.

Confirmar y exportar descartan las cachés de edición y comprueban de nuevo la anatomía. Durante R/G se mantienen las verificaciones diferidas y las alertas esperan a que termine el control modal.

## Verificación

- Pruebas Blender: separación lateral y apical de 1,8 mm bloqueada con margen 2 mm; separación de 2,5 mm admitida a 2 mm y bloqueada a 3 mm; separación diagonal euclídea admitida; canal oculto bilateral, contención, canal ausente y envolvente conservadora sin cambiar la malla original.
- Pruebas matemáticas: punto más próximo en el interior de una cara con todos sus vértices alejados; distancia diagonal; límite incierto; datos inválidos que no pasan el control.
- Prueba sobre copias con el canal real cargado: 55.738 vértices. Se rechazó una copia del implante situada sobre el canal y se admitió al alejarla. Preparación inicial de geometría 0,53 s; comprobación reutilizando caché 4,4 ms en esa posición de intersección y 5,8 ms al separarla ampliamente. No son medidas garantizadas para otras posiciones o mallas. El implante original quedó intacto.
- Se conservan las pruebas de R/G, aviso sin repetición, raíces ocultas, canales y microtornillos. La escena abierta corresponde a un caso superior; esta entrega no sustituye una validación clínica sobre una planificación mandibular real.
