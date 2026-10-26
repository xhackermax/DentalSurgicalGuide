# Extensión oclusal del resto radicular · 9.19.3

## Uso

1. En la ruta **Implante inmediato**, elige el FDI que extraerás y prepara el IOS: selección guiada y cierre hacia dentro, o la omisión permitida de la retirada manual.
2. En el paso del modelo aparece **Extensión oclusal · mm**, una barra de 0 a 10 mm. **VER EXTENSIÓN OCLUSAL** prepara o refresca la vista previa. La primera vista calcula una longitud inicial suficiente cuando cabe dentro del límite.
3. Mueve la barra. La prolongación de alambre cambia al instante, sin ejecutar una booleana en cada movimiento. El estado muestra longitud elegida, longitud necesaria y **SUFICIENTE / INSUFICIENTE**. La longitud indica milímetros adicionales hacia oclusal, sobre el extremo del resto segmentado.
4. Usa **REINTENTAR BOOLEANA** para aplicar la longitud elegida. Si no alcanza la superficie, la operación se detiene y conserva la geometría anterior. Si la vista todavía no se ha inicializado, el cierre automático utiliza el alcance calculado, limitado a 10 mm.
5. Al cambiar la longitud después de aplicarla, la booleana queda pendiente. Reaplicarla parte de una copia del IOS cerrado anterior a esa booleana, de modo que los cortes no se acumulan. Vuelve a **PREPARAR MODELO RETENTIVO** para incorporar cualquier cambio posterior del IOS.

**SUFICIENTE** comprueba el alcance de la prolongación, no garantiza por sí solo el resultado final. Al aplicar se comprueba también que el alvéolo abre hacia la raíz y que el IOS mantiene una malla cerrada y manifold. La extensión sigue el eje propio del diente; preserva la raíz y extruye un contorno transversal hacia oclusal, en lugar de estirar el extremo de la corona. El diente CBCT original se conserva.

La vista previa actual admite un FDI de extracción a la vez. No se puede superar 10 mm con la barra. Si esa longitud resulta insuficiente, hay que revisar el IOS, la segmentación o el eje antes de continuar.

## Verificación del 13 de octubre de 2026

- Blender 5.2.2 LTS: barra limitada a 0–10 mm, actualización de geometría, bloqueo de longitud insuficiente, preservación del IOS ante error y reaplicación desde la copia anterior.
- Prueba geométrica: extrusión de sección constante, raíz apical intacta, booleana sobre IOS oculto, disminución real del volumen y comprobación del acceso al alvéolo.
- Caso abierto, FDI 15: alcance necesario 6,448 mm; actualización medida de la vista previa 37 ms; eliminación de 267,897 mm³; acceso axial comprobado de 13,597 mm; cero aristas abiertas o no manifold. Las geometrías originales de 14, 15 y 16 permanecen iguales. El modelo retentivo se recalculó con su vía de inserción guardada. Son medidas de este caso, no un tiempo o resultado garantizado para todos los modelos.
- 179 pruebas de la capa pura superadas. El control global de métricas tiene dos desviaciones ya presentes en el ZIP recibido. La prueba antigua `test_ios_boolean_after_socket.py` se detiene en la selección sintética del IOS; no se presenta como una comprobación superada de esta entrega.

Esta actualización conserva el canal experimental del paquete recibido; las comprobaciones descritas son geométricas y de software.

## Siguientes mejoras

- Vista previa independiente por FDI para extracciones múltiples.
- Indicar separadamente las colisiones de la prolongación con estructuras vecinas.
- Medir el alcance en varios puntos del contorno, además de la comprobación axial y la columna local.
