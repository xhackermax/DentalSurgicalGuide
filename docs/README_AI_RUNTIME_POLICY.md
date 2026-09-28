# AI Runtime Policy — DSG

This is a short operational summary. The normative rules are in `AGENTS.md` and `docs/specs/DSG_9.6/runtime_scope.md`.

DSG targets dentistry and maxillofacial workflows. The default AI profile should support teeth/FDI, maxilla, mandible, relevant bone, dental nerve canals and maxillary sinuses. It must not download unrelated whole-body model weights by default.

Do not optimize installation by randomly deleting Python packages. First map imports/assets to actual DSG consumers, then remove or avoid anything with no consumer. Prefer a tested prebuilt runtime plus selected model weights over a large interactive `pip install`.

Runtime updates, model updates and addon-code updates should be independently versioned so a UI/code patch does not trigger a multi-gigabyte reinstall.
