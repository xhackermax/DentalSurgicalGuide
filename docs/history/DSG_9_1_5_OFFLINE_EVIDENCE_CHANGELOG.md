# DSG 9.1.5 · Offline Scientific Evidence Engine

## Added

- Versioned offline repository in `resources/evidence/`.
- 32 curated references already discussed for implant distances, immediate placement/loading, narrow implants, bone/soft tissue phenotype, critical/subcritical contours, emergence, implant platform/connection, platform switching, soft-tissue augmentation, MRONJ and current global guidance.
- 18 traceable clinical/evidence rules with `rule_id`, source links, context, limitations and review intervals.
- 9 priority journals and permanent literature-search queries.
- 21-person international expert watchlist. Reputation changes reading priority only, never evidence weight.
- `evidence_core.py`: pure-Python integrity validation, offline search, rule/topic retrieval and live-update request/proposal validation.
- `evidence_context.py`: Blender UI and scene persistence for evidence-update proposals.
- MCP bridge operations for offline evidence queries and update requests.
- Evidence IDs attached to implant-tooth clearance/interdental/diameter analyses.

## Safety / governance

- No copyrighted article full text is bundled.
- Active bundled rules are immutable at runtime.
- Live MCP searches may create proposals only; proposals remain `PENDING_CLINICIAN_REVIEW`.
- Contextual numeric values are not universal hard-coded clinical laws.
