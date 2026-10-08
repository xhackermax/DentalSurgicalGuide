"""Lossless synthetic pixel checks; never reads patient files."""
import sys
from pathlib import Path

def validate(vendor):
    sys.path.append(str(vendor))
    import numpy as np
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, RLELossless, JPEGLSLossless, JPEG2000Lossless, generate_uid
    array = (np.arange(64 * 64, dtype=np.uint16).reshape(64, 64) % 4096)
    passed = []
    for uid in (RLELossless, JPEGLSLossless, JPEG2000Lossless):
        ds = Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.SOPInstanceUID = generate_uid()
        ds.Rows, ds.Columns = array.shape
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = 'MONOCHROME2'
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
        ds.PixelData = array.tobytes()
        ds.compress(uid)
        if not np.array_equal(ds.pixel_array, array):
            raise RuntimeError(f'DICOM {uid.name}: los píxeles no coinciden')
        passed.append(uid.name)
    return passed

if __name__ == '__main__':
    print('DSG_DICOM_CODEC_PASS', validate(sys.argv[-1]), flush=True)
