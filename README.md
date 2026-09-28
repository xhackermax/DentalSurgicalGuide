# Dental Surgical Guide (DSG)

Guia sencilla y repositorio oficial de DSG para Blender 5.x.

## Instalar

1. Descarga el ZIP desde **[Releases](https://github.com/xhackermax/DentalSurgicalGuide/releases/latest)**.
2. En Blender abre **Edit > Preferences > Add-ons > Install from Disk**.
3. Selecciona el ZIP sin descomprimir.
4. Activa **DSG Dental Surgical Guide**.

## Motores y modelos

**DSG 9.7.3 o superior** instala el motor de IA (TotalSegmentator 2.18 + PyTorch 2.8) desde
[engines/manifest-v2.json](engines/manifest-v2.json):

- se instala una sola vez y **se reutiliza en todas las actualizaciones de DSG**;
- descarga en paralelo, se reanuda si se corta y verifica cada archivo con SHA-256;
- espejos: Release `engine-v2` de este repositorio y Google Drive;
- sin tarjeta NVIDIA se instala la version CPU (mucho mas ligera).

Detalles y como publicar los motores: [engines/README.md](engines/README.md).
Novedades de cada version: [docs/CHANGELOG.md](docs/CHANGELOG.md).

Las versiones antiguas (≤ 9.2) siguen usando el indice
[manifest.json](https://raw.githubusercontent.com/xhackermax/DentalSurgicalGuide/main/manifest.json)
y el Release `engine-v1`, que no se modifican.

## Fuentes y proyectos externos

DSG integra o es compatible con componentes de terceros. Cada proyecto conserva su autoria y licencia original:

- [TotalSegmentator](https://github.com/wasserth/TotalSegmentator) - modelos dentales ToothFairy3 (Dataset113) y craneofacial (Dataset115).
- [nnU-Net](https://github.com/MIC-DKFZ/nnUNet) - framework de segmentacion medica.
- [DentalSegmentator Dataset112](https://zenodo.org/records/10829675) - modelo/dataset dental distribuido desde Zenodo.
- [SlicerAutomatedDentalTools / UniversalLab](https://github.com/DCBIA-OrthoLab/SlicerAutomatedDentalTools) - modelo de dientes individuales.
- [PyTorch](https://pytorch.org/) - runtime de inferencia.
- [pydicom](https://github.com/pydicom/pydicom) - lectura DICOM.
- [pylibjpeg](https://github.com/pydicom/pylibjpeg) y sus plugins - codecs JPEG, JPEG-LS, JPEG 2000 y RLE.
- [GDCM](https://github.com/malaterre/GDCM) - codecs y utilidades DICOM.
- [MMG / MMGpy](https://github.com/kmarchais/mmgpy) - herramientas opcionales de malla.

Las licencias y avisos incluidos por los proyectos externos deben conservarse al redistribuir sus archivos.

## Enlaces permanentes

- Addon actual: https://github.com/xhackermax/DentalSurgicalGuide/releases/latest
- Manifest: https://raw.githubusercontent.com/xhackermax/DentalSurgicalGuide/main/manifest.json
- Motores (DSG ≥ 9.7.3): https://raw.githubusercontent.com/xhackermax/DentalSurgicalGuide/main/engines/manifest-v2.json
- Motores (DSG ≤ 9.2): https://github.com/xhackermax/DentalSurgicalGuide/releases/tag/engine-v1
