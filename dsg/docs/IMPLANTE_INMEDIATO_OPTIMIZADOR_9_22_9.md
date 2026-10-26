# DSG 9.22.9 · Implante inmediato en el optimizador

En la ruta de implante inmediato, el hueso segmentado tiene un hueco donde estaba la raíz extraída. Hasta 9.22.8 el optimizador lo trataba como falta de hueso, así que cualquier implante en el alvéolo era "no admisible" y no proponía nada.

Ahora:

- Los dientes marcados para extracción se envían como **alvéolos**. La parte del implante dentro del alvéolo (más 0,3 mm de espacio periodontal) no cuenta como falta de pared ni reduce la cobertura.
- Se exige **anclaje apical en hueso nativo**: longitud del implante más allá del punto más profundo del alvéolo. Por defecto 3 mm, configurable de 1 a 8 mm en el panel (solo visible en la ruta inmediata).
- La reserva de pared y la cobertura se comprueban en la parte del implante fuera del alvéolo.
- El panel muestra el % de superficie en el alvéolo y el anclaje apical de la propuesta. Si nada cumple, el motivo indica el anclaje alcanzado.

No cambia el resto de restricciones (raíces vecinas, nervio, seno con tolerancia, cavidad nasal, implantes vecinos). El hueco vestibular entre implante y pared del alvéolo no se evalúa como injerto ni como estabilidad.

Verificación: bloque de hueso con alvéolo de 6 mm: Ø4 × 11,5 admitido (5,5 mm de anclaje), Ø4 × 8 rechazado por anclaje, y sin alvéolo rechazado; regresiones del optimizador. No es validación clínica.
