# DSG 9.0 · Contrato común de assets dentales

DSG y cualquier motor externo de reconocimiento dental deben compartir **el mismo contrato**:

`dsg/resources/dental_assets/asset_contract_v1.json`

El archivo es la fuente de verdad para nombres, roles, landmarks y sistema de coordenadas. El motor externo debe comprobar `contract_version` y `contract_sha256` antes de devolver resultados a DSG.

## Familia

Cada diente usa `family_id = FDI_XX`.

Ejemplo FDI 46:

- diente paciente: `DSG_Tooth_FDI_46`
- plantilla dental: `DSG_ToothTemplate_FDI_46`
- fantasma de registro: `DSG_ToothGhost_FDI_46`
- corona biblioteca: `DSG_CrownTemplate_FDI_46`
- corona adaptada: `DSG_CrownTarget_FDI_46`
- frame local: `DSG_ToothFrame_FDI_46`
- landmark: `DSG_Landmark_FDI_46__MESIAL_CONTACT`
- región de emergencia: `DSG_EmergenceRegion_FDI_46`
- centro de emergencia: `DSG_EmergenceCenter_FDI_46`
- eje protésico: `DSG_ProstheticAxis_FDI_46`
- perfil cervical: `DSG_CervicalProfile_FDI_46`

La relación entre elementos no depende del nombre visual solamente. Cada objeto lleva `DSG_family_id`, `DSG_asset_id`, `DSG_asset_role`, `DSG_fdi_number`, clase, arcada, lado y hash del contrato.

## Frame dental común

- +X = mesial
- -X = distal
- +Y = facial/bucal
- -Y = lingual/palatino
- +Z = coronal/oclusal/incisal
- -Z = apical
- unidad = mm

El motor de reconocimiento debe devolver landmarks en uno de los espacios declarados por el contrato: `TEMPLATE_LOCAL`, `CBCT_DSG_ROOT`, `IOS_ALIGNED` o `WORLD`.

## API Python

Dentro de Blender:

```python
from dsg import dental_assets
from dsg import dental_asset_blender

print(dental_assets.family_descriptor(46))
print(dental_assets.required_landmarks(46))
print(dental_assets.object_name(46, "CROWN_TEMPLATE"))
```

Para un resultado del motor externo:

```python
payload = dental_assets.canonical_recognition_payload(
    46,
    source="IOS_RECOGNITION",
    coordinate_space="WORLD",
    landmarks=[
        {"name": "MESIAL_CONTACT", "xyz": [0.0, 0.0, 0.0], "confidence": 0.95},
    ],
)

dental_assets.validate_recognition_payload(payload)
dental_asset_blender.apply_recognition_payload(payload)
```

No deben inventarse nombres alternativos en el motor externo. Si necesita un landmark nuevo, se añade primero al contrato y se incrementa la versión.

## Biblioteca geométrica

El contrato reserva un único archivo compartido:

`dsg/resources/dental_assets/dsg_dental_library.blend`

Todavía no se incluye geometría dental artificial en DSG 9.0. El archivo deberá contener los objetos con los nombres canónicos del contrato. Esto evita crear STLs duplicados o librerías divergentes entre DSG y el motor de reconocimiento.

## Puente MCP / motor externo

Con el puente local de DSG activo, un cliente autorizado puede consultar el mismo contrato con la operación de solo lectura:

`get_dental_asset_contract`

DSG devuelve el JSON completo y su SHA-256. Un motor externo debe rechazar el intercambio si su copia del contrato no coincide.
