# DSG 9.22.6 · Optimizador de posición y tamaño corregido

Sustituye al manual 9.22.0 en todo lo que se indica aquí; el resto de aquel manual (restricciones, catálogo con mallas reales, temporales) sigue vigente. Sigue siendo una ayuda geométrica experimental: no predice estabilidad primaria ni sustituye la revisión clínica.

## Qué cambia

| Problema en 9.22.5 | Corrección |
|---|---|
| BUSCAR POSICIÓN tendía a hundir el implante: casi siempre gana cobertura al bajar. | El movimiento se expresa en el sistema del implante: desplazamiento lateral (perpendicular al eje), profundidad (a lo largo del eje) e inclinación. **Cambio de profundidad máximo** es un límite propio y vale 0 por defecto: el optimizador no cambia la profundidad salvo que se le permita. |
| El desplazamiento usaba los ejes del mundo; en un implante inclinado "bajar" también lo movía de lado. | Traslación en el marco del implante. |
| Proponía moverse por mejoras de ruido (umbral 0,001, menor que un punto de muestreo). | Umbral de 0,03 (~4 de los 384 puntos). Entre las posiciones con puntuación a menos de ese margen de la mejor se elige la de **menor movimiento**; si es la original, se informa "sin mejora apreciable". |
| COMPARAR TAMAÑOS nunca reconocía el implante actual (siempre "comparación"). | Se reconoce por su referencia de catálogo o, en las bibliotecas nominales, por su diámetro y longitud. Ahora puede decir "propuesta" o "sin mejora". |
| El manual decía que se ordenaba por área y el código por mayor diámetro. | Criterio elegible: **Mayor medida admisible** (diámetro y después longitud) o **Mayor soporte con reserva**. Topes opcionales de diámetro y longitud para la posición. |
| La reserva de pared solo se exigía al comparar tamaños y casi a ras de plataforma (0,05 mm), lo que hacía inviables casos reales. | Misma comprobación en los dos motores. **Zona cervical libre** (1 mm por defecto) excluye la franja coronal de la reserva de pared. |
| Las bibliotecas integradas no se podían aplicar nunca. | APLICAR revalida la envolvente nominal (cilindro circunscrito) y redimensiona el implante DSG con su propia malla, con plataforma y eje fijos. Se comprueba que la malla resultante cabe en la envolvente validada; si no, se restaura el tamaño anterior. |
| La matriz CORE-X tenía 3,5 × 11,0 y faltaban Ø4,0 y Ø4,75. | Catálogo BTI completo de la tienda oficial. |
| "Guardar como" invalidaba la propuesta; topología recalculada en cada evaluación; paso de deshacer vacío. | Corregidos. |

## Bibliotecas de medidas nominales

| Biblioteca | Referencias | Fuente |
|---|---|---|
| BTI: Plataforma 2.5, 3.0, 3.0-X, CORE, CORE-X, Universal, Universal Plus (Interna); TINY, Universal, Universal Plus (Externa) | 267 | Tienda oficial BTI, 14/10/2026. Diámetro y longitud decodificados del código y contrastados con el nombre |
| Klockner VEGA | 16 | Lista de referencias VEGA (distribuidor) y manual VEGA·VEGA+ |
| Klockner VEGA+ | 4 (solo 10 mm verificada) | Manual VEGA·VEGA+ Surgery 09/2025. El resto de longitudes no aparece en la documentación pública consultada |
| MIS SEVEN | 26 | Internal Hexagon Product Catalog 2025 |
| MIS C1 | 19 | Conical Connection Product Catalog |
| Astra Tech OsseoSpeed EV recto, EV cónico, Profile EV | 32 · 12 · 24 | Product catalog ASTRA TECH Implant System EV |
| Straumann Standard Plus | 12 | Matriz aportada por el usuario |

Todas son medidas nominales: no incluyen la geometría del fabricante (conicidad, cuello, roscas, bisel de Profile EV). La disponibilidad varía por mercado.

## Uso

1. Selecciona el implante y revisa estructuras y CBCT.
2. Posición: fija desplazamiento lateral, profundidad (0 = profundidad fija) e inclinación máximos → BUSCAR POSICIÓN. El panel muestra lateral, profundidad y ángulo propuestos.
3. Tamaño: elige biblioteca, criterio y topes → COMPARAR TAMAÑOS. El panel muestra la medida y la referencia comercial.
4. Revisa la propuesta (malla de alambre), marca la revisión de perfil y tejidos, y APLICAR PROPUESTA: se revalida con la anatomía actual antes de cambiar nada.
