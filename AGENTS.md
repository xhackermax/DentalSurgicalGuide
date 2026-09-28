# DSG Engineering Constitution — Mandatory for AI Agents and Developers

**Status:** Normative / non-negotiable governance for all future DSG changes  
**Target:** Blender 5.2  
**Baseline:** DSG 9.6.x  
**Applies to:** humans, coding agents, LLMs, refactoring tools, automated patchers and CI assistants.

> If a requested change conflicts with this document, the implementation must stop, explain the conflict, update the specification first, and only then change code.

## 1. Core engineering principles

KISS · SOLID · DRY · YAGNI · SoC · SSOT · Fail-Fast · DBC · Idempotence.

1. Do not break previously working clinical functionality.
2. No dead buttons. Every visible control must execute, change state, open a valid action, or be disabled with a reason.
3. SIMPLE must remain genuinely simple. Never run the full FDI pipeline and merely hide its outputs.
4. Do not execute work the user did not request.
5. Maintain one source of truth for each state/version/result.
6. Every destructive clinical transition must be reversible or checkpointed.
7. Fail early and surface an actionable cause.
8. Keep UI, operators, services/domain logic and heavy workers separated.
9. Do not duplicate pipelines, data, models or code without a demonstrated need.
10. Before adding complexity, prove that it is necessary.
11. Every important fixed bug must gain a regression test.
12. Never declare a build stable without a real Blender 5.2 smoke test.

## 2. Clinical AI scope: Dental / Maxillofacial first

DSG is not a general whole-body medical segmentation workstation. Its default AI installation and inference scope must remain limited to anatomy that has a direct dental, oral surgery, implantology, maxillofacial or surgical-guide purpose.

### Default clinically justified scope

Keep or support, when technically available and validated:

- individual teeth and FDI identity;
- maxilla;
- mandible;
- clinically relevant craniofacial bone;
- inferior alveolar / mandibular canals and other clinically useful dental canals;
- maxillary sinuses;
- other craniofacial structures only when they support a defined DSG workflow.

### Not installed or executed by default

Do **not** download, install, preload or execute models/weights whose only purpose is unrelated whole-body anatomy, including for example:

- lungs and thoracic organs;
- abdominal organs;
- pelvic structures;
- general skeletal muscles unrelated to maxillofacial workflows;
- brain-region segmentation unrelated to a defined dental/maxillofacial workflow;
- cardiac structures;
- any other model that has no current DSG clinical consumer.

A future feature may expand this scope only after the spec names the clinical use case and acceptance test.

## 3. Every megabyte must have a consumer

Treat runtime size, download time and disk use as architectural constraints.

Before adding any dependency, model, weight archive or runtime asset, document:

1. **Consumer** — exact DSG feature that imports/uses it.
2. **Clinical value** — why that feature needs it.
3. **Install size** — compressed and installed size when known.
4. **Runtime cost** — RAM/VRAM/startup/inference impact when relevant.
5. **Alternative** — whether an already-installed component can do the job.
6. **Removal test** — what test fails if this asset is absent.

If no concrete consumer can be identified, the dependency/asset is considered unnecessary and must not be included by default.

## 4. Runtime architecture

Prefer a reproducible **DSG Dental/Maxillofacial Runtime** over an unrestricted generic AI environment.

Target architecture:

```text
Blender / DSG UI
      ↓
Controller
      ↓
External worker
      ↓
Minimal shared inference runtime
      +
Only clinically required model weights
      ↓
Explicit manifest
      ↓
Blender import/postprocess
```

Rules:

- Heavy inference should run outside Blender's UI process when feasible.
- Avoid interactive `pip` dependency solving during normal user operation when a reproducible prebuilt runtime can be shipped/downloaded instead.
- Prefer verified archives/wheels with hashes over dynamic dependency resolution.
- Reuse an already valid runtime across DSG updates. Do not redownload gigabytes because the addon code changed.
- Separate **runtime** from **model weights** so models can be added/removed independently.
- Cache verified downloads and resume/retry safely when possible.
- Never require administrator writes to `Program Files` for the normal runtime.
- Store mutable runtime data under Blender/user-controlled writable directories.

