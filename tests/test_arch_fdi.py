import numpy as np
import importlib

ta = importlib.import_module("dsg.tooth_analysis")  # package attr is lazily None until register()


def _put(a, label, z, y, x, r=1):
    a[max(0,z-r):z+r+1, max(0,y-r):y+r+1, max(0,x-r):x+r+1] = label


def test_jaw_structures_conflict_fails_closed_without_mutating_learned_identity():
    a=np.zeros((40,20,20),dtype=np.uint8)
    _put(a,53,5,10,10)
    _put(a,54,35,10,10)
    _put(a,1,8,8,8)      # upper label physically lower
    _put(a,32,32,8,12)   # lower label physically upper
    before=a.copy()
    r=ta.correct_universal_arch_array(np,a,(1,1,1),np.eye(3),(0,0,0))
    assert not r['checked'] and not r['corrected']
    assert sorted(r['conflicting_labels']) == [1,32]
    assert np.array_equal(a,before)


def test_correct_arch_is_unchanged_and_verified():
    a=np.zeros((40,20,20),dtype=np.uint8)
    _put(a,53,5,10,10); _put(a,54,35,10,10)
    _put(a,1,32,8,8); _put(a,32,8,8,12)
    before=a.copy()
    r=ta.correct_universal_arch_array(np,a,(1,1,1),np.eye(3),(0,0,0))
    assert r['checked'] and not r['corrected']
    assert np.array_equal(a,before)


def test_uses_patient_lps_not_voxel_z():
    # Patient +Z comes from local +Y. Both jaw masks share voxel-z, differ in y.
    a=np.zeros((20,40,20),dtype=np.uint8)
    _put(a,53,10,5,10); _put(a,54,10,35,10)
    _put(a,1,10,32,8); _put(a,32,10,8,12)
    orientation=np.array([[1,0,0],[0,0,-1],[0,1,0]],dtype=float)
    r=ta.correct_universal_arch_array(np,a,(1,1,1),orientation,(0,0,0))
    assert r['checked'] and r['source']=='JAW_STRUCTURES_LPS'


def test_fallback_global_arch_inversion_is_reported_not_rewritten():
    a=np.zeros((40,20,20),dtype=np.uint8)
    _put(a,1,5,6,6); _put(a,8,6,8,8)
    _put(a,25,34,10,10); _put(a,32,35,12,12)
    before=a.copy()
    r=ta.correct_universal_arch_array(np,a,(1,1,1),np.eye(3),(0,0,0))
    assert not r['checked'] and not r['corrected']
    assert r['source']=='DENTAL_ARCH_ORDER_LPS'
    assert r['suggested_global_swap']
    assert np.array_equal(a,before)


def test_single_arch_without_jaw_evidence_fails_closed():
    a=np.zeros((20,20,20),dtype=np.uint8)
    _put(a,1,10,6,6); _put(a,2,10,8,8)
    r=ta.correct_universal_arch_array(np,a,(1,1,1),np.eye(3),(0,0,0))
    assert not r['checked'] and not r['corrected']
    assert r['source']=='INSUFFICIENT_ARCH_EVIDENCE'


def test_mirroring_relabels_only_wrong_side_voxels_not_whole_semantic_label():
    a=np.zeros((40,40,60),dtype=np.uint8)
    # Correct central identities in DICOM LPS (+X = patient left).
    for lab,x in ((8,25),(9,35),(24,35),(25,25)):
        _put(a,lab,20,20,x)
    _put(a,5,20,20,8,r=2)    # FDI 14 correct patient-right component
    _put(a,12,20,20,50,r=2)  # FDI 24 correct patient-left component
    _put(a,12,20,20,18,r=2)  # only this label-12 island is on wrong side
    r=ta.correct_universal_mirroring_array(np,a,(1,1,1),np.eye(3),(0,0,0))
    assert r['corrected'] and r['changed_labels']==[12]
    # The correct left component must remain 12.  Old DSG 9.1.29 could remap
    # the entire label and swallow it into label 5.
    assert np.any(a[:,:,:,] == 12)
    xs12=np.argwhere(a==12)[:,2]
    assert xs12.min() >= 48
    q=ta.validate_universal_labelmap_topology(np,a,(1,1,1))
    assert q['invalid_fdi']==[14]


def test_topology_gate_rejects_two_tooth_sized_islands():
    a=np.zeros((40,40,60),dtype=np.uint8)
    _put(a,5,20,20,10,r=2)
    _put(a,5,20,20,40,r=2)
    q=ta.validate_universal_labelmap_topology(np,a,(1,1,1))
    assert not q['pass']
    assert q['invalid_labels']==[5]
    assert q['invalid_fdi']==[14]
    assert q['details'][0]['significant_component_count']==2


def test_counterparts():
    assert ta.universal_arch_counterpart(1)==32
    assert ta.universal_arch_counterpart(8)==25
    assert ta.universal_arch_counterpart(9)==24
    assert ta.universal_arch_counterpart(16)==17
    assert ta.universal_arch_counterpart(33)==52
    assert ta.universal_arch_counterpart(42)==43
