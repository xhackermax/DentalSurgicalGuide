# DSG9.22.22

El optimizador ya puede evaluar las superficies con el suavizado medido de DSG activo. No requiere aplicarlo ni desactivarlo. Conserva la malla original y repite las comprobaciones antes de aceptar. Véase docs/OPTIMIZADOR_SUPERFICIE_SUAVIZADA_9_22_22.md.

# DSG9.22.21

Corregido CAMBIAR DIENTES VECINOS: abre de nuevo la selección aunque ya haya implantes colocados. Conserva los dientes elegidos y los implantes existentes.

# DSG9.22.20

Corregido el suavizado del diente SÍ/NO en mallas reconstruidas y en resultados de suavizado en caché. Vista previa y cortador coinciden con la superficie visible. Véase docs/SUAVIZADO_EXTRACCION_9_22_20.md.

# DSG 9.22.19

18 familias y467 referencias contrastadas con las fuentes documentadas. Catálogos VEGA y Standard Plus ampliados. Regla del seno según longitud: <10mm hasta2mm con alerta; ≥10mm sin penetración (margen0mm). Se aplica en búsqueda, aceptación y alertas de la escena. Consulta docs/AUDITORIA_CATALOGOS_REGLA_SENO_9_22_19.md para fuentes, ediciones y límites.

# DSG 9.22.18

Catálogo VEGA+ corregido: 20 referencias del fabricante frente a las cuatro de 10 mm anteriores. Longitud primero, diámetro después. El panel indica si la propuesta alcanza el máximo del catálogo; esto no equivale al límite anatómico. Entrada máxima configurada en seno: 2 mm, con alerta y revisión.

# DSG 9.22.17

Prioridad de selección: mayor longitud admisible y, a igualdad de longitud, mayor diámetro. Se mantienen las comprobaciones geométricas y la revisión antes de aceptar. Esta prioridad no garantiza disponer de un implante de rescate mayor.

# DSG 9.22.16 · Espacio geométrico por cortes

BUSCAR PROPUESTA analiza una pila local de cortes del hueso, alvéolo, senos y estructuras vecinas. Calcula dónde cabe cada diámetro y longitud, ordena las medidas del catálogo y verifica los candidatos finales sobre las mallas3D. Conserva los márgenes y la previsualización aceptable/descartable, sin aplicar cambios automáticamente.

[Manual, cálculo de áreas/volúmenes y limitaciones](docs/SECCIONES_9_22_16.md). El resultado es una propuesta de encaje geométrico para revisión clínica; no certifica estabilidad primaria ni un óptimo global.

# DSG 9.22.15 · Penetración del seno hasta 2 mm

Por petición del usuario, el optimizador permite hasta **2 mm de penetración en el seno maxilar**, con alerta y profundidad medida; rechaza valores superiores o una profundidad no verificable. **Cavidad nasal: margen adicional 0 mm y penetración no permitida.** Se utiliza tanto al buscar como al revalidar antes de aceptar. Es una configuración de planificación solicitada, no una validación clínica ni un valor universal de consenso.

No modifica los márgenes de dientes, nervio o implantes ni las comprobaciones óseas: superar la comprobación del seno no garantiza que una alternativa supere las demás. El panel continúa minimalista, sin nuevos controles. La documentación de versiones anteriores es histórica.

# DSG 9.22.14 · Diferenciar revisión ósea de rechazo anatómico

En implantes inmediatos, si la alternativa de referencia respeta las comprobaciones de estructuras protegidas, anclaje geométrico y cobertura configurados, y solo falla el criterio de reserva/hueso, se muestra **Requiere revisión ósea en CBCT** en ámbar. No se etiqueta como un diagnóstico de inviabilidad clínica. Se mantienen el valor medido y el incumplimiento de la heurística, sin afirmar que el hueco sea hueso ni que sea un defecto clínico confirmado.

Este cambio corrige la interpretación/presentación, no valida clínicamente el implante ni modifica la búsqueda, la reserva de 1,6 mm, los límites ni la aceptación: la referencia sigue sin poder aplicarse como propuesta admisible. Conserva la revisión y el descarte. Las invasiones de estructuras, anclaje insuficiente, cobertura insuficiente y comprobaciones no verificables conservan su rechazo.

