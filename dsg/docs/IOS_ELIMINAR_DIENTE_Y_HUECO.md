# Eliminar un diente del IOS: flujo guiado — 9.15.8

La herramienta aparece después de cerrar el modelo IOS. El botón inicia y guía el proceso; no es necesario cambiar manualmente a modo Edición ni borrar con X.

1. Pulsa **1 · SELECCIONAR DIENTE (C)**. DSG activa el IOS, entra en Edición, configura selección de vértices y activa la herramienta circular.
2. Marca con el círculo los vértices del diente que quieres retirar, hasta el borde de encía elegido. **C** permite volver a activar el círculo durante esta sesión. La selección circular usa la herramienta persistente para que el atajo P siga disponible al soltar el ratón.
3. Pulsa **P** o **2 · GUARDAR SELECCIÓN (P)**. DSG guarda una copia de la región elegida y comprueba que eliminarla dejaría un solo hueco válido. Todavía no elimina ni separa la malla. En esta sesión P guarda la región en DSG; fuera de ella conserva su función normal en Blender.
4. Aparece **3 · CERRAR HUECO HACIA DENTRO**. Ajusta Profundidad mm y púlsalo. DSG elimina exclusivamente la selección guardada, suaviza todo el borde, aplica Grid Fill y hunde el centro con una transición gradual.
5. En la ruta inmediata, la booleana con los dientes CBCT fijados se ejecuta después de completar el cierre cóncavo. En la ruta simple termina con la concavidad.
6. Revisa el resultado y continúa con el modelo retentivo.

Cambiar la selección visible después de guardar con P no cambia la región guardada. Para sustituirla, selecciona de nuevo y vuelve a pulsar P. El cierre permanece oculto hasta guardar una selección válida.

El suavizado utiliza tres iteraciones conservadoras sobre todos los vértices del borde, en coordenadas físicas, con un desplazamiento máximo de 0,20 mm. No mueve el resto del IOS. Rechaza bordes degenerados o cambios que inviertan las caras adyacentes. El borde suavizado permanece fijo durante el hundimiento de la cuadrícula.

Grid Fill admite bordes pares, impares mediante subdivisión de una arista y bordes de cuatro aristas mediante una cuadrícula con centro. La profundidad se comprueba contra la pared del modelo para evitar atravesarla. La profundidad predeterminada es de 2 mm.

**CANCELAR Y RESTAURAR** recupera la malla anterior al comienzo de la sesión. Si sales a modo Objeto antes de terminar, **VOLVER A EDICIÓN (C)** reanuda el proceso. Si el cierre falla, se conserva el IOS anterior al intento y la selección guardada para corregir la profundidad o volver a seleccionar.

En caso de booleana pendiente, **REINTENTAR BOOLEANA** permanece disponible y el modelo retentivo sigue bloqueado hasta completarla. Al cerrar correctamente se invalidan los resultados de retención anteriores para recalcularlos sobre el IOS modificado.

El cierre es una edición geométrica controlada; la concavidad no pretende reconstruir la anatomía real de una raíz. Las pruebas de esta versión utilizan mallas sintéticas en Blender.

## Omitir la eliminación manual

**SIGUIENTE** permite omitir este paso antes o durante la selección guiada. Si existe una edición en curso, recupera su copia previa. En simple mantiene la malla sin borrar ni cerrar un hueco. En inmediato ejecuta la booleana con los FDI fijados sobre el IOS ya cerrado, sin registrar un cierre cóncavo ficticio. Si falla, conserva el IOS y deja REINTENTAR BOOLEANA disponible; la retención continúa bloqueada. Tras omitirlo, desaparece la tarjeta de selección y se continúa con la preparación del modelo retentivo.
