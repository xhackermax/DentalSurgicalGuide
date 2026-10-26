# Auditoría de catálogos y regla del seno — DSG 9.22.19

Verificado el 15 de octubre de 2026.

## Alcance

Se contrastan las 18 familias incorporadas en DSG con las referencias de las ediciones citadas y la tienda BTI consultada. Esto confirma la integridad respecto a esas fuentes; no afirma disponibilidad comercial actual en todos los países ni incluye todos los productos de cada fabricante. El catálogo personalizado depende del archivo aportado por el usuario y no puede declararse completo sin su fuente externa.

## Resultado

| Familia | Referencias verificadas | Medidas diámetro × longitud distintas | Resultado |
|---|---:|---:|---|
| MIS_SEVEN | 26 | 26 | Coincide con la fuente |
| MIS_C1 | 19 | 19 | Coincide con la fuente |
| ASTRA_EV_S | 32 | 32 | Coincide con la fuente |
| ASTRA_EV_C | 12 | 12 | Coincide con la fuente |
| ASTRA_PROFILE_EV | 24 | 12 | Coincide con la fuente |
| KLOCKNER_VEGA | 20 | 20 | Corregido:16→20; añadidos Ø3,5/4,0 ×16/18mm |
| KLOCKNER_VEGA_PLUS | 20 | 20 | Coincide con la fuente |
| STRAUMANN_SP | 47 | 16 | Ampliado:12 medidas de matriz→47 referencias /16 medidas |
| BTI_CORE | 50 | 50 | Coincide con la fuente |
| BTI_P25 | 7 | 7 | Coincide con la fuente |
| BTI_COREX | 60 | 60 | Coincide con la fuente |
| BTI_P30X | 8 | 8 | Coincide con la fuente |
| BTI_EXT_UNI | 14 | 14 | Coincide con la fuente |
| BTI_EXT_UNIPLUS | 14 | 14 | Coincide con la fuente |
| BTI_TINY | 26 | 26 | Coincide con la fuente |
| BTI_INT_UNIPLUS | 33 | 33 | Coincide con la fuente |
| BTI_INT_UNI | 32 | 32 | Coincide con la fuente |
| BTI_P30 | 23 | 23 | Coincide con la fuente |

Total:467 referencias. Las distintas superficies/plataformas de Straumann se conservan con su referencia individual aunque compartan diámetro y longitud.

BTI:303 entradas de tienda=267 referencias individuales+36 agrupaciones acabadas en xx, que no son implantes adicionales. Los diámetros y longitudes de las 267 referencias coinciden con sus nombres de producto.

VEGA+ ya estaba corregido en9.22.18 y mantiene20 referencias. MIS SEVEN:26; C1:19. Astra EV S:32; EV C:12; Profile EV:24, conservando PS y PC.

La matriz Excel original y su JSON se conservan sin modificación (SHA-256 del Excel:9aaf6fb5f1ce96e1dcb0622ade2db41105468ee980fb878502500bc658b12857). Standard Plus ahora utiliza referencias verificadas del fabricante; no se inventan códigos para llenar combinaciones.

## Regla del seno solicitada

- Longitud menor de10mm:entrada máxima2mm, con alerta por cualquier entrada cuantificada.
- Longitud de10mm o mayor:0mm de margen adicional y ninguna entrada permitida.
- Se mantiene la cavidad nasal sin entrada y el resto de márgenes existentes.
- Regla común en búsqueda por cortes, comprobación3D, búsqueda de posición, revalidación antes de aceptar y alertas de la escena. Se considera la longitud física transformada para que una escala no eluda el umbral.
- Es una preferencia de planificación solicitada por el usuario; no se presenta como recomendación de consenso ni como garantía clínica.
- Los resultados previos caducan al cambiar el perfil. Los implantes ya aceptados se conservan y se vuelven a evaluar.

## Fuentes

- BTI_*: https://shop.bti-biotechnologyinstitute.com/catalogo?category=49629&delta=60 · Live shop 2026-10-15, pages1-6
- KLOCKNER_*: https://www.zauchnerdentalprodukte.at/wp-content/uploads/2025/09/VEGA_IM_KLOCKNER_EN.pdf · tablas en páginas5y27
- MIS_SEVEN: https://mis-implants.com/upload/pdf/Products/MIS_Internal_Hexagon_Catalog.pdf · 2025
- MIS_C1: https://mis-implants.com/upload/pdf/Products/MIS_Conical_Connection_Catalog.pdf · Downloaded on2026-10-15
- ASTRA_*: https://assets.dentsplysirona.com/flagship/en_gb/products/implants/UK-IMP-DS-Implants-Price-Booklet-EN-062021-PG6682.pdf · UK2021
- STRAUMANN_SP: https://www.straumann.com/content/dam/media-center/straumann/en-us/documents/brochure/product-catalog/CALIT-007-Product-Catalog-2021-DIGITAL.pdf · USA2021

## Límites del modelo

Las referencias describen cuerpos intraóseos nominales, no archivos CAD de rosca, cuello, plataforma o perfil inclinado del fabricante. La propuesta requiere revisar el MPR y aceptar o descartar. La búsqueda utiliza posiciones discretas y no demuestra un máximo anatómico continuo.
