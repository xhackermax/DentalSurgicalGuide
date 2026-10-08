# Pipeline y roadmap recuperados de DSG 8.6.7

DSG 9.9.5 conserva como contrato clínico el flujo visible de DSG 8.6.7. No se
copió el monolito antiguo: la implementación actual permanece modular y se
verifica por tests para impedir regresiones.

## Pipeline clínico global

1. DICOM / CBCT
2. Alineamiento IOS ↔ CBCT
3. Modelo retentivo
4. Planificación de implantes
5. Contorno
6. Microtornillo / frame
7. Cilindros
8. Irrigación
9. Refuerzos
10. Canales de fresado
11. Corte final
12. Nombre y exportación

Los diez pasos internos de guía mantienen exactamente los índices de 8.6.7:
`MODEL=0, IMPLANT=1, CONTOUR=2, FRAME=3, SLEEVE=4, IRRIGATION=5,
REINFORCEMENT=6, DRILL=7, FINAL_CUT=8, NAME=9`.

## Roadmap clínico heredado

Los pasos de roadmap de 8.6.7 siguen siendo obligatorios en 9.9.5:

- tooth_analysis
- alignment_review
- guide_model_review
- axis_from_fdi
- implant_preview
- implant_confirm
- contour_review
- frame_preview
- frame_confirm
- sleeve_preview
- sleeve_confirm
- irrigation_preview
- irrigation_path_confirm
- irrigation_apply

La versión actual puede añadir pasos adicionales, pero no eliminar ni cambiar el
significado de estos pasos sin romper el test de compatibilidad.

## Procedencia

Fuentes históricas preservadas en `docs/history/8_6_7/`:

- `roadmap_module.py.txt`
- `guide_pipeline_contract.py.txt`
