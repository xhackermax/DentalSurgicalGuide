# Colocación del implante y rotación · DSG 9.20.3

## Qué cambia

El control de emergencia permite **G** para mover y **R** para rotar usando los controles nativos de Blender. Antes, una comprobación de contacto se ejecutaba durante cada cambio y devolvía el implante a su pose anterior. Un giro que pasaba temporalmente cerca de una raíz se deshacía, dando la impresión de que R no funcionaba.

Ahora el movimiento conserva la pose elegida. Tras una pausa de 150 ms, DSG comprueba la posición y muestra si hay contacto con una estructura protegida. La confirmación y la exportación siempre hacen una comprobación exacta y bloquean una posición inválida. Durante la edición pueden existir contactos temporales; el usuario debe ajustar la posición antes de confirmar. No se amplían ni reducen los márgenes ni la altura del halo.

El cálculo procesa juntos los triángulos que quedan entre las tapas del cilindro. Solo los que cruzan una tapa requieren el recorte individual. Se conserva el cálculo de contención y los controles de dientes ocultos, implantes vecinos y canales mandibulares. Al editar la geometría de un obstáculo se invalida su caché.

## Uso

1. En el paso de implantes selecciona el control de emergencia.
2. Usa **G** para mover o **R** para girar; puedes restringir el eje con X, Y o Z.
3. Al pausar, lee el aviso de seguridad. Si indica contacto, ajusta la posición.
4. Confirma el implante cuando la posición sea válida. Un contacto impide confirmar o exportar.

## Verificación del 13 de octubre de 2026

- Caso abierto en Blender 5.2.2 LTS: la rotación nativa del control de emergencia se conserva después de la comprobación. El giro de prueba tocaba el diente 14 y fue rechazado por el control de confirmación. Se restauró la posición original al terminar la prueba.
- Mismo caso, geometría y comprobación: tres medidas anteriores 195, 190 y 187 ms; optimizadas 50, 48 y 51 ms. Aproximadamente 3,9 veces más rápido en este caso. La rotación nativa de prueba tardó 1,6 ms al sacar el cálculo pesado del movimiento. Estas cifras no garantizan el rendimiento de otros casos.
- 181 pruebas de la capa pura superadas, incluida comparación con el algoritmo anterior en 1.003 casos individuales y 60 grupos de triángulos.
- Prueba Blender de movimiento: sin cálculo pesado dentro del actualizador del movimiento, rotación preservada, aviso diferido y bloqueo explícito de confirmación y exportación.
- Pruebas Blender de dientes vecinos: raíces ocultas, selección persistente y canales mandibulares. Prueba de microtornillos: halo de 2 mm, protección de toda la longitud, contacto con diente/nervio/implante/otro tornillo y bloqueo de confirmación. El caso de microtornillo se identifica explícitamente como mandíbula.
- La prueba antigua de frame orgánico se detiene en una expectativa de forma anterior a esta corrección. No se presenta como prueba superada. Se conserva el canal experimental de la versión local recibida.

## Alcance

Esta revisión corrige el movimiento y la rotación y mantiene las comprobaciones de seguridad al confirmar. No vuelve a segmentar el CBCT ni modifica la extracción del caso abierto.
