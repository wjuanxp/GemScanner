import numpy as np
from scratchpad.cleanroom.support_samples import synthetic_support_from_planes
from scratchpad.cleanroom.polytope import planes_to_mesh, merge_planes
from scratchpad.cleanroom.cand_c_egi import reconstruct_egi

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
