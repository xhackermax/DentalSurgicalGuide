> Actualización 9.22.12: por petición del usuario, seno y cavidad nasal usan margen 0 mm, con penetración bloqueada. Sustituye su fila anterior. Los demás márgenes se conservan.

# Optimizador minimalista · DSG 9.22.11

## Uso

1. Selecciona el implante o su control de emergencia.
2. Elige la biblioteca. Confirma la revisión real del CBCT y sus estructuras.
3. Pulsa **BUSCAR PROPUESTA**. Busca tamaño y traslaciones conjuntamente, conservando el eje que has colocado.
4. Revisa el resultado en el MPR. Cian: candidato que supera las comprobaciones actuales; rojo: referencia rechazada con sus incumplimientos. Solo la propuesta admisible permite aceptar tras revisar perfil/tejidos/límites protésicos y revalidar. **Descartar** recupera el original.

**Detalles y márgenes** despliega las reglas y las mediciones, sin barras de ajuste. No se modifica el implante original durante la búsqueda. Una búsqueda local sin resultado no demuestra que no exista una solución clínica.

## Evidencia y aplicación

| Estructura o criterio | Regla del optimizador | Alcance |
|---|---|---|
| Diente vecino | ≥1,5 mm de separación de superficies | Referencia ITI; la comprobación sobre toda la envolvente es conservadora respecto a una medida solo cervical. Se conserva cualquier margen manual superior. |
| Implante vecino | ≥3 mm | Referencia ITI; comprobación conservadora sobre las superficies. Se conserva un mínimo interno superior si lo hubiera. |
| Conducto dentario inferior | ≥2 mm desde su superficie segmentada | Margen de planificación habitual referido por ITI. Se conserva cualquier margen manual superior. Depende de identificar canal y variantes anatómicas. |
| Seno maxilar y cavidad nasal | 0 mm, sin penetración admitida | Configuración solicitada por el usuario; sin reserva adicional. No se presenta como un valor universal de consenso. |
| Hueso nativo | Reserva geométrica isotrópica de 1,6 mm | Proxy conservador elegido por DSG a partir de la recomendación ITI de pared vestibular >1,5 mm en sitios cicatrizados. No mide directamente el espesor vestibular ni distingue direcciones anatómicas. Puede rechazar casos que requieren valoración específica. |
| Inmediato | Conserva mínimo geométrico apical de 3 mm fuera del alvéolo | Heurística previa de DSG; no es un umbral universal de consenso ni una medición de estabilidad primaria. El hueco del alvéolo conocido se trata por separado. |

No existe un único conjunto de valores aplicable a todos los implantes, sitios y procedimientos. En particular, el consenso ITI de implante inmediato y carga inmediata en zona estética maxilar contempla un gap facial de al menos 2 mm; ese espacio NO equivale a 2 mm de hueso remanente, y su simulación genérica no certifica un caso inmediato. Esta versión no afirma evaluar completamente esa selección clínica ni el espesor facial direccional. La revisión del CBCT sigue siendo necesaria.

### Fuentes consultadas

- ITI, 7.ª conferencia, posición 3D: distancia mínima de 1,5 mm a dientes y 3 mm entre implantes. https://forum-implantologicum.iti.org/feature-article/implant-placement-and-loading-protocols-at-the-7th-iti-consensus-conference-a-narrative-review-of-the-findings-of-group-5-6001
- ITI, consenso de técnicas quirúrgicas 2023: pared vestibular >1,5 mm en sitios cicatrizados y manejo de defectos. https://academy.iti.org/academy/consensus-database/consensus-statement/-/consensus/influence-of-buccal-bone-wall-thickness-on-the-peri-implant-hard-and-soft-tissue-dimensional-changes/1901
- ITI, conferencia de imagenología: margen de seguridad de 2 mm sobre el conducto dentario referido en la evidencia revisada. https://academy.iti.org/iti-academy-consensus/CC5_Group1_4.pdf
- ITI, selección de implante inmediato/carga inmediata maxilar: gap facial ≥2 mm y necesidad de hueso de anclaje, sin convertir estabilidad clínica en una simple distancia universal. https://academy.iti.org/academy/consensus-database/consensus-statement/-/consensus/selection-criteria-for-immediate-implant-placement-and-immediate-loading-for-single-tooth-replacement-in-the-maxillary-esthetic-zone/2305

## Parámetros internos

Las propiedades antiguas se conservan para leer escenas previas, pero sus valores ya no gobiernan este optimizador. La configuración activa se obtiene siempre de optimizer_profile.py. No se admite la tolerancia anterior de invasión del seno ni una regeneración hipotética como alternativa aceptable. Los controles y el manual de 9.22.10 son históricos.

La búsqueda usa traslaciones locales de hasta 3 mm y descenso apical de hasta 1,5 mm; ángulo fijo al combinar medidas. Prueba las medidas disponibles del catálogo sin topes adicionales de diámetro/longitud y prioriza diámetro, después longitud, entre las alternativas que superan las comprobaciones. Son decisiones de búsqueda, no recomendaciones clínicas. Cobertura mínima muestreada 80 %, banda cervical libre 1 mm, muestreo y demás tolerancias numéricas continúan como heurísticas técnicas internas, sin atribuirlas al consenso. Los porcentajes de soporte no certifican estabilidad ni integración.

Los márgenes de este perfil se usan en la búsqueda y en la revalidación antes de aceptar. No se reescriben los ajustes generales de planificación manual. Las alertas generales siguen refiriéndose al original hasta aceptar; el MPR sigue la alternativa visible.

## Verificación

Pruebas unitarias del perfil y pisos de seguridad, pruebas Blender del panel compacto y sus solicitudes reales de cálculo, rechazo de valores permisivos guardados, referencia rechazada no aplicable, descarte/restauración, aplicación de medida con traslación y rollback exacto. Se verifica también el ciclo de propuesta válida con revalidación, MPR y deshacer/rehacer.
