# DSG 9.10 segmentation engines

All three engines receive the same calibrated CBCT and return a normalized DSG labelmap before
surface extraction. This build is intended for direct quality/speed comparison.

## TotalSegmentator
Production-oriented full dental anatomy engine. `teeth` is used with its official model stack.

## ToothSeg
Dual-branch semantic + border/core instance segmentation with FDI self-correction. DSG executes
both official branches and their post-processing. Output is teeth-only.

## U-Mamba2
ToothFairy3 adapter based on the authors' official inference implementation. The repository is
installed, but DSG requires a final trained segmentation checkpoint. SSL pretraining alone does
not satisfy the READY check.

## Normalized output
- tooth compatibility IDs: 1..32
- mandible: 53
- maxilla: 54
- mandibular canal: 55

## Benchmarking
The engine ID, engine metadata and phase timings are persisted in the external pipeline manifest,
allowing the same patient CBCT to be run with different engines without changing downstream mesh
creation.
