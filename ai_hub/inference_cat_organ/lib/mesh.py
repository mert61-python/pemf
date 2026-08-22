# Author: mertaygn, cglrgrkn
"""mesh.py - Canonical cat mesh build (govde + kafa + boyun + bacaklar + kuyruk)."""
from __future__ import annotations
import numpy as np

from .canonical import CANONICAL_ORGANS_3D
from .geometry import apply_morphology_to_mesh, apply_morphology_to_atlas


def _tapered_tube(path_pts: np.ndarray, radii: np.ndarray,
                     sections: int = 10) -> "trimesh.Trimesh":
    """Path boyunca tapered tube/spline mesh uretir.

    Args:
        path_pts: (M, 3) merkez nokta dizisi
        radii:    (M,) her noktada yaricap
        sections: cevre cember nokta sayisi
    """
    import trimesh
    M = len(path_pts)
    assert len(radii) == M
    verts = []
    faces = []
    # Her path nokta icin Frenet-like frame (basit: world Z up'a normalize)
    for i in range(M):
        p = path_pts[i]
        if i == 0:
            tangent = path_pts[1] - path_pts[0]
        elif i == M - 1:
            tangent = path_pts[-1] - path_pts[-2]
        else:
            tangent = path_pts[i + 1] - path_pts[i - 1]
        tn = np.linalg.norm(tangent)
        if tn < 1e-6:
            tangent = np.array([1.0, 0.0, 0.0])
        else:
            tangent = tangent / tn
        # Reference up (world dorsal +Y)
        up = np.array([0.0, 1.0, 0.0])
        if abs(np.dot(tangent, up)) > 0.99:
            up = np.array([0.0, 0.0, 1.0])
        right = np.cross(tangent, up)
        right = right / max(np.linalg.norm(right), 1e-6)
        nrml = np.cross(right, tangent)
        nrml = nrml / max(np.linalg.norm(nrml), 1e-6)
        # Cember
        for k in range(sections):
            ang = 2 * np.pi * k / sections
            offset = radii[i] * (np.cos(ang) * right + np.sin(ang) * nrml)
            verts.append(p + offset)
    verts = np.array(verts, dtype=np.float64)
    # Faces: her halka icin 2 ucgen
    for i in range(M - 1):
        for k in range(sections):
            k1 = (k + 1) % sections
            a = i * sections + k
            b = i * sections + k1
            c = (i + 1) * sections + k
            d = (i + 1) * sections + k1
            faces.append([a, b, d])
            faces.append([a, d, c])
    return trimesh.Trimesh(vertices=verts, faces=np.array(faces, dtype=np.int64),
                              process=False)




