import unittest
from dsg.implant_catalogues import rows
class VegaPlusReferences(unittest.TestCase):
    def test_all_manufacturer_listed_dimensions(self):
        items=rows('KLOCKNER_VEGA_PLUS')
        expected={(d,l) for d,ls in [(3.1,[8,10,12,14]),(3.6,[8,10,12,14,16,18]),(4.1,[8,10,12,14,16,18]),(4.6,[8,10,12,14])] for l in ls}
        self.assertEqual({(a['diameter_mm'],a['length_mm']) for a in items},expected)
        self.assertEqual(len(items),20)
        for a in items:self.assertEqual(a['source_cell'],f"19 {round(a['diameter_mm']*10):02d} {round(a['length_mm']):02d}")

class UnverifiableCandidate(unittest.TestCase):
    def test_candidate_guard_failure_rejects_without_aborting_search(self):
        from dsg.section_optimizer import exact_section_evaluation
        class Field:
            def assess_matrix(self,*a):return dict(admissible=True,score=1.,violations=[])
        class Evaluator:
            def check_structures(self,*a):raise RuntimeError('Distance unresolved')
        value=exact_section_evaluation(Field(),Evaluator(),None,None)
        self.assertFalse(value['admissible'])
        self.assertFalse(value['exact_structure_check'])
        self.assertEqual(value['violations'][0]['code'],'STRUCTURE')
