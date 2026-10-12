"""Synthetic physically grounded DICOM multi-frame orientation regressions."""
import ast
from pathlib import Path
import unittest
from types import SimpleNamespace

import numpy as np
from dsg.dicom_multiframe_geometry import (
    MultiframeGeometryError, normalize_multiframe_geometry,
)

ROOT=Path(__file__).resolve().parents[1]


def fixture(projections, *, lateral=None, calibration=None):
    count=len(projections)
    volume=np.stack([np.full((3,4), k+10, np.int16) for k in range(count)])
    slopes=np.asarray(calibration if calibration is not None else [k+1 for k in range(count)], dtype=float)
    intercepts=np.asarray([100+k for k in range(count)],dtype=float)
    lateral=lateral or [0.]*count
    positions=[(lateral[i],0.,float(z)) for i,z in enumerate(projections)]
    return volume, slopes, intercepts, np.eye(3), positions


class MultiframeGeometryTests(unittest.TestCase):
    def test_ascending_keeps_pixels_and_physical_first_origin(self):
        args=fixture([-5.,-4.5,-4.])
        result=normalize_multiframe_geometry(*args)
        self.assertEqual(result.source_frame_indices,(0,1,2))
        self.assertFalse(result.reordered)
        self.assertAlmostEqual(result.spacing_z_mm,.5)
        self.assertEqual(result.origin_lps,(0.,0.,-5.))
        np.testing.assert_array_equal(result.volume,args[0])
        np.testing.assert_array_equal(result.slopes,args[1])

    def test_descending_reverses_frames_and_each_calibration(self):
        args=fixture([10.,9.7,9.4,9.1])
        result=normalize_multiframe_geometry(*args)
        self.assertEqual(result.source_frame_indices,(3,2,1,0))
        self.assertEqual(result.origin_lps,(0.,0.,9.1))
        self.assertAlmostEqual(result.spacing_z_mm,.3)
        self.assertEqual(result.volume[:,0,0].tolist(),[13,12,11,10])
        self.assertEqual(result.slopes.tolist(),[4,3,2,1])
        self.assertEqual(result.intercepts.tolist(),[103,102,101,100])
        self.assertEqual(args[0][:,0,0].tolist(),[10,11,12,13],
                         "Source volume must not be changed in-place")

    def test_shuffled_frames_sort_by_real_position(self):
        args=fixture([12.,10.,11.])
        r=normalize_multiframe_geometry(*args)
        self.assertEqual(r.source_frame_indices,(1,2,0))
        self.assertEqual(r.volume[:,0,0].tolist(),[11,12,10])
        self.assertEqual(r.origin_lps,(0.,0.,10.))

    def test_oblique_orientation_is_supported_not_mirrored(self):
        a=fixture([0.,1.,2.])
        rotation=np.array([[0.,0.,1.],[1.,0.,0.],[0.,1.,0.]])
        positions=[tuple(rotation @ np.array([0.,0.,z])) for z in [3.,2.,1.]]
        r=normalize_multiframe_geometry(a[0],a[1],a[2],rotation,positions)
        self.assertEqual(r.source_frame_indices,(2,1,0))
        self.assertEqual(r.origin_lps,(1.,0.,0.))
        self.assertGreater(np.linalg.det(rotation),0)

    def test_absent_or_partial_positions_fail_closed(self):
        args=fixture([0.,1.,2.])
        for positions in (None,[args[-1][0]], [args[-1][0],None,args[-1][2]]):
            with self.subTest(positions=positions):
                with self.assertRaises(MultiframeGeometryError):
                    normalize_multiframe_geometry(*args[:-1],positions)

    def test_duplicate_positions_fail_closed(self):
        with self.assertRaisesRegex(MultiframeGeometryError,"DUPLICATE"):
            normalize_multiframe_geometry(*fixture([0.,.4,.4]))

    def test_irregular_spacing_fail_closed(self):
        with self.assertRaisesRegex(MultiframeGeometryError,"NONUNIFORM"):
            normalize_multiframe_geometry(*fixture([0.,.4,1.3]))

    def test_nonplanar_shift_fail_closed(self):
        with self.assertRaisesRegex(MultiframeGeometryError,"INPLANE"):
            normalize_multiframe_geometry(*fixture([0.,.4,.8],lateral=[0.,.1,.6]))

    def test_reflection_or_unequal_calibrations_fail_closed(self):
        args=fixture([0.,1.,2.])
        with self.assertRaisesRegex(MultiframeGeometryError,"INVALID_ORIENTATION"):
            normalize_multiframe_geometry(args[0],args[1],args[2],
                np.diag([-1.,1.,1.]),args[-1])
        with self.assertRaisesRegex(MultiframeGeometryError,"CALIBRATION_MISMATCH"):
            normalize_multiframe_geometry(args[0],args[1][:2],args[2],
                args[3],args[-1])

    def test_loader_normalization_occurs_before_cache(self):
        src=(ROOT/"_dicom_parts/01_utils_dicom_io.py").read_text(encoding="utf-8")
        fn=src[src.index("def _decode_volume_payload("):src.index("\ndef _commit_volume_payload(")]
        self.assertIn("normalize_multiframe_geometry",fn)
        self.assertLess(fn.index("normalize_multiframe_geometry"),fn.index("_sample_density_statistics"))
        self.assertLess(fn.index("normalize_multiframe_geometry"),fn.index("_prepare_external_pipeline_cache"))
        self.assertIn("image_position",src)

    def test_reader_never_reorders_pixels_without_slopes_intercepts(self):
        src=(ROOT/"_dicom_parts/01_utils_dicom_io.py").read_text(encoding="utf-8")
        self.assertIn("slopes = geometry.slopes",src)
        self.assertIn("intercepts = geometry.intercepts",src)
        self.assertIn("origin = geometry.origin_lps",src)


if __name__=="__main__":
    unittest.main()