def build_canonical_cat_mesh() -> dict:
    """Canonical cat body'i anatomik primitives ile uretir.

    Iyilestirmeler v2:
      - Body: dorso-ventral hacim artirildi (4.5 -> 5.5)
      - Tail: tapered tube (Bezier-benzeri), 2.2 -> 0.6 cm yaricap
      - Bacaklar: bent (thigh+calf 2 segment, knee'de kirik)
      - Head: head sphere boynun ucunda, hafifce daha buyuk

    Returns:
        vertices (V, 3): 3D vertex pozisyonlari (cm)
        faces (F, 3):    triangle index'leri
        groups: {part_name: vertex_index_list}
    """
    import trimesh
    parts = []
    groups = {}
    vert_offset = 0

    def add(mesh, name):
        nonlocal vert_offset
        n_v = len(mesh.vertices)
        parts.append(mesh)
        groups[name] = list(range(vert_offset, vert_offset + n_v))
        vert_offset += n_v

    # Govde — origin'de (CANONICAL_ORGANS_3D ile hizali)
    body = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    body.apply_scale([14.0, 5.5, 5.5])
    # Translation: (0, 0, 0) — organ koordinat sistemine hizali. Onceden
    # (0, 1, 0) idi -> organlar mesh icinde 1cm asagida gorunuyordu.
    add(body, "body")

    # Kafa
    head = trimesh.creation.icosphere(subdivisions=2, radius=4.0)
    head.apply_translation([14.5, 2.5, 0.0])
    add(head, "head")

    # Boyun
    neck = trimesh.creation.cylinder(radius=2.6, height=5.5, sections=12)
    neck.apply_transform(trimesh.transformations.rotation_matrix(
        np.pi / 2, [0, 1, 0]))
    neck.apply_translation([10.5, 3.5, 0.0])
    add(neck, "neck")

    # Kuyruk — tapered tube (Bezier control points)
    # cubic Bezier: P0=(-10,4,0), P1=(-15,3,0), P2=(-22,2,0), P3=(-28,2,0)
    p0 = np.array([-10.0, 4.0, 0.0])
    p1 = np.array([-15.0, 3.0, 0.0])
    p2 = np.array([-22.0, 2.0, 0.0])
    p3 = np.array([-28.0, 2.0, 0.0])
    n_tail = 18
    ts = np.linspace(0, 1, n_tail)
    path = np.array([(1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1
                       + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3 for t in ts])
    # Yaricap: 2.2 -> 0.6 (taper)
    tail_radii = 2.2 * (1.0 - 0.73 * ts) + 0.05
    tail_mesh = _tapered_tube(path, tail_radii, sections=10)
    add(tail_mesh, "tail")

    # Kulaklar
    for side, z in (("left_ear", -3.0), ("right_ear", +3.0)):
        ear = trimesh.creation.cone(radius=1.7, height=3.8, sections=8)
        ear.apply_translation([12.5, 7.0, z])
        add(ear, side)

    # Bacaklar — knee'de kirik (bent geometry)
    # Front: thai(5.5, 1, ±3.5) -> knee(4.5, -5, ±3.5) -> paw(5, -9, ±3.5)
    # Back:  thai(-8, 2, ±4) -> knee(-7, -4, ±4.5) -> paw(-8.5, -13, ±4.5)
    leg_segments = [
        # (name, p_start, p_end, radius_start, radius_end)
        ("front_left_thigh",  [5.5, 1.0, -3.5], [4.5, -5.0, -3.5], 1.8, 1.4),
        ("front_left_calf",   [4.5, -5.0, -3.5], [5.0, -9.0, -3.5], 1.4, 1.0),
        ("front_right_thigh", [5.5, 1.0,  3.5], [4.5, -5.0,  3.5], 1.8, 1.4),
        ("front_right_calf",  [4.5, -5.0,  3.5], [5.0, -9.0,  3.5], 1.4, 1.0),
        ("back_left_thigh",   [-8.0, 2.0, -4.0], [-7.0, -4.0, -4.5], 2.2, 1.6),
        ("back_left_calf",    [-7.0, -4.0, -4.5], [-8.5, -13.0, -4.5], 1.5, 1.0),
        ("back_right_thigh",  [-8.0, 2.0,  4.0], [-7.0, -4.0,  4.5], 2.2, 1.6),
        ("back_right_calf",   [-7.0, -4.0,  4.5], [-8.5, -13.0,  4.5], 1.5, 1.0),
    ]
    for name, ps, pe, rs, re in leg_segments:
        path = np.array([np.asarray(ps, dtype=np.float64),
                            np.asarray(pe, dtype=np.float64)])
        radii = np.array([rs, re], dtype=np.float64)
        leg = _tapered_tube(path, radii, sections=8)
        add(leg, name)

    combined = trimesh.util.concatenate(parts)
    return {
        "vertices": np.asarray(combined.vertices, dtype=np.float64),
        "faces": np.asarray(combined.faces, dtype=np.int64),
        "groups": groups,
    }


# Cached mesh (lazy)


_CACHED_MESH = None



def get_canonical_mesh() -> dict:
    global _CACHED_MESH
    if _CACHED_MESH is None:
        _CACHED_MESH = build_canonical_cat_mesh()
    return _CACHED_MESH




def get_per_cat_mesh(result: dict) -> dict:
    """Result'tan morphology al, canonical mesh'i scale et."""
    base = get_canonical_mesh()
    morph = (result.get("morphology") if result else None) or {
        "sx": 1.0, "sy": 1.0, "sz": 1.0, "bcs": 0.0}
    return apply_morphology_to_mesh(base, morph)




def get_per_cat_organ_atlas(result: dict) -> dict:
    """Per-cat scaled organ atlas (CANONICAL_ORGANS_3D scaled)."""
    morph = (result.get("morphology") if result else None) or {
        "sx": 1.0, "sy": 1.0, "sz": 1.0, "bcs": 0.0}
    return apply_morphology_to_atlas(CANONICAL_ORGANS_3D, morph)


# ============================================================================
# Pose-specific template atlas (eski, fallback)

# ============================================================================
# YOLO segmentation
# ============================================================================
