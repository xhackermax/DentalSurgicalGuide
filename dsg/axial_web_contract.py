"""Immutable native-volume transport contract for the axial web generator."""
import hashlib
from pathlib import Path
TOPOLOGY='AXIAL_RADIAL_WEB_V2'
def file_digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def seal_files(paths):return {str(Path(p).resolve()):file_digest(p)for p in paths}
def verify_files(manifest):
 if not manifest:raise ValueError('MISSING_INPUT_MANIFEST')
 for path,expected in manifest.items():
  if not Path(path).is_file()or file_digest(path)!=expected:raise ValueError('CHANGED_FILE:'+path)
def input_paths(request):
 return [request[k]for k in ('surface_file','frame_support_file','frame_lower_surface_file','guide_surface_file')]+list(request['sleeve_surface_files'].values())+[o['file']for o in request.get('obstacles',[])]
def verify_geometry_report(web,report,sleeves):
 if not report.get('valid')or not report.get('ios_original_clear')or report.get('self_intersections')!=0 or report.get('physical_cell_count',0)<8:raise ValueError('INCOMPLETE_NATIVE_GEOMETRY_REPORT')
 receipts=report.get('attachment_receipts',{})
 if set(receipts)!=set(web['attachments']):raise ValueError('ATTACHMENT_RECEIPTS_INCOMPLETE')
 for key,a in web['attachments'].items():
  r=receipts[key]
  if not r.get('valid')or not r.get('positive_volume_overlap'):raise ValueError('ATTACHMENT_NO_POSITIVE_VOLUME:'+key)
  if not r.get('visible_guide_overlap_verified'):raise ValueError('VISIBLE_GUIDE_ATTACHMENT_UNVERIFIED:'+key)
 for s in sleeves:
  if sum(a['kind']=='SLEEVE'and a['target']==s['id']for a in web['attachments'].values())<2:raise ValueError('INSUFFICIENT_SLEEVE_ATTACHMENTS:'+s['id'])
 if sum(a['kind']=='FRAME'for a in web['attachments'].values())<4:raise ValueError('INSUFFICIENT_UPPER_FRAME_ATTACHMENTS')
 style=web.get('style',{})
 if style.get('surface_fairing'):
  if web['report'].get('surface_fairing')!='ONE_SIDED_HEAT_FAIRING'or not web['report'].get('original_strut_envelope_preserved'):raise ValueError('SURFACE_FAIRING_REQUIRED')
 if style.get('support_fairing'):
  unions=report.get('manual_union_receipts',{})
  if set(unions)!=set(web['attachments'])or report.get('manual_union_count')!=len(unions):raise ValueError('SUPPORT_FAIRING_RECEIPTS_INCOMPLETE')
  if any(not a.get('shared_manual_builder')or a.get('fullness_scale')!=0. or a.get('footprint_radius_ratio')is None or a['footprint_radius_ratio']>1.35 for a in unions.values()):raise ValueError('FLAT_SUPPORT_FAIRING_REQUIRED')
 if style.get('frame_smoothing'):
  if not web['report'].get('frame_smoothing')or web['report'].get('terminal_enlargement')is not False:raise ValueError('FRAME_SMOOTHING_REQUIRED')
  if web['report']['frame_origin_count']!=style['target_frame_origins']:raise ValueError('HALF_DENSITY_NOT_MET')
  if any(any(abs(float(r)-float(p['radius_mm']))>1.e-8 for r in p['point_radii_mm'])for p in web['pieces']):raise ValueError('UNIFORM_MEMBER_RADIUS_REQUIRED')
 if style.get('manual_union'):
  unions=report.get('manual_union_receipts',{})
  if set(unions)!=set(web['attachments'])or report.get('manual_union_count')!=len(unions):raise ValueError('MANUAL_UNION_RECEIPTS_INCOMPLETE')
  if any(not r.get('shared_manual_builder')or r.get('footprint_radius_ratio')is not None or r.get('fullness_scale')!=1. for r in unions.values()):raise ValueError('SHARED_MANUAL_UNION_REQUIRED')
  if web['report']['frame_origin_count']!=style['target_frame_origins']:raise ValueError('HALF_DENSITY_NOT_MET')

 if report.get('manifold',{}).get('status')!='PASS' or not report.get('envelope',{}).get('flat_faces_clear')or not report.get('keepouts',{}).get('valid')or not report.get('frame_contact',{}).get('lower_frame_surface_clear')or not report.get('sections',{}).get('valid'):raise ValueError('NATIVE_FINAL_CHECKS_INCOMPLETE')
def verify_payload(request,outcome):
 if request.get('reinforcement_topology')!=TOPOLOGY or outcome.get('topology')!=TOPOLOGY or outcome.get('status')!='CANDIDATE':raise ValueError('WRONG_AXIAL_WEB_RESULT')
 if outcome.get('case_fingerprint')!=request['case_fingerprint']or outcome.get('run_id')!=request['run_id']:raise ValueError('STALE_AXIAL_WEB_RESULT')
 verify_files(request.get('axial_input_manifest'));verify_files(outcome.get('artifact_manifest'))
 if set(request['axial_input_manifest'])!={str(Path(p).resolve())for p in input_paths(request)}:raise ValueError('INCOMPLETE_INPUT_MANIFEST')
 for path in outcome['artifact_manifest']:
  if Path(path).resolve().parent!=Path(request['job_dir']).resolve():raise ValueError('WRONG_ARTIFACT_FOLDER')
 import json
 web=json.loads(Path(outcome['web_file']).read_text(encoding='utf-8'))
 if set(outcome['artifact_manifest'])!={str(Path(outcome[k]).resolve())for k in ('web_file','volume_file')}:raise ValueError('INCOMPLETE_ARTIFACT_MANIFEST')
 verify_geometry_report(web,outcome['report']['native_geometry'],request['sleeves']);return web
