# Author: mertaygn, cglrgrkn
"""validation.py - Anatomic consistency check + cross-photo consistency."""
from __future__ import annotations
import numpy as np


ORGAN_REGIONS = {
    # oid: (x_min, x_max, y_min, y_max, z_min, z_max, desc)
    1: (-2.0,   8.0, -6.0,  1.5, -8.0, +1.0,  "mide: cranio-ventral SOL"),
    2: (-7.0,   4.0, -1.0,  8.0, +0.0, +6.0,  "bobrek: dorsal SAG"),
    3: ( 0.0,  12.0, -6.0,  3.0, -3.0, +5.0,  "karaciger: cranio-ventral"),
    4: (-14.0, -3.0, -8.0, -1.0, -3.0, +3.0,  "mesane: caudo-ventral pelvik"),
    5: (-4.0,   6.0, -5.0,  2.0, -3.0, +5.0,  "pankreas: orta-ventral"),
    6: (-8.0,   3.0, -6.0,  2.0, -4.0, +4.0,  "bagirsak: caudo-ventral"),
    7: ( 3.0,  13.0, -3.0,  6.0, -3.0, +3.0,  "kalp: mediastinum toraks"),
    8: (-3.0,   7.0, -5.0,  3.0, -8.0, -1.0,  "dalak: sol abdomen lateral"),
    9: ( 3.0,  12.0, -1.0,  7.0, +0.0, +7.0,  "sag akciger: dorso-lateral SAG"),
   10: ( 3.0,  12.0, -1.0,  7.0, -7.0, -0.0,  "sol akciger: dorso-lateral SOL"),
}


BODY_BOUNDS_CANONICAL = {
    "x_min": -22.0, "x_max": 17.0,
    "y_min": -10.0, "y_max":  8.0,
    "z_min":  -7.0, "z_max":  7.0,
}


def anatomic_consistency_check(organs_3d: dict, morph: "dict | None" = None,
                                    strict: bool = False) -> dict:
    """Organ pozisyonlarinin anatomik plausibility kontrolu."""
    if morph is None:
        morph = {"sx": 1.0, "sy": 1.0, "sz": 1.0, "bcs": 0.0}
    sx = float(morph.get("sx", 1.0))
    sy = float(morph.get("sy", 1.0))
    sz = float(morph.get("sz", 1.0))
    bcs_shift = float(morph.get("bcs", 0.0)) * (-1.5)

    violations = []
    warnings_list = []
    n_passed = 0
    n_checked = 0

    for oid_or_str, info in organs_3d.items():
        try:
            oid = int(oid_or_str)
        except (TypeError, ValueError):
            continue
        coord = info.get("coord_3d_cm")
        if coord is None or len(coord) < 3:
            continue
        x, y, z = float(coord[0]), float(coord[1]), float(coord[2])
        n_checked += 1

        bb = BODY_BOUNDS_CANONICAL
        in_body = (
            bb["x_min"] * sx <= x <= bb["x_max"] * sx
            and bb["y_min"] * sy + bcs_shift <= y <= bb["y_max"] * sy
            and bb["z_min"] * sz <= z <= bb["z_max"] * sz
        )
        if not in_body:
            violations.append((
                oid, info.get("name", "?"), "outside_body",
                f"({x:+.1f},{y:+.1f},{z:+.1f}) vucut hududu disinda"))
            continue

        reg = ORGAN_REGIONS.get(oid)
        if reg is None:
            n_passed += 1
            continue
        xmin, xmax, ymin, ymax, zmin, zmax, desc = reg
        xmin_s, xmax_s = xmin * sx, xmax * sx
        ymin_s = ymin * sy + bcs_shift
        ymax_s = ymax * sy + (bcs_shift if ymin < 0 else 0.0)
        zmin_s, zmax_s = zmin * sz, zmax * sz

        if not (xmin_s <= x <= xmax_s
                and ymin_s <= y <= ymax_s
                and zmin_s <= z <= zmax_s):
            violations.append((
                oid, info.get("name", "?"), "wrong_region",
                f"({x:+.1f},{y:+.1f},{z:+.1f}) -> beklenen [{desc}]: "
                f"x[{xmin_s:+.1f},{xmax_s:+.1f}] "
                f"y[{ymin_s:+.1f},{ymax_s:+.1f}] "
                f"z[{zmin_s:+.1f},{zmax_s:+.1f}]"))
        else:
            n_passed += 1

    score = n_passed / max(n_checked, 1)
    passed_overall = (
        len(violations) == 0 if strict
        else score >= 0.7
    )
    return {
        "passed": passed_overall,
        "score": round(score, 3),
        "n_organs_checked": n_checked,
        "n_organs_passed": n_passed,
        "violations": violations,
        "warnings": warnings_list,
        "policy": "strict" if strict else "lenient_70pct",
    }


# ============================================================================
# Per-cat morphology (L1+L2: anisotropic body scaling + BCS)
# ============================================================================
# CANONICAL boyutlar (cm) — Hudson & Hamilton + Done et al.
