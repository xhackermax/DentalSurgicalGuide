**Estado:** Baseline funcional

**Target:** Blender 5.2

**Principio:** KISS · SOLID · DRY · YAGNI · SoC · SSOT · Fail-Fast · DBC · Idempotencia

**Objetivo:** flujo clínico rápido, comprensible, reversible y sin botones muertos.

---

## 1. Propósito

DSG es un sistema de planificación odontológica dentro de Blender orientado a convertir datos clínicos, principalmente **DICOM/CBCT e IOS/STL**, en geometría utilizable para planificación y diseño de guías.

El programa debe comportarse como un **wizard clínico**, no como una colección de herramientas independientes.

```
```

```
PACIENTE
   ↓
DICOM / IOS
   ↓
PREPARACIÓN
   ↓
SEGMENTACIÓN
   ↓
ALINEAMIENTO
   ↓
PLANIFICACIÓN
   ↓
DSG
   ↓
RESULTADO
```

Cada pantalla debe responder únicamente a tres preguntas:

```
```

```
¿Dónde estoy?
¿Qué tengo que hacer?
¿Cómo continúo o vuelvo atrás?
```

---

# 2. Principios no negociables

### SPEC-01 · Ningún botón muerto

Todo botón visible debe:

1.  ejecutar una operación real; 
2.  cambiar un estado; 
3.  abrir una función válida; 
4.  o estar explícitamente deshabilitado indicando por qué. 

Nunca:

```
```

```
Botón visible
     ↓
clic
     ↓
nada
```

### SPEC-02 · Reversibilidad

Toda operación destructiva o que cambie una etapa clínica debe poder revertirse.

```
```

```
ESTADO A
   ↓
operación
   ↓
CHECKPOINT
   ↓
ESTADO B
```

`Atrás` restaura el estado anterior.

`Ctrl+Z` debe ser compatible con la operación cuando corresponda.

No se reconstruirá el caso desde cero si existe un checkpoint válido.

---

# 3. Arquitectura de rutas

DSG 9.6 introduce una separación estricta entre rutas.

## SIMPLE\_ARCHES

Ruta rápida.

Objetivo:

> obtener exclusivamente dos arcadas anatómicas utilizables con el mínimo procesamiento posible.

Salida obligatoria:

```
```

```
Upper_Arch
Lower_Arch
```

Cada arcada contiene dientes + estructura correspondiente fusionados.

### Prohibido en SIMPLE\_ARCHES

No generar:

-  numeración FDI; 
-  dientes individuales; 
-  nombres dentarios; 
- `teeth_req`; 
-  child workers de dientes individuales; 
- `universal_labels_path`; 
-  canal dentario como requisito; 
-  estructuras innecesarias para el flujo simple. 

El manifiesto debe reflejarlo:

```
```

```
prepared_meshes: {}
universal_labels_path: ""
```

La ruta SIMPLE no puede ejecutar silenciosamente el pipeline FDI completo y después ocultar los resultados.

Eso sería una violación de la spec.

---

# 4. Segmentación SIMPLE\_ARCHES

Debe realizarse:

```
```

```
CBCT
 ↓
TotalSegmentator
 ↓
volumen segmentado
 ↓
traducción SIMPLE
 ↓
Upper Arch
Lower Arch
 ↓
mesh
```

La traducción utiliza una tabla mínima:

```
```

```
_translate_totalseg_simple_arches
```

con lookup reducido de 256 entradas.

No debe utilizar la traducción FDI completa.

### Resultado visual

| ObjetoColor     |                |
| --------------- | -------------- |
| Arcada superior | amarillo arena |
| Arcada inferior | azul celeste   |

No deben aparecer objetos dentarios separados en el Outliner.

Resultado esperado:

```
```

```
CASE
├── Upper_Arch
└── Lower_Arch
```

No:

```
```

```
11
12
13
14
...
UpperJaw
LowerJaw
```

