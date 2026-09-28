# Motores de IA de DSG (manifest v2)

`manifest-v2.json` es el índice que usa DSG ≥ 9.7.3 para instalar el motor de
segmentación (TotalSegmentator 2.18 + PyTorch 2.8) sin compilarlo en el PC del
usuario. `manifest.json` (schema 1, en la raíz) se mantiene sin cambios para
las versiones antiguas de DSG.

* **Perfiles:** plataforma → ABI de Python → acelerador (`cuda126` / `cpu`) →
  lista de paquetes.
* **Paquetes:** capas `torch` y `core` del runtime (troceadas en partes < 2 GiB
  para los Releases de GitHub) y los modelos dentales Dataset113 / Dataset115.
* **Espejos:** cada parte lista sus URLs por orden: Release `engine-v2` de este
  repositorio, Google Drive (`gdrive:<id>`) y la URL oficial. Todas se
  verifican con SHA-256.

Mientras no haya perfiles publicados, DSG construye el motor localmente con
`uv` (más lento, pero ya sin reinstalaciones en cada actualización).

## Publicar una versión del motor

En Windows, con el Python de Blender 5.2 y el código de DSG:

```bat
"C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe" tools\build_engine_release.py --out engine_release
gh release create engine-v2 --repo xhackermax/DentalSurgicalGuide engine_release\upload\*
```

Copia `engine_release\manifest-v2.json` a `engines/manifest-v2.json` y haz commit.
Para añadir Google Drive como espejo: sube los mismos archivos, compártelos
como "cualquier persona con el enlace" y regenera el manifest con
`--manifest-only --drive-ids ids.json` (`{"archivo": "id_drive"}`).
