# DSG 9.10.10 · Blender 5.2

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