El ITI describe un gap facial en ciertos protocolos inmediatos; no equivale a hueso remanente, ni justifica una excepción automática. Fuente: https://academy.iti.org/academy/consensus-database/consensus-statement/-/consensus/selection-criteria-for-immediate-implant-placement-and-immediate-loading-for-single-tooth-replacement-in-the-maxillary-esthetic-zone/2305

# DSG 9.22.13 · Resultado y progreso visibles

Corrige el filtro general del panel minimalista que ocultaba los mensajes del optimizador. BUSCAR PROPUESTA muestra el estado de cálculo y, al terminar, el número de alternativas y duración. Si ninguna cumple, se ve la referencia rechazada, sus medidas y su incumplimiento; no se permite aceptarla. Los detalles técnicos siguen plegados. El material de la referencia usa el color también en su shader, para que la vista de materiales muestre rojo/cian correctamente.

No cambia el algoritmo ni los márgenes: seno y cavidad nasal mantienen 0 mm sin penetración. El implante original se conserva hasta aceptar una propuesta admisible tras revalidación.

# DSG 9.22.12 · Seno y cavidad nasal a 0 mm

El optimizador usa **0 mm de margen adicional** en senos maxilares y cavidades nasales. Sigue rechazando intersecciones y contención dentro de esas estructuras. No se autoriza penetración. Dientes, nervio, implantes vecinos y reserva ósea mantienen sus reglas. Panel minimalista sin nuevos controles.

# DSG 9.22.11 · Optimizador minimalista

Biblioteca → revisión del CBCT → **BUSCAR PROPUESTA** → revisar y aceptar o descartar. Tamaño y posición se comparan juntos. Los márgenes están protegidos y se consultan en un desplegable; ya no aparecen barras de búsqueda, cobertura, invasión del seno ni injerto.

[Manual actual, márgenes, fuentes y limitaciones](docs/PERFIL_MINIMO_9_22_11.md). El perfil distingue recomendaciones publicadas de políticas conservadoras y heurísticas del programa. La documentación de versiones anteriores que sigue a continuación es histórica.

# DSG 9.22.10 · Alternativas rechazadas y escenarios de injerto

Aunque no encuentre una alternativa admisible, el panel muestra una referencia roja con sus incumplimientos y valores. «Simular hueco a injertar» permite comparar un espacio próximo al alvéolo hasta el límite elegido: el escenario ámbar sigue siendo hipotético, no añade hueso nativo ni se puede aplicar como propuesta admisible. Se mantienen los límites de nervio, raíces, seno, cavidad nasal y anclaje apical.

«Combinar tamaño y posición» evalúa medidas y traslaciones en una misma búsqueda, respetando los límites y conservando la inclinación. Las propuestas admisibles conservan su aceptación con revalidación. [Manual y alcance](docs/COMPARACION_INJERTO_9_22_10.md).

# DSG 9.22.9 · Implante inmediato en el optimizador

En la ruta inmediata el alvéolo de la raíz extraída ya no cuenta como falta de hueso; se exige anclaje apical en hueso nativo (3 mm por defecto). [Detalles](docs/IMPLANTE_INMEDIATO_OPTIMIZADOR_9_22_9.md).

# DSG 9.22.8 · Seno maxilar en el optimizador

BUSCAR POSICIÓN y COMPARAR TAMAÑOS admiten invasión del seno maxilar hasta el límite de la planificación manual (2 mm) con alerta; la cavidad nasal mantiene 2 mm de margen. [Detalles](docs/SENO_OPTIMIZADOR_9_22_8.md).

# DSG 9.22.7 · Medición de hueso y propuestas visibles

Conserva los límites, la profundidad independiente, los criterios de tamaño y todas las bibliotecas de 9.22.6. Añade mediciones de hueso, huecos y pared alrededor del implante original y de la propuesta. Muestra el implante propuesto como sólido cian; el MPR lo sigue y se puede **ACEPTAR CAMBIOS** o **DESCARTAR CAMBIOS**. La aplicación sigue requiriendo revisión y revalidación.

Corrige la recuperación de la malla exacta tras una aplicación fallida y evita guardar una propuesta huérfana en el paso de deshacer. [Manual y alcance de las mediciones](docs/HUESO_Y_PROPUESTAS_9_22_7.md).

