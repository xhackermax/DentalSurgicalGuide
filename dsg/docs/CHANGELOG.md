# 9.15.3 — Mejora de dientes con un solo botón

- MEJORAR DIENTES reúne preparación/refinado disponible, reparación necesaria y acabado automático.
- Una sola aparición en la primera revisión después de segmentar; sin controles repetidos en DICOM o alineación.
- Tras completarse sustituye el botón por estado; desaparece al avanzar y se restablece con una nueva segmentación.
- La misma acción permite cancelar; conserva originales y evita aplicar resultados al cambiar de paso.
- Mantiene edición del IOS, cierre cóncavo y booleana posterior para implante inmediato.

# 9.15.2 — Booleana inmediatamente después del cierre cóncavo

- En Implante inmediato, cerrar el hueco hacia dentro ejecuta la diferencia con los dientes CBCT seleccionados.
- La alineación no ejecuta ni ofrece una booleana IOS prematura.
- Booleana transaccional sobre copia temporal, resultado manifold y lista de FDI aplicados para evitar duplicados.
- Un fallo conserva el cierre cóncavo y permite reintentar; preparación retentiva e implante quedan pendientes hasta completar la resta.
- Pruebas Blender con diferencia real, orden, bloqueo prematuro, integridad, reintento y deshacer nativo.

# 9.15.1 — Diente IOS y cierre cóncavo

- Después de cerrar el modelo IOS: entrar en Edición, seleccionar el diente y borrarlo con X → Vértices.
- Cierre del hueco mediante Grid Fill nativo con centro hundido y borde fijo; profundidad ajustable, 2 mm por defecto.
- Cancelar restaura el diente. Rechaza varios huecos, bordes inválidos y una profundidad que atraviese el modelo.
- Invalida retención/blockout para recalcular con la malla modificada.
- Mantiene suavizado y remesh ocultos antes/durante la segmentación.
- Pruebas Blender de geometría, controles de la etapa y deshacer nativo.

# 9.10.11 — Contratos y diagnóstico

DSG 9.10.11 — Primera fase de mejora gradual del pipeline

Contratos puros de entrada, labelmap y manifest. Diagnóstico por ejecución con etapas, duración y fallbacks. Nuevo botón Copiar diagnóstico. Trinquete automático de métricas. Mantiene motores, suavizado, geometría e historial Ctrl+Z.

Las capturas amplias bajan de 1775 a 1768 y las silenciosas de 170 a 164; las otras métricas no empeoran. Los labels de hueso/canal se conservan; la normalización no recorta valores inválidos a un diente. No presupone HU absolutos para todos los CBCT.

Esta fase no sustituye los nueve fragmentos DICOM ni RUNTIME por sesiones de escena. Esas migraciones siguen documentadas como deuda y necesitan más caracterización.

# 9.10.10 — Historial de todas las etapas

DSG 9.10.10 — Ctrl+Z en segmentación, alineación y todas las etapas DSG

Añade historial a las operaciones de modelo, casquillos, canales de fresado, revisión MPR, navegación y regreso que antes omitían UNDO. Cancela modales y callbacks pendientes antes de recuperar datos. Recupera también el estado Python de planificación y descarta cachés geométricas antiguas. Completa la presentación diferida de las etapas dentro de la misma transacción. Impide el avance automático inmediato después de deshacer.

No añade un atajo de rehacer. Las exportaciones ya escritas, las instalaciones y otros efectos externos no se eliminan con Ctrl+Z.

Verificación en Blender 5.2.2: 20 estados de segmentación/alineación/DSG, recuperación nativa y archivada con geometría, transformaciones, materiales, punteros, FDI, labels y máscaras; creación real de un casquillo con requisitos sintéticos, limpieza real de puntos; cancelación modal, loaders anidados y timers; 35 cambios sobre una pila de 32. Las pruebas de estados no sustituyen recorrer todos los botones de un caso clínico real.

# 9.10.9 — suavizado bajo demanda

DSG 9.10.9 — botón de suavizado después de segmentar

- SUAVIZAR DIENTES / DIENTES ORIGINALES en revisión FDI y alineación.
- Visual intenso por defecto; Surface Nets fiel como opción experimental con rechazo por diente y grupo de contacto.
- Cálculo externo, cancelar, caché y restauración persistente de las mallas originales.
- Referencia ICP original, FDI, materiales y transformaciones conservados.
- Informe visible por diente; no oculta los fallos topológicos de Surface Nets.
- No se modifica la velocidad ni ejecución de la inferencia.

# 9.10.7 — reducción de escalones

- Refina Windowed Sinc/Nuttall: 40 iteraciones y banda 0,02.
- Límite físico de 1,25 vóxeles nativos, máximo 0,25 mm.
- Incluye maxilar y mandíbula. Canal mandibular original.
- Conserva el volumen por componente y reduce el filtro donde no pasa los controles.
- Mantiene la topología y coordenadas originales, las etiquetas y la referencia ICP.
- Caché y cálculo bajo demanda; no se modifica la inferencia.

# 9.10.6 — suavizado medido con volumen conservado

- Sustituye el suavizado Laplaciano apenas visible por Windowed Sinc/Nuttall.
- Conserva el volumen por componente con tolerancia relativa 1e-6.
- Limita el movimiento a la mitad del menor espaciado nativo del CBCT.
- Mantiene las coordenadas originales, etiquetas, topología y referencia ICP.
- Calcula bajo demanda y reutiliza una caché invalidada por cambios de malla.
- Rechaza superficies abiertas o resultados que no pasan los límites.
- Mantiene las correcciones de segmentación inmediata, DICOM, SciPy y CUDA.

# 9.10.5 — control de superficie suave

Añade un botón reversible de suavizado visual en revisión FDI y alineamiento IOS, conserva la elección en la escena y evita que el modificador visual altere las referencias numéricas de ICP.

# 9.10.4 — inicio e individualización de la ruta inmediata

Corrige API de comprobación y carga SciPy desde el runtime privado para construir dientes después de la inferencia.

# 9.10.3 — DICOM completo y CUDA verificado

Incluye códecs DICOM; prepara y verifica PyTorch CUDA; corrige indicadores de disponibilidad; prueba los cuatro modelos en GPU con datos sintéticos.

# 9.10.2 — reparación de instalación en Windows

Detecta modelos en rutas largas, valida su carga antes del éxito, evita instalaciones concurrentes y reporta correctamente el bloqueo nativo de U-Mamba2. No incluye un modelo final U-Mamba2 ni declara tres motores listos.

# DSG changelog

## 9.10.1
- Fixed Blender add-on registration: restored the three DICOM segmentation operators as wrappers over the new multi-engine worker.
- Added a failtest that rejects any undefined operator present in the DICOM registration tuple.
- Verified all DSG/DICOM operator symbols are defined before packaging.

## 9.10.0
- Blender 5.2-only multi-engine CBCT segmentation architecture.
- TotalSegmentator 2.18.0 `teeth`, ToothSeg dual-branch and U-Mamba2 adapters.
- External inference worker with one normalized DSG label contract.
- Real checkpoint checks; no folder-only READY state.
- Legacy DenseVNet/DentalSegmentator/UniversalLab execution paths removed.
