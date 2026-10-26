# DSG 9.22.0 · Posición y tamaño independientes

Primera implementación experimental. Propone alternativas según geometría segmentada; no calcula estabilidad primaria, torque, ISQ, densidad ósea fiable ni una posición clínicamente óptima. No es una validación para fabricar una guía o realizar cirugía.

## Qué hace cada botón

En el paso del implante, abre **Propuestas de posición y tamaño · experimental**.

| Botón | Qué puede cambiar | Qué conserva |
|---|---|---|
| BUSCAR POSICIÓN | Traslación y dos inclinaciones, dentro de los límites elegidos | Malla y tamaño del implante |
| COMPARAR TAMAÑOS | Malla concreta de otra medida del catálogo de la misma familia | Plataforma y orientación del eje |
| APLICAR PROPUESTA | Aplica únicamente la propuesta visible, tras comprobar de nuevo los datos actuales | El resto de objetos clínicos |
| DESCARTAR / CANCELAR | Cancela el cálculo y elimina la previsualización y sus datos temporales | Implante original, si aún no se había aplicado |

Los dos motores son independientes. No se ejecutan automáticamente uno después del otro: si aplicas un tamaño, puedes volver a buscar posición para ese tamaño y revisar el resultado. No se promete una solución global mediante estas búsquedas locales.

## Uso

1. Coloca aproximadamente un implante endoóseo y selecciónalo o selecciona su control de emergencia. Termina cualquier edición de malla.
2. Revisa la segmentación y el campo del CBCT, incluidas las estructuras recortadas. Marca la casilla de revisión solo después de hacerlo. Se exige hueso nativo separado de los dientes, canal mandibular para un implante inferior y las cuatro cavidades para uno superior. Un modelo cerrado del IOS no sustituye al hueso nativo.
3. Para posición, configura desplazamiento e inclinación máximos y pulsa **BUSCAR POSICIÓN**. La búsqueda usa una copia local de las mallas en otro proceso de Blender; no mueve el implante mientras calcula.
4. Para tamaño, indica la familia y selecciona su archivo de catálogo. Pulsa **COMPARAR TAMAÑOS**. Sin catálogo real no se ofrecen medidas inventadas. Las mallas con escala o deformación no aplicada se rechazan para esta comparación.
5. La propuesta aparece como malla de alambre no seleccionable. Revisa plataforma, eje, MPR, perfil cervical, tejidos y límites protésicos. La casilla de revisión final vuelve a quedar desmarcada en cada búsqueda.
6. **APLICAR PROPUESTA** ejecuta una nueva evaluación de esa alternativa con la anatomía actual. Si no cumple, se rechaza. Cambiar de caso, borrar el implante, entrar en edición o cambiar anatomía, pose, márgenes, parámetros o archivos de catálogo invalida el resultado. La aplicación espera a que termine una herramienta modal como R/G.
7. Después de aplicar, revisa nuevamente el MPR y los avisos habituales de DSG. La aplicación utiliza pasos del historial de Blender. Descartar después de aplicar no revierte una aplicación anterior.

## Qué se calcula

Primero se aplican restricciones de separación: caras completas, intersección e inclusión entre sólidos y cotas de distancia. Un resultado incierto se rechaza; una puntuación alta nunca compensa una restricción incumplida. Se consideran dientes vecinos segmentados, nervios, cavidades superiores, otros implantes y microtornillos, aunque estén ocultos. Los dientes marcados para extracción inmediata se excluyen de los obstáculos dentales. Solo se toma anatomía del caso activo, sin copias de checkpoints ni objetos obsoletos.

Esta búsqueda usa una política conservadora: separación positiva de 2 mm para todas las cavidades superiores; canal mandibular con su margen configurado, mínimo 2 mm; otros implantes con la separación existente en DSG; dientes con el margen dental configurado. Son límites de esta implementación, no una prescripción universal. El optimizador no utiliza la tolerancia de penetración sinusal de la planificación manual existente.

Una malla de implante abierta usa una envolvente convexa para las exclusiones, sin reparar ni deformar el original. Esto puede rechazar alternativas viables. Hueso y obstáculos anatómicos abiertos o no verificables detienen la evaluación. No se aplican modificadores ocultamente: los modificadores activos deben estar aplicados o desactivados antes de evaluar.

