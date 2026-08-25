# Dental Surgical Guide (DSG)

Addon DSG v9.2.20 para Blender 5.x.

## Descargar el addon

La version estable se publica en:

https://github.com/xhackermax/DentalSurgicalGuide/releases/latest

## Motores remotos

DSG utiliza este manifiesto estable:

https://raw.githubusercontent.com/xhackermax/DentalSurgicalGuide/main/manifest.json

Los motores y modelos pesados se publican como assets del Release `engine-v1`. El manifest solo se publica despues de generar los paquetes y calcular sus SHA-256 reales, evitando enlaces rotos o instalaciones corruptas.

## Estructura

- Releases de version: ZIP instalable del addon.
- `manifest.json`: indice verificable de motores.
- Release `engine-v1`: runtimes DICOM/IA y modelos.
