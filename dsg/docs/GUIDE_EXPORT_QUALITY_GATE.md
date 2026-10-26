# Guide export quality gate

DSG 9.9 retains the 9.8.4 export validation service under `guide_export/`.

Before a final guide is exported, the service can inspect clinically relevant mesh properties including:

- closed/manifold mesh status;
- degenerate triangles;
- disconnected islands;
- volume and bounding box sanity;
- minimum wall thickness / thin-wall fraction;
- configured implant-to-mandibular-canal clearance checks;
- explicit override/reporting when policy allows a user exception.

The export report records DSG version and Blender version to improve traceability.

This gate is a software quality/safety check, not a substitute for clinician review or a certified medical-device validation process.
