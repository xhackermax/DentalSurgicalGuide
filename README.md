# Dental Surgical Guide (DSG)

Guia sencilla y repositorio oficial de DSG para Blender 5.x.

## Instalar

1. Descarga el ZIP desde **[Releases](https://github.com/xhackermax/DentalSurgicalGuide/releases/latest)**.
2. En Blender abre **Edit > Preferences > Add-ons > Install from Disk**.
3. Selecciona el ZIP sin descomprimir.
4. Activa **DSG Dental Surgical Guide**.

## Motores y modelos

DSG usa un unico indice estable:

[manifest.json](https://raw.githubusercontent.com/xhackermax/DentalSurgicalGuide/main/manifest.json)

Los archivos grandes se guardan en el Release `engine-v1`. El manifest incluye el SHA-256 de cada paquete para comprobar su integridad antes de instalarlo.

## Fuentes y proyectos externos

DSG integra o es compatible con componentes de terceros. Cada proyecto conserva su autoria y licencia original:

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
- Motores: https://github.com/xhackermax/DentalSurgicalGuide/releases/tag/engine-v1
