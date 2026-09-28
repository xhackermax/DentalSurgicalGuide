"""Pure-Python offline scientific evidence repository for DSG.

The repository contains bibliographic metadata and DSG-authored clinical
summaries only. It intentionally does not bundle copyrighted article full text.
Live MCP searches may propose updates, but active bundled rules are immutable at
runtime and are never silently replaced.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

MANIFEST_SCHEMA = "dsg.offline_evidence_manifest.v1"
REPOSITORY_SCHEMA = "dsg.offline_evidence_repository.v1"
UPDATE_REQUEST_SCHEMA = "dsg.evidence_update_request.v1"
UPDATE_PROPOSAL_SCHEMA = "dsg.evidence_update_proposal.v1"


class EvidenceRepositoryError(RuntimeError):
    pass


def _base_dir(base_dir: str | Path | None = None) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    return Path(__file__).resolve().parent / "resources" / "evidence"


def _json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        raise EvidenceRepositoryError(f"Cannot read evidence resource {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise EvidenceRepositoryError(f"Evidence resource {path.name} must contain a JSON object")
    return data


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_repository(base_dir: str | Path | None = None, *, verify_integrity: bool = True) -> dict[str, Any]:
    base = _base_dir(base_dir)
    manifest = _json(base / "manifest.json")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise EvidenceRepositoryError("Invalid evidence manifest schema")
    if manifest.get("repository_schema") != REPOSITORY_SCHEMA:
        raise EvidenceRepositoryError("Unsupported evidence repository schema")

    resources = {}
    for filename, key, expected_schema in (
        ("references.json", "references", "dsg.evidence_references.v1"),
        ("rules.json", "rules", "dsg.evidence_rules.v1"),
        ("journals.json", "journals", "dsg.evidence_journals.v1"),
        ("expert_watchlist.json", "experts", "dsg.evidence_expert_watchlist.v1"),
        ("search_queries.json", "queries", "dsg.evidence_search_queries.v1"),
    ):
        path = base / filename
        if not path.is_file():
            raise EvidenceRepositoryError(f"Missing evidence resource: {filename}")
        expected = (manifest.get("files") or {}).get(filename) or {}
        if verify_integrity and expected.get("sha256"):
            actual = _sha256(path)
            if actual != expected["sha256"]:
                raise EvidenceRepositoryError(f"Evidence resource integrity failure: {filename}")
        payload = _json(path)
        if payload.get("schema") != expected_schema:
            raise EvidenceRepositoryError(f"Invalid schema in {filename}: {payload.get('schema')}")
        items = payload.get(key)
        if not isinstance(items, list):
            raise EvidenceRepositoryError(f"{filename} must contain a '{key}' array")
        resources[key] = items

    if bool(manifest.get("contains_full_text_articles")):
        raise EvidenceRepositoryError("Offline DSG evidence repository must not bundle full-text articles")

    repo = {"manifest": manifest, **resources}
    _validate_repository_links(repo)
    return repo


def _validate_repository_links(repo: dict[str, Any]) -> None:
    ref_ids = {str(r.get("id")) for r in repo["references"] if r.get("id")}
    rule_ids = set()
    for rule in repo["rules"]:
        rid = str(rule.get("id", "") or "")
        if not rid or rid in rule_ids:
            raise EvidenceRepositoryError(f"Duplicate or missing evidence rule id: {rid!r}")
        rule_ids.add(rid)
        missing = [ref for ref in rule.get("reference_ids", []) if ref not in ref_ids]
        if missing:
            raise EvidenceRepositoryError(f"Rule {rid} references missing sources: {missing}")


def _indexes(repo: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {str(x["id"]): x for x in repo["references"] if x.get("id")},
        {str(x["id"]): x for x in repo["rules"] if x.get("id")},
    )


def repository_summary(repo: dict[str, Any] | None = None) -> dict[str, Any]:
    repo = repo or load_repository()
    m = repo["manifest"]
    return {
        "schema": "dsg.evidence_repository_summary.v1",
        "repository_version": m.get("repository_version"),
        "bundled_at": m.get("bundled_at"),
        "last_literature_search": m.get("last_literature_search"),
        "offline_mode_supported": bool(m.get("offline_mode_supported")),
        "contains_full_text_articles": bool(m.get("contains_full_text_articles")),
        "reference_count": len(repo["references"]),
        "rule_count": len(repo["rules"]),
        "journal_count": len(repo["journals"]),
        "expert_watch_count": len(repo["experts"]),
        "copyright_policy": m.get("copyright_policy"),
        "update_policy": m.get("update_policy"),
        "authority_policy": m.get("authority_policy"),
    }


def _text_blob(item: dict[str, Any]) -> str:
    values = []
    for key in ("id", "title", "title_es", "journal", "publication_type", "summary_es", "limitations_es", "recommendation_es", "must_not", "country", "institution"):
        val = item.get(key)
        if val:
            values.append(str(val))
    for key in ("authors", "topics", "keywords", "focus", "reference_ids"):
        val = item.get(key)
        if isinstance(val, list):
            values.extend(str(v) for v in val)
    return " ".join(values).casefold()


def query_references(*, topic: str | None = None, text: str | None = None,
                     limit: int = 25, repo: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    repo = repo or load_repository()
    topic_cf = str(topic or "").strip().casefold()
    text_cf = str(text or "").strip().casefold()
    out = []
    for ref in repo["references"]:
        topics = [str(v).casefold() for v in ref.get("topics", [])]
        if topic_cf and not any(topic_cf == t or topic_cf in t for t in topics):
            continue
        if text_cf and text_cf not in _text_blob(ref):
            continue
        out.append(copy.deepcopy(ref))
    out.sort(key=lambda x: (int(x.get("evidence_tier", 99) or 99), -int(x.get("year", 0) or 0), str(x.get("id", ""))))
    return out[: max(1, min(int(limit), 100))]


def query_rules(*, topic: str | None = None, text: str | None = None,
                repo: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    repo = repo or load_repository()
    topic_cf = str(topic or "").strip().casefold()
    text_cf = str(text or "").strip().casefold()
    out = []
    for rule in repo["rules"]:
        if topic_cf and topic_cf not in str(rule.get("topic", "")).casefold():
            continue
        if text_cf and text_cf not in _text_blob(rule):
            continue
        out.append(copy.deepcopy(rule))
    return out


def get_rule(rule_id: str, *, repo: dict[str, Any] | None = None) -> dict[str, Any]:
    repo = repo or load_repository()
    refs, rules = _indexes(repo)
    rid = str(rule_id or "").strip().upper()
    if rid not in rules:
        raise KeyError(f"Unknown DSG evidence rule: {rule_id}")
    rule = copy.deepcopy(rules[rid])
    rule["references"] = [copy.deepcopy(refs[x]) for x in rule.get("reference_ids", []) if x in refs]
    rule["repository_version"] = repo["manifest"].get("repository_version")
    rule["last_literature_search"] = repo["manifest"].get("last_literature_search")
    return rule


def get_topic_context(topic: str, *, repo: dict[str, Any] | None = None) -> dict[str, Any]:
    repo = repo or load_repository()
    topic = str(topic or "").strip()
    if not topic:
        raise ValueError("topic is required")
    rules = query_rules(topic=topic, repo=repo)
    references = query_references(topic=topic, limit=100, repo=repo)
    linked = set()
    for r in rules:
        linked.update(r.get("reference_ids", []))
    refs_by_id, _ = _indexes(repo)
    for ref_id in linked:
        if ref_id in refs_by_id and not any(x.get("id") == ref_id for x in references):
            references.append(copy.deepcopy(refs_by_id[ref_id]))
    return {
        "schema": "dsg.evidence_topic_context.v1",
        "topic": topic,
        "repository_version": repo["manifest"].get("repository_version"),
        "last_literature_search": repo["manifest"].get("last_literature_search"),
        "rules": rules,
        "references": references,
    }


def search_offline_evidence(query: str, *, limit: int = 30,
                            repo: dict[str, Any] | None = None) -> dict[str, Any]:
    repo = repo or load_repository()
    q = str(query or "").strip()
    if not q:
        raise ValueError("query is required")
    qcf = q.casefold()
    refs = [copy.deepcopy(x) for x in repo["references"] if qcf in _text_blob(x)]
    rules = [copy.deepcopy(x) for x in repo["rules"] if qcf in _text_blob(x)]
    experts = [copy.deepcopy(x) for x in repo["experts"] if qcf in _text_blob(x)]
    journals = [copy.deepcopy(x) for x in repo["journals"] if qcf in _text_blob(x)]
    return {
        "schema": "dsg.offline_evidence_search.v1",
        "query": q,
        "repository_version": repo["manifest"].get("repository_version"),
        "rules": rules[:limit],
        "references": refs[:limit],
        "experts": experts[:limit],
        "journals": journals[:limit],
        "offline": True,
    }


def _normalize_topics(topics: Iterable[str] | None) -> list[str]:
    if topics is None:
        return []
    return sorted({str(x).strip().upper() for x in topics if str(x).strip()})


def build_update_request(topics: Iterable[str] | None = None, *, country_code: str | None = None,
                         repo: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a live-search task for MCP without modifying active evidence."""
    repo = repo or load_repository()
    selected = _normalize_topics(topics)
    rules = repo["rules"] if not selected else [r for r in repo["rules"] if str(r.get("topic", "")).upper() in selected]
    existing_pmids = sorted({str(r.get("pmid")) for r in repo["references"] if r.get("pmid")})
    existing_dois = sorted({str(r.get("doi")).lower() for r in repo["references"] if r.get("doi")})
    request = {
        "schema": UPDATE_REQUEST_SCHEMA,
        "repository_version": repo["manifest"].get("repository_version"),
        "last_literature_search": repo["manifest"].get("last_literature_search"),
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "country_code": str(country_code or "INT").upper(),
        "topics": selected,
        "active_rule_ids": [r.get("id") for r in rules],
        "priority_journals": copy.deepcopy(repo["journals"]),
        "expert_watchlist": copy.deepcopy(repo["experts"]),
        "permanent_queries": copy.deepcopy(repo["queries"]),
        "deduplicate_against": {"pmids": existing_pmids, "dois": existing_dois},
        "instructions": [
            "Search current peer-reviewed periodontal, implant, oral surgery and prosthodontic literature, prioritizing Early View/ahead-of-print in the listed journals.",
            "Use author prominence only to prioritize reading; never increase evidence weight because of reputation.",
            "Prioritize consensus/guidelines, systematic reviews/meta-analyses and prospective/RCT evidence for rule changes.",
            "For country-sensitive medication or surgical guidance, prioritize official national regulators/professional societies and report conflicts with international guidance.",
            "Classify every finding as supports, refines, contradicts, supersedes, or does_not_change an active rule.",
            "Do not activate or overwrite any DSG rule. Return an update proposal for clinician review.",
            "Do not return copyrighted full text. Return citation metadata, identifiers, a concise original evidence summary, limitations and relevance to DSG metrics.",
        ],
    }
    canonical = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request["request_sha256"] = hashlib.sha256(canonical).hexdigest()
    return request


