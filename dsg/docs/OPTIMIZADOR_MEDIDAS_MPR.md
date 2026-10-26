# Mediciones alrededor del eje en la propuesta automática

Solicitud: incorporar al optimizador las comprobaciones de distancia del MPR del implante.

La detección de superficies protegidas ya se realizaba en 3D. Se mantienen sus márgenes, la comprobación exacta al aplicar y las puertas de confirmación. No se usan píxeles de la imagen ni medidas manuales como anatomía automática.

La evaluación de posición añade ocho niveles y dieciséis direcciones de pared nativa alrededor del eje. Se excluye la banda cervical configurada y el espacio sin hueso cuenta como reserva cero. Un bono geométrico acotado distingue posiciones con igual cobertura; no vuelve admisible una posición rechazada. La medida es muestreada y no predice estabilidad primaria.

La búsqueda de tamaños mantiene longitud y diámetro como prioridades. A igual contacto, usa la reserva transversal nativa mínima estimada por cortes antes del menor desplazamiento. La incertidumbre del raster se descuenta y las regiones rellenadas, alvéolos y seno no se convierten en hueso nativo. La selección final y VALIDATE vuelven a medir sobre las superficies 3D originales.

Aceptación: dos posiciones admisibles con cobertura idéntica pueden diferenciarse por reserva de pared; las colisiones siguen rechazadas; a igual tamaño/contacto la búsqueda por cortes prefiere más pared; el tamaño mantiene su prioridad; resultados muestran medida y muestreo. El cambio se prueba en geometría sintética antes de instalarlo. No mover ni aplicar una propuesta en el caso abierto.