Las notas siguientes son históricas; para la vista previa prevalece el manual 9.22.7.

# DSG 9.22.6 · Optimizador de posición y tamaño corregido y más catálogos

BUSCAR POSICIÓN ya no hunde el implante por defecto (profundidad con límite propio, movimiento en el marco del implante, sin propuestas por ruido de muestreo). COMPARAR TAMAÑOS reconoce el implante actual, permite elegir criterio y topes y aplica medidas nominales redimensionando el implante DSG tras revalidar. Catálogo BTI completo (267 referencias) y bibliotecas Klockner VEGA/VEGA+, MIS SEVEN/C1 y Astra Tech EV. [Cambios, fuentes y límites](docs/OPTIMIZADORES_9_22_6.md).

# DSG 9.22.5 · Confirmación de retención directa

Se elimina el aviso informativo de éxito al confirmar el modelo retentivo y la segunda ventana de confirmación del botón Continuar tras revisión manual. Las comprobaciones del asiento, errores, advertencias y registro de la revisión manual se conservan.

# DSG 9.22.4 · Selección simplificada

Se elimina el botón REVISAR SELECCIÓN. Tras marcar el diente se continúa con 2 · CERRAR HUECO HACIA DENTRO, que guarda y comprueba la selección actual. El atajo P se conserva.

# DSG 9.22.3 · Ocultar antagonista al seleccionar un diente

SELECCIONAR DIENTE (C) oculta los antagonistas registrados del caso activo antes de entrar en modo Edición. Se puede volver a mostrarlos con MOSTRAR ANTAGONISTA. Comprobado en Blender: ocultación, entrada en edición y conservación de geometría/posición al cancelar.

# DSG 9.22.2 · Corrección de cerrar agujeros

Resuelve el error `NameError: name _progress is not defined` al finalizar CERRAR AGUJEROS. La función y la ruta volumétrica importan su propia referencia de progreso. Se conservan los algoritmos de geometría y de protección de la anatomía. [Corrección y verificación](docs/CIERRE_AGUJEROS_9_22_2.md).

# DSG 9.22.1 · Mayor tamaño admisible: BTI y Straumann

Bibliotecas integradas con las combinaciones listadas en la matriz del usuario: 45 BTI CORE-X y 12 Straumann Standard Plus. Primero se aplican los límites de dientes, hueso y estructuras peligrosas; después se prioriza mayor diámetro y mayor longitud. Las medidas pendientes o condicionales quedan fuera. La matriz permite preselección nominal; para validar y aplicar un implante comercial completo hacen falta su perfil real y referencia cervical. [Uso, datos y límites](docs/MEDIDAS_BTI_STRAUMANN_9_22_1.md).

Las notas siguientes son históricas.

# DSG 9.22.0 · Dos algoritmos: posición y tamaño

**BUSCAR POSICIÓN** conserva la malla y el tamaño. **COMPARAR TAMAÑOS** compara mallas reales de un catálogo de la misma familia conservando eje y plataforma. Calculan en segundo plano, muestran una propuesta y solo la aplican por acción expresa tras una nueva comprobación. [Manual, catálogo y límites](docs/OPTIMIZADORES_9_22_0.md). Es una primera implementación experimental de soporte geométrico, sin validación clínica de estabilidad primaria. El catálogo real está pendiente de aportación.

Las notas que siguen corresponden a versiones anteriores; para esta función prevalece el manual 9.22.0.

# DSG 9.21.17 · Seguridad por arcada seleccionada

El panel inferior identifica el nervio dentario inferior como zona de peligro, muestra su margen y resultado de comprobación. Sigue al implante seleccionado, incluso con implantes en ambas arcadas. [Verificación](docs/SEGURIDAD_MANDIBULA_9_21_17.md).

# DSG 9.21.16 · Inclinación continua del MPR del implante

Barra de −180° a +180° en el plano del implante seleccionado. Gira el corte alrededor del eje, conserva la posición del implante y guarda un ángulo independiente por plano. [Uso y verificación](docs/INCLINACION_MPR_9_21_16.md).

# DSG 9.21.15 · Avisos visibles de invasión sinusal

