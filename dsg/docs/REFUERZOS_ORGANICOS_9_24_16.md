# Refuerzo automático orgánico · 9.24.16

## Cambios

La celosía automática utiliza las rutas geodésicas del IOS como referencia. Cada rama se remuestrea por longitud de arco, se reconstruye mediante controles dispersos de Catmull-Rom centrípeta/Bézier y se regulariza minimizando flexión. Los apoyos y nudos permanecen fijos. La suavidad se comprueba con el radio real del tubo para evitar pliegues locales.

Las dos ramas principales se construyen completas, con orientación continua de su sección. Sus nudos ya no crean tres tubos independientes con tapas interiores. Las conexiones al frame, sleeve y otros refuerzos utilizan el constructor Coons-Hermite tangente del refuerzo manual: cuerpo recortado, aros coincidentes y huella adaptada al apoyo. La huella automática se limita a1,2 radios y no añade el volumen central del collar manual.

El constructor detecta intersecciones de la piel resultante. Cuando es necesario, regulariza exclusivamente la malla nueva a0,08 mm y aplica un filtrado leve; nunca remalla el IOS, el frame ni los originales. Después vuelve a comprobar cierre, intersecciones propias, obstáculos y dimensiones del cuerpo. La opción manual mantiene su comportamiento previo por defecto.

## Apoyo sobre el IOS

La referencia geodésica continúa certificada sobre la triangulación con tolerancia0,02 mm. El eje del tubo suavizado puede separarse de esa referencia hasta0,8 de su radio, conservando contacto del volumen. Esto permite suavizar las pequeñas irregularidades sin crear puentes elevados. El límite no es un margen clínico. También se comprueba el apoyo en secciones del cuerpo y de los collares después de regularizar: son comprobaciones muestreadas de la malla final, no una demostración continua de toda su superficie.

## Uso

En **Refuerzos**, pulsa **OPTIMIZAR FRAME**. Las ramas principales se muestran en naranja y la celosía secundaria en cian. Examina las uniones y selecciona **USAR CELOSÍA** o **Descartar celosía**. Hasta aceptar se conservan los refuerzos originales. Descartar restaura su visibilidad y retira los datos temporales de la propuesta.

## Límites

Se comprueban geometría, conectividad, apoyo, sección nominal y los obstáculos registrados. La resistencia mecánica, el espesor que deje la booleana final y la aceptación clínica siguen pendientes. Las mejoras siguientes son elegir mejor los corredores anatómicos y evaluar rigidez con condiciones de carga verificadas.
