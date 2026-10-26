import unittest
import numpy as np
from dsg.ios_surface import GenerationConfig,ConstraintSet,SurfaceAnchor
from dsg.geodesic_router import CandidatePath
from dsg.frame_generator import FramePerimeter,build_frame_graph
from dsg.frame_optimizer import evaluate_frame


def route(label,start,end,points):
    xyz=np.asarray(points,float)
    length=float(np.linalg.norm(np.diff(xyz,axis=0),axis=1).sum())
    return CandidatePath(label,start,end,xyz,(),length,length,'fixture',0,None)


class ContinuousPrimaryTests(unittest.TestCase):
    def check(self,paths,groups):
        anchors=tuple(SurfaceAnchor('P'+str(i),'s',0,(1.,0.,0.),0) for i in range(3))
        perimeter=FramePerimeter('frame',np.array([[0,0,0],[10,0,0],[5,-5,0]]),anchors,'unchanged')
        config=GenerationConfig(radius_mm=1.25)
        return evaluate_frame(build_frame_graph(perimeter,paths,config),ConstraintSet(),config,continuous_primary_groups=groups)

    def fixture(self):
        return (route('a','P0','J0',[[0,0,0],[2,0,0]]),route('b','J0','S',[[2,0,0],[4,0,0]]))

    def test_short_straight_continuation_is_one_tube(self):
        checked=self.check(self.fixture(),{'parent':('a','b')})
        self.assertEqual(checked.status,'CANDIDATE',checked.rejections)

    def test_other_branch_still_collides(self):
        paths=self.fixture()+(route('cross','P1','X',[[10,0,0],[2,-4,0],[2,4,0]]),)
        checked=self.check(paths,{'parent':('a','b')})
        self.assertIn('MEMBER_INTERSECTION',checked.rejections)
        unnamed=self.check(paths,{None:('a','b')})
        self.assertIn('MEMBER_INTERSECTION',unnamed.rejections)

    def test_invalid_disconnected_group_does_not_bypass_collision(self):
        paths=(self.fixture()[0],route('b','P1','S',[[2,0,0],[4,0,0]]))
        checked=self.check(paths,{'parent':('a','b')})
        self.assertNotEqual(checked.status,'CANDIDATE')

    def test_nonlocal_fold_in_whole_parent_is_rejected(self):
        paths=(route('a','P0','J0',[[0,0,0],[8,0,0]]),
               route('b','J0','S',[[8,0,0],[8,5,0],[0,5,0],[0,1,0],[6,1,0]]))
        checked=self.check(paths,{'parent':('a','b')})
        self.assertIn('MEMBER_SELF_INTERSECTION',checked.rejections)

    def test_member_cannot_belong_to_two_parents(self):
        checked=self.check(self.fixture(),{'one':('a','b'),'two':('a',)})
        self.assertNotEqual(checked.status,'CANDIDATE')

    def test_adjacent_edges_fold_back_into_the_same_tube(self):
        paths=(self.fixture()[0],route('b','J0','S',[[2,0,0],[0,.5,0]]))
        checked=self.check(paths,{'parent':('a','b')})
        self.assertIn('MEMBER_SELF_INTERSECTION',checked.rejections)

    def test_malformed_group_is_rejected(self):
        checked=self.check(self.fixture(),{'parent':None})
        self.assertIn('INVALID_CONTINUOUS_PRIMARY_GROUP',checked.rejections)


if __name__=='__main__':unittest.main()
