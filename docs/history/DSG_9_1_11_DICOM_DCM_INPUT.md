# DSG 9.1.11 — DICOM/DCM input

DSG treats DICOM as a content format rather than a filename extension.

Accepted through the same input pipeline:
- `.dcm` / `.DCM`
- `.dicom` / `.DICOM`
- `DICOMDIR`
- extension-less DICOM files
- other vendor filenames when pydicom recognizes DICOM content

The Blender file selector no longer declares `.dcm` as `filename_ext`; `check_extension` remains disabled. The file browser shows all files so extension-less dental CBCT exports can be selected. Actual validation is performed by `read_header()` using standard DICOM parsing first and `force=True` only as a fallback for valid preamble-less/vendor DICOM objects.

Non-image DICOM objects are not mistaken for slices: recovery searches the surrounding study tree for image-bearing DICOM objects with valid Rows/Columns and groups them by Study/Series UID.
