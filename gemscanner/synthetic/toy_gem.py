"""Parametric convex faceted test solid + ground-truth plane extraction."""
import numpy as np
import trimesh


def make_toy_gem(n=8, r_girdle=5.0, r_table=3.0, z_table=2.0,
                 z_girdle=0.0, z_culet=-4.0):
    """Return (vertices, planes) for a convex faceted 'toy gem'.

    Geometry: regular n-gon girdle at z_girdle, table polygon (radius r_table)
    at z_table, single apex culet at z_culet. Planes are the unique outward
    face planes (normal unit, body on normal.x <= d)."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    girdle = np.column_stack([r_girdle * np.cos(a), r_girdle * np.sin(a),
                              np.full(n, z_girdle)])
    table = np.column_stack([r_table * np.cos(a), r_table * np.sin(a),
                             np.full(n, z_table)])
    culet = np.array([[0.0, 0.0, z_culet]])
    verts = np.vstack([girdle, table, culet])
    hull = trimesh.Trimesh(vertices=verts).convex_hull
    planes = unique_face_planes(hull)
    return np.asarray(hull.vertices, float), planes


def unique_face_planes(mesh, angle_tol_deg=1.0, offset_tol=1e-3):
    """Cluster a convex mesh's triangles into distinct (normal, d) facet planes."""
    normals = np.asarray(mesh.face_normals, float)
    # signed offset d = normal . (any vertex of the face)
    tri0 = mesh.vertices[mesh.faces[:, 0]]
    d = np.einsum("ij,ij->i", normals, tri0)
    cos_tol = np.cos(np.radians(angle_tol_deg))
    out = []
    for nrm, off in zip(normals, d):
        for i, (kn, kd) in enumerate(out):
            if float(np.dot(nrm, kn)) >= cos_tol and abs(off - kd) <= offset_tol:
                break
        else:
            out.append((nrm / np.linalg.norm(nrm), float(off)))
    return out
