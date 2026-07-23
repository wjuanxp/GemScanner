import numpy as np
from scratchpad.cleanroom.support_samples import synthetic_support_from_planes
from scratchpad.cleanroom.polytope import planes_to_mesh, merge_planes
from scratchpad.cleanroom.cand_c_egi import reconstruct_egi
from scratchpad.cleanroom.cand_a_ransac import reconstruct_ransac
from scratchpad.cleanroom.cand_b_dual import reconstruct_dual

def _bipyramid_planes(n=6, slope=1.2, r=2.0):
    planes = []
    for k in range(n):
        az = 2*np.pi*k/n
        for sgn in (+1.0, -1.0):
            a = np.cos(az); b = -np.sin(az); c = sgn*slope
            nrm = np.hypot(np.hypot(a, b), c)
            planes.append((a/nrm, b/nrm, c/nrm, r/nrm))
    return planes

def _samples_for(planes, nth=180, nz=140):
    thetas = np.linspace(0, 2*np.pi, nth, endpoint=False)
    zs = np.linspace(-1.5, 1.5, nz)
    return synthetic_support_from_planes(planes, thetas, zs)

def _normal_error_deg(recs, truth):
    tn = np.array([p[:3] for p in truth])
    errs = []
    for r in recs:
        n = np.array(r["plane"][:3])
        cs = np.clip(tn @ n, -1, 1)
        errs.append(np.degrees(np.arccos(cs.max())))
    return np.array(errs)

def test_egi_recovers_bipyramid():
    truth = _bipyramid_planes()
    s = _samples_for(truth)
    recs = merge_planes(reconstruct_egi(s))
    assert len(recs) >= 12                       # all 12 slanted facets
    err = _normal_error_deg(recs, truth)
    assert np.median(err) < 3.0                  # normals within a few deg
    mesh, _, _ = planes_to_mesh([r["plane"] for r in recs])
    assert mesh.is_watertight


def _unique_normals(normals, tol_deg=2.0):
    out = []
    cos_tol = np.cos(np.radians(tol_deg))
    for n in normals:
        n = n / np.linalg.norm(n)
        if not any(float(np.dot(n, m)) >= cos_tol for m in out):
            out.append(n)
    return np.array(out)


def _asymmetric_gem_planes():
    """Irregular double-pyramid: 8 crown facets (up-tilt, top apex) at uneven
    azimuths/slopes + 6 pavilion facets (down-tilt, bottom apex) at a DIFFERENT
    uneven azimuth set. Mismatched crown/pavilion partition = the realistic
    case that breaks naive normal recovery. All slanted -> watertight from
    tangent facets alone (no horizontal caps needed)."""
    rng = np.random.default_rng(0)
    planes = []
    for az in np.sort(rng.uniform(0, 2*np.pi, 8)):
        slope = 0.7 + 0.15*rng.uniform()
        a = np.cos(az); b = -np.sin(az); c = slope
        nn = np.hypot(np.hypot(a, b), c)
        planes.append((a/nn, b/nn, c/nn, 2.0/nn))
    for az in np.sort(rng.uniform(0, 2*np.pi, 6)):
        slope = -(1.2 + 0.3*rng.uniform())
        a = np.cos(az); b = -np.sin(az); c = slope
        nn = np.hypot(np.hypot(a, b), c)
        planes.append((a/nn, b/nn, c/nn, 1.8/nn))
    return planes


def test_egi_recovers_asymmetric_gem():
    planes = _asymmetric_gem_planes()
    truth_mesh, _, _ = planes_to_mesh(planes)
    s = _samples_for(planes, nth=360, nz=220)
    recs = merge_planes(reconstruct_egi(s))
    mesh, _, _ = planes_to_mesh([r["plane"] for r in recs])
    truth_n = _unique_normals(np.array(truth_mesh.face_normals))
    err = _normal_error_deg(recs, [(n[0], n[1], n[2], 0.0) for n in truth_n])
    assert np.median(err) < 3.0                                    # recovered normals are real facets
    assert abs(mesh.volume - truth_mesh.volume) / truth_mesh.volume < 0.06   # no spurious volume-carving


def test_ransac_recovers_bipyramid():
    truth = _bipyramid_planes()
    s = _samples_for(truth)
    recs = merge_planes(reconstruct_ransac(s, n_iter=1500, seed=1))
    assert len(recs) >= 12
    err = _normal_error_deg(recs, truth)
    assert np.median(err) < 3.0
    mesh, _, _ = planes_to_mesh([r["plane"] for r in recs])
    assert mesh.is_watertight


def test_ransac_recovers_asymmetric_gem():
    planes = _asymmetric_gem_planes()
    truth_mesh, _, _ = planes_to_mesh(planes)
    s = _samples_for(planes, nth=360, nz=220)
    recs = merge_planes(reconstruct_ransac(s, n_iter=3000, seed=1))
    mesh, _, _ = planes_to_mesh([r["plane"] for r in recs])
    truth_n = _unique_normals(np.array(truth_mesh.face_normals))
    err = _normal_error_deg(recs, [(n[0], n[1], n[2], 0.0) for n in truth_n])
    assert np.median(err) < 3.0
    assert abs(mesh.volume - truth_mesh.volume) / truth_mesh.volume < 0.06


def test_dual_recovers_bipyramid():
    truth = _bipyramid_planes()
    s = _samples_for(truth)
    recs = reconstruct_dual(s)     # returns already-merged planes
    assert len(recs) >= 12
    err = _normal_error_deg(recs, truth)
    assert np.median(err) < 3.5
    mesh, _, _ = planes_to_mesh([r["plane"] for r in recs])
    assert mesh.is_watertight


def test_dual_recovers_asymmetric_gem():
    planes = _asymmetric_gem_planes()
    truth_mesh, _, _ = planes_to_mesh(planes)
    s = _samples_for(planes, nth=360, nz=220)
    recs = reconstruct_dual(s)
    mesh, _, _ = planes_to_mesh([r["plane"] for r in recs])
    truth_n = _unique_normals(np.array(truth_mesh.face_normals))
    err = _normal_error_deg(recs, [(n[0], n[1], n[2], 0.0) for n in truth_n])
    assert np.median(err) < 3.0
    assert abs(mesh.volume - truth_mesh.volume) / truth_mesh.volume < 0.06
