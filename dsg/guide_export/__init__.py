"""Guide export quality gate and traceability report (DSG 9.7.0).

Layering (SOLID):

* ``policy``      – immutable thresholds (configuration, no behaviour).
* ``mesh_checks`` – pure NumPy geometry analysis. Depends only on the
                    ``RayCaster`` protocol, never on Blender (DIP).
* ``report``      – pure builder/writer of the JSON traceability sidecar.
* ``blender_adapter`` – the only module that touches ``bpy``: converts Blender
                    objects to arrays and provides a BVH-backed ``RayCaster``.
* ``service``     – orchestrates the above for the export operator.

The operator depends on ``service``; ``service`` depends on abstractions. Pure
modules are unit-tested without Blender (tests/test_guide_export_*.py).
"""
