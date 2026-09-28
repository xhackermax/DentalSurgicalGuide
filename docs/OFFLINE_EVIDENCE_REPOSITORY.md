# DSG Offline Scientific Evidence Repository

DSG bundles a versioned scientific evidence baseline under `resources/evidence/`.

It contains bibliographic metadata, DOI/PMID/URLs, DSG-authored evidence summaries, limitations, clinical rule links, priority journals, search queries and an expert watchlist. It deliberately contains **no copyrighted article full text**.

## Design principles

1. Offline-first: active evidence is available without Internet.
2. Traceable: every actionable clinical rule has a stable `rule_id` and linked references.
3. Non-dogmatic: contextual values such as 1.5 mm, 3 mm, 2 mm or torque/ISQ criteria explicitly include limits and context.
4. Evidence hierarchy: author reputation never overrides study design/evidence level.
5. Live update without silent mutation: MCP can search new literature and create an update proposal, but bundled active rules cannot be changed at runtime.
6. Country-aware: medication/regulatory guidance remains under the separate Clinical Context layer and requires current country-specific source resolution when online.

## Main MCP operations

- `get_evidence_repository_summary`
- `get_evidence_rule`
- `get_evidence_topic`
- `search_offline_evidence`
- `build_evidence_update_request`
- `get_evidence_update_request`
- `store_evidence_update_proposal` (proposal only, never activation)
- `get_evidence_update_proposal`
