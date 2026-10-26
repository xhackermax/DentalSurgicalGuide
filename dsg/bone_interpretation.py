"""Interpret an isolated immediate-site bone-proxy failure; never approval.

This flag distinguishes a software heuristic from a clinical contraindication.
It cannot change admissibility, exclusions, acceptance or export gates.
"""
import math

def requires_bone_review(evaluation,*,immediate=False,minimum_coverage=.8):
    if not immediate or evaluation.get('admissible'):return False
    violations=evaluation.get('violations') or []
    if not violations or any(v.get('code')!='WALL' for v in violations):return False
    support=float(evaluation.get('support_fraction',float('nan')))
    return math.isfinite(support) and minimum_coverage<=support<=1.

def interpret_search_result(result,*,immediate=False,minimum_coverage=.8):
    row=result.get('closest')
    if result.get('status')=='NO_FEASIBLE' and result.get('best') is None and row and requires_bone_review(
            row['evaluation'],immediate=immediate,minimum_coverage=minimum_coverage):
        result['status']='BONE_REVIEW'
        result['clinical_viability']='NOT_DETERMINED'
    return result
