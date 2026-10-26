"""Pure-Python clinical context helpers for DSG.

This module deliberately contains no Blender or network imports.  It normalizes
patient context, identifies *topics that need live guidance*, and validates the
traceability envelope of guidance returned by MCP.  It does not encode clinical
care recommendations or country-specific treatment rules.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

PATIENT_SCHEMA = "dsg.patient_clinical_context.v1"
GUIDANCE_REQUEST_SCHEMA = "dsg.clinical_guidance_request.v1"
GUIDANCE_RESULT_SCHEMA = "dsg.clinical_guidance_result.v1"
SOURCE_REGISTRY_SCHEMA = "dsg.clinical_source_registry.v1"

_ALLOWED_SEX = {"", "F", "M", "OTHER", "UNKNOWN"}
_ALLOWED_SMOKING = {"UNKNOWN", "NEVER", "FORMER", "CURRENT"}
_ALLOWED_SEVERITY = {"UNKNOWN", "MILD", "MODERATE", "SEVERE"}

# These are discovery tags, not treatment rules.  They only determine which
# current guidance must be looked up before MCP reasons about a procedure.
_MEDICATION_TOPIC_PATTERNS = {
    "MRONJ_ANTIRESORPTIVE": (
        r"\balendron", r"\brisedron", r"\bibandron", r"\bzoledron",
        r"\bpamidron", r"\bclodron", r"\betidron", r"\bdenosumab",
        r"\bbisphosph", r"\bbifosfon", r"\bantiresorpt",
    ),
    "MRONJ_ANTIANGIOGENIC": (
        r"\bbevacizumab", r"\bsunitinib", r"\bsorafenib", r"\baflibercept",
        r"\bantiangiogenic", r"\bantiangiog",
    ),
    "ANTICOAGULATION": (
        r"\bacenocoumar", r"\bacenocumar", r"\bwarfarin", r"\bapixaban",
        r"\brivaroxaban", r"\bedoxaban", r"\bdabigatran", r"\bheparin",
        r"\benoxaparin", r"\banticoagul",
    ),
    "ANTIPLATELET": (
        r"\bclopidogrel", r"\bprasugrel", r"\bticagrelor", r"\baspirin",
        r"\bacetylsalicy", r"\bantiaggreg", r"\bantiagreg",
    ),
    "IMMUNOSUPPRESSION": (
        r"\btacrolimus", r"\bcyclospor", r"\bciclospor", r"\bmycophen",
        r"\bazathiop", r"\bsirolimus", r"\beverolimus", r"\bimmunosuppress",
    ),
    "SYSTEMIC_CORTICOSTEROID": (
        r"\bprednisone", r"\bprednisona", r"\bdexameth", r"\bdexamet",
        r"\bmethylpred", r"\bmetilpred", r"\bcorticost", r"\bcorticoid",
    ),
}

_CONDITION_TOPIC_PATTERNS = {
    "DIABETES_GLYCEMIC_CONTROL": (r"\bdiabet", r"\bhba1c", r"\bhemoglobina glicosil"),
    "RENAL_IMPAIRMENT": (r"\brenal", r"\bkidney", r"\binsuficiencia renal", r"\bdialysis", r"\bdi[aá]lisis"),
    "HEPATIC_IMPAIRMENT": (r"\bhepatic", r"\bliver", r"\bcirrhos", r"\bcirrosis"),
    "ENDOCARDITIS_PROPHYLAXIS": (
        r"\bendocard", r"\bprosthetic valve", r"\bv[aá]lvula prot[eé]sica",
        r"\bcongenital heart", r"\bcardiopat[ií]a cong[eé]nita",
    ),
    "HEAD_NECK_RADIOTHERAPY": (r"\bradiotherap", r"\bradioterap", r"\bosteoradionec"),
    "IMMUNOCOMPROMISE": (r"\bimmunocomprom", r"\binmunodefic", r"\bneutropen", r"\btransplant"),
    "HEMATOLOGIC_BLEEDING_RISK": (r"\bthrombocyt", r"\btrombocit", r"\bhemoph", r"\bhemofil", r"\bcoagulopath"),
    "OSTEOPOROSIS_BONE_HEALTH": (r"\bosteopor",),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any, limit: int = 512) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _finite_number(value: Any, default=None):
    if value in (None, ""):
        return default
    try:
        x = float(value)
    except Exception:
        return default
    if x != x or x in (float("inf"), float("-inf")):
        return default
    return x


def normalize_country_code(value: Any) -> str:
    code = _text(value, 8).upper().replace("-", "_")
    aliases = {
        "SPAIN": "ES", "ESPANA": "ES", "ESPAÑA": "ES",
        "UK": "GB", "UNITED_KINGDOM": "GB", "GREAT_BRITAIN": "GB",
        "USA": "US", "UNITED_STATES": "US", "UNITED_STATES_OF_AMERICA": "US",
    }
    code = aliases.get(code, code)
    if not re.fullmatch(r"[A-Z]{2}", code):
        return "XX"
    return code


def normalize_medication(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        item = {"name": item}
    if not isinstance(item, dict):
        raise ValueError("Each medication must be an object or string")
    out = {
        "name": _text(item.get("name"), 160),
        "active_ingredient": _text(item.get("active_ingredient"), 160),
        "brand_name": _text(item.get("brand_name"), 160),
        "dose": _text(item.get("dose"), 96),
        "route": _text(item.get("route"), 96),
        "frequency": _text(item.get("frequency"), 96),
        "indication": _text(item.get("indication"), 160),
        "start_date": _text(item.get("start_date"), 32),
        "last_dose": _text(item.get("last_dose"), 32),
        "duration_months": _finite_number(item.get("duration_months"), None),
        "prescriber_specialty": _text(item.get("prescriber_specialty"), 96),
        "source": _text(item.get("source") or "CLINICIAN_ENTERED", 64),
    }
    if not (out["name"] or out["active_ingredient"] or out["brand_name"]):
        raise ValueError("Medication requires name, brand_name or active_ingredient")
    if out["duration_months"] is not None and out["duration_months"] < 0:
        raise ValueError("duration_months cannot be negative")
    return out


def normalize_condition(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        item = {"name": item}
    if not isinstance(item, dict):
        raise ValueError("Each condition must be an object or string")
    severity = _text(item.get("severity") or "UNKNOWN", 16).upper()
    if severity not in _ALLOWED_SEVERITY:
        severity = "UNKNOWN"
    out = {
        "name": _text(item.get("name"), 160),
        "status": _text(item.get("status") or "ACTIVE", 48).upper(),
        "severity": severity,
        "diagnosed_date": _text(item.get("diagnosed_date"), 32),
        "notes": _text(item.get("notes"), 512),
        "source": _text(item.get("source") or "CLINICIAN_ENTERED", 64),
    }
    if not out["name"]:
        raise ValueError("Condition requires name")
    return out


def normalize_lab(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("Each lab result must be an object")
    out = {
        "name": _text(item.get("name"), 120),
        "value": _finite_number(item.get("value"), None),
        "value_text": _text(item.get("value_text"), 96),
        "unit": _text(item.get("unit"), 48),
        "date": _text(item.get("date"), 32),
        "reference_low": _finite_number(item.get("reference_low"), None),
        "reference_high": _finite_number(item.get("reference_high"), None),
        "source": _text(item.get("source") or "CLINICIAN_ENTERED", 64),
    }
    if not out["name"]:
        raise ValueError("Lab result requires name")
    if out["value"] is None and not out["value_text"]:
        raise ValueError("Lab result requires value or value_text")
    return out


def normalize_patient_context(raw: Any) -> dict[str, Any]:
    raw = copy.deepcopy(raw or {})
    if not isinstance(raw, dict):
        raise ValueError("Patient clinical context must be an object")
    age = raw.get("age")
    if age in (None, ""):
        age = None
    else:
        age = int(age)
        if not 0 <= age <= 125:
            raise ValueError("age must be 0..125")
    sex = _text(raw.get("sex"), 16).upper()
    if sex not in _ALLOWED_SEX:
        sex = "UNKNOWN"
    smoking = _text(raw.get("smoking_status") or "UNKNOWN", 16).upper()
    if smoking not in _ALLOWED_SMOKING:
        smoking = "UNKNOWN"

    meds = [normalize_medication(x) for x in list(raw.get("medications") or [])]
    conds = [normalize_condition(x) for x in list(raw.get("conditions") or [])]
    labs = [normalize_lab(x) for x in list(raw.get("labs") or [])]
    allergies = sorted({_text(x, 160) for x in list(raw.get("allergies") or []) if _text(x, 160)})

    return {
        "schema": PATIENT_SCHEMA,
        "country_code": normalize_country_code(raw.get("country_code") or "XX"),
        "age": age,
        "sex": sex or "UNKNOWN",
        "smoking_status": smoking,
        "medications": meds,
        "conditions": conds,
        "labs": labs,
        "allergies": allergies,
        "previous_mronj": bool(raw.get("previous_mronj", False)),
        "head_neck_radiotherapy": bool(raw.get("head_neck_radiotherapy", False)),
        "pregnancy": bool(raw.get("pregnancy", False)),
        "clinical_notes": _text(raw.get("clinical_notes"), 4000),
        "updated_at": _text(raw.get("updated_at"), 40) or _utc_now(),
        "data_authority": _text(raw.get("data_authority") or "CLINICIAN_ENTERED", 64),
        "direct_identifiers_supported": False,
    }


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def context_hash(context: Any) -> str:
    normalized = normalize_patient_context(context)
    stable = copy.deepcopy(normalized)
    stable.pop("updated_at", None)
    return hashlib.sha256(canonical_json(stable).encode("utf-8")).hexdigest()


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    text = text.lower()
    return any(re.search(pattern, text, re.I) is not None for pattern in patterns)


def infer_guidance_topics(context: Any, procedure: Any = None) -> list[dict[str, Any]]:
    ctx = normalize_patient_context(context)
    procedure = copy.deepcopy(procedure or {})
    if not isinstance(procedure, dict):
        raise ValueError("procedure must be an object")

    topics: dict[str, dict[str, Any]] = {}

    def add(topic: str, reason: str, evidence: str = ""):
        entry = topics.setdefault(topic, {"topic": topic, "reasons": [], "evidence": []})
        if reason and reason not in entry["reasons"]:
            entry["reasons"].append(reason)
        if evidence and evidence not in entry["evidence"]:
            entry["evidence"].append(evidence)

    for med in ctx["medications"]:
        searchable = " ".join(str(med.get(k, "")) for k in ("name", "brand_name", "active_ingredient"))
        if not med.get("active_ingredient"):
            add("MEDICATION_RECONCILIATION", "Medication lacks resolved active ingredient", med.get("name") or med.get("brand_name"))
        for topic, patterns in _MEDICATION_TOPIC_PATTERNS.items():
            if _matches(searchable, patterns):
                add(topic, "Medication may affect oral-surgical planning; current local guidance required", med.get("active_ingredient") or med.get("name"))

    for cond in ctx["conditions"]:
        searchable = " ".join(str(cond.get(k, "")) for k in ("name", "notes"))
        for topic, patterns in _CONDITION_TOPIC_PATTERNS.items():
            if _matches(searchable, patterns):
                add(topic, "Medical condition may modify perioperative planning; current guidance required", cond.get("name"))

    if ctx.get("previous_mronj"):
        add("MRONJ_HISTORY", "Previous MRONJ explicitly reported")
    if ctx.get("head_neck_radiotherapy"):
        add("HEAD_NECK_RADIOTHERAPY", "Head/neck radiotherapy explicitly reported")
    if ctx.get("pregnancy"):
        add("PREGNANCY", "Pregnancy explicitly reported")
    if ctx.get("allergies"):
        add("MEDICATION_ALLERGY", "Allergies must be checked against any proposed medication", ", ".join(ctx["allergies"]))

    procedure_name = _text(procedure.get("procedure"), 160).lower()
    if any(token in procedure_name for token in ("implant", "extraction", "exodon", "bone graft", "injerto", "sinus", "elevaci")):
        add("INVASIVE_ORAL_SURGERY", "Planned procedure is dentoalveolar/oral surgery")
    if bool(procedure.get("active_infection")):
        add("ACTIVE_LOCAL_INFECTION", "Active local infection reported")
    if bool(procedure.get("immediate_implant")):
        add("IMMEDIATE_IMPLANT", "Immediate implant placement is planned")
    if bool(procedure.get("bone_regeneration")):
        add("BONE_REGENERATION", "Bone regeneration is planned")
    if bool(procedure.get("sinus_augmentation")):
        add("SINUS_AUGMENTATION", "Sinus augmentation is planned")

    return [topics[key] for key in sorted(topics)]


def missing_information(context: Any, procedure: Any = None) -> list[dict[str, str]]:
    ctx = normalize_patient_context(context)
    missing: list[dict[str, str]] = []
    if ctx["country_code"] == "XX":
        missing.append({"field": "country_code", "reason": "Country is required to resolve local regulation and professional guidance"})
    if ctx["age"] is None:
        missing.append({"field": "age", "reason": "Age not recorded"})

    for i, med in enumerate(ctx["medications"]):
        label = med.get("name") or med.get("brand_name") or f"medication[{i}]"
        if not med.get("active_ingredient"):
            missing.append({"field": f"medications[{i}].active_ingredient", "reason": f"Resolve active ingredient for {label}"})
        for field in ("dose", "route", "frequency", "indication"):
            if not med.get(field):
                missing.append({"field": f"medications[{i}].{field}", "reason": f"{field} missing for {label}"})

    return missing


def build_guidance_request(context: Any, procedure: Any, source_registry: Any) -> dict[str, Any]:
    ctx = normalize_patient_context(context)
    if not isinstance(procedure, dict):
        raise ValueError("procedure must be an object")
    country = ctx["country_code"]
    registry = source_registry or {}
    sources = []
    for key in (country, "EU" if country in {"ES", "FR", "DE", "IT", "PT", "NL", "BE", "IE", "AT", "GR", "FI", "SE", "DK", "LU"} else None, "INT"):
        if not key:
            continue
        for src in list((registry.get("countries") or {}).get(key, {}).get("sources") or []):
            if src not in sources:
                sources.append(src)

    country_entry = copy.deepcopy((registry.get("countries") or {}).get(country) or {})
    request = {
        "schema": GUIDANCE_REQUEST_SCHEMA,
        "created_at": _utc_now(),
        "country_code": country,
        "country_source_discovery_required": not bool(country_entry),
        "required_local_source_types": [
            "MEDICINE_REGULATOR", "DENTAL_PROFESSIONAL_BODY",
            "ORAL_MAXILLOFACIAL_SOCIETY", "NATIONAL_CLINICAL_GUIDANCE"
        ],
        "patient_context_hash": context_hash(ctx),
        "patient_context": ctx,
        "procedure": copy.deepcopy(procedure),
        "guidance_topics": infer_guidance_topics(ctx, procedure),
        "missing_information": missing_information(ctx, procedure),
        "source_priority": sources,
        "instructions": {
            "live_verification_required": True,
            "official_local_sources_first": True,
            "resolve_brand_to_active_ingredient": True,
            "separate_fact_guideline_and_inference": True,
            "report_conflicts_between_sources": True,
            "do_not_infer_hu_or_medical_clearance_from_geometry": True,
            "clinician_final_decision_required": True,
            "if_country_unregistered": "Discover and verify the official medicine regulator, dental professional body, oral/maxillofacial society and national guidance for that country before advising.",
        },
    }
    stable = copy.deepcopy(request)
    stable.pop("created_at", None)
    request["request_sha256"] = hashlib.sha256(canonical_json(stable).encode("utf-8")).hexdigest()
    return request


def validate_guidance_result(result: Any, *, expected_request_sha256: str = "", expected_country_code: str = "") -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("Guidance result must be an object")
    if result.get("schema") != GUIDANCE_RESULT_SCHEMA:
        raise ValueError(f"Guidance result schema must be {GUIDANCE_RESULT_SCHEMA}")
    request_hash = _text(result.get("request_sha256"), 128)
    if expected_request_sha256 and request_hash != expected_request_sha256:
        raise ValueError("Guidance result does not match current request_sha256")
    country = normalize_country_code(result.get("country_code"))
    if expected_country_code and country != normalize_country_code(expected_country_code):
        raise ValueError("Guidance result country does not match current patient country")
    verified_at = _text(result.get("verified_at"), 40)
    if not verified_at:
        raise ValueError("verified_at is required")
    sources = list(result.get("sources") or [])
    if not sources:
        raise ValueError("At least one source is required")
    source_ids = set()
    clean_sources = []
    for src in sources:
        if not isinstance(src, dict):
            raise ValueError("Each source must be an object")
        sid = _text(src.get("id"), 96)
        if not sid or sid in source_ids:
            raise ValueError("Each source requires a unique id")
        url = _text(src.get("url"), 1200)
        publisher = _text(src.get("publisher"), 200)
        if not url.startswith(("https://", "http://")) or not publisher:
            raise ValueError("Each source requires publisher and http(s) url")
        source_ids.add(sid)
        clean_sources.append({
            "id": sid,
            "publisher": publisher,
            "title": _text(src.get("title"), 300),
            "url": url,
            "published_or_updated": _text(src.get("published_or_updated"), 40),
            "accessed_at": _text(src.get("accessed_at"), 40),
            "source_type": _text(src.get("source_type") or "GUIDELINE", 64).upper(),
        })

    def clean_claims(values: Any, label: str) -> list[dict[str, Any]]:
        out = []
        for item in list(values or []):
            if not isinstance(item, dict):
                raise ValueError(f"Each {label} item must be an object")
            text = _text(item.get("text"), 2000)
            refs = [_text(x, 96) for x in list(item.get("source_ids") or [])]
            if not text:
                raise ValueError(f"{label} item requires text")
            if not refs:
                raise ValueError(f"{label} item requires at least one source_id")
            unknown = [x for x in refs if x not in source_ids]
            if unknown:
                raise ValueError(f"{label} references unknown source ids: {unknown}")
            out.append({
                "text": text,
                "source_ids": refs,
                "classification": _text(item.get("classification") or "SOURCE_DERIVED", 64).upper(),
                "confidence": max(0.0, min(1.0, _finite_number(item.get("confidence"), 0.5))),
            })
        return out

    return {
        "schema": GUIDANCE_RESULT_SCHEMA,
        "request_sha256": request_hash,
        "country_code": country,
        "verified_at": verified_at,
        "sources": clean_sources,
        "medication_resolution": list(result.get("medication_resolution") or []),
        "applicable_guidance": clean_claims(result.get("applicable_guidance"), "applicable_guidance"),
        "risk_flags": clean_claims(result.get("risk_flags"), "risk_flags"),
        "recommendations": clean_claims(result.get("recommendations"), "recommendations"),
        "source_conflicts": clean_claims(result.get("source_conflicts"), "source_conflicts"),
        "missing_information": list(result.get("missing_information") or []),
        "requires_clinician_review": bool(result.get("requires_clinician_review", True)),
        "requires_medical_consultation": bool(result.get("requires_medical_consultation", False)),
        "status": _text(result.get("status") or "ADVISORY_ONLY", 64).upper(),
        "mcp_summary": _text(result.get("mcp_summary"), 4000),
        "stored_at": _utc_now(),
    }
