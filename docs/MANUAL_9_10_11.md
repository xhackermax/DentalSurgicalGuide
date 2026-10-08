# Manual de instrucciones — DSG 9.10.11

## 1. Preparar e instalar

Utiliza Blender 5.2; esta publicación se comprueba en 5.2.2 LTS. Prepara el CBCT/DICOM, el escaneado intraoral IOS y una carpeta de proyecto escribible. Guarda el `.blend` y conserva los datos originales.

1. Descarga el [ZIP instalable](../releases/v9.10.11/DSG_v9_10_11_BLENDER_5_2_PIPELINE_CONTRACTS_DIAGNOSTICS.zip). El ZIP de código fuente generado por GitHub no tiene la misma estructura.
2. Guarda el caso y cancela segmentaciones, suavizados o instalaciones pendientes.
3. Abre **Edit → Preferences → Add-ons → Install from Disk**, selecciona el ZIP y activa DSG.
4. Reinicia Blender tras sustituir una versión anterior. En la vista 3D pulsa **N → DSG**.
5. Inicia una ejecución nueva: el addon exige un esquema y un `run_id` compatibles y no debe mezclar resultados de un worker anterior.

SHA-256 del ZIP original:

```text
d39ff9a4af0ddc4024582f538adf65de30d47d29d3a6986b719b337208169206
```

En PowerShell, `Get-FileHash -Algorithm SHA256` seguido de la ruta del ZIP permite comprobarlo.

## 2. Preparar y seleccionar motores

El ZIP no contiene los pesos IA. Incluye el addon y componentes DICOM Windows/Python 3.13. La preparación de motores puede requerir descargas grandes; disponer de GPU no confirma que CUDA funcione.

En DICOM consulta **Motor**, pulsa **INSTALAR / REPARAR MOTORES**, observa fase/progreso y utiliza **REVISAR** al terminar.

| Motor | Salida y requisitos |
|---|---|
| TotalSegmentator teeth | Dientes y anatomía dental/maxilofacial usada por las rutas; requiere runtime, dependencias y checkpoints válidos; CPU/CUDA según entorno |
| ToothSeg dual-branch | Dientes individuales y FDI; necesita las dos ramas y sus pesos; no crea maxilares ni canal |
| U-Mamba2 ToothFairy3 | Adaptador de modelo final; requiere Linux/CUDA y checkpoint final ToothFairy3; sin instalación nativa Windows compatible |

**READY** requiere código, dependencias y checkpoints; una carpeta no basta. **PENDIENTE** exige completar componentes. **PARTIAL** puede dejar algunos motores utilizables y otro ausente: revisa cada fila. **NO COMPATIBLE CON WINDOWS** expresa la limitación de U-Mamba2. Sus pesos SSL no sirven como checkpoint final.

No vuelvas a instalar mientras siga indicando trabajo en marcha. Si falla, conserva fase y mensaje antes de reparar.

## 3. Importar el CBCT/DICOM

Elige el CBCT mediante la carga/selección DICOM de la suite. Si hay varias series, selecciona la correspondiente y conserva juntos los archivos del estudio. Espera la lectura del volumen y revisa orientación, spacing y vistas MPR.

Un estudio incompleto, codecs o metadatos incompatibles pueden impedir procesarlo. Resuelve la causa mostrada antes de continuar con un volumen incorrecto. Los textos de interfaz pueden aparecer en inglés o español.

## 4. Segmentar según la ruta

### Implante simple

Elige **IMPLANTE SIMPLE** y un motor READY compatible con arcadas. Pulsa **SEGMENTAR 2 ARCADAS**. Revisa las dos arcadas por color antes de alinearlas con IOS. Esta ruta no exige individualizar FDI como paso obligatorio. ToothSeg se bloquea porque no produce la anatomía necesaria para ese botón.

### Implante inmediato

Elige **IMPLANTE INMEDIATO**, comprueba el FDI objetivo y pulsa **SEGMENTAR PARA IMPLANTE INMEDIATO** con un motor listo compatible. Necesita diente individual, FDI, hueso y canal.

Revisa dientes e identidades, maxila, mandíbula y canal antes de confirmar. La selección de dientes a extraer y los modelos posteriores dependen de esta revisión; completar la inferencia no confirma la planificación clínica.

### Durante el cálculo

Observa fase y tiempo transcurrido. Cargar pesos puede tardar antes de que aparezcan mallas. Espera la importación final. Si cancelas, permite la limpieza del proceso antes de iniciar otro trabajo.

