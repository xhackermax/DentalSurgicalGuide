import unittest
import numpy as np
from dsg.ios_surface import GenerationConfig,ConstraintSet,SurfaceAnchor
from dsg.geodesic_router import CandidatePath
from dsg.frame_generator import FramePerimeter,build_frame_graph,split_lattice_primaries,lattice_links
from dsg.frame_optimizer import evaluate_frame


def route(name,start,end,points,radius=None):
    values=np.asarray(points,float);length=float(np.linalg.norm(np.diff(values,axis=0),axis=1).sum())
    return CandidatePath(name,start,end,values,(),length,length,'fixture',0,radius)


class LatticeTests(unittest.TestCase):
    def fixture(self):
        return (route('left','P0','S_LEFT',[[0,y,0] for y in range(21)]),
                route('right','P1','S_RIGHT',[[10,y,0] for y in range(21)]))

    def test_split_preserves_primary_geometry_and_shared_junctions(self):
        original=self.fixture();segments,junctions=split_lattice_primaries(original)
        self.assertEqual(len(segments),6);self.assertEqual(len(junctions),4)
        for parent in original:
            parts=[p for p in segments if p.route_id.startswith(parent.route_id+':')]
            joined=np.vstack([parts[0].points_mm]+[p.points_mm[1:] for p in parts[1:]])
            np.testing.assert_array_equal(joined,parent.points_mm)
            for a,b in zip(parts,parts[1:]):
                self.assertEqual(a.end_id,b.start_id)
                np.testing.assert_array_equal(a.points_mm[-1],b.points_mm[0])

    def test_links_connect_reinforcements_not_everything_to_sleeve(self):
        _,junctions=split_lattice_primaries(self.fixture())
        links=lattice_links(junctions)
        self.assertEqual(len(links),3)
        self.assertTrue(all(a.startswith('J:') and b.startswith('J:') for a,b in links))
        self.assertEqual(links,lattice_links(junctions))
        edges={frozenset(pair) for pair in links}
        a,b=junctions[:2];c,d=junctions[2:]
        self.assertIn(frozenset((a['id'],c['id'])),edges)
        self.assertIn(frozenset((b['id'],d['id'])),edges)

    def test_secondary_radius_survives_graph_build_and_physical_checks(self):
        anchors=tuple(SurfaceAnchor('P'+str(i),'s',0,(1.,0.,0.),0) for i in range(3))
        perimeter=FramePerimeter('frame',np.array([[0,0,0],[10,0,0],[5,-5,0]]),anchors,'unchanged')
        segments,junctions=split_lattice_primaries(self.fixture())
        coords={j['id']:j['point_mm'] for j in junctions}
        secondary=tuple(route('cross'+str(i),a,b,[coords[a],coords[b]],.2) for i,(a,b) in enumerate(lattice_links(junctions)))
        graph=build_frame_graph(perimeter,segments+secondary,GenerationConfig(radius_mm=.3))
        self.assertEqual([m.radius_mm for m in graph.members[-3:]],[.2,.2,.2])
        checked=evaluate_frame(graph,ConstraintSet(),GenerationConfig(radius_mm=.3))
        self.assertEqual(checked.status,'CANDIDATE',checked.rejections)
        self.assertFalse(checked.report['mechanics_evaluated'])

    def test_surface_worker_builds_lattice_without_fan_to_sleeve(self):
        from test_generative_router import grid_surface,anchor_at
        from dataclasses import replace
        from dsg.generative_frame_worker import generate_lattice_paths
        surface=grid_surface()
        from dsg.ios_surface import prepare_surface
        xyz=surface.vertices_mm.copy();xyz[:,1]*=3.
        src=np.repeat(np.arange(len(xyz)),np.diff(surface.csr_offsets));lengths=np.linalg.norm(xyz[src]-xyz[surface.csr_destinations],axis=1)
        surface=prepare_surface(xyz,surface.triangles,surface.csr_offsets,surface.csr_destinations,lengths,source_id='grid',source_role='PASSIVE',world_matrix=np.eye(4),unit_scale_mm=1.)
        supports=(anchor_at(surface,3,'P0'),anchor_at(surface,5,'P1'),anchor_at(surface,54,'P2'))
        coords=np.array([surface.vertices_mm[3],surface.vertices_mm[5],surface.vertices_mm[54]])
        perimeter=FramePerimeter('frame',coords,supports,'unchanged')
        primary=tuple(replace(route(label,start,end,[surface.vertices_mm[y*9+x] for y in range(7)]),surface_vertex_ids=tuple(y*9+x for y in range(7)))
                      for label,start,end,x in [('left','P0','S_LEFT',3),('right','P1','S_RIGHT',5)])
        sleeves={'S1':{'id':'S1','center':[4,20,0],'axis':[0,0,-1],'inner_radius_mm':.5,'height_mm':2}}
        originals={a.id:p for a,p in zip(supports,coords)}
        from test_generative_bridges import box_obstacle
        from dsg.ios_surface import SolidClearanceIndex
        model=SolidClearanceIndex(box_obstacle())
        paths,metadata,report,rejections,local=generate_lattice_paths(surface,perimeter,primary,{'left':'S1','right':'S1'},supports,originals,sleeves,ConstraintSet(),GenerationConfig(radius_mm=.5),lambda text:None,model)
        self.assertTrue(report['lattice_complete'],rejections)
        self.assertEqual(report['lattice_layout'],'TRIANGLES_BETWEEN_PRIMARY_REINFORCEMENTS')
        for member in paths:
            if metadata[member.route_id]['role']=='SECONDARY':
                self.assertNotEqual(member.backend,'CERTIFIED_FREE_BRIDGE')
                self.assertLessEqual(float(np.max(np.abs(member.points_mm[:,2]))),.02)
        self.assertEqual(report['lattice_links_completed'],3)
        self.assertGreaterEqual(sum(m['role']=='SECONDARY' for m in metadata.values()),3)
        self.assertEqual(evaluate_frame(build_frame_graph(perimeter,paths,GenerationConfig(radius_mm=.5)),local,GenerationConfig(radius_mm=.5)).status,'CANDIDATE')

    def test_short_primary_has_no_fake_internal_junction(self):
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT_PRIMARY_SPAN'):
            split_lattice_primaries((route('short','P0','S1',[[0,0,0],[0,1,0]]),))

if __name__=='__main__':unittest.main()