Las alertas anatómicas no bloqueantes también abren la ventana de seguridad, permanecen en el panel y muestran el halo amarillo. Los contactos bloqueantes conservan el halo rojo y el bloqueo. La posición con aviso ya no se anuncia como libre. [Corrección y verificación](docs/ALERTA_SENO_9_21_15.md).

# DSG 9.20.6 · Senos maxilares y cavidad nasal

Cuatro cavidades independientes, revisión sobre el CBCT y márgenes 3D para implantes y microtornillos. La confirmación y la exportación se bloquean si falta anatomía, revisión o separación. [Manual y límites](docs/CAVIDADES_SUPERIORES_9_20_6.md).

# DSG 9.20.5 · Margen del nervio dentario

Separación 3D al canal mandibular segmentado, independiente del margen de dientes. Control Margen nervio · mm, inicial 2 mm y ampliable hasta 10 mm. Alerta y bloqueo antes del contacto físico; también se verifica en microtornillos. [Cálculo, fuentes y límites](docs/MARGEN_NERVIO_9_20_5.md).

Ventana de alerta al entrar en contacto con una estructura protegida, identificada por FDI, y aviso rojo persistente en el panel. Espera a finalizar R/G y evita avisos repetidos para el mismo contacto. [Uso y verificación](docs/ALERTAS_SEGURIDAD_9_20_4.md).

Corrección del lag al colocar implantes y del giro con R del control de emergencia. La comprobación de contactos se realiza tras una pausa del movimiento; permite editar y bloquea la confirmación y exportación si la posición final invade el volumen de seguridad. [Instrucciones y verificación](docs/IMPLANTE_MOVIMIENTO_9_20_3.md). Las notas que siguen pertenecen a versiones anteriores.

La extracción inmediata dispone de una barra de **0 a 10 mm** y una vista previa de la prolongación radicular. El estado compara la longitud elegida con la necesaria para superar el IOS. La booleana se bloquea si falta alcance y solo confirma el resultado después de comprobar el acceso al alvéolo y la topología cerrada. Instrucciones y pruebas actuales: [EXTENSION_OCLUSAL_9_19_3](docs/EXTENSION_OCLUSAL_9_19_3.md).

Las verificaciones y notas de versiones anteriores que siguen a continuación son históricas.

Ver RELEASE_NOTES_9_11_0.txt: CBCT multi-frame ordenado por posición real (sin volumen invertido), Ctrl+Z nativo de Blender (los botones ↻ DICOM, ↻ ALINEAR y ↻ DSG vuelven al inicio de cada etapa) y alineación solo con 3 puntos. La sección "Historial reversible del pipeline" de abajo describe el sistema anterior, ya retirado.

## Base anterior: DSG 9.10.10

Carga SciPy desde el runtime privado al individualizar dientes. La comprobación de Implante inmediato usa la API vigente de los motores y mantiene el bloqueo de motores sin maxila/mandíbula.

Reparación de DICOM y PyTorch CUDA sobre la versión 9.10.2. Las funciones clínicas y el pipeline existente se conservan.

El ZIP contiene pydicom 3.0.2 y cinco paquetes de códecs compatibles con Windows/Python 3.13. INSTALAR / REPARAR MOTORES también prepara DICOM y comprueba JPEG-LS, JPEG2000 y RLE con píxeles sintéticos. No sustituye el NumPy de Blender.

El instalador detecta el runtime real de PyTorch. Con NVIDIA instala las ruedas oficiales PyTorch 2.14.1 + CUDA 12.6 y torchvision 0.29.1; la descarga CUDA ocupa unos 2.6 GB. Comprueba operaciones CUDA y convolución 3D antes de anunciar CUDA. Las reparaciones de dependencias mantienen esta variante. Sin NVIDIA conserva CPU.

TotalSegmentator y ToothSeg conservan sus pesos. Antes de completar la instalación se cargan los dos modelos de cada motor y, con CUDA, se ejecuta una prueba pequeña de la red con datos sintéticos. Se mantienen la detección de rutas largas y el bloqueo de instalaciones simultáneas.

U-Mamba2 sigue sin instalación nativa compatible en Windows. Necesita Linux/CUDA y un checkpoint final ToothFairy3; los pesos SSL no son un segmentador final. El resultado global muestra PARTIAL si este motor falta y registra por separado DICOM, PyTorch y cada motor.

