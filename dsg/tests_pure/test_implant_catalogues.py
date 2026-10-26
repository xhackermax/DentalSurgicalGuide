import re,unittest
import numpy as np
from dsg.implant_optimization import search_size

def row(ident,d,l,status='LISTED'):
    return dict(id=ident,family='TEST',diameter_mm=d,length_mm=l,platform_local_mm=[0,0,l/2],
        vertices_path='v.npy',faces_path='f.npy',reference='test',availability=status)

BTI_KEYS=('BTI_P25','BTI_P30','BTI_P30X','BTI_CORE','BTI_COREX','BTI_INT_UNI','BTI_INT_UNIPLUS','BTI_TINY','BTI_EXT_UNI','BTI_EXT_UNIPLUS')
BTI_D={'25':2.5,'30':3.,'33':3.3,'35':3.5,'37':3.75,'40':4.,'42':4.25,'45':4.5,'47':4.75,'50':5.,'55':5.5,'60':6.}
BTI_L={'45':4.5,'55':5.5,'65':6.5,'75':7.5,'85':8.5,'10':10.,'11':11.5,'13':13.,'15':15.}

class CatalogueSelection(unittest.TestCase):
    def test_largest_admissible_not_highest_support_score(self):
        rows=[row('wide',5,8),row('long',4,14),row('wide_long',5,10),row('too_large',6,16)]
        def evaluate(matrix,asset=None):
            return {'admissible':asset['id']!='too_large','score':1000 if asset['id']=='long' else 1}
        result=search_size(evaluate,rows,'TEST',np.eye(4),(0,0,0),current_id='wide')
        self.assertEqual(result['best']['asset']['id'],'long')
        self.assertEqual(result['status'],'PROPOSAL')

    def test_unverified_and_conditional_never_automatically_selected(self):
        rows=[row('known',4,10),row('pending',6,16,'UNVERIFIED'),row('conditional',5,14,'CONDITIONAL')]
        r=search_size(lambda *a,**k:{'admissible':True,'score':0},rows,'TEST',np.eye(4),(0,0,0))
        self.assertEqual(r['best']['asset']['id'],'known')
        self.assertEqual(r['evaluated'],1)

    def test_bti_store_catalogue_matches_reference_codes(self):
        from dsg.implant_catalogues import rows
        total=0
        for key in BTI_KEYS:
            items=rows(key);total+=len(items)
            self.assertEqual(len({r['id'] for r in items}),len(items))
            for r in items:
                code=re.match(r'^(?:IIP2CA|IIP3XCA|IIP3CA|IIPEXCA|IIPECA|IIPUCA|IIPSCA|IRPUCA|IRPSCA|IRTCA)(\d\d)(\d\d)$',r['source_cell'])
                self.assertIsNotNone(code,r['source_cell'])
                self.assertEqual((BTI_D[code.group(1)],BTI_L[code.group(2)]),(r['diameter_mm'],r['length_mm']),r['source_cell'])
                self.assertTrue(r['dimension_only'])
        self.assertEqual(total,267)
        corex={(r['diameter_mm'],r['length_mm']) for r in rows('BTI_COREX')}
        self.assertIn((3.5,11.5),corex);self.assertNotIn((3.5,11.),corex)
        self.assertIn((4.,13.),corex);self.assertIn((4.75,4.5),corex)
        self.assertEqual(len(corex),60)

    def test_other_brands(self):
        from dsg.implant_catalogues import rows,LIBRARIES
        counts={'KLOCKNER_VEGA':20,'KLOCKNER_VEGA_PLUS':20,'MIS_SEVEN':26,'MIS_C1':19,'ASTRA_EV_S':32,'ASTRA_EV_C':12,'ASTRA_PROFILE_EV':24}
        for key,n in counts.items():self.assertEqual(len(rows(key)),n,key)
        seven={(r['diameter_mm'],r['length_mm']):r['source_cell'] for r in rows('MIS_SEVEN')}
        self.assertEqual(seven[(3.75,8.)],'MF7-D08375');self.assertEqual(seven[(6.,13.)],'MF7-13600')
        self.assertNotIn((3.3,8.),seven)
        ev={(r['diameter_mm'],r['length_mm']):r['source_cell'] for r in rows('ASTRA_EV_S')}
        self.assertEqual(ev[(4.2,17.)],'25237');self.assertNotIn((3.0,6.),ev);self.assertNotIn((5.4,17.),ev)
        self.assertEqual({r['length_mm'] for r in rows('KLOCKNER_VEGA_PLUS')},{8.,10.,12.,14.,16.,18.})
        keys=[k for k,_,_ in LIBRARIES];self.assertEqual(len(keys),len(set(keys)))

    def test_standard_plus_complete_and_original_matrix_preserved(self):
        from dsg.implant_catalogues import rows
        sp=rows('STRAUMANN_SP')
        self.assertTrue(any(r['length_mm']==6 for r in sp))
        self.assertEqual(len(sp),47)
        from dsg.implant_catalogues import USER_PATH
        import hashlib
        raw=__import__('json').loads(USER_PATH.read_text('utf-8'))
        self.assertEqual(raw['source_sha256'],'9aaf6fb5f1ce96e1dcb0622ade2db41105468ee980fb878502500bc658b12857')

    def test_nominal_body_dimensions(self):
        from dsg.implant_catalogues import nominal_body_mesh,inside_envelope
        vertices,faces=nominal_body_mesh(4.1,12)
        self.assertAlmostEqual(float(np.ptp(vertices[:,2])),12)
        self.assertGreaterEqual(float(np.ptp(vertices[:,0])),4.1)
        self.assertLess(float(np.ptp(vertices[:,0])),4.11)
        self.assertTrue(np.isfinite(vertices).all())
        self.assertEqual(faces.shape[1],3)
        self.assertTrue(inside_envelope(vertices*[.99,.99,1],4.1,12))
        self.assertFalse(inside_envelope(vertices*[1.1,1.1,1],4.1,12))

if __name__=='__main__':unittest.main()
