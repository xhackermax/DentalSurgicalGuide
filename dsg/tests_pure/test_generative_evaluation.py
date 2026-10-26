import unittest
import numpy as np
from dsg.ios_surface import SurfaceAnchor,GenerationConfig,ConstraintSet
from dsg.geodesic_router import CandidatePath
from dsg.frame_generator import FramePerimeter,build_frame_graph
from dsg.frame_optimizer import evaluate_frame,rank_candidate_sets
from dsg.frame_swept_clearance_core import SphereKeepOut


def graph(paths):
    anchors=tuple(SurfaceAnchor('P'+str(i),'s',0,(1.,0.,0.),0) for i in range(4))
    perimeter=FramePerimeter('frame',np.array([[0,0,0],[10,0,0],[10,10,0],[0,10,0]],float),anchors,'digest')
    return build_frame_graph(perimeter,tuple(paths),GenerationConfig(radius_mm=.1))


def path(label,start,points,end='S1'):
    points=np.asarray(points,float);length=float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum())
    return CandidatePath(label,start,end,points,(),length,length,'test',0)


class EvaluationTests(unittest.TestCase):
    def test_valid_geometry_does_not_claim_mechanics(self):
        result=evaluate_frame(graph([path('a','P0',[[0,0,0],[5,5,0]])]),ConstraintSet(),GenerationConfig(radius_mm=.1))
        self.assertEqual(result.status,'CANDIDATE')
        self.assertFalse(result.report['mechanics_evaluated'])
        self.assertFalse(result.report['post_boolean_validated'])
        self.assertIn('FRAME_PATH_SOURCE_UNVERIFIABLE',result.report['warnings'])

    def test_physical_crossing_requires_joint_or_rejection(self):
        g=graph([path('a','P0',[[0,0,0],[10,10,0]],'S1'),path('b','P1',[[10,0,0],[0,10,0]],'S2')])
        result=evaluate_frame(g,ConstraintSet(),GenerationConfig(radius_mm=.1))
        self.assertEqual(result.status,'INVALID_INPUT');self.assertIn('MEMBER_INTERSECTION',result.rejections)

    def test_clear_projected_crossing_is_not_intersection(self):
        g=graph([path('a','P0',[[0,0,0],[10,10,0]],'S1'),path('b','P1',[[10,0,0],[10,0,3],[0,10,3]],'S2')])
        result=evaluate_frame(g,ConstraintSet(),GenerationConfig(radius_mm=.1))
        self.assertEqual(result.status,'CANDIDATE')

    def test_missing_required_volume_is_unverifiable(self):
        result=evaluate_frame(graph([]),ConstraintSet(required_zones_complete=False),GenerationConfig())
        self.assertEqual(result.status,'UNVERIFIABLE')

    def test_path_or_smoothing_cannot_cross_keepout(self):
        zone=SphereKeepOut('block',(5,5,0),1.)
        result=evaluate_frame(graph([path('a','P0',[[0,0,0],[10,10,0]])]),ConstraintSet(protected_zones=(zone,)),GenerationConfig(radius_mm=.1))
        self.assertNotEqual(result.status,'CANDIDATE')

    def test_self_crossing_and_folded_tube_are_rejected(self):
        for points in ([[0,0,0],[10,10,0],[10,0,0],[0,10,0]],
                       [[0,0,0],[10,0,0],[10,.15,0],[0,.15,0]]):
            result=evaluate_frame(graph([path('self','P0',points)]),ConstraintSet(),GenerationConfig(radius_mm=.1))
            self.assertEqual(result.status,'INVALID_INPUT')
            self.assertIn('MEMBER_SELF_INTERSECTION',result.rejections)

    def test_acute_declared_junction_is_not_a_false_crossing(self):
        g=graph([path('a','P0',[[x,0,0] for x in range(21)],'S1'),path('b','P0',[[x,.4*x,0] for x in range(21)],'S2')])
        checked=evaluate_frame(g,ConstraintSet(),GenerationConfig(radius_mm=.1))
        self.assertEqual(checked.status,'CANDIDATE',checked.rejections)

    def test_shared_joint_does_not_authorize_later_recrossing(self):
        g=graph([path('a','P0',[[0,0,0],[5,0,0],[10,0,0],[15,0,0],[20,0,0]],'S1'),path('b','P0',[[0,0,0],[5,5,0],[10,5,0],[15,-2,0],[20,-2,0]],'S2')])
        checked=evaluate_frame(g,ConstraintSet(),GenerationConfig(radius_mm=.1))
        self.assertIn('MEMBER_INTERSECTION',checked.rejections)

    def test_long_coincident_branch_is_not_a_declared_joint(self):
        g=graph([path('a','P0',[[0,0,0],[20,0,0]],'S1'),path('b','P0',[[0,0,0],[15,0,0],[15,5,0]],'S2')])
        checked=evaluate_frame(g,ConstraintSet(),GenerationConfig(radius_mm=1.))
        self.assertIn('MEMBER_INTERSECTION',checked.rejections)

    def test_fully_encased_branch_is_not_a_lattice_member(self):
        g=graph([path('a','P0',[[0,0,0],[20,0,0]],'S1'),path('b','P0',[[0,0,0],[.02,.00001,0]],'S2')])
        checked=evaluate_frame(g,ConstraintSet(),GenerationConfig(radius_mm=1.))
        self.assertIn('MEMBER_INTERSECTION',checked.rejections)

    def test_rank_is_stable(self):
        a=evaluate_frame(graph([path('b','P0',[[0,0,0],[8,8,0]])]),ConstraintSet(),GenerationConfig(radius_mm=.1))
        b=evaluate_frame(graph([path('a','P0',[[0,0,0],[5,5,0]])]),ConstraintSet(),GenerationConfig(radius_mm=.1))
        self.assertEqual(rank_candidate_sets((a,b)),rank_candidate_sets((b,a)))

if __name__=='__main__':unittest.main()