Verificado en Blender 5.2.2 LTS, Python 3.13 y RTX 2070: los cuatro modelos Dataset113, Dataset115, Dataset121 y Dataset123 superan la carga y la prueba GPU. Esto comprueba el entorno y los modelos; la calidad del resultado requiere revisión clínica.

Prueba de la ruta inmediata por MCP en el CBCT abierto: completó 26 dientes con FDI, maxila, mandíbula y canal mandibular en 81.2 segundos y pasó a IMMEDIATE_FDI_REVIEW. No se confirmó ni modificó la revisión clínica.

## Suavizar dientes después de segmentar

Tras segmentar, en la revisión FDI y en alineación aparece SUAVIZAR DIENTES. El selector ofrece Visual intenso (por defecto) y Fiel a la segmentación (experimental). El cálculo se ejecuta con Python de Blender en un worker externo: no inicia otra inferencia. Durante el cálculo se puede cancelar. DIENTES ORIGINALES restaura las mallas exactas; los resultados se guardan en caché y se conservan al guardar el .blend. Solo modifica la representación de los dientes; conserva objetos, materiales, FDI y transformaciones. La alineación numérica usa siempre la malla original guardada.

Visual intenso: Windowed Sinc/Nuttall, 40 iteraciones, banda 0,02. Límite de desplazamiento min(0,25 mm, 1,25 × spacing mínimo); conserva el volumen de cada componente de la malla con tolerancia relativa 1e-6. Es un acabado visual, sin precisión anatómica validada ni control de ocupación del labelmap. No subdivide ni aumenta el número de vértices; las caras originales se representan trianguladas.

Fiel a la segmentación: Surface Nets multilabel con todos los labels presentes, en coordenadas voxel; caja ±0,45 voxel por eje (argumento VTK 0,90), 16 iteraciones, relajación 0,20. VTK >=9.7 usa Atlas con regiones completas; 9.6 usa BoundaryLabels e inversión de caras. Comprueba aristas cerradas, caras no colapsadas, correspondencia/caja, aumento máximo de vértices 10%, componentes respecto a RAW Surface Nets, volumen respecto a la máscara sin modificar y consistencia de ocupación de frontera >=99,5%. El volumen descarta cambios >2% o >50% de la banda heurística de frontera. Informa de la reducción de rugosidad; >=60% es una meta, no un requisito demostrado en todos los dientes. No rellena cavidades ni modifica labels ni aplica compensación de volumen.

Si un diente no pasa los controles, conserva la malla original. También conserva originales los dientes conectados por contactos dentales compartidos con uno rechazado, para evitar actualizaciones incompatibles de una interfaz. VER RESULTADO POR DIENTE muestra los motivos. No se afirma ausencia de todas las autointersecciones ni solapamiento volumétrico cero; ANATOMICAL por intensidad aún no está implementado. En el caso de referencia: Visual suavizó 26/26; Surface Nets aceptó 3/26 con la máscara sin rellenar. Los problemas topológicos de Surface Nets detectados en las pruebas no se ocultan rellenando caras.

Editar las mallas invalida la caché del lote. Si un objeto, identidad o transformación cambia durante el cálculo, se descarta el lote antes de aplicar. Cambiar de archivo o desactivar el addon cancela el worker. Las rutas de segmentación simple e inmediata y sus motores no se modifican.





## Historial reversible del pipeline

Ctrl+Z registra las operaciones de segmentación, alineación y las diez etapas DSG: modelo/eje/bloqueo, implantes, contorno, estructura, casquillos, irrigación, refuerzos, fresado, corte final y nombre/exportación. Incluye la navegación y los botones de regreso. Las exportaciones en disco, instalación de dependencias y otros efectos externos quedan fuera del deshacer de la escena.

El historial conserva geometría, transformaciones, referencias IOS/CBCT, propiedades y confirmaciones existentes, máscaras, semillas, FDI y labels. No repite la inferencia. Las operaciones asíncronas publican un estado solo después de importar su resultado. Ctrl+Z cancela los procesos pendientes antes de invalidar sus referencias; las herramientas de puntos con historial local siguen retirando el último punto con Ctrl+Z. No añade otro atajo.

