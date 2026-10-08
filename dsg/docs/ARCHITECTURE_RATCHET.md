# Mejora gradual de DSG: fase 1 en 9.10.11

El objetivo es aplicar los principios complementarios a SOLID sin reescribir el addon. El pipeline y su esquema de labels conservan compatibilidad: dientes 1..32, mandíbula 53, maxila 54 y canal 55. La numeración FDI se deriva para los dientes; los labels de hueso no se transforman en dientes. No se asumen unidades HU universales para todos los CBCT.

Implementado:

- Núcleo `pipeline_core` importable y comprobable con Python independiente de Blender, NumPy y unittest. El bootstrap del paquete importa Blender solo al utilizar su API.
- Errores con etapa y contratos de volumen, calibración, spacing, labelmap y manifest versionado. El worker comprueba los labels antes de preparar geometría y el cliente rechaza versiones o resultados de otra ejecución. La UI comprueba dimensiones y dtype antes de publicar labels en RUNTIME.
- Diagnóstico persistente por ejecución, con run_id, etapas, duración, estado y fallbacks de lanzamiento/CUDA. Se guarda fuera de los temporales de inferencia y permanece después de cleanup. «Copiar diagnóstico» copia únicamente este registro estructurado; no copia requests privados ni logs libres que podrían contener datos del paciente.
- Trinquete de métricas del código productivo. `tools/check_quality.py` comprueba la línea base, la regla de dependencias del núcleo y las pruebas puras. No actualiza la línea base automáticamente ni oculta regresiones excluyendo módulos heredados.
- Pruebas puras de entradas inválidas, bones/FDI, traducción, manifest, errores, privacidad del diagnóstico, FakeEngine y métricas; pruebas Blender de instalación, portapapeles, superficies e historial reversible existente.

Línea base de 9.10.10: 1775 broad_except, 170 silent_except, 95 global_stmt, 1332 getattr_hasattr, 1 exec_calls, 126 bpy_outside_blender y 4487 max_file_lines. El análisis cuenta cuerpos silenciosos de una sentencia (pass/continue/return vacío) y omite únicamente tests y bytecode. Las cifras no equivalen a una auditoría manual de cada captura.

Deuda pendiente:

- Migrar progresivamente los nueve fragmentos DICOM a módulos normales con imports explícitos.
- Sustituir los registros globales y RUNTIME heredados por sesiones de escena, con pruebas de varias escenas y undo.
- Extraer adaptadores reales de los tres motores y una configuración explícita compartida, sin sustituir los modelos existentes.
- Ampliar caracterización con 2–3 CBCT anonimizados. Las pruebas sobre arrays y dientes exportados de un caso no certifican inferencia clínica de los tres motores.

No se sustituyeron masivamente except/getattr y no se alteraron motores, parámetros de inferencia ni algoritmos de suavizado. El historial Ctrl+Z y sus limitaciones de recuperación archivada permanecen en la suite y en el README.