Después se muestrean 384 puntos sobre la superficie real del implante, ponderados por área. Se informa el porcentaje que queda dentro del hueso nativo segmentado y el porcentaje que además supera la **reserva de pared local** elegida. Es una aproximación muestreada; no demuestra que toda la superficie tenga apoyo ni mide contacto mecánico. Tampoco diferencia por sí sola hueso cortical/trabecular o identifica hueso enfermo, injertos o errores de segmentación.

Posición ordena por `2 × fracción con reserva + fracción dentro de hueso`. Tamaño ordena por área superficial muestreada con reserva entre las opciones admisibles del catálogo. Puede favorecer medidas mayores; la revisión protésica y cervical sigue siendo obligatoria. Cuando no se reconoce de forma verificada el implante actual dentro del catálogo, se muestra una comparación entre alternativas, no una mejora demostrada frente al original.

La reserva local representa sensibilidad a la proximidad de una pared segmentada. **No es una predicción de pérdida ósea**, remodelado individual, reabsorción uniforme ni garantía de estabilidad futura. Los valores iniciales de búsqueda, reserva y cobertura son parámetros experimentales de evaluación, sin validación clínica. No se predice estabilidad a partir de valores grises del CBCT.

## Catálogo

La interfaz requiere un JSON preparado con las mallas reales. Esta versión no incluye un catálogo comercial. Formato de integración:

```json
{
  "schema_version": 1,
  "units": "mm",
  "family": "SISTEMA_Y_MODELO",
  "implants": [{
    "id": "REFERENCIA_REAL",
    "diameter_mm": 4.0,
    "length_mm": 10.0,
    "platform_local_mm": [0, 0, 5.0],
    "axis_local": [0, 0, 1],
    "vertices_path": "referencia_vertices.npy",
    "faces_path": "referencia_caras.npy",
    "reference": "Referencia a las instrucciones y al modelo del fabricante"
  }]
}
```

Este bloque es un ejemplo de formato, no un implante disponible ni un catálogo instalable. Los archivos NPY contienen coordenadas Nx3 y triángulos Mx3 sin objetos Python. Las rutas pueden ser relativas al JSON. La malla debe estar centrada en Z, con eje +Z hacia coronal y plataforma en el extremo superior; diámetro y longitud deben coincidir con la geometría dentro de 0,1 mm. Los modelos que necesiten otra referencia cervical requieren adaptar previamente su contrato; no se interpretan automáticamente cuellos de implantes tissue-level o posiciones subcrestales. La referencia documental aportada no equivale a verificar las instrucciones del fabricante.

No se escala una malla genérica para fingir tamaños comerciales. Se copian las mallas del catálogo al cálculo y se comprueban sus archivos al aplicar. Los datos de cada cálculo permanecen en una carpeta temporal local mientras la propuesta esté disponible y se eliminan al descartarla, sustituirla, aplicarla o descargar el módulo; un cierre anormal de Blender puede dejar temporales.

## Corrección adicional de contacto con cavidades

Se añade una comprobación de superficie completa al análisis superior habitual. Una cavidad puede atravesar una cara sin contener los vértices del implante. Si se detecta ese contacto y no se puede cuantificar su profundidad con el método existente, se bloquea con el mensaje de profundidad no cuantificable. Esto evita anunciar ese caso como libre. No supone haber certificado la profundidad máxima de cualquier intersección sinusal.

## Verificación y siguientes mejoras

Las pruebas incluyen búsqueda local con tamaño fijo; catálogo con eje/plataforma fijos; rechazo de escala, restricciones incumplidas y datos inválidos; cruce de caras y contención; hueso abierto; proceso real en segundo plano; previsualización sin mover el original; aplicación con nueva comprobación; cambios de pose y catálogo; cancelación; rechazo de anatomía perteneciente a otra escena. Los escenarios de posición y catálogo son sintéticos y no constituyen validación clínica en pacientes.

Próximas mejoras: importador de bibliotecas comerciales; contratos por modelo para cuello, plataforma y nivel de colocación; envolvente protésica y tejidos como restricciones cuantitativas; diferenciación del soporte apical y cortical; escenarios de remodelado con incertidumbre; evaluación de confianza de la segmentación; búsqueda conjunta alternada con trazabilidad; validación clínica independiente. Los implantes yuxtaóseos requieren otro método y quedan fuera de estos motores endoóseos.
