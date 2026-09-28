"""Fast, reproducible installation of DSG's AI engine (TotalSegmentator runtime).

Pure standard library: it is imported by Blender (as ``dsg.engine_install``)
and by the external installer worker (as ``engine_install``, without ``bpy``).

Modules (single responsibility each):

* ``identity``  – which runtime a machine needs and where it lives
                  (independent of the DSG add-on version).
* ``manifest``  – remote/offline manifest (schema 2): profiles, assets, mirrors.
* ``download``  – parallel, resumable, hash-verified downloads with mirrors.
* ``archive``   – safe extraction of (multi-part) archives.
* ``builder``   – local build fallback with ``uv`` (or ``pip``).
* ``installer`` – orchestration: reuse → adopt legacy → prebuilt → local build,
                  staged install and atomic activation.
"""
