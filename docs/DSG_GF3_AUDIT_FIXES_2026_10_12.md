# DSG · auditoría correctiva del 12/10/2026

**Canal:** `feature/generative-frame-3-geodesic-h0`, PR #1 en borrador.
**Versión interna heredada:** `9.10.11`. **Variante visible:** `GF3 EXPERIMENTAL`.
**Invariantes:** odontología/maxilofacial solamente, modo SIMPLE sin exigir FDI,
implante inmediato con FDI y nervio independiente, geometría de guía clínica
sin sustitución destructiva inadvertida, motores externos sin `pip` automático,
rollback y seguridad de los corredores de fresado.

## Corregido en el código, con cobertura incremental

- **Implante inmediato:** el ensamblaje importa su runtime DICOM en el alcance
  correcto. Si falla el segundo Ctrl+J, retira composites parciales antes
  de tocar la visibilidad de las fuentes. Aún requiere caso real Blender con
  ambas arcadas y un error inyectado después del primer Ctrl+J.
- **Segmentación automática y tejidos blandos:** `scene=context.scene`
  dentro de la función real; regresión AST para la ruta SIMPLE_DENSITY.
- **SIMPLE_ARCHES edéntulo:** `Labelmap.parse` y `ResultManifest.parse`
  tienen `require_teeth` explícito: mínimo una etiqueta de maxila (54) o
  mandíbula (53). `FULL` y otros modos siguen exigiendo FDI. El worker pasa
  la política; el cliente verifica también el modo de ejecución.
- **Worker y fallback:** idle state no lee `./status.json`; timeout
  de arranque es terminal y visible; fallback de fallo sin manifest elimina
  status viejo y reinicia la hora de comienzo. No hay bucles de fallback.
- **Implante inmediato asíncrono:** el cerrojo permanece durante retries;
  temporizador gestionado por DSG lifecycle, cancelado en Undo;
  error de arranque restituye la ruta clínica anterior.
- **FEM geodésico:** longitud de pandeo del miembro continuo, no de cada
  elemento numérico; rechazo de desplazamientos no finitos; guardia de RAM
  ANTES de reservar la matriz densa cuando no existe SciPy.
- **Historial:** se descubren `CLASSES` y `_CLASSES`; análisis solo-lectura
  no dispara la captura de la escena; vistas previas que sí mutan siguen
  siendo reversibles.
- **Servicio FEM:** valida etapa de refuerzos y previsualizaciones manuales
  pendientes también cuando se invoca fuera del operador UI.
- **Irrigación:** elimina clave JSON duplicada, conserva el punto clicado
  separadamente y alinea shoulder/trunk/rejoin entre JSON y propiedades.
- **Sleeves:** elimina la escala del implante de la matriz de pose del
  casquillo; los radios físicos provienen de parámetros de diseño.
- **Métricas:** `--update` se analiza como bandera y escribe en el
  `metrics_baseline.json` indicado, nunca en un fichero llamado `--update`.
- **VTK:** documentación de dependencia específica de SUAVIZAR DIENTES,
  sin instalaciones automáticas invasivas.

## Pendientes críticos: **NO APROBAR USO CLÍNICO**

1. **P0:** `OPTIMIZAR FRAME` todavía utiliza comprobación de centrolinea
   insuficiente en el modelo recto. Faltan volumen barrido completo, corredor
   de fresado extendido, objetos reales de irrigación y microtornillos.
   El preflight estricto de la red geodésica experimental no valida por sí
   mismo los refuerzos definitivos ni la luz post-booleana.
2. **P0:** se necesitan pruebas Blender 5.2 end-to-end con casos anonimizados:
   pipeline CBCT→IOS→guía→refuerzos→canales→Boolean→Undo→STL,
   incluido fallo después de construir la primera arcada.
3. **P0:** soporte mecánico FEM realista y benchmarking de pandeo de vigas
   curvas/soldadas. El nuevo largo completo evita falsos ratios por
   discretización, pero NO sustituye comprobación de estabilidad geométrica.
4. **P1:** invalidación de resultados FEM por cambios de sleeve/frame,
   limpieza de vistas previas antiguas, cache/memoria, comparación coherente
   entre FEM recto y geodésico, límites de historial cifrado/deletion.
5. **P1:** `BUILD_MANIFEST.json` base 9.10.11 es evidencia histórica de la
   versión publicada y no identifica esta rama; generar un manifiesto
   experimental diferenciado y comprobar CODEMAP/ratchet, sin sustituir
   hashes originales ni elevar artificialmente la línea base.
6. **P2:** botón SUAVIZAR DIENTES condicionado a VTK existente, además de la
   documentación corregida; tests con instalación limpia sin motores.

**CI actual:** `dsg/tests_pure/` y smoke Blender 5.2 básicos.
Un verde de ambos NO es conformidad clínica, manufactura ni FEM validado.
No modificar `main` ni fusionar PR #1 hasta completar las puertas anteriores.
