"""Pure OFF/EOFF parser used by Blender authoring and external tooling."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _clean_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def parse_eoff(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    lines = _clean_lines(path.read_text(encoding="utf-8", errors="strict"))
    if not lines or lines[0].upper() not in {"OFF", "EOFF"}:
        raise ValueError("Expected OFF/EOFF header")
    cursor = 1
    if cursor >= len(lines):
        raise ValueError("Missing OFF counts")
    counts = lines[cursor].split()
    cursor += 1
    if len(counts) < 2:
        raise ValueError("OFF counts must contain vertex and face counts")
    n_vertices, n_faces = int(counts[0]), int(counts[1])
    if n_vertices <= 0 or n_faces < 0:
        raise ValueError("Invalid OFF counts")

    vertices = []
    for _ in range(n_vertices):
        if cursor >= len(lines):
            raise ValueError("Unexpected end of OFF vertices")
        fields = lines[cursor].split()
        cursor += 1
        if len(fields) < 3:
            raise ValueError("OFF vertex requires x y z")
        vertices.append(tuple(float(v) for v in fields[:3]))

    faces = []
    for _ in range(n_faces):
        if cursor >= len(lines):
            raise ValueError("Unexpected end of OFF faces")
        fields = lines[cursor].split()
        cursor += 1
        count = int(fields[0])
        if count < 3 or len(fields) < count + 1:
            raise ValueError("Invalid OFF face")
        faces.append(tuple(int(v) for v in fields[1:count+1]))

    feature_labels = None
    while cursor < len(lines):
        token = lines[cursor].strip().upper()
        cursor += 1
        if token != "VERTEX_FEATURE_LABELS":
            continue
        values = []
        if cursor < len(lines):
            first = lines[cursor].split()
            if len(first) == 1:
                try:
                    possible_count = int(first[0])
                except ValueError:
                    possible_count = None
                if possible_count == n_vertices:
                    cursor += 1
        while cursor < len(lines) and len(values) < n_vertices:
            parts = lines[cursor].split()
            cursor += 1
            for part in parts:
                values.append(int(part))
                if len(values) == n_vertices:
                    break
        if len(values) != n_vertices:
            raise ValueError(
                f"VERTEX_FEATURE_LABELS expected {n_vertices} values, got {len(values)}"
            )
        feature_labels = values
        break

    return {
        "header": lines[0].upper(),
        "vertices": vertices,
        "faces": faces,
        "vertex_feature_labels": feature_labels,
    }
