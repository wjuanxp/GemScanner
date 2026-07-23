import numpy as np
import trimesh
from scipy.spatial import HalfspaceIntersection
from scipy.optimize import linprog
from scratchpad.cleanroom.polytope import merge_planes, affine_to_plane, facet_rms


def _slice_polygon(u, hvals):
    """2D convex polygon = {x : u_i . x <= h_i}. Returns (N,2) or None."""
    hs = np.column_stack([u, -hvals])          # a x + b y - h <= 0
    A = hs[:, :2]; b = -hs[:, 2]
    norm = np.linalg.norm(A, axis=1, keepdims=True)
    c = np.zeros(3); c[-1] = -1.0
    res = linprog(c, A_ub=np.hstack([A, norm]), b_ub=b,
                  bounds=[(None, None), (None, None), (0, None)])
    if not res.success or res.x[-1] <= 0:
        return None
    try:
        hi = HalfspaceIntersection(hs, res.x[:2])
    except Exception:
        return None
    return hi.intersections


def reconstruct_dual(samples, merge_deg=6.0, min_face_area_frac=0.002, rms_tol_mm=0.15):
    """Dual / convex-hull facet recovery.

    Per z-slice, intersect the 2D half-planes u_i.X <= h_i into the slice
    polygon; stack every slice polygon's vertices over z into a 3D surface
    point cloud (this cloud lies ON the true convex body, since each vertex
    is an exact intersection of two supporting half-planes at that height);
    take the 3D convex hull of that cloud; its faces are candidate facet
    normals. Cluster faces by normal (area-weighted, so a real facet's many
    coplanar hull triangles outvote noise) and refit ONE plane per cluster.

    Two failure modes this guards against, both shared with candidates A and
    C on the same fixtures:

    1. Naive plane offset (hull centroid / per-cluster least squares) cuts
       into the body. A hull face is a *triangulation* of the true facet, so
       its centroid is an interior point of that facet, not a tangency
       witness in 3D. We instead re-derive the plane's affine form
       (theta*, alpha) from the clustered normal and then SNAP the offset to
       the exact support envelope of the nearest sampled azimuth column,
         beta = max_z ( h(theta*, z) - alpha*z ),
       which is the true 3D support value in that direction. This makes
       every emitted plane exactly tangent to (a superset of) the sampled
       body, so intersecting them can never carve away real volume --
       whatever offset error the hull's triangulation geometry introduced is
       corrected away.

    2. Spurious near-horizontal hull faces straddling the girdle transition
       (or hull-triangulation artifacts at all) are rejected with the same
       `facet_rms` discriminator A and C use: a genuine facet fits its own
       azimuth neighbourhood tightly (rms a few hundredths of a mm); an
       artifact plane does not (rms several tenths of a mm). rms_tol_mm=0.15
       cleanly separates the two on both fixtures.
    """
    u = np.column_stack([np.cos(samples.theta), -np.sin(samples.theta)])
    cloud = []
    for vi in range(len(samples.z)):
        sel = samples.valid[vi]
        if sel.sum() < 3:
            continue
        poly = _slice_polygon(u[sel], samples.h[vi, sel])
        if poly is None or len(poly) < 3:
            continue
        cloud.append(np.column_stack([poly, np.full(len(poly), samples.z[vi])]))
    if not cloud:
        return []
    pts = np.vstack(cloud)
    hull = trimesh.Trimesh(vertices=pts).convex_hull
    total = float(hull.area)

    # cluster hull faces by normal, area-weighted -> candidate normals
    cos_tol = np.cos(np.radians(merge_deg))
    clusters = []   # [accum_normal(weighted), area]
    faces = sorted(
        zip(hull.face_normals, hull.area_faces),
        key=lambda x: -x[1],
    )
    for fn, fa in faces:
        if fa < min_face_area_frac * total:
            continue
        n = np.asarray(fn, float)
        for cl in clusters:
            ref = cl[0] / np.linalg.norm(cl[0])
            if float(n @ ref) >= cos_tol:
                cl[0] += fa * n; cl[1] += fa
                break
        else:
            clusters.append([fa * n.copy(), fa])

    out = []
    for accum, _area in clusters:
        nrm = accum / np.linalg.norm(accum)
        if abs(nrm[2]) > 0.999:                 # near-horizontal cap, skip here
            continue
        theta_star = float(np.arctan2(-nrm[1], nrm[0]))
        alpha = float(-nrm[2] / np.hypot(nrm[0], nrm[1]))
        dth = np.angle(np.exp(1j * (samples.theta - theta_star)))
        i = int(np.argmin(np.abs(dth)))
        sel = samples.valid[:, i]
        if sel.sum() < 2:
            continue
        # envelope-snap: exact 3D support in this direction -> always tangent
        beta = float(np.max(samples.h[sel, i] - alpha * samples.z[sel]))
        plane = affine_to_plane(theta_star, alpha, beta)
        rms, nin = facet_rms(plane, samples)
        if nin >= 4 and np.isfinite(rms) and rms <= rms_tol_mm:
            out.append(dict(plane=plane, rms=rms, source="dual"))
    return merge_planes(out, merge_deg=merge_deg)
