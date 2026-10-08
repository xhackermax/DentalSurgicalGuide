# Verificación de la actualización 9.10.11

Fecha: 8 de octubre de 2026. Se importa el ZIP proporcionado expresamente por el autor; no procede de una selección automática de Drive. Se trabaja en un clon separado de `origin/main` para conservar el checkout local que tenía cambios pendientes.

## Integridad y correspondencia

| Comprobación | Resultado |
|---|---|
| Versión de `version.py` y BUILD_MANIFEST | 9.10.11 |
| Integridad CRC del ZIP | PASS |
| Archivos declarados | 426, con tamaño y SHA-256 válidos |
| Total de entradas | 427: archivos declarados + BUILD_MANIFEST |
| Código `dsg/` frente al paquete original | Correspondencia byte a byte; se eliminan del clon los archivos anteriores que no están en el ZIP |
| ZIP original publicado | 7 157 729 bytes |
| Modelos incluidos | No; manifiesto `weights_bundled=false` |
| Motores declarados | TOTALSEG, TOOTHSEG, UMAMBA2 |

SHA-256: `d39ff9a4af0ddc4024582f538adf65de30d47d29d3a6986b719b337208169206`.

[Proveniencia verificable](DSG_9_10_11_PROVENANCE.json). `.gitattributes` impide convertir finales de línea de `dsg/` al clonar, de modo que sus hashes permanezcan válidos. El ZIP generado por el empaquetador puede tener otro hash por sus metadatos de compresión; el asset original conserva el hash anterior.

## Comprobaciones portables

- Compilación Python del addon: PASS.
- Las 20 pruebas actuales en `dsg/tests_pure`: PASS.
- Métricas: PASS; 1768 capturas amplias, 164 silenciosas, 95 globales, 1332 accesos getattr/hasattr, 1 exec, 126 imports Blender fuera de rutas con ese nombre y máximo 4487 líneas.
- Regla de dependencias del núcleo puro: PASS.
- Índice generado: `CODEMAP_INDEX_PASS`.
- Control de calidad: `DSG_QUALITY_GATE_PASS`.
- Construcción de ZIP instalable y checksum: PASS.

La manifestación de tres adaptadores y la ausencia de pesos empaquetados no verifican qué modelos existen en el runtime particular de un usuario. Esta publicación no instala ni ejecuta modelos de cuerpo completo.

## Blender real

Se usa Blender **5.2.2 LTS**, con perfiles de usuario temporales y escenas sintéticas; el caso abierto del usuario no se modifica.

| Caso | Resultado |
|---|---|
| Instalar ZIP original, activar/desactivar/reactivar y verificar hashes | PASS |
| Registro y dibujo de paneles | PASS; 99 referencias estáticas de UI a operadores resueltas |
| Suavizado visual y conservación de referencia de alineación | PASS con VTK compatible |
| Suavizado posterior a segmentación | PASS |
| Historial de workflow | PASS |
| Historial más allá del límite nativo | PASS |
| Deshacer de suavizado asíncrono | PASS |
| Recuperación de estado en todas las etapas | PASS |
| Historial modal | PASS |
| Deshacer de operador de casquillo | PASS |
| Historial de imagen MPR | PASS |
| Copia del diagnóstico estructurado y persistencia después de cleanup | PASS |

La prueba de suavizado falló inicialmente porque el perfil limpio no contenía VTK. Se repitió con las bibliotecas VTK del runtime Blender/Python 3.13 existente y pasó; no se modificó el addon ni se instalaron modelos para resolverlo. El comando admite `--vtk-site-packages` para declarar ese requisito.

La comprobación de 99 referencias acredita registro e introspección y dibujo de paneles; no sustituye recorrer cada botón con todos los estados posibles de un caso clínico. La copia de diagnóstico se prueba con un buffer en segundo plano; esta ejecución no valida el portapapeles del sistema operativo en primer plano.

## Resultados que no se presentan como aprobados

- La suite histórica `tests/` de 9.7 falla al recoger cinco módulos, porque importa `engine_install`, `frangible_seal` e `irrigation_network`, retirados del paquete recibido. Se conserva para auditar y migrar sus requisitos; no se eliminan ni se cuentan como aprobadas esas pruebas.
- Una ejecución inicial de la suite de ZIP anterior se detuvo en `test_immediate_gate.py` al no disponer de checkpoints TotalSegmentator/ToothSeg en el perfil limpio. Ese test requiere modelos; no se interpreta como comprobación de inferencia ni se fuerza un estado READY ficticio.
- No se ejecutó inferencia completa sobre un CBCT real con los tres motores, ni una validación clínica de precisión de FDI/canal.
- La CI actual ejecuta las comprobaciones portables; no declara pruebas Blender real en un runner sin Blender. El workflow anterior exigía `bpy==5.2.2`, ausente del índice consultado, y se reemplaza por gates que corresponden al paquete actual.

## Reproducir

```bash
python -m pip install numpy
python tools/run_checks.py --no-smoke
python tools/run_checks.py --blender "/ruta/a/blender" --vtk-site-packages "/runtime/site-packages"
python tools/build_addon_zip.py --out dist
```

Los logs Blender se escriben en `dist/blender-checks`. Las pruebas que dependen de modelos, como `test_immediate_gate.py`, necesitan un runtime preparado y checkpoints reales. La [hoja de ruta](FUTURAS_MEJORAS.md) incluye esa ampliación de evidencia y la migración de tests históricos.
