import unittest
from dsg.bone_interpretation import requires_bone_review, interpret_search_result
class BoneInterpretationTests(unittest.TestCase):
 def test_isolated_bone_proxy_failure_is_not_a_clinical_verdict(self):
  value={'admissible':False,'support_fraction':.874,'violations':[{'code':'WALL'}]}
  self.assertTrue(requires_bone_review(value,immediate=True))
  self.assertFalse(requires_bone_review(value,immediate=False))
 def test_danger_or_unverifiable_support_is_never_promoted(self):
  for code in ('STRUCTURE','UNVERIFIABLE','NO_NATIVE','APICAL','COVERAGE'):
   value={'admissible':False,'support_fraction':.9,'violations':[{'code':'WALL'},{'code':code}]}
   self.assertFalse(requires_bone_review(value,immediate=True),code)
  for support in (0.,.5,float('nan'),float('inf')):
   self.assertFalse(requires_bone_review({'support_fraction':support,'violations':[{'code':'WALL'}]},immediate=True))
 def test_search_interpretation_never_makes_a_valid_best(self):
  row={'evaluation':{'admissible':False,'support_fraction':.874,'violations':[{'code':'WALL'}]}}
  result={'status':'NO_FEASIBLE','best':None,'closest':row}
  interpret_search_result(result,immediate=True)
  self.assertEqual(result['status'],'BONE_REVIEW')
  self.assertEqual(result['clinical_viability'],'NOT_DETERMINED')
  self.assertIsNone(result['best']);self.assertFalse(row['evaluation']['admissible'])
 def test_missing_diagnostics_fail_closed(self):
  for value in ({},{'violations':[]},{'support_fraction':.9,'violations':[{'code':'UNKNOWN'}]}):
   self.assertFalse(requires_bone_review(value,immediate=True))
if __name__=='__main__':unittest.main()