## 5. Suavizar y restaurar

Después de segmentar, **SUAVIZAR DIENTES** aparece en revisión FDI y alineación. Elige:

- **Visual intenso:** acabado visual con límites de desplazamiento y conservación de volumen. No añade detalle anatómico por subdivisión ni demuestra más precisión clínica.
- **Fiel a la segmentación:** Surface Nets multilabel experimental con controles de cierre, componentes, volumen y ocupación. Puede rechazar dientes o grupos de contacto y mantener originales.

**VER RESULTADO POR DIENTE** muestra los rechazos; **DIENTES ORIGINALES** restaura las mallas guardadas. El cálculo se puede cancelar y no inicia otra inferencia. La alineación numérica conserva la referencia original.

Editar una malla invalida caché. Cambiar identidad/transformaciones durante el cálculo puede descartar el lote. Un rechazo de calidad no es una instrucción para forzar la malla.

## 6. Alinear el IOS

Importa o selecciona el IOS y úsalo como modelo intraoral en alineación. Identifica las referencias CBCT/IOS que pide el flujo y ejecuta la operación correspondiente. Revisa superposición y MPR antes de confirmar; guarda el caso. En inmediato, revisa además los dientes a extraer y los modelos que utilizará el diseño.

## 7. Diseñar y exportar

Sigue las etapas visibles y confirma sus requisitos. El flujo incluye modelo/eje/bloqueo, implantes, contorno, estructura, casquillos, irrigación, refuerzos, fresado, corte final y nombre/exportación. Utiliza las operaciones pertinentes al caso.

Revisa posiciones, dirección de fresado, anatomía relevante, ajuste y geometría. Consulta el control de calidad antes de escribir STL y resuelve sus fallos. Conserva `.blend` e informes con la exportación. Detalle: [GUIDE_EXPORT_QUALITY_GATE.md](../dsg/docs/GUIDE_EXPORT_QUALITY_GATE.md).

## 8. Ctrl+Z, historial y transporte

Ctrl+Z revierte operaciones y navegación registradas. Cancela tareas y callbacks antes de restaurar; no repite inferencia ni adelanta automáticamente el flujo. Conserva geometría, transformaciones, propiedades, referencias, FDI, labels y máscaras.

Combina deshacer nativo y copias en `scripts/dsg_history/<proyecto>/states`. Los arrays se deduplican. La recuperación archivada requiere una sola escena y modo Objeto; con varias escenas/modo Edición permanece el deshacer nativo.

Para transportar el historial lleva el `.blend` y su carpeta `dsg_history`. Las copias contienen datos del caso y no se eliminan automáticamente. STL ya escritos, descargas e instalaciones permanecen en disco. No se añade otro atajo de rehacer ni checkpoints retroactivos.

## 9. Copiar diagnóstico

En DICOM pulsa **Copiar diagnóstico** después de una ejecución/fallo. Recupera identificador, versión, motor, etapas, tiempos, estado y fallbacks. El registro persiste en `scripts/dsg_diagnostics` tras la limpieza del worker y no copia peticiones privadas ni logs libres.

Acompáñalo con versión de Blender, motor, ruta y acción que falló. No hace falta copiar manualmente `request.json` para utilizar el botón.

## 10. Problemas frecuentes

| Síntoma | Comprobación |
|---|---|
| No activa el addon | Blender 5.2, ZIP con `dsg/`, reinicio tras actualizar y mensaje de registro |
| Segmentación bloqueada | Volumen cargado, motor READY, compatibilidad de ruta y ausencia de pendientes |
| ToothSeg bloqueado en simple/inmediato | No ofrece maxilares/canal; elige motor compatible |
| U-Mamba2 pendiente en Windows | Requiere entorno Linux/CUDA y modelo final |
| Instalación PARTIAL | Estado individual de DICOM, PyTorch y motores |
| Manifest/run_id incompatible | Cancela un worker anterior e inicia una ejecución nueva |
| Surface Nets mantiene originales | Consulta motivos por diente y grupo de contacto |
| Ctrl+Z no borra STL | La escritura externa está fuera del historial de escena |
| No recupera historial archivado | Una escena, modo Objeto y carpeta `dsg_history` presente |

Consulta [VERIFICACION_9_10_11.md](VERIFICACION_9_10_11.md) para distinguir comprobaciones sintéticas y pruebas con modelos/casos reales.