---

# 5. Ruta FDI

FDI constituye la ruta anatómica avanzada.

Debe mantenerse separada de SIMPLE.

Puede producir:

```
```

```
Maxilla
Mandible
Teeth
 ├── 11
 ├── 12
 ├── ...
 └── 48
Nerve / Canal
otras estructuras requeridas
```

FDI puede utilizar:

-  traducción completa; 
-  labels universales; 
-  dientes individuales; 
-  workers secundarios; 
-  postprocesamiento anatómico adicional. 

### Regla fundamental

```
```

```
SIMPLE ≠ FDI reducido visualmente
```

Son pipelines distintos.

---

# 6. Motor de segmentación

Motor principal:

**TotalSegmentator**

La instalación del motor debe ser verificable.

Estados mínimos:

```
```

```
NOT_INSTALLED
INSTALLING
READY
ERROR
```

Nunca puede permanecer indefinidamente:

```
```

```
INSTALLING...
```

Debe existir timeout o detección de fallo.

Si falla una dependencia:

```
```

```
ERROR
↓
causa concreta
↓
acción posible
```

No:

```
```

```
Error desconocido
```

---

# 7. Worker

La inferencia pesada no debe bloquear la interfaz de Blender innecesariamente.

Arquitectura:

```
```

```
BLENDER
   │
   ├── UI
   │
   └── Controller
          │
          ▼
      Worker externo
          │
          ├── TotalSegmentator
          ├── traducción
          └── postproceso
          │
          ▼
       Manifest
          │
          ▼
       Blender
```

`cbct_pipeline_worker.py` constituye una frontera arquitectónica.

Blender no debe convertirse en el proceso que realiza toda la inferencia pesada.

---

# 8. Fail-fast

Antes de comenzar una segmentación deben comprobarse:

```
```

```
DICOM válido
↓
Python worker disponible
↓
dependencias disponibles
↓
modelo disponible
↓
espacio temporal
↓
permisos escritura
↓
RAM/VRAM suficiente o ruta CPU disponible
```

Si falla el paso 3:

```
```

```
STOP
```

No deben ejecutarse los pasos 4-7.

---

# 9. Manifiesto como contrato

La comunicación Worker → Blender debe realizarse mediante un contrato explícito.

Ejemplo conceptual:

```
```

```
{
  "status": "success",
  "route_mode": "SIMPLE_ARCHES",
  "prepared_meshes": {},
  "universal_labels_path": "",
  "arches": {
    "upper": "...",
    "lower": "..."
  }
}
```

Blender no debe deducir el resultado inspeccionando arbitrariamente carpetas temporales.

El manifiesto constituye la **SSOT del resultado del worker**.

---

# 10. Máquina de estados

El wizard debe tener estados explícitos.

Ejemplo:

```
```

```
EMPTY
 ↓
CASE_SELECTED
 ↓
DICOM_IMPORTED
 ↓
SEGMENTED
 ↓
ALIGNED
 ↓
PLANNED
 ↓
GUIDE_READY
```

No se permitirá saltar arbitrariamente entre estados incompatibles.

Por ejemplo:

```
```

```
EMPTY → GENERATE_GUIDE
```

debe ser imposible.

---

# 11. Checkpoints

Cada transición importante genera checkpoint.

```
```

```
DICOM_IMPORTED
     ↓
[checkpoint_01]

SEGMENTED
     ↓
[checkpoint_02]

ALIGNED
     ↓
[checkpoint_03]
```

Un checkpoint debe contener únicamente la información necesaria para restaurar el estado.

No duplicar gigabytes de datos cuando pueda reconstruirse mediante referencias y geometría persistente.

---

# 12. ATRÁS

`Atrás` no significa simplemente cambiar de panel.

Debe significar:

> restaurar coherentemente la etapa anterior.

Ejemplo:

```
```

