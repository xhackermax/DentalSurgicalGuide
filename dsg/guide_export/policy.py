"""Export quality thresholds. Pure configuration: no behaviour, no bpy."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExportPolicy:
    """Thresholds used by the export quality gate.

    Defaults are deliberately conservative *warnings*; only a non-closed mesh
    and unconfirmed removal of a significant island block the export, because
    both produce a physically different guide from the one planned.
    Wall-thickness and canal-distance limits are clinician-configurable and
    reported, not silently enforced (they depend on material and technique).
    """

    # Closed-solid gate ----------------------------------------------------
    block_non_manifold: bool = True
    degenerate_area_mm2: float = 1.0e-10

    # Wall thickness (ray sampling along the inward normal) ------------------
    min_wall_thickness_mm: float = 1.0
    thin_wall_warn_fraction: float = 0.001   # >0.1 % of samples below → warning
    block_thin_walls: bool = False
    thickness_max_samples: int = 20000
    thickness_ray_epsilon_mm: float = 1.0e-4
    thickness_max_distance_mm: float = 50.0

    # Disconnected islands -------------------------------------------------
    max_auto_remove_island_mm3: float = 0.5   # |volume| of each removed shell
    max_auto_remove_island_faces: int = 2000

    # Anatomical clearance -------------------------------------------------
    min_canal_distance_mm: float = 2.0

    def __post_init__(self) -> None:
        if self.min_wall_thickness_mm < 0 or self.min_canal_distance_mm < 0:
            raise ValueError("clearance/thickness thresholds must be >= 0")
        if self.thickness_max_samples <= 0:
            raise ValueError("thickness_max_samples must be > 0")
        if not 0.0 <= self.thin_wall_warn_fraction <= 1.0:
            raise ValueError("thin_wall_warn_fraction must be within [0, 1]")
