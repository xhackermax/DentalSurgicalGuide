# DSG 9.1.4 — Implant/Tooth Safety Envelope

- Upgrades the former short 1.5 mm platform ring to a longitudinal safety envelope covering the implant body.
- The visual envelope is not the measurement engine. Actual implant↔segmented-tooth clearance uses world-space BVH geometry.
- Adds configurable `implant_tooth_clearance` (default 1.50 mm).
- Implant confirmation blocks only when a target FDI is known and the measured segmented-neighbor clearance violates the explicit context value.
- Adds `analyze_interdental_space` for contextual tooth↔tooth spacing.
- Adds `analyze_implant_diameter_options` to test real catalog diameters on the current center/axis/length without automatically choosing the largest implant.
- Diameter selection remains MCP/clinician reasoning using prosthetics, anatomy, bone, stability, evidence and optional rescue-reserve strategy.
