# Pasos opcionales y SIGUIENTE · DSG 9.15.8

El análisis del flujo distingue omitir una mejora opcional de avanzar después de comprobar un resultado obligatorio. SIGUIENTE no cambia manualmente el número del paso para evitar esas comprobaciones.

| Paso o acción | ¿Puede omitirse? | Cómo continuar |
|---|---|---|
| Instalar motores | Si el entorno ya está preparado | El flujo reconoce el entorno existente. |
| Paciente, CBCT y segmentación | No | Cargar y segmentar antes de confirmar. |
| MEJORAR DIENTES | Sí | CONFIRMAR; en inmediato, fijar antes los dientes de extracción. |
| Elegir dientes a extraer | Obligatorio en ruta inmediata | FIJAR DIENTES → CONFIRMAR. |
| Alineamiento IOS–CBCT | No | ALINEAR → SIGUIENTE, conservando su validación. |
| Cerrar agujeros y generar modelo cerrado | Solo si el IOS ya está cerrado | Usar el modelo cerrado existente. |
| Eliminar un diente y cierre cóncavo | Opcional en ambas rutas | SIGUIENTE omite la eliminación manual. En inmediato aplica la booleana sobre el IOS cerrado antes del modelo retentivo. |
| Modelo retentivo | No | PREPARAR y CONFIRMAR MODELO RETENTIVO. |
| Alivio local adicional | Sí | Confirmar el modelo válido sin aplicar alivio adicional. |
| Implantes | Debe existir al menos uno válido | SIGUIENTE confirma los implantes con las comprobaciones de seguridad. |
| Implantes adicionales, paralelización y revisión DICOM | Sí | SIGUIENTE conserva la planificación válida. |
| Contorno | No | SIGUIENTE aparece al disponer de los puntos necesarios y confirma el contorno. |
| Crear estructura | No | CREAR ESTRUCTURA antes de continuar. |
| Microtornillos | Sí | SIGUIENTE confirma la estructura sin añadir fijación opcional. |
| Cilindros | No | SIGUIENTE tras crear los cilindros con medidas vigentes. |
| Irrigación | Sí | SIGUIENTE resuelve la ausencia de conductos y avanza a refuerzos. |
| Apertura lateral | Sí | SIGUIENTE avanza sin aplicar una ventana pendiente. |
| Refuerzos automáticos o manuales | Sí | SIGUIENTE resuelve la ausencia de refuerzo y avanza a canales de fresado. |
| Canales de fresado | No | Crear canales y después SIGUIENTE. |
| Corte final | No | FINALIZAR GUÍA y después SIGUIENTE. |
| Grabado del nombre y animación | Sí | EXPORTAR STL directamente. No hace falta otra pantalla ni botón de avance. |
| Exportación | Es la salida del pipeline | EXPORTAR STL mantiene sus comprobaciones. |

## Comportamiento en las ramas opcionales

SIGUIENTE aparece también cuando hay una vista previa de microtornillo, irrigación o refuerzo. Su descripción indica que descarta lo pendiente de confirmar. Si quieres conservar esa vista previa, usa primero USAR MICROTORNILLO, USAR ESTE CONDUCTO o USAR REFUERZO.

- **Microtornillos:** descarta la vista previa pendiente, incorpora los microtornillos ya confirmados si los hay y confirma la estructura antes de pasar a cilindros.
- **Irrigación:** descarta el conducto pendiente. Si hay conductos confirmados, los aplica; si no los hay, registra que se omite la irrigación. Después avanza a refuerzos, omitiendo la apertura lateral no aplicada. Para elegir una apertura lateral, resuelve antes la irrigación con APLICAR IRRIGACIÓN y utiliza sus controles de ventana.
- **Refuerzos:** descarta la vista previa pendiente y aplica los refuerzos confirmados. Si no hay refuerzos, registra que se omiten. Conserva un refuerzo ya aplicado al volver a este paso.

En los pasos obligatorios se unifica el texto de los botones de avance a SIGUIENTE, conservando los operadores de confirmación existentes. CONFIRMAR en la segmentación y CONFIRMAR MODELO RETENTIVO mantienen sus nombres y funciones específicas.

Si falla una comprobación o una aplicación geométrica, SIGUIENTE no ejecuta la acción posterior. Las pruebas incluyen transiciones de los operadores originales en Blender, disponibilidad del botón durante vistas previas y conservación de las rutas de trabajo confirmado.
