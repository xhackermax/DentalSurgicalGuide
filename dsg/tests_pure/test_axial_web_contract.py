import unittest,tempfile,json
from pathlib import Path
class ContractTests(unittest.TestCase):
 def test_surface_finish_cannot_omit_support_transition_proof(self):
  from dsg.axial_web_contract import verify_geometry_report
  attachments={k:dict(kind='FRAME'if k.startswith('F')else'SLEEVE',target='S1')for k in ['F1','F2','F3','F4','P1','P2']}
  web=dict(attachments=attachments,style=dict(surface_fairing=True,support_fairing=True),report=dict(surface_fairing='ONE_SIDED_HEAT_FAIRING',original_strut_envelope_preserved=True),pieces=[])
  report=dict(valid=True,ios_original_clear=True,self_intersections=0,physical_cell_count=12,attachment_receipts={k:dict(valid=True,positive_volume_overlap=True,visible_guide_overlap_verified=True)for k in attachments})
  with self.assertRaisesRegex(ValueError,'SUPPORT_FAIRING_RECEIPTS'):verify_geometry_report(web,report,[dict(id='S1')])
 def test_frame_finish_rejects_swollen_terminal_radii(self):
  from dsg.axial_web_contract import verify_geometry_report
  attachments={k:dict(kind='FRAME'if k.startswith('F')else'SLEEVE',target='S1')for k in ['F1','F2','F3','F4','P1','P2']}
  web=dict(attachments=attachments,style=dict(frame_smoothing=True,target_frame_origins=4),report=dict(frame_smoothing=True,terminal_enlargement=False,frame_origin_count=4),pieces=[dict(radius_mm=1.,point_radii_mm=[1.,1.5])])
  report=dict(valid=True,ios_original_clear=True,self_intersections=0,physical_cell_count=12,attachment_receipts={k:dict(valid=True,positive_volume_overlap=True,visible_guide_overlap_verified=True)for k in attachments})
  with self.assertRaisesRegex(ValueError,'UNIFORM_MEMBER_RADIUS'):verify_geometry_report(web,report,[dict(id='S1')])
 def test_changed_input_cannot_reuse_a_valid_candidate(self):
  from dsg.axial_web_contract import seal_files,verify_files
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'ios';p.write_bytes(b'original');manifest=seal_files([str(p)]);verify_files(manifest);p.write_bytes(b'changed')
   with self.assertRaisesRegex(ValueError,'CHANGED_FILE'):verify_files(manifest)
 def test_missing_an_attachment_receipt_rejects_the_candidate(self):
  from dsg.axial_web_contract import verify_geometry_report
  web=dict(attachments={'F':dict(kind='FRAME',target='F'),'P':dict(kind='SLEEVE',target='S1')})
  report=dict(valid=True,ios_original_clear=True,self_intersections=0,physical_cell_count=12,attachment_receipts={})
  with self.assertRaisesRegex(ValueError,'ATTACHMENT_RECEIPTS'):verify_geometry_report(web,report,[dict(id='S1')])
 def test_positive_overlap_with_only_a_hidden_reference_is_insufficient(self):
  from dsg.axial_web_contract import verify_geometry_report
  web=dict(attachments={})
  for k in ['F1','F2','F3','F4']:web['attachments'][k]=dict(kind='FRAME',target=k)
  for k in ['P1','P2']:web['attachments'][k]=dict(kind='SLEEVE',target='S1')
  receipts={k:dict(valid=True,positive_volume_overlap=True,visible_guide_overlap_verified=False)for k in web['attachments']}
  report=dict(valid=True,ios_original_clear=True,self_intersections=0,physical_cell_count=12,attachment_receipts=receipts)
  with self.assertRaisesRegex(ValueError,'VISIBLE_GUIDE'):verify_geometry_report(web,report,[dict(id='S1')])