def validate_update_proposal(payload: dict[str, Any], *, expected_request_sha256: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema") != UPDATE_PROPOSAL_SCHEMA:
        raise ValueError(f"Expected schema {UPDATE_PROPOSAL_SCHEMA}")
    request_hash = str(payload.get("request_sha256", "") or "")
    if expected_request_sha256 and request_hash != str(expected_request_sha256):
        raise ValueError("Evidence update proposal does not match the current request")
    verified_at = str(payload.get("verified_at", "") or "")
    if not verified_at:
        raise ValueError("Evidence proposal must contain verified_at")
    refs = payload.get("new_or_updated_references") or []
    proposals = payload.get("rule_change_proposals") or []
    if not isinstance(refs, list) or not isinstance(proposals, list):
        raise ValueError("Evidence proposal reference/rule arrays are invalid")
    for ref in refs:
        if not isinstance(ref, dict) or not ref.get("title") or not (ref.get("doi") or ref.get("pmid") or ref.get("url")):
            raise ValueError("Every proposed reference requires title plus DOI, PMID or URL")
    for change in proposals:
        if not isinstance(change, dict) or not change.get("rule_id") or not change.get("classification"):
            raise ValueError("Every proposed rule change requires rule_id and classification")
        if str(change.get("classification")) not in {"supports", "refines", "contradicts", "supersedes", "does_not_change"}:
            raise ValueError("Invalid evidence change classification")
    result = copy.deepcopy(payload)
    result["activation_status"] = "PENDING_CLINICIAN_REVIEW"
    result["active_rules_modified"] = False
    return result


def due_for_review(*, on_date: date | None = None, repo: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    repo = repo or load_repository()
    on_date = on_date or date.today()
    last = repo["manifest"].get("last_literature_search")
    try:
        last_date = date.fromisoformat(str(last))
    except Exception:
        return copy.deepcopy(repo["rules"])
    days = (on_date - last_date).days
    return [copy.deepcopy(r) for r in repo["rules"] if days >= int(r.get("review_interval_days", 180) or 180)]