## 5. Installation UX is part of correctness

Any operation lasting roughly >0.5–1 s must provide visible feedback.

Motor installation must expose at minimum:

- state: `NOT_INSTALLED | INSTALLING | READY | ERROR`;
- current phase;
- progress percentage when measurable;
- heartbeat/activity when exact percentage is not measurable;
- bytes downloaded when available;
- current asset/package/model name;
- actionable error on failure;
- timeout/stall detection for subprocesses;
- retry without corrupting an existing valid runtime.

Never leave the user at a static percentage while a long opaque subprocess runs.

## 6. Routes are distinct contracts

### SIMPLE_ARCHES

Purpose: produce only two clinically usable anatomical arches with minimum work.

Required output:

```text
Upper_Arch
Lower_Arch
```

Forbidden unless the SIMPLE spec explicitly changes:

- FDI numbering;
- individual tooth objects;
- `teeth_req`;
- child workers for individual teeth;
- universal FDI labels;
- mandibular canal as a prerequisite;
- hidden execution of the full FDI pipeline.

Architectural invariant:

```text
Work(SIMPLE_ARCHES) < Work(FDI)
```

If SIMPLE approaches FDI in time, RAM, VRAM or I/O, treat it as an architecture regression even if the visual result is correct.

### FDI / advanced anatomical route

May use individual teeth, FDI, canals/nerves, maxilla, mandible, sinuses and additional craniofacial postprocessing required by the advanced clinical workflow.

`SIMPLE != FDI with hidden objects`.

## 7. Manifest is the worker → Blender contract

The worker must communicate results using an explicit manifest. Blender must not infer success by scanning arbitrary temporary folders.

The manifest is the SSOT for worker results.

## 8. State machine and reversibility

Use explicit wizard states, e.g.:

```text
EMPTY → CASE_SELECTED → DICOM_IMPORTED → SEGMENTED → ALIGNED → PLANNED → GUIDE_READY
```

Invalid jumps must be impossible.

`Atrás` must restore the coherent previous clinical state, not merely switch panels.

Blender Undo and DSG checkpoints are complementary, not interchangeable.

## 9. Idempotence

Repeating an action must not silently create duplicate outputs such as `.001`, duplicate runtimes or duplicate model archives.

Detect existing valid results and reuse or replace them transactionally.

## 10. Stable internal naming

Use stable DSG semantic names rather than Blender-generated object names for program logic.

Examples:

```text
DSG_CASE
DSG_UPPER_ARCH
DSG_LOWER_ARCH
DSG_IOS
DSG_IMPLANT
DSG_GUIDE
```

## 11. Required validation before delivery

A release is not complete until the relevant checks pass:

```text
compileall
unit tests
manifest/contract tests
route tests
operator registration audit
runtime/dependency scope test
ZIP integrity
real Blender 5.2 smoke test
```

### Mandatory dead-button audit

Every operator referenced by UI must be verified as implemented, registered and callable/poll-valid.

Required invariant:

```text
DEAD_BUTTONS = 0
```

### Mandatory runtime-scope regression test

The default Dental/Maxillofacial installation must have a machine-checkable allowlist/manifest. Tests must fail if unrelated whole-body model assets are accidentally added to the default profile.

## 12. Spec-driven development

Do not implement a substantial feature directly from a casual request.

Flow:

```text
request
  ↓
spec change
  ↓
plan
  ↓
tasks
  ↓
implementation
  ↓
tests
  ↓
acceptance
```

Normative specification files live under `docs/specs/DSG_9.6/`.

## 13. Definition of Done

A DSG feature is DONE only when all applicable items are true:

```text
SPEC ✓
IMPLEMENTATION ✓
TEST ✓
UI ✓
ERROR HANDLING ✓
UNDO / ROLLBACK ✓
PERFORMANCE/SCOPE ✓
NO REGRESSION ✓
BLENDER SMOKE TEST ✓
```

Otherwise it is **NOT DONE**.
