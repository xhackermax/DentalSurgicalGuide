# Hueso y propuestas visibles · DSG 9.22.7

## Cambios conservados de 9.22.6

Movimiento en el marco del implante, profundidad independiente y fija por defecto, umbral frente al ruido de muestreo, selección por tamaño o soporte, topes de diámetro/longitud, zona cervical libre y bibliotecas BTI, Klockner, MIS, Astra Tech y Straumann. No se modifican los límites de seguridad, cobertura, reserva o profundidad del caso abierto. La revisión de las fuentes comerciales de los catálogos no forma parte de esta corrección.

## Medición del hueso

Se reutilizan las consultas BVH y la comprobación de contención del sistema de seguridad sobre la superficie de hueso nativo segmentado. El hueso se mantiene separado de dientes y otras estructuras. Un diente, un alvéolo vacío o una cavidad de aire no se consideran soporte.

La cobertura mide 384 muestras de superficie; la reserva mide cuántas están dentro del hueso y alejadas de su borde más que el valor configurado. Además, se miden 16 direcciones radiales en 8 alturas (128 rayos) sobre la envolvente nominal del implante:

- Si el origen está dentro del hueso, distancia desde el borde del implante hasta la primera salida del hueso: pared radial.
- Si está fuera, distancia hasta la primera entrada al hueso: hueco, y distancia desde esa entrada hasta su primera salida: espesor de la primera pared.
- Sin intersección con el hueso en esa dirección: dirección sin hueso detectado.

El panel muestra cobertura y reserva del original, pared radial mínima medida, hueco radial máximo medido y número de direcciones sin hueso. Muestra también los datos de la propuesta si la hay. Los resultados completos por altura/ángulo se incluyen en el resultado del cálculo.

Estas nuevas mediciones son diagnósticas: no rebajan ni sustituyen las comprobaciones completas de reserva y estructuras protegidas. No convierten hueso lejano en contacto. El cálculo continúa rechazando alternativas que incumplen los límites configurados y muestra los motivos. Si no hay alternativa admisible, el original permanece intacto.

Los rayos y las muestras no certifican toda la pared ni predicen estabilidad primaria, torque, densidad o remodelado. Las medidas dependen de la segmentación. Deben revisarse con el CBCT/MPR; el método no establece por sí solo una posición clínicamente óptima.

## Uso

1. Selecciona el implante o su control de emergencia. Revisa las estructuras y el CBCT.
2. Ejecuta BUSCAR POSICIÓN o COMPARAR TAMAÑOS con tus límites. El progreso indica la preparación y la medición.
3. Si hay alternativa admisible, aparece el implante sólido cian. El original, el control y su aro se ocultan temporalmente; sus datos se conservan. El MPR sigue la propuesta. Las alertas generales del implante original siguen correspondiendo al original hasta aceptar; la propuesta se comprueba por su cálculo propio.
4. Revisa las mediciones y la casilla de perfil, tejidos y límites protésicos. ACEPTAR CAMBIOS revalida antes de aplicar. DESCARTAR CAMBIOS / CANCELAR recupera el original.

En bibliotecas nominales se muestra una referencia sólida DSG que cabe dentro de la envolvente evaluada; no es CAD comercial. Se conserva la estrategia de 9.22.6: las búsquedas de posición y de tamaño son independientes, y comparar tamaños conserva plataforma y eje.

Cambiar de escena, implante o capa de vista descarta la propuesta. Abrir un archivo guardado con una propuesta recupera el original sin aplicarla. Al aceptar, se restaura el original antes de guardar el paso de deshacer; así Ctrl+Z no recupera una propuesta sin controles.

## Correcciones de integridad

Si falla una aplicación nominal, se conserva/restaura la malla original exacta, incluida cualquier edición local, y los datos del catálogo/plataforma. Los valores de propiedades de Blender se copian antes de borrarlos para evitar referencias a datos eliminados.

## Verificación

Pruebas sintéticas en Blender 5.2: pared de 3 mm, hueco de 3 mm, direcciones sin hueso, conservación de posición; aplicación nominal y rollback exacto; propuesta sólida, MPR, aceptar/descartar, capas de vista, archivo guardado y deshacer/rehacer. Regresiones de nervio, seno/cavidad nasal, movimiento interactivo, alertas, microtornillos y estructuras vecinas. Son pruebas de software, no validación clínica.
