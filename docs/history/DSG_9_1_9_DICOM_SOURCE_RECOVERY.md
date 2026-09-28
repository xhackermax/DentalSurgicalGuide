# DSG 9.1.9 – Robust DICOM source recovery

Fixes the error **“El DICOM no contiene dimensiones de imagen válidas”** when the user selects a DICOM container/non-image object such as `DICOMDIR`, SR/metadata, or another non-pixel DICOM file.

## Behaviour

- Image DICOM with valid `Rows`/`Columns`: unchanged.
- Non-image selection: DSG searches nearby DICOM files without decoding pixel data.
- One unambiguous image series: DSG automatically switches to a representative image and continues.
- Multiple plausible series: fail closed and ask the user to select a slice from the intended CBCT series rather than guessing clinically.
- `DICOMDIR`: recursive discovery is enabled because referenced image files are commonly stored in nested directories.
- The selected recovery path is written back to the DICOM properties so `Siguiente` loads the recovered image series rather than the non-image file.

This is a source-discovery fix, not a change to CBCT voxel geometry, density handling, or segmentation.
