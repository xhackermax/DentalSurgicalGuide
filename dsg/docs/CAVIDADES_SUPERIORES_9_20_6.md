# DSG 9.20.6 · Protección de senos maxilares y cavidad nasal

Esta versión experimental incorpora cuatro superficies de protección: seno maxilar izquierdo, seno maxilar derecho, cavidad nasal izquierda y cavidad nasal derecha. Se mantienen independientes del hueso, del IOS y de la guía.

## Qué cambia

El motor TotalSegmentator ya predecía los senos, pero DSG descartaba sus etiquetas al convertir el resultado dental. Ahora conserva las etiquetas 56 y 57. El modelo oficial `head_glands_cavities` aporta las cavidades nasales, etiquetas 58 y 59. No se interpreta cualquier región oscura del CBCT como un seno.

Los implantes superiores y los microtornillos superiores se comprueban frente a estas superficies con los controles **Margen seno · mm** y **Margen nasal · mm**. Son independientes del margen dental y del margen neural. El valor inicial del software es 2 mm y puede ampliarse hasta 10 mm. No representa un criterio clínico universal ni autoriza una intervención.

El cálculo utiliza la distancia entre superficies en 3D, incluyendo ápice y caras laterales. También detecta penetración e inclusión dentro de una cavidad. Se trabaja con límites inferior y superior de distancia; no se presenta un límite como una distancia exacta. Si la malla del implante está abierta, se verifica una envolvente convexa conservadora sin cambiar el implante original. Las cavidades necesitan mallas cerradas. Una distancia no verificable, una cavidad ausente o una revisión pendiente bloquean confirmar y exportar.

## Uso

1. Segmenta el CBCT. Con TotalSegmentator, las cavidades se preparan junto al resultado dental, como candidatos pendientes de revisión.
2. En un caso anterior o generado por otro motor, pulsa **IDENTIFICAR SENOS Y CAVIDAD NASAL**. Recupera solamente las cavidades y conserva dientes, hueso, IOS y posiciones de implantes. Requiere el CBCT preparado; si su caché se ha perdido, recarga y segmenta el estudio. La identificación se ejecuta en un proceso aparte y muestra su progreso.
3. Pulsa **REVISAR SENOS Y CAVIDAD NASAL**. Contrasta las superficies con los cortes del CBCT, especialmente el suelo junto al sitio del implante. Corrige una predicción incorrecta antes de continuar. **ASIGNAR MALLA DE CAVIDAD** permite etiquetar una superficie previamente delineada sobre el CBCT; no dibuja ni valida automáticamente la anatomía.
4. Pulsa **CONFIRMAR CAVIDADES SUPERIORES** y marca que has revisado el CBCT. Si alguna cavidad llega al límite del estudio, exige además una revisión expresa del suelo relevante pese al campo parcial. El cierre artificial de una malla en el límite del volumen no demuestra que se haya observado la anatomía fuera de ese límite.
5. Ajusta los dos márgenes. Coloca y rota el implante con normalidad. Tras la pausa del movimiento, la alerta identifica la estructura cuyo margen se invade. Las cavidades pueden permanecer ocultas: se siguen comprobando.
6. Antes de confirmar o exportar, DSG repite la comprobación con geometría fresca. Cambiar la forma o posición de una cavidad invalida su revisión y exige confirmarla de nuevo.

La identificación se ejecuta localmente. El primer uso puede descargar pesos oficiales; el estudio no se envía para la predicción y se desactiva la telemetría de uso de TotalSegmentator. Si el modelo no puede ejecutarse, la protección queda pendiente, nunca se informa como segura por omisión.

## Límites clínicos

Los modelos usados se entrenaron para CT; las predicciones sobre CBCT requieren revisión humana. Los valores del CBCT no equivalen necesariamente a HU calibradas. Mucosa engrosada, opacificación, artefactos, enfermedad y campos parciales pueden alterar la representación de las cavidades. Una segmentación de aire por sí sola no demuestra la integridad de la membrana ni la ausencia de patología.

La elevación del suelo sinusal es una intervención específica que requiere planificación propia. Esta versión no la autoriza ni permite ignorar una alerta. El margen neural tampoco se reutiliza como criterio universal para los senos.

El paquete conserva su condición **GF3 EXPERIMENTAL / sin aprobación clínica**. Las pruebas de software y la predicción real no equivalen a validación clínica para fabricar guías o operar.

## Verificación local del 13-10-2026

Se recuperaron las cuatro cavidades del CBCT local: 452426 y 635985 vóxeles de senos; 1624263 y 1229910 de cavidades nasales. La predicción local tardó aproximadamente 62 s para senos y 52 s para nariz. Las cuatro superficies resultaron cerradas, sin bordes abiertos ni aristas no manifold. La copia del caso conserva las mallas y transformaciones originales y deja la revisión pendiente. Ambas cavidades nasales están recortadas por el campo de visión.

Pruebas de Blender: estructuras ocultas, margen de seno y nasal, invalidación al mover geometría, revisión de campo parcial, exclusión de copias de restauración y conservación de anatomía ante importación fallida. Regresiones comprobadas: margen neural, R/G del control, alertas, microtornillos y dientes vecinos. La suite pura incluye 187 pruebas. El control global de calidad mantiene desviaciones históricas de métricas; no se presenta como aprobado.

## Futuras mejoras

- Validación clínica específica del modelo nasal sobre CBCT y revisión de mucosa y artefactos.
- Delimitación asistida del suelo y comparación de superficies directamente en cortes multiplanares.
- Gestión explícita de estudios con campo limitado y estructuras pertinentes al sitio, sin asumir ausencia de anatomía.
- Preparación anticipada de índices geométricos para reducir la primera comprobación de superficies grandes.
- Planificación separada de elevación sinusal, con sus propios requisitos clínicos.

## Fuentes primarias

- [TotalSegmentator: clases teeth y head_glands_cavities](https://github.com/wasserth/TotalSegmentator).
- [AAOMR: CBCT y evaluación anatómica del sitio de implante](https://aaomr.org/common/Uploaded%20files/Position%20Papers/aaomr_implants_position_paper.pdf).
- [ITI: precisión de medidas CBCT y margen respecto a estructuras anatómicas](https://academy.iti.org/academy/consensus-database/consensus-statement/-/consensus/accuracy-of-linear-measurements-on-cbct-images-related-to-presurgical-implant-treatment-planning/1819).
- [ITI: principios de elevación del suelo sinusal](https://academy.iti.org/academy/theory-and-principles/learning-module/-/module/principles-of-sinus-floor-elevation/4301).
