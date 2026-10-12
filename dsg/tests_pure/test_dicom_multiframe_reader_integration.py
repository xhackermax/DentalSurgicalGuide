"""Exercise the real DICOM reader functions with synthetic enhanced headers.

AST isolation loads exactly the production function implementations without
requiring bpy, actual patient files or 3-D image engines.
"""
from __future__ import annotations

import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
READER=ROOT/"_dicom_parts/01_utils_dicom_io.py"


def production_functions(*names, injected):
    tree=ast.parse(READER.read_text(encoding="utf-8"))
    nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
    if len(nodes)!=len(names):
        raise AssertionError("Production reader functions not found")
    module=ast.Module(
        body=[ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0),*nodes],
        type_ignores=[],
    )
    ns={"__package__":"dsg","__name__":"dsg.reader_regression","math":math,
        "load_numpy":lambda:np,"_DSG_LOG":SimpleNamespace(info=lambda *x:None)}
    ns.update(injected)
    exec(compile(ast.fix_missing_locations(module),str(READER),"exec"),ns)
    return ns


def enhanced_header(z_positions, *, top_level_position=(900.,900.,900.), missing_at=None):
    seq=[]
    for i,z in enumerate(z_positions):
        position=None if i==missing_at else SimpleNamespace(
            ImagePositionPatient=(0.,0.,float(z)))
        plane=[position] if position is not None else []
        seq.append(SimpleNamespace(PlanePositionSequence=plane))
    return SimpleNamespace(
        ImageOrientationPatient=(1.,0.,0.,0.,1.,0.),
        ImagePositionPatient=top_level_position,
        PerFrameFunctionalGroupsSequence=seq,
        PixelSpacing=(.25,.25),
    )


def _first_item(dataset, key):
    val=getattr(dataset,key,None)
    return val[0] if val else None


def position_functions():
    def _seq(ds,name,index):
        seq=getattr(ds,name,None)
        return seq[index] if seq and index<len(seq) else None
    return production_functions("image_position","_strict_multiframe_positions",
         "_strict_multiframe_orientation",injected=dict(
            _first_item=_first_item,_sequence_item=_seq,
            _nested_first=lambda d,*attrs:None,
            as_tuple3=lambda x,default=(0,0,0):tuple(map(float,x)),
        ))


class DicomReaderIntegration(unittest.TestCase):
    def test_per_frame_position_has_priority_over_stale_top_level(self):
        r=position_functions()
        header=enhanced_header((9.,8.,7.))
        self.assertEqual(r["image_position"](header,2),(0.,0.,7.))
        self.assertEqual(r["_strict_multiframe_positions"](header,3),
                         [(0.,0.,9.),(0.,0.,8.),(0.,0.,7.)])

    def test_partial_position_is_rejected_not_repeated(self):
        r=position_functions()
        header=enhanced_header((9.,8.,7.),missing_at=1)
        self.assertEqual(r["image_position"](header,1),(900.,900.,900.))
        with self.assertRaisesRegex(RuntimeError,"POSITIONS_MISSING"):
            r["_strict_multiframe_positions"](header,3)

    def test_orientation_missing_and_changing_rejected(self):
        r=position_functions()
        h=enhanced_header((3.,2.,1.))
        h.ImageOrientationPatient=None
        with self.assertRaisesRegex(RuntimeError,"ORIENTATION_MISSING"):
            r["_strict_multiframe_orientation"](h,3)
        h.ImageOrientationPatient=(1.,0.,0.,0.,1.,0.)
        h.PerFrameFunctionalGroupsSequence[1].PlaneOrientationSequence=[
            SimpleNamespace(ImageOrientationPatient=(0.,1.,0.,-1.,0.,0.))]
        with self.assertRaisesRegex(RuntimeError,"CONFLICTING_ORIENTATION"):
            r["_strict_multiframe_orientation"](h,3)

    def payload_factory(self, kind, positions):
        reader=position_functions()
        header=enhanced_header(positions)
        vox=np.stack([np.full((2,3),10+i,dtype=np.int16) for i in range(len(positions))])
        slopes=np.arange(1,len(positions)+1,dtype=float)
        offsets=np.arange(101,101+len(positions),dtype=float)
        cache=Mock(return_value={"pipeline_volume_path":"fixture.npy"})
        stats=Mock(return_value=(0.,1.,0.,1.))
        if kind=="MULTIFRAME":
            datasets=[header]
        else:
            datasets=[SimpleNamespace(ImagePositionPatient=(0.,0.,float(z)),
                                      ImageOrientationPatient=header.ImageOrientationPatient)
                      for z in positions]
        probe=SimpleNamespace(source_kind=kind,header=header,
             spacing_zyx_mm=(.9,.25,.25),source_files=[f"{i}.dcm" for i in range(len(positions))])
        def loader(p,callback):
            return vox,slopes,offsets,datasets
        injected=dict(
            _load_multiframe=loader,_load_classic_series=loader,
            _resolve_classic_series_in_worker=lambda *x:None,
            _orientation_matrix=lambda ds:np.eye(3),
            image_position=reader["image_position"],
            _strict_multiframe_orientation=reader["_strict_multiframe_orientation"],
            _strict_multiframe_positions=reader["_strict_multiframe_positions"],
            pixel_spacing=lambda ds:(.25,.25),
            _sample_density_statistics=stats,
            _prepare_external_pipeline_cache=cache,
        )
        ns=production_functions("_decode_volume_payload",injected=injected)
        return ns["_decode_volume_payload"],probe,stats,cache

    def test_multiframe_normalized_before_cache_and_statistics(self):
        run,probe,stats,cache=self.payload_factory("MULTIFRAME",(3.,2.,1.))
        result=run(probe)
        self.assertEqual(result["origin"],(0.,0.,1.))
        self.assertEqual(result["spacing_zyx_mm"],(1.,.25,.25))
        self.assertEqual(result["volume"][:,0,0].tolist(),[12,11,10])
        self.assertEqual(result["slopes"].tolist(),[3.,2.,1.])
        self.assertEqual(result["intercepts"].tolist(),[103.,102.,101.])
        self.assertEqual(stats.call_args.args[0][:,0,0].tolist(),[12,11,10])
        self.assertEqual(cache.call_args.args[2].tolist(),[3.,2.,1.])

    def test_classic_downward_files_keep_header_order_in_sync(self):
        run,probe,stats,cache=self.payload_factory("SERIES",(4.,3.,2.))
        result=run(probe)
        self.assertEqual(result["origin"],(0.,0.,2.))
        self.assertEqual(result["volume"][:,0,0].tolist(),[12,11,10])
        self.assertEqual([ds.ImagePositionPatient[2] for ds in result["datasets"]],[2.,3.,4.])
        self.assertEqual(probe.source_files,["2.dcm","1.dcm","0.dcm"])

    def test_classic_missing_orientation_fails_before_cache(self):
        run,probe,stats,cache=self.payload_factory("SERIES",(3.,2.,1.))
        probe.header.ImageOrientationPatient=None
        def loader(p, callback):
            return (np.zeros((3,2,3),dtype=np.int16),np.ones(3),np.zeros(3),
                    [SimpleNamespace(ImagePositionPatient=(0,0,k)) for k in (3,2,1)])
        # The reader binds its loader via function globals.
        run.__globals__["_load_classic_series"]=loader
        with self.assertRaisesRegex(RuntimeError,"SERIES_ORIENTATION_MISSING"):
            run(probe)
        cache.assert_not_called()


if __name__=="__main__":
    unittest.main()
