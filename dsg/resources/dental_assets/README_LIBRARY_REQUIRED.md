# DSG Dental Library master

DSG 9.1 implements the canonical loader/validator for a shared native Blender dental library. **No synthetic dental anatomy is bundled by this implementation.** The real authored resource must be placed at:

`dsg/resources/dental_assets/dsg_dental_library.blend`

The `.blend` is the editable SSOT. STL/OBJ/PLY/GLB/EOFF may be import/interchange sources, never the authoritative library.

## Required family structure

For each initial permanent FDI family (11–17, 21–27, 31–37, 41–47):

- Collection: `DSG_DentalFamily_FDI_XX`
- `DSG_ToothTemplate_FDI_XX`
- `DSG_CrownTemplate_FDI_XX`
- `DSG_ToothFrame_FDI_XX`
- all required `DSG_Landmark_FDI_XX__NAME`
- `DSG_EmergenceRegion_FDI_XX`
- `DSG_EmergenceCenter_FDI_XX`
- `DSG_ProstheticAxis_FDI_XX`
- optional `DSG_CervicalProfile_FDI_XX`

Every object must carry the canonical Dental Assets v1 properties/hash, `DSG_asset_source=LIBRARY`, `DSG_coordinate_space=TEMPLATE_LOCAL`, units in millimetres, and frame standard `DSG_TOOTH_LOCAL_V1`.

## Definitive local frame

- +X MESIAL / -X DISTAL
- +Y FACIAL_BUCCAL / -Y LINGUAL_PALATAL
- +Z CORONAL_OCCLUSAL_INCISAL / -Z APICAL
- right-handed

The runtime validates this contract and fails explicitly on missing/incompatible families. It does not silently rename or reinterpret a library.
