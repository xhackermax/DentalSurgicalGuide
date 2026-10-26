# Alternativas y escenarios de injerto · 9.22.10

## Tres estados diferentes

- **Cian: propuesta admisible según las comprobaciones actuales.** Se conserva ACEPTAR CAMBIOS, la casilla de revisión y una revalidación completa con las estructuras actuales.
- **Rojo: alternativa rechazada.** Es la alternativa con menor incumplimiento según el orden heurístico descrito abajo. Puede revisarse en el MPR y descartarse. No habilita ACEPTAR CAMBIOS.
- **Ámbar: escenario hipotético de injerto.** Sigue sin ser una propuesta admisible y no habilita ACEPTAR CAMBIOS. Distingue el espacio propuesto de la geometría de hueso nativo.

El implante original mantiene malla y posición durante la búsqueda. Solo se oculta temporalmente al mostrar la alternativa. DESCARTAR CAMBIOS / CANCELAR restaura su visibilidad y el MPR, como en las versiones anteriores. Guardar/cargar y cambiar de capa mantienen la recuperación del original. Los objetos de comparación tienen las marcas de previsualización; no se convierten en implantes del plan.

## Uso

1. Selecciona implante y biblioteca. Conserva o cambia los topes de tamaño y de movimiento. Un tope de longitud 0 significa sin tope adicional al catálogo.
2. Activa «Combinar tamaño y posición» para probar medidas y traslaciones conjuntamente. Desactivado conserva la comparación de tamaño a plataforma/eje fijos.
3. Para explorar un posible injerto, elige «Simular hueco a injertar · mm». **0 lo desactiva**; no se elige automáticamente un ancho para el paciente. Modificarlo requiere volver a calcular.
4. Ejecuta COMPARAR TAMAÑOS. Revisa medida, desplazamiento, anclaje estimado, porcentaje nativo, hueco y todos los incumplimientos. Los valores del anclaje se muestran con más decimales para que un valor inferior al límite no aparezca redondeado como si lo alcanzara; esos decimales no equivalen a precisión clínica del CBCT.
5. Las comparaciones roja y ámbar solo permiten revisión/descarte. Una comparación que necesite regeneración no se etiqueta como segura ni se aplica automáticamente.

## Búsqueda conjunta

Para cada medida LISTED de la biblioteca se prueban traslaciones laterales en las cuatro direcciones del marco del implante, a media distancia y a la distancia máxima configurada. Se combinan con profundidad 0, la mitad del máximo hacia apical y el máximo hacia apical. Se conserva la inclinación; BUSCAR POSICIÓN conserva su búsqueda angular propia. No se exceden los topes de diámetro/longitud ni los límites de traslación. Es una búsqueda finita, no una prueba exhaustiva de todas las posiciones ni una garantía de tamaño óptimo global. El cálculo y el progreso son cancelables en segundo plano.

Las alternativas admisibles se ordenan por el criterio elegido (mayor diámetro y longitud, o soporte). Para las rechazadas se prioriza tener comprobaciones verificables, menos infracciones de estructuras protegidas y menor exceso de esas infracciones; después menor déficit apical, menor hueco/reserva, menor déficit de cobertura y menor movimiento. Esta clasificación es una ayuda para mostrar una referencia; no es una recomendación clínica de la mejor intervención. Una alternativa mostrada puede diferir de la encontrada en un ensayo previo si cambian parámetros o posiciones probadas.

## Escenario de injerto

Se consideran muestras de superficie fuera del hueso nativo, fuera del alvéolo ya conocido y por debajo de la banda cervical libre. Se mide su distancia a la superficie de hueso nativo y su proximidad al alvéolo original. Solo se etiqueta un escenario si todas las muestras de hueco consideradas quedan dentro del límite elegido y próximas al alvéolo. La cobertura del hueso nativo que queda fuera de ese espacio debe seguir cumpliendo el mínimo configurado.

El ancho es una distancia euclídea a superficies, no un volumen de injerto ni una medida garantizada en una dirección bucolingual. No se genera hueso, no se suma el hueco al porcentaje nativo y no se predice consolidación. Los datos conservan por separado las muestras de espacio hipotético y las de hueso real. La simulación es muestreada y puede omitir defectos pequeños.

**No se relajan** mínimos apicales, márgenes de dientes/nervios/implantes/microtornillos ni el límite del seno. La cavidad nasal mantiene su política. Una comprobación no cuantificable impide considerar el escenario elegible. Superar el límite del injerto tampoco se convierte en aceptable. La comparación sigue siendo un escenario pendiente de decisión clínica incluso si no hay otro déficit.

El algoritmo conserva las reglas de anclaje geométrico de 9.22.9: la longitud fuera del alvéolo es una estimación geométrica que no mide torque, densidad ni estabilidad primaria. Las medidas dependen de las superficies segmentadas y requieren revisión del CBCT/MPR.

## Verificación

Pruebas de búsqueda: alternativa rechazada nunca en best; estructuras protegidas prioritarias; escenario de injerto nunca admisible; tamaño/posición con límites respetados. Blender: hueco dentro/fuera del límite, porcentaje nativo idéntico al activar simulación, anclaje/nervio no relajados, previsualización roja/ámbar, aplicación bloqueada y descarte sin cambios. Se conservan las pruebas de aceptación válida, revalidación, controlador, rollback exacto, MPR, deshacer/rehacer y recuperación al cargar.
