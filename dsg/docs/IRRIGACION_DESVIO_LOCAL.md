# Desvío local de irrigación

Al confirmar una vista previa bloqueada por invasión del modelo, se busca un desvío de los controles intermedios. Los controles inicial profundo y de contacto con el sleeve y el punto final quedan fijos. No se cambian diámetro, pared ni posiciones de los implantes.

Se usa el eje Z real del implante transformado a mundo, no el Z global de la pantalla. Se prueban primero desplazamientos pequeños en ambos sentidos paralelos al eje, con preferencia por su sentido positivo; si no hay un desvío verificado se buscan ajustes locales en una base orientada por ese eje y por la superficie invadida. La búsqueda está limitada a 8 mm por control, 24 iteraciones y aproximadamente 20 segundos; puede fallar sin alterar el recorrido original. Si solo hay tres controles se permite añadir uno intermedio manteniendo la conexión y los extremos.

El criterio aproximado usa distancia al modelo y el radio de la luz para orientar la búsqueda. Nunca autoriza el resultado: cada propuesta aceptada debe pasar la comprobación existente de la luz final completa y del manifold del sleeve, con sus rayos y pruebas de interior. El bloqueo se mantiene si no se puede verificar el modelo o no hay recorrido admisible. La pared exterior no sustituye la luz real como criterio, según la política existente.

El paso de confirmación conserva sus puertas y guarda el recibo del desvío. La comprobación final al cortar no se desactiva. Un error de la operación interior se devuelve como cancelación normal, evitando el traceback del operador exterior.

Validación: prueba sintética de obstáculos, extremos inmutables, fallo cerrado y eje oblicuo; prueba de una copia independiente del caso real, con desplazamiento de un control de 1.5 mm paralelo al eje y preflight verde; no se confirma ni corta automáticamente el caso abierto desde las herramientas de mantenimiento.

## Ajuste adaptativo por caso

1.5 mm es exclusivamente el resultado medido de una prueba concreta, nunca una traslación impuesta. La búsqueda calcula su paso inicial y alcance a partir del radio de la luz, la invasión estimada y la longitud externa disponible. Si no progresa, reduce el paso para afinar el ajuste. Conserva un límite técnico de desplazamiento de 12 mm y de tiempo; estos límites no autorizan geometría. Cada resultado guarda los parámetros adaptativos y el desplazamiento real, y debe superar de nuevo la comprobación exacta. Los extremos y el contacto con el sleeve siguen fijos.
