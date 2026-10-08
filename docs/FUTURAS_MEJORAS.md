# Futuras mejoras propuestas

Estas propuestas no están implementadas en 9.10.11 y no tienen fecha prometida. Se basan en [ARCHITECTURE_RATCHET.md](../dsg/docs/ARCHITECTURE_RATCHET.md) y las limitaciones comprobadas de la actualización.

| Prioridad | Propuesta | Criterio de aceptación |
|---|---|---|
| 1 | Caracterizar 2–3 CBCT anonimizados con cada motor disponible | Comparar anatomía, FDI, canal, tiempos, RAM/VRAM y fallos con revisión humana; tests sintéticos no bastan |
| 1 | Migrar la suite histórica 9.7 | Inventario de comportamientos, imports actuales y pruebas equivalentes sin perder requisitos aplicables |
| 1 | Ejecutar Blender 5.2 real en CI | Distribución/runner verificados y pruebas de ZIP, operadores e historial; el workflow antiguo dependía de una rueda ausente |
| 1 | Medir SIMPLE frente a FDI | Menos trabajo en SIMPLE sobre el mismo estudio; sin individualización/FDI innecesarios |
| 2 | Migrar fragmentos DICOM a imports explícitos | Una unidad cada vez con resultados, contratos y operadores equivalentes |
| 2 | Sustituir globales/RUNTIME por sesiones de escena | Dos escenas/casos aislados y undo coherente, sin contaminación de arrays o procesos |
| 2 | Extraer adaptadores y configuración común de motores | Contrato uniforme, capacidades claras y comparación sin duplicar pesos ni pipelines |
| 2 | Instalación reproducible y recuperación de descargas | Versiones/hashes fijados, reanudación y reutilización del runtime al actualizar solo addon |
| 2 | U-Mamba2 mediante entorno Linux/CUDA reproducible | Inferencia real con checkpoint final y comunicación con Blender; repositorio/SSL no prueban disponibilidad |
| 3 | Consolidar Surface Nets en contactos difíciles | Medir cierre, ocupación, volumen, contactos y autointersecciones sin rellenar fallos ni alterar labels |
| 3 | Gestión visible del tamaño e historial | Mostrar espacio, transportar checkpoints y limpiar por selección sin romper referencias |
| 3 | Comparar diagnósticos de ejecuciones | Motor, fallbacks y cuellos de botella accesibles sin peticiones privadas/logs libres |

Primero ampliar evidencia y migrar pruebas. Después refactorizar una frontera cada vez, protegida por equivalencia. Rendimiento y suavizado deben medirse sobre casos representativos conservando restauración a originales.

La reducción de excepciones amplias es gradual: cada cambio necesita una causa accionable y pruebas. No se propone sustituir capturas/accesos dinámicos masivamente solo para bajar una cifra.
