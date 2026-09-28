# DSG 9.6 — AI Runtime Scope Contract

**Normative.** This file defines the default installation boundary for AI assets.

## Goal

Minimize installation time, download size, disk use and failure surface without sacrificing dental/maxillofacial clinical capability.

## Default profile: `DENTAL_MAXILLOFACIAL`

Allowed capabilities when validated and consumed by DSG:

- teeth / individual tooth segmentation / FDI;
- maxilla;
- mandible;
- relevant craniofacial bone;
- mandibular / inferior alveolar canals and clinically useful dental canals;
- maxillary sinuses;
- explicitly documented craniofacial support structures.

## Default-deny rule

Whole-body model assets are **not** part of the default profile unless a DSG specification explicitly adds a clinical consumer and acceptance test.

Examples normally denied by default: lungs, abdominal organs, pelvis, cardiac structures, unrelated skeletal muscles, unrelated brain structures and other non-craniofacial anatomy.

## Dependency admission rule

For every new dependency or model asset, record:

| Field | Required |
|---|---|
| DSG consumer/feature | yes |
| clinical purpose | yes |
| compressed size | when measurable |
| installed size | when measurable |
| runtime/RAM/VRAM impact | when relevant |
| existing alternative considered | yes |
| regression/contract test | yes |

No consumer = no default installation.

## Packaging preference

Prefer:

1. prebuilt reproducible runtime;
2. verified hashes;
3. runtime separated from weights;
4. cached/reusable downloads;
5. only required weights;
6. no admin rights;
7. no unnecessary pip solving at runtime.

## Required test invariant

A test/manifest audit must be able to answer:

```text
Which installed megabytes are used by which DSG feature?
```

Unmapped large assets are a release blocker until justified or removed.