```
SEGMENTACIÓN
      ↓
ALINEAMIENTO
      ↓
usuario pulsa ATRÁS
      ↓
SEGMENTACIÓN
```

Los cambios exclusivos de alineamiento deben desaparecer.

La segmentación debe permanecer.

---

# 13. Ctrl+Z

Las operaciones Blender que modifiquen geometría deben integrarse con Undo siempre que técnicamente sea seguro.

Los operadores correspondientes deben utilizar correctamente:

```
```

```
bl_options = {'REGISTER', 'UNDO'}
```

cuando proceda.

Pero:

```
```

```
UNDO Blender
        +
Checkpoint DSG
```

son mecanismos complementarios, no equivalentes.

---

# 14. UI

La interfaz 9.6 abandona el aspecto de panel técnico plano.

Debe utilizar una jerarquía visual consistente basada en aproximadamente **cinco niveles/tonos azules**.

El color primario sigue siendo:

```
```

```
#19A3C2
```

El color debe comunicar jerarquía, no decorar arbitrariamente.

```
```

```
ACCIÓN PRINCIPAL
████████

acción secundaria
██████

herramientas auxiliares
████

avanzado
██
```

---

# 15. Progressive disclosure

No mostrar herramientas que todavía no son relevantes.

Ejemplo:

Antes de seleccionar ruta:

```
```

```
[ SIMPLE ]
[ AVANZADA ]
```

Después de elegir SIMPLE:

```
```

```
SIMPLE
│
├ Importar DICOM
├ Segmentar arcadas
├ Alinear
└ Siguiente
```

Las herramientas FDI desaparecen.

No deben permanecer ocupando espacio ni confundiendo al operador.

---

# 16. Feedback de operaciones

Toda operación > aproximadamente 0,5-1 s debe ofrecer feedback.

Ejemplos:

```
```

```
Preparando CBCT...
████████░░ 78 %
```

o cuando no pueda determinarse porcentaje:

```
```

```
Segmentando arcadas...
```

Idealmente con fase actual:

```
```

```
1/4 Preparando volumen
2/4 Ejecutando TotalSegmentator
3/4 Construyendo arcadas
4/4 Importando geometría
```

La UI no debe parecer congelada mientras el worker está trabajando.

---

# 17. Errores

Los errores deben ser accionables.

Malo:

```
```

```
Segmentation failed
```

Correcto:

```
```

```
No se pudo iniciar TotalSegmentator.

Dependencia:
torch

Worker:
Python 3.x

Acción:
Reparar instalación del motor
```

Los detalles técnicos extensos pueden ir a log.

La UI clínica muestra primero la causa útil.

---

# 18. Logs

Separar:

```
```

```
USER MESSAGE
DEBUG LOG
WORKER LOG
```

El usuario no debería recibir 80 líneas de traceback como primera respuesta.

Los logs sí deben conservar toda la información necesaria para diagnóstico.

---

# 19. Idempotencia

Ejecutar accidentalmente dos veces una acción no debe duplicar el caso.

Ejemplo:

```
```

```
Segmentar
Segmentar
```

no puede producir:

```
```

```
Upper_Arch
Upper_Arch.001
Lower_Arch
Lower_Arch.001
```

El sistema debe:

```
```

```
detectar resultado existente
      ↓
reutilizar / reemplazar controladamente
```

---

# 20. Nombres internos

Debe existir nomenclatura estable.

Por ejemplo:

```
```

```
DSG_CASE
DSG_UPPER_ARCH
DSG_LOWER_ARCH
DSG_IOS
DSG_IMPLANT
DSG_GUIDE
```

No depender de:

```
```

```
Cube.003
Mesh.017
Object.001
```

para lógica interna.

---

# 21. Separación UI / lógica

Los operadores Blender no deben contener toda la lógica del programa.

Arquitectura objetivo:

```
```

