# DSG 9.10.11 para Blender 5.2

Actualización con el paquete original del autor. **Descarga el asset `DSG_v9_10_11_BLENDER_5_2_PIPELINE_CONTRACTS_DIAGNOSTICS.zip`**; los ZIP de código fuente de GitHub no son el instalador del addon.

## Mejoras

- Contratos de volumen, calibración, spacing, etiquetas y manifest versionado con identificador de ejecución.
- Diagnóstico persistente con etapas, duración, estado y fallbacks; botón **Copiar diagnóstico**.
- Núcleo independiente de Blender, 20 pruebas puras, control de deuda técnica e índice de código verificable.
- Incluye las mejoras previas de la serie 9.10: motores, reparación DICOM, suavizado reversible e historial Ctrl+Z.

## Uso y documentación

Instala el ZIP desde **Edit → Preferences → Add-ons → Install from Disk**, activa DSG y abre **N → DSG**. Guarda el caso, cancela tareas y reinicia Blender después de actualizar. En DICOM utiliza **INSTALAR / REPARAR MOTORES** y **REVISAR**.

- [Manual de instrucciones](https://github.com/xhackermax/DentalSurgicalGuide/blob/v9.10.11/docs/MANUAL_9_10_11.md)
- [Mejoras y alcance](https://github.com/xhackermax/DentalSurgicalGuide/blob/v9.10.11/docs/MEJORAS_9_10_11.md)
- [Cómo funciona](https://github.com/xhackermax/DentalSurgicalGuide/blob/v9.10.11/docs/FUNCIONAMIENTO_9_10_11.md)
- [Futuras mejoras](https://github.com/xhackermax/DentalSurgicalGuide/blob/v9.10.11/docs/FUTURAS_MEJORAS.md)
- [Verificación y limitaciones](https://github.com/xhackermax/DentalSurgicalGuide/blob/v9.10.11/docs/VERIFICACION_9_10_11.md)

## Verificación y requisitos

426 archivos con hashes válidos, 20 pruebas puras y comprobaciones de instalación/registro, suavizado, historial y diagnóstico en Blender 5.2.2 LTS. 99 referencias estáticas de interfaz a operadores resueltas. La prueba geométrica de suavizado requiere VTK compatible.

El ZIP no incluye pesos. U-Mamba2 necesita Linux/CUDA y un checkpoint final ToothFairy3; no ofrece instalación nativa Windows compatible. ToothSeg no genera maxilares/canal. Surface Nets continúa experimental. No se verificó inferencia clínica completa con los tres motores. La suite histórica 9.7 requiere migración y sus errores están documentados.

SHA-256 del instalador: `d39ff9a4af0ddc4024582f538adf65de30d47d29d3a6986b719b337208169206`.
