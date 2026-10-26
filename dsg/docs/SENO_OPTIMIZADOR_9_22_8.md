# DSG 9.22.8 · Seno maxilar en el optimizador

El optimizador de posición y tamaño aplica al seno maxilar la misma tolerancia que la planificación manual: se admite invasión hasta el límite configurado en Seguridad (2 mm por defecto) con ALERTA; más allá se rechaza. La cavidad nasal mantiene 2 mm de separación.

- Opción **Seno: invasión permitida como en planificación manual** (activada por defecto). Desactivada, el seno vuelve a exigir 2 mm de separación.
- Solo cuenta como invasión un cruce real de superficies. Estar cerca del seno no es invasión, igual que en la planificación manual.
- Profundidad: punto del implante más hundido dentro del seno (vértices y muestras de superficie; si el cruce es más fino que el muestreo, se remuestrea a ~0,1 mm y se informa como máximo esa resolución).
- La propuesta muestra "ALERTA · Seno maxilar: invasión X mm (límite 2)". A igual soporte óseo, BUSCAR POSICIÓN prefiere la posición que invade menos.
- No cambia el resto de restricciones (raíces, nervio, implantes, reserva de pared, cobertura).

Verificación: prueba sintética de 1 mm (alerta), 3 mm (rechazo), sin contacto y cavidad nasal con margen; regresiones del optimizador. No es validación clínica.