```
UI
 ↓
Operator
 ↓
Service / Controller
 ↓
Domain
 ↓
Worker / Blender API
```

La UI pregunta.

El controller decide.

El dominio contiene las reglas.

El worker procesa.

---

# 22. Rendimiento

Equipo objetivo mínimo razonable:

```
```

```
RAM:      16 GB
GPU:      RTX 3060 class
CPU:      Intel i5 12ª gen class
Blender:  5.2
```

SIMPLE\_ARCHES debe ser siempre significativamente más ligera que FDI.

Por definición:

```
```

```
Work(SIMPLE) < Work(FDI)
```

Una regresión donde SIMPLE consume aproximadamente el mismo tiempo, RAM y E/S que FDI debe considerarse **bug de arquitectura**, aunque el resultado visual sea correcto.

---

# 23. Uso de disco

Evitar:

-  STL intermedios innecesarios; 
-  copias duplicadas; 
-  labels que SIMPLE no utiliza; 
-  outputs FDI durante SIMPLE; 
-  temporales abandonados. 

Objetivo global del ecosistema instalado:

**≈ 2 GB cuando sea técnicamente viable**, excluyendo aquellos componentes externos cuyo tamaño haga imposible cumplirlo.

---

# 24. Tests obligatorios

La entrega de una versión no termina cuando Blender "parece funcionar".

Debe superar:

```
```

```
compileall
    ↓
unit tests
    ↓
manifest tests
    ↓
route tests
    ↓
operator registration
    ↓
ZIP integrity
    ↓
Blender smoke test
```

La 9.6.0 ya alcanzó en nuestra revisión:

```
```

```
compileall       PASS
tests puros      18/18 PASS
ZIP integrity    PASS
```

La comprobación pendiente que no debemos confundir con una validación completada es el **smoke test interactivo real en Blender 5.2**.

---

# 25. Test crítico SIMPLE

Debe existir un test que garantice explícitamente:

```
```

```
route_mode == "SIMPLE_ARCHES"
```

y compruebe conceptualmente:

```
```

```
2 arcadas
✓

dientes individuales
0

prepared_meshes
{}

universal_labels_path
""

child workers FDI
0
```

Este test evita que futuras modificaciones vuelvan a inflar SIMPLE sin que nos demos cuenta.

---

# 26. Test de botones

Debe existir un **UI Operator Audit**.

Por cada operador referenciado por la UI:

```
```

```
botón
 ↓
operator idname
 ↓
¿registrado?
 ↓
¿implementado?
 ↓
¿poll válido?
```

Resultado obligatorio:

```
```

```
DEAD_BUTTONS = 0
```

Esta comprobación es importante porque precisamente detectamos que la batería tradicional de tests no cubría completamente el registro real de la interfaz.

---

# 27. No regresión

Una nueva versión no puede romper una característica funcional anterior simplemente porque introduce una nueva.

Antes de aceptar:

```
```

```
9.6.0 → 9.6.1
```

deben compararse:

```
```

```
SPEC
+
tests
+
diff
+
smoke test
```

No basta:

```
```

```
"he cambiado solo tres archivos"
```

---

# 28. Criterio de aceptación de SIMPLE\_ARCHES

La función se considera terminada únicamente cuando:

**Entrada**

```
```

```
CBCT válido
```

**Acción**

```
```

```
Seleccionar SIMPLE
→ Segmentar
```

**Resultado**

```
```

```
Upper Arch       ✓
Lower Arch       ✓

Superior arena   ✓
Inferior celeste ✓

FDI               ✗
dientes sueltos   ✗
labels universales✗
child workers     ✗
bloqueo Blender   ✗
botones muertos   ✗
```

y posteriormente:

```
```

```
Atrás   → restaura estado anterior ✓
Ctrl+Z  → comportamiento coherente ✓
```

---

# 29. Definition of Done

Una característica DSG solo está **DONE** cuando cumple simultáneamente:

```
```

