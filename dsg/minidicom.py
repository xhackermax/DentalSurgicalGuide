"""Tiny self-contained DICOM reader used only when pydicom is unavailable.

It intentionally supports the common uncompressed little-endian CT/CBCT
transfer syntaxes used by classic dental series and basic multi-frame files.
Compressed/encapsulated Pixel Data is rejected with a clear message instead of
silently decoding it incorrectly.  The full pydicom package, when already
present, remains preferred automatically.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import struct
from pathlib import Path
from types import SimpleNamespace

import numpy as np

__version__ = "DSG-mini-1.0"


class InvalidDicomError(Exception):
    pass


class _Errors:
    InvalidDicomError = InvalidDicomError

errors = _Errors()

# tag -> (keyword, VR)
TAGS = {
    (0x0002,0x0010): ("TransferSyntaxUID","UI"),
    (0x0008,0x0016): ("SOPClassUID","UI"),
    (0x0008,0x0060): ("Modality","CS"),
    (0x0008,0x0070): ("Manufacturer","LO"),
    (0x0008,0x103E): ("SeriesDescription","LO"),
    (0x0008,0x1090): ("ManufacturerModelName","LO"),
    (0x0010,0x0010): ("PatientName","PN"),
    (0x0010,0x0020): ("PatientID","LO"),
    (0x0018,0x0050): ("SliceThickness","DS"),
    (0x0018,0x0088): ("SpacingBetweenSlices","DS"),
    (0x0018,0x1164): ("ImagerPixelSpacing","DS"),
    (0x0020,0x000E): ("SeriesInstanceUID","UI"),
    (0x0020,0x0013): ("InstanceNumber","IS"),
    (0x0020,0x0032): ("ImagePositionPatient","DS"),
    (0x0020,0x0037): ("ImageOrientationPatient","DS"),
    (0x0020,0x1041): ("SliceLocation","DS"),
    (0x0028,0x0002): ("SamplesPerPixel","US"),
    (0x0028,0x0004): ("PhotometricInterpretation","CS"),
    (0x0028,0x0008): ("NumberOfFrames","IS"),
    (0x0028,0x0010): ("Rows","US"),
    (0x0028,0x0011): ("Columns","US"),
    (0x0028,0x0030): ("PixelSpacing","DS"),
    (0x0028,0x0100): ("BitsAllocated","US"),
    (0x0028,0x0101): ("BitsStored","US"),
    (0x0028,0x0102): ("HighBit","US"),
    (0x0028,0x0103): ("PixelRepresentation","US"),
    (0x0028,0x1052): ("RescaleIntercept","DS"),
    (0x0028,0x1053): ("RescaleSlope","DS"),
    (0x7FE0,0x0010): ("PixelData","OW"),
}

_LONG_VR = {"OB","OD","OF","OL","OV","OW","SQ","UC","UR","UT","UN"}
_TEXT_VR = {"AE","AS","CS","DA","DT","LO","LT","PN","SH","ST","TM","UC","UI","UR","UT"}


def _clean_text(raw: bytes):
    return raw.decode("utf-8", errors="ignore").rstrip("\x00 ")


def _decode(vr: str, raw: bytes):
    if vr in _TEXT_VR:
        return _clean_text(raw)
    if vr in {"DS","IS"}:
        text = _clean_text(raw)
        parts = text.split("\\") if text else []
        if vr == "DS":
            vals = [float(x) for x in parts if x != ""]
        else:
            vals = [int(float(x)) for x in parts if x != ""]
        return vals[0] if len(vals) == 1 else vals
    if vr == "US":
        vals = list(struct.unpack("<" + "H" * (len(raw)//2), raw[:len(raw)//2*2]))
        return vals[0] if len(vals) == 1 else vals
    if vr == "SS":
        vals = list(struct.unpack("<" + "h" * (len(raw)//2), raw[:len(raw)//2*2]))
        return vals[0] if len(vals) == 1 else vals
    if vr == "UL":
        vals = list(struct.unpack("<" + "I" * (len(raw)//4), raw[:len(raw)//4*4]))
        return vals[0] if len(vals) == 1 else vals
    if vr == "SL":
        vals = list(struct.unpack("<" + "i" * (len(raw)//4), raw[:len(raw)//4*4]))
        return vals[0] if len(vals) == 1 else vals
    if vr == "FL":
        vals = list(struct.unpack("<" + "f" * (len(raw)//4), raw[:len(raw)//4*4]))
        return vals[0] if len(vals) == 1 else vals
    if vr == "FD":
        vals = list(struct.unpack("<" + "d" * (len(raw)//8), raw[:len(raw)//8*8]))
        return vals[0] if len(vals) == 1 else vals
    return raw


def _skip_undefined(fp):
    """Skip undefined-length item/sequence by scanning delimiter tags."""
    depth = 1
    while depth > 0:
        raw = fp.read(8)
        if len(raw) < 8:
            return
        group, elem, length = struct.unpack("<HHI", raw)
        if (group, elem) in {(0xFFFE,0xE000), (0xFFFE,0xE100)}:
            if length == 0xFFFFFFFF:
                depth += 1
            else:
                fp.seek(length, 1)
        elif (group, elem) in {(0xFFFE,0xE00D), (0xFFFE,0xE0DD)}:
            depth -= 1
            if length not in (0, 0xFFFFFFFF):
                fp.seek(length, 1)
        else:
            if length == 0xFFFFFFFF:
                depth += 1
            else:
                fp.seek(length, 1)


def _read_element(fp, explicit: bool):
    tag_raw = fp.read(4)
    if len(tag_raw) < 4:
        return None
    group, elem = struct.unpack("<HH", tag_raw)
    tag = (group, elem)
    if group == 0xFFFE:
        length_raw = fp.read(4)
        if len(length_raw) < 4:
            return None
        return tag, "ITEM", struct.unpack("<I", length_raw)[0], None
    if explicit:
        vr_raw = fp.read(2)
        if len(vr_raw) < 2:
            return None
        vr = vr_raw.decode("ascii", errors="ignore")
        if vr in _LONG_VR:
            fp.read(2)
            length_raw = fp.read(4)
            if len(length_raw) < 4:
                return None
            length = struct.unpack("<I", length_raw)[0]
        else:
            length_raw = fp.read(2)
            if len(length_raw) < 2:
                return None
            length = struct.unpack("<H", length_raw)[0]
    else:
        length_raw = fp.read(4)
        if len(length_raw) < 4:
            return None
        length = struct.unpack("<I", length_raw)[0]
        vr = TAGS.get(tag, (None, "UN"))[1]
    return tag, vr, length, None


class Dataset(SimpleNamespace):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._filepath = ""
        self._transfer_syntax = "1.2.840.10008.1.2.1"
        self._pixel_offset = None
        self._pixel_length = 0

    @property
    def pixel_array(self):
        return pixel_array(self._filepath, dataset=self)

    def __str__(self):
        keys = sorted(k for k in self.__dict__ if not k.startswith("_"))
        return "\n".join(f"{k}: {getattr(self,k)!r}" for k in keys)


def dcmread(filepath, force=False, stop_before_pixels=False, specific_tags=None, **kwargs):
    path = Path(filepath)
    ds = Dataset()
    ds._filepath = str(path)
    with path.open("rb") as fp:
        pre = fp.read(132)
        has_magic = len(pre) >= 132 and pre[128:132] == b"DICM"
        if not has_magic:
            if not force:
                raise InvalidDicomError("Missing DICM preamble")
            fp.seek(0)

        # File meta is always explicit VR little-endian.
        transfer = "1.2.840.10008.1.2.1"
        dataset_start = fp.tell()
        while True:
            pos = fp.tell()
            elem = _read_element(fp, True)
            if elem is None:
                break
            tag, vr, length, _ = elem
            if tag[0] != 0x0002:
                fp.seek(pos)
                dataset_start = pos
                break
            if length == 0xFFFFFFFF:
                _skip_undefined(fp); continue
            raw = fp.read(length)
            info = TAGS.get(tag)
            if info:
                value = _decode(vr or info[1], raw)
                setattr(ds, info[0], value)
                if info[0] == "TransferSyntaxUID":
                    transfer = str(value)

        ds._transfer_syntax = transfer
        if transfer == "1.2.840.10008.1.2.2":
            raise InvalidDicomError("Big-endian DICOM is not supported by the bundled reader")
        if transfer == "1.2.840.10008.1.2.1.99":
            # In Deflated Explicit VR Little Endian the dataset itself is deflated,
            # so the mini reader cannot even inspect Rows/Columns safely.
            raise InvalidDicomError(
                "Deflated DICOM requires the full DSG DICOM engine"
            )

        # Most encapsulated image transfer syntaxes (JPEG/JPEG-LS/JPEG2000/RLE)
        # still encode the dataset header as Explicit VR Little Endian; only the
        # PixelData payload is compressed.  Therefore the bundled reader may inspect
        # metadata such as Rows/Columns/Series UID, but pixel_array() will continue
        # to fail closed until the full pydicom codec runtime is installed.
        explicit = transfer != "1.2.840.10008.1.2"
        fp.seek(dataset_start)
        while True:
            pos = fp.tell()
            elem = _read_element(fp, explicit)
            if elem is None:
                break
            tag, vr, length, _ = elem
            if tag == (0x7FE0,0x0010):
                ds._pixel_offset = fp.tell()
                ds._pixel_length = int(length)
                if stop_before_pixels:
                    # Metadata discovery is valid even when PixelData is encapsulated.
                    break
                if length == 0xFFFFFFFF:
                    raise InvalidDicomError(
                        "Encapsulated/compressed PixelData requires the full DSG DICOM engine"
                    )
                ds.PixelData = fp.read(length)
                continue
            if length == 0xFFFFFFFF:
                _skip_undefined(fp)
                continue
            raw = fp.read(length)
            info = TAGS.get(tag)
            if info:
                try:
                    setattr(ds, info[0], _decode(vr or info[1], raw))
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        return ds


def pixel_array(filepath, dataset=None):
    ds = dataset if dataset is not None else dcmread(filepath, force=True, stop_before_pixels=False)
    if ds._transfer_syntax not in {"1.2.840.10008.1.2", "1.2.840.10008.1.2.1"}:
        raise RuntimeError("El lector DICOM incluido solo decodifica píxeles sin compresión")
    raw = getattr(ds, "PixelData", None)
    if raw is None:
        if ds._pixel_offset is None:
            # Re-read including pixels to establish offset.
            ds = dcmread(filepath, force=True, stop_before_pixels=False)
            raw = getattr(ds, "PixelData", None)
        else:
            with open(filepath, "rb") as fp:
                fp.seek(ds._pixel_offset)
                raw = fp.read(ds._pixel_length)
    if raw is None:
        raise RuntimeError("DICOM sin PixelData")
    rows = int(getattr(ds, "Rows", 0) or 0)
    cols = int(getattr(ds, "Columns", 0) or 0)
    frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
    samples = int(getattr(ds, "SamplesPerPixel", 1) or 1)
    bits = int(getattr(ds, "BitsAllocated", 16) or 16)
    signed = int(getattr(ds, "PixelRepresentation", 0) or 0) == 1
    if bits == 8:
        dtype = np.dtype("i1" if signed else "u1")
    elif bits == 16:
        dtype = np.dtype("<i2" if signed else "<u2")
    elif bits == 32:
        dtype = np.dtype("<i4" if signed else "<u4")
    else:
        raise RuntimeError(f"BitsAllocated={bits} no soportado por el lector incluido")
    arr = np.frombuffer(raw, dtype=dtype)
    expected = frames * rows * cols * samples
    if rows <= 0 or cols <= 0 or arr.size < expected:
        raise RuntimeError("PixelData DICOM incompleto")
    arr = arr[:expected]
    if samples > 1:
        arr = arr.reshape((frames, rows, cols, samples)) if frames > 1 else arr.reshape((rows, cols, samples))
    else:
        arr = arr.reshape((frames, rows, cols)) if frames > 1 else arr.reshape((rows, cols))
    return arr.copy()


class _Pixels:
    @staticmethod
    def pixel_array(path):
        return pixel_array(path)

pixels = _Pixels()