Las copias se conservan en scripts/dsg_history/<proyecto>/states (.blend y JSON). Los arrays se deduplican por contenido y se leen con mmap; los arrays editables usan copia al escribir. El archivo del usuario no se sobrescribe. El .blend guardado conserva el enlace al historial; para transportar el caso también se necesita su carpeta dsg_history. Los estados contienen datos del caso y no se eliminan automáticamente.

Primero utiliza el deshacer nativo y, al agotarse, recupera estados archivados. Mantiene las preferencias originales de memoria y cantidad de pasos. La recuperación archivada requiere un proyecto con una sola escena y modo Objeto; con varias escenas o modo Edición permanece el deshacer nativo. Las acciones externas al addon solo tienen el historial nativo. Las copias de etapas anteriores a la instalación no se pueden reconstruir retroactivamente.

La recuperación conserva la etapa capturada: no reconstruye geometría ni adelanta automáticamente el flujo tras Ctrl+Z. Los estados de planificación externos a Scene se recuperan y las cachés geométricas se invalidan. La actualización diferida de presentación se completa antes de guardar cada operación.

DSG 9.10.10 — Ctrl+Z en segmentación, alineación y todas las etapas DSG

Añade historial a las operaciones de modelo, casquillos, canales de fresado, revisión MPR, navegación y regreso que antes omitían UNDO. Cancela modales y callbacks pendientes antes de recuperar datos. Recupera también el estado Python de planificación y descarta cachés geométricas antiguas. Completa la presentación diferida de las etapas dentro de la misma transacción. Impide el avance automático inmediato después de deshacer.

No añade un atajo de rehacer. Las exportaciones ya escritas, las instalaciones y otros efectos externos no se eliminan con Ctrl+Z.

Verificación en Blender 5.2.2: 20 estados de segmentación/alineación/DSG, recuperación nativa y archivada con geometría, transformaciones, materiales, punteros, FDI, labels y máscaras; creación real de un casquillo con requisitos sintéticos, limpieza real de puntos; cancelación modal, loaders anidados y timers; 35 cambios sobre una pila de 32. Las pruebas de estados no sustituyen recorrer todos los botones de un caso clínico real.


## Mejora gradual del pipeline

DSG 9.10.11 — Primera fase de mejora gradual del pipeline

Contratos puros de entrada, labelmap y manifest. Diagnóstico por ejecución con etapas, duración y fallbacks. Nuevo botón Copiar diagnóstico. Trinquete automático de métricas. Mantiene motores, suavizado, geometría e historial Ctrl+Z.

Las capturas amplias bajan de 1775 a 1768 y las silenciosas de 170 a 164; las otras métricas no empeoran. Los labels de hueso/canal se conservan; la normalización no recorta valores inválidos a un diente. No presupone HU absolutos para todos los CBCT.

Incluye docs/CODEMAP.md actualizado y CODEMAP_INDEX.md regenerable con clases, funciones, métodos, operadores y líneas reales; tools/gen_index.py --check detecta un índice obsoleto.

Esta fase no sustituye los nueve fragmentos DICOM ni RUNTIME por sesiones de escena. Esas migraciones siguen documentadas como deuda y necesitan más caracterización.

Copiar diagnóstico aparece en el panel DICOM. Copia únicamente el informe estructurado de la última ejecución; no incluye requests privados ni logs libres. Los registros se conservan en scripts/dsg_diagnostics. El manifest operativo privado sigue separado y contiene las rutas necesarias para importar geometría.

Comprobación de calidad: ejecutar tools/check_quality.py con un Python con NumPy. Comprueba métricas, dependencias puras y tests unitarios. La línea base no se actualiza automáticamente.

El cliente y el worker exigen schema_version=1 y el mismo run_id. Tras actualizar, iniciar una ejecución nueva; no mezcla resultados de workers anteriores. Ver docs/ARCHITECTURE_RATCHET.md para el alcance y la deuda restante.

Mapa de desarrollo: [docs/CODEMAP.md](docs/CODEMAP.md). Índice de símbolos: [docs/CODEMAP_INDEX.md](docs/CODEMAP_INDEX.md). Se regenera con python dsg/tools/gen_index.py dsg --write desde la carpeta padre del addon y se verifica también en check_quality.py.