```
SPEC
  ✓
IMPLEMENTACIÓN
  ✓
TEST
  ✓
UI
  ✓
ERROR HANDLING
  ✓
UNDO / ROLLBACK
  ✓
NO REGRESSION
  ✓
```

Si falta cualquiera:

```
```

```
NOT DONE
```

Aunque visualmente funcione.

---

# 30. Constitución de DSG

Finalmente pondría estas reglas en `AGENTS.md`, porque son las que deben gobernar cualquier modificación futura:

```
```

```
1. No romper funcionalidad existente.

2. Ningún botón muerto.

3. SIMPLE debe seguir siendo SIMPLE.

4. No ejecutar trabajo que el usuario no ha solicitado.

5. Una única fuente de verdad para cada estado.

6. Toda operación destructiva debe ser reversible.

7. Fallar pronto y explicar la causa.

8. UI y lógica de negocio permanecen separadas.

9. No duplicar código ni pipelines innecesariamente.

10. Antes de añadir complejidad, demostrar que es necesaria.

11. Todo bug corregido importante genera un test de regresión.

12. Ninguna versión se declara estable sin smoke test real en Blender.
```

## Estructura SDD que usaría a partir de ahora

Con esto, **DSG 9.6.0 pasa a ser nuestra baseline**:

```
```

```
DSG/
│
├── AGENTS.md
│
├── specs/
│   └── DSG_9.6/
│       ├── spec.md          ← QUÉ debe hacer
│       ├── plan.md          ← CÓMO está construido
│       ├── tasks.md         ← QUÉ hay que implementar
│       ├── acceptance.md    ← CUÁNDO está terminado
│       └── regressions.md   ← QUÉ jamás debe volver a romperse
│
├── dsg/
│   ├── ui/
│   ├── operators/
│   ├── services/
│   ├── domain/
│   └── workers/
│
└── tests/
```

Y aquí está la parte potente: **a partir de esta SPEC yo no tocaría directamente el código cuando pidieras "añade X"**. Primero convertiríamos X en un cambio de especificación, después generaríamos el plan y las tareas, y finalmente modificaríamos el código y ejecutaríamos los tests.

Eso nos permitiría dejar de construir DSG como una torre de parches y empezar a tratar **9.6.0 como una plataforma con contrato**, especialmente ahora que SIMPLE\_ARCHES ya tiene una arquitectura genuinamente distinta de FDI y tenemos reversibilidad/checkpoints.
---

# 31. Alcance obligatorio del runtime IA dental/maxilofacial

DSG no debe tratar TotalSegmentator ni ningún otro framework médico como una instalación de anatomía corporal completa por defecto.

El perfil recomendado debe instalar y ejecutar únicamente modelos y dependencias con consumidor clínico DSG explícito.

## Alcance clínico por defecto

- dientes y FDI;
- maxilar;
- mandíbula;
- hueso craneofacial necesario;
- canal dentario inferior / canales nerviosos clínicamente relevantes;
- senos maxilares;
- estructuras craneofaciales adicionales solo cuando una función DSG documentada las utilice.

## Fuera del alcance por defecto

No descargar pesos de pulmón, abdomen, pelvis, corazón, musculatura corporal, cerebro u otras regiones sin una función dental/maxilofacial aprobada en la spec.

## Regla del megabyte útil

Toda dependencia o peso nuevo debe indicar su consumidor dentro de DSG. Si puede eliminarse sin que falle ninguna función o test clínico actual, no pertenece al perfil por defecto.

## Arquitectura objetivo

```text
DSG
 ↓
Runtime común mínimo y reproducible
 +
Pesos dentales/maxilofaciales seleccionados
 ↓
Worker externo
 ↓
Manifest explícito
 ↓
Blender
```

El addon y el runtime deben evolucionar independientemente. Actualizar el código DSG no debe obligar a redescargar gigabytes de motores ya verificados.
