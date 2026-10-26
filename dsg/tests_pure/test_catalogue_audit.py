import unittest,json
from pathlib import Path
from dsg.implant_catalogues import rows,FOLDER,LIBRARIES
class CompleteReferences(unittest.TestCase):
    def test_all_built_in_libraries_match_verified_reference_inventory(self):
        expected=json.loads((FOLDER/'catalogue_audit_2026_10.json').read_text('utf-8'))['catalogues']
        self.assertEqual(set(expected),{key for key,_,_ in LIBRARIES if key!='CUSTOM'})
        for key,source in expected.items():
            actual=rows(key)
            with self.subTest(key=key):
                self.assertEqual(len(actual),len(source))
                self.assertEqual({(a['source_cell'],a['diameter_mm'],a['length_mm']) for a in actual},
                                 {(a['ref'],a['diameter_mm'],a['length_mm']) for a in source})
                self.assertEqual(len(actual),len({a['id'] for a in actual}))
