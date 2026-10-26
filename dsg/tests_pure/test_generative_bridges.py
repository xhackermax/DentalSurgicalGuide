import unittest
import numpy as np
from dsg.ios_surface import SolidClearanceIndex,ConstraintSet,GenerationConfig
from dsg.geodesic_router import generate_bridge_candidates
from dsg.frame_swept_clearance_core import CylinderKeepOut


def box_obstacle(lo=(-20,-20,-4),hi=(20,20,0)):
    vertices=np.array([[x,y,z] for z in (lo[2],hi[2]) for y in (lo[1],hi[1]) for x in (lo[0],hi[0])],float)
    faces=np.array([[0,2,3],[0,3,1],[4,5,7],[4,7,6],[0,1,5],[0,5,4],[2,6,7],[2,7,3],[0,4,6],[0,6,2],[1,3,7],[1,7,5]])
    return {'label':'IOS','vertices_mm':vertices,'triangles':faces,'closed':True}


class BridgeTests(unittest.TestCase):
    def test_index_detects_containment_and_tube_not_only_centerline(self):
        index=SolidClearanceIndex(box_obstacle())
        self.assertFalse(index.clear([[0,0,-2],[5,0,-2]],.4)[0])
        self.assertFalse(index.clear([[0,0,.2],[5,0,.2]],.4)[0])
        self.assertTrue(index.clear([[0,0,1],[5,0,1]],.4)[0])

    def test_bridge_lifts_over_ios_and_preserves_attachments(self):
        index=SolidClearanceIndex(box_obstacle());config=GenerationConfig(radius_mm=.5)
        result=generate_bridge_candidates('A','B',[0,0,0],[10,0,0],[0,0,1],[0,0,1],index,ConstraintSet(),config,joint_radius_mm=1.)
        self.assertTrue(result.paths,result.rejections)
        for path in result.paths:
            np.testing.assert_allclose(path.points_mm[[0,-1]],[[0,0,0],[10,0,0]])
            self.assertGreater(float(path.points_mm[:,2].max()),.5)
            self.assertEqual(path.backend,'CERTIFIED_FREE_BRIDGE')

    def test_unverified_solid_cannot_authorize_bridge(self):
        obstacle=box_obstacle();obstacle['closed']=False
        with self.assertRaisesRegex(ValueError,'UNVERIFIABLE'):
            SolidClearanceIndex(obstacle)

    def test_short_link_does_not_hide_whole_collision_in_attachment_pockets(self):
        result=generate_bridge_candidates('A','B',[0,0,-2],[.1,0,-2],[0,0,1],[0,0,1],SolidClearanceIndex(box_obstacle()),ConstraintSet(),GenerationConfig(radius_mm=.5),joint_radius_mm=1.)
        self.assertFalse(result.paths)

    def test_protected_drill_is_checked_even_inside_attachment_pocket(self):
        zone=CylinderKeepOut('DRILL',(0,0,0),(0,0,1),1.,20.)
        result=generate_bridge_candidates('A','B',[0,0,0],[10,0,0],[0,0,1],[0,0,1],SolidClearanceIndex(box_obstacle()),ConstraintSet(protected_zones=(zone,)),GenerationConfig(radius_mm=.5),joint_radius_mm=1.)
        self.assertFalse(result.paths)

    def test_overlapping_closed_shells_are_solid_union(self):
        a=box_obstacle((-20,-20,-20),(12,13,14));b=box_obstacle((-12,-13,-14),(20,20,20))
        joined={'label':'IOS','vertices_mm':np.vstack((a['vertices_mm'],b['vertices_mm'])),'triangles':np.vstack((a['triangles'],b['triangles']+8)),'closed':True}
        index=SolidClearanceIndex(joined)
        self.assertFalse(index.clear([[0,0,0],[10,0,0]],.5)[0])
        result=generate_bridge_candidates('A','B',[0,0,0],[10,0,0],[0,0,1],[0,0,1],index,ConstraintSet(),GenerationConfig(radius_mm=.5),joint_radius_mm=1.)
        self.assertFalse(result.paths)

    def test_outward_is_derived_from_model_not_implant_axis(self):
        index=SolidClearanceIndex(box_obstacle())
        self.assertGreater(index.outward_at([0,0,0])[2],.9)
        self.assertLess(index.outward_at([0,0,-4])[2],-.9)

    def test_bridge_can_detour_around_middle_drill_lumen(self):
        from dsg.frame_swept_clearance_core import check_swept_tube_clearance
        zone=CylinderKeepOut('DRILL',(5,0,2),(0,0,1),1.,20.)
        result=generate_bridge_candidates('A','B',[0,0,2],[10,0,2],[0,0,1],[0,0,1],SolidClearanceIndex(box_obstacle()),ConstraintSet(protected_zones=(zone,)),GenerationConfig(radius_mm=.5),joint_radius_mm=1.)
        self.assertTrue(result.paths,result.rejections)
        for path in result.paths:self.assertTrue(check_swept_tube_clearance(path.points_mm,[.5]*len(path.points_mm),(zone,)).clear)

    def test_alternatives_are_ranked_by_real_length_not_search_order(self):
        result=generate_bridge_candidates('A','B',[0,0,2],[10,0,2],[0,0,1],[0,0,1],SolidClearanceIndex(box_obstacle()),ConstraintSet(),GenerationConfig(radius_mm=.5),joint_radius_mm=1.)
        self.assertGreaterEqual(len(result.paths),2)
        self.assertLess(result.paths[1].length_mm,10.5)

    def test_clear_air_prefers_direct_short_bridge(self):
        result=generate_bridge_candidates('A','B',[0,0,2],[10,0,2],[0,0,1],[0,0,1],SolidClearanceIndex(box_obstacle()),ConstraintSet(),GenerationConfig(radius_mm=.5),joint_radius_mm=1.)
        self.assertTrue(result.paths)
        self.assertAlmostEqual(result.paths[0].length_mm,10.,places=6)

if __name__=='__main__':unittest.main()
