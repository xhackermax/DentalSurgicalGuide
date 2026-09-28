# DSG v9.2.1 · PATIENT FIRST · roadmap clínico

## 0. Carpeta del paciente

El flujo empieza siempre con **ELEGIR PACIENTE**. La carpeta seleccionada queda guardada como ruta maestra del caso para importar y exportar archivos durante toda la sesión DSG.

Orden automático de entrada:

1. localizar y cargar CBCT/DICOM desde la carpeta del paciente;
2. elegir la ruta clínica después de que el CBCT esté cargado;
3. importar los STL IOS automáticamente únicamente cuando se entra en Alineamiento.

## Ruta A · Implante simple

Secuencia visible propia:

**IMPLANTE SIMPLE → DENSIDAD/HU → CONFIRMAR STL → ALINEAMIENTO**

1. Usar el umbral automático de tejido óseo como punto de partida.
2. Crear una superficie sólida de CBCT automáticamente.
3. Permitir al usuario modificar la densidad/HU mediante una barra; la previsualización 3D se actualiza con ese valor.
4. Al confirmar, generar el STL definitivo y guardarlo como `DSG_CBCT_SIMPLE.stl` en la carpeta del paciente.
5. Importar automáticamente los STL IOS encontrados en esa carpeta.
6. Alinear con el protocolo establecido: **3 pares de puntos/zonas → prealineamiento rígido → ICP robusto → confirmación**.
7. Continuar con DSG como en las versiones previas.

Esta ruta no necesita DentalSegmentator ni UniversalLab para poder funcionar.

## Ruta B · Implante inmediato

Secuencia visible propia:

**IMPLANTE INMEDIATO → INVERTIR FDI (solo si hace falta) → FDI CORRECTO → seleccionar dientes + H → DIENTES H → UNIR → CONFIRMAR → ALINEAMIENTO**

1. Ejecutar la segmentación completa con los dos motores:
   - DentalSegmentator 8.7: soporte anatómico, continuidad dental y verificación del canal.
   - UniversalLab: dientes individuales/FDI y clases específicas de maxila, mandíbula y canal.
2. Crear maxila, mandíbula, canal/nervio y dientes individualizados.
3. Revisar FDI. Si está correcto, seguir directamente. `INVERTIR FDI` es únicamente una herramienta de corrección cuando maxilar y mandíbula han quedado intercambiados.
4. El usuario selecciona uno o varios dientes que va a extraer y pulsa **H**. Los dientes ocultos son la selección clínica de los futuros alvéolos/implantes inmediatos.
5. Al pulsar `DIENTES H → UNIR`, DSG duplica la geometría y reproduce un Ctrl+J por arcada:
   - **maxila + dientes superiores visibles**;
   - **mandíbula + dientes inferiores visibles**.
6. Los dientes ocultos con H no se incluyen en la unión. Su ausencia deja visible el hueco del alvéolo.
7. **El nervio mandibular nunca entra en Ctrl+J** y permanece como objeto independiente de seguridad.
8. Tras confirmar, guardar los dos modelos en la carpeta del paciente e importar automáticamente los STL IOS.
9. Alinear con **3 pares de puntos/zonas → prealineamiento rígido → ICP robusto → confirmación**.
10. Continuar con DSG como en las versiones previas.

## Regla de motores

No existe un único motor que sustituya al otro. Para implante inmediato se conservan ambos:

- UniversalLab 1-52: identidad dentaria / FDI.
- UniversalLab 53: mandíbula específica.
- UniversalLab 54: maxila específica.
- UniversalLab 55: canal mandibular.
- DentalSegmentator 1/2: soporte/fallback óseo.
- DentalSegmentator 3/4: soporte de continuidad corona-cuello-raíz-ápice.
- DentalSegmentator 5: verificación del canal.

Para los modelos alveolares se prefieren las clases 54/53 de UniversalLab porque representan maxila y mandíbula de forma más específica. Si alguna no existe, se usa como fallback la clase 1/2 de DentalSegmentator.

## Roadmap posterior al alineamiento

Se conserva la filosofía ya acordada: **primero dónde debe estar el diente; después dónde puede estar el implante**.

`CROWN_TEMPLATE → CROWN_GHOST → TOOTH → ToothFrame/landmarks → CROWN_TARGET → EMERGENCE_REGION → PROSTHETIC_AXIS → IMPLANT → MPR/revisión → guía`

La IA puede proponer y calcular, pero las confirmaciones clínicas siguen perteneciendo al usuario.
