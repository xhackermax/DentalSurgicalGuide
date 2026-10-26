# DSG 9.21.15 · Avisos anatómicos visibles

## Fallo observado en la sesión abierta

El 14 de octubre de 2026, el implante activo invadía el seno maxilar derecho. DSG 9.21.14 calculaba 2,01 mm de penetración y lo clasificaba como ALERT, con el umbral configurado de 2 mm y su tolerancia numérica. La ventana de seguridad recibía solamente los contactos BLOCK. Por eso el informe interno contenía la invasión, pero no había ventana ni aviso persistente de esa categoría. La barra de estado podía incluso anunciar una posición sin contactos.

## Corrección

- Los avisos ALERT y los contactos BLOCK llegan a la ventana y al botón persistente de seguridad.
- El halo amarillo identifica avisos; el rojo, contactos bloqueantes; el azul, ausencia de avisos/contactos detectados.
- El texto distingue aviso y bloqueo. Un aviso no afirma que la confirmación esté bloqueada.
- La barra de estado conserva el aviso anatómico, en lugar de anunciar una posición libre.
- La ventana espera a terminar una operación modal, como R/G. No repite la misma alerta continuamente, pero vuelve a avisar después de salir y reentrar, o cuando la misma estructura pasa de aviso a bloqueo.
- También se muestran los avisos de proximidad nasal y de cavidades sin delimitar.

No cambian la posición del implante, el IOS, la segmentación ni los límites de aviso/bloqueo configurados en 9.21.14. No se modifica en este parche el algoritmo de medición de cavidades. Sus limitaciones de intersección de superficies documentadas en la revisión de 9.21.14 siguen pendientes; esta corrección resuelve el aviso omitido en el caso abierto.

## Verificación

Una prueba con invasión de un seno oculto falló antes de corregir: ALERT no aparecía en los avisos visibles. Después verifica el encaminamiento a ventana/panel, barra de estado, colores, espera durante R/G, deduplicación, reentrada, escalado a bloqueo y texto correcto de la ventana. Se verifican además las regresiones de seguridad superior, neural, movimiento del implante, alertas, microtornillos y dientes vecinos, y la suite de 196 pruebas unitarias.

Antes de actuar en la sesión abierta se guardó una copia del archivo con `copy=True`, conservando la sesión original y la selección. Los avisos se pueden reabrir desde **ALERTA ANATÓMICA** en el paso del implante.

Esta versión mantiene el carácter experimental del paquete y sus limitaciones previas.

## Simplificación de la colocación

Se retiran los botones Seleccionar emergencia y Analizar del paso del implante. Cada implante recibe automáticamente su control de emergencia, visible y seleccionable durante la colocación. El análisis continuo de seguridad sigue activo. El plano MPR utiliza un marco gris neutro y ya no ofrece el selector de color ni el botón Rehacer plano; conserva creación inicial, orientación y visibilidad. Los colores de las estructuras anatómicas se conservan. No se añade coloreado sobre los píxeles del corte radiográfico.
