# DSG 9.7.x — Developer / AI entrypoint

DSG is a dental and maxillofacial clinical planning addon for Blender 5.2.

## Before changing code

**Mandatory:** read `AGENTS.md` first. It is the engineering constitution for this repository and applies to humans and AI coding agents.

Then read:

- `docs/specs/DSG_9.6/spec.md` — product/clinical behavior contract.
- `docs/specs/DSG_9.6/runtime_scope.md` — what AI/runtime components are allowed by default.
- `docs/specs/DSG_9.6/acceptance.md` — release acceptance gates.

## One-sentence architecture rule

> DSG installs and executes only the dental/maxillofacial AI capability required by an explicit clinical workflow; it must not carry unrelated whole-body models or dependencies by default.

## Core invariants

- No dead buttons.
- SIMPLE_ARCHES is a genuinely smaller pipeline than FDI.
- Heavy inference belongs in an external worker where feasible.
- Manifest = SSOT for worker results.
- Every destructive transition is reversible/checkpointed.
- Long operations show visible progress/activity.
- Every megabyte added to the runtime must have a named DSG consumer.
- Runtime and model weights are separated and reusable across addon updates.
- No release is stable without a real Blender 5.2 smoke test.

## Repository layout (9.7.0)

```text
dsg/            the Blender add-on (the only folder that is packaged)
  guide_export/ export quality gate + traceability report (SOLID, see docs/MEJORAS_9_7_0.md)
tests/          pytest suite (pure tests run without Blender; `requires_bpy` tests need bpy)
tools/          run_checks.py, blender_smoke.py, install_smoke.py, build_addon_zip.py, codemods
docs/           specs, architecture notes, history of release notes
```

## Everyday commands

```bash
pip install "bpy==5.2.2" pytest ruff numpy scipy   # Python 3.13, same as Blender 5.2
python tools/run_checks.py                          # all automated release gates
python tools/build_addon_zip.py --out dist          # installable ZIP (+ .sha256)
```

What changed in 9.7.0 and why: `docs/MEJORAS_9_7_0.md`.
