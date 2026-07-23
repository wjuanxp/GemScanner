import numpy as np
import pytest
from scratchpad.cleanroom.polytope import (
    affine_to_plane, plane_to_affine, planes_to_mesh, merge_planes, extremal_caps)

def _box_planes(hx, hy, hz):
    return [(1,0,0,hx),(-1,0,0,hx),(0,1,0,hy),(0,-1,0,hy),(0,0,1,hz),(0,0,-1,hz)]

def test_affine_plane_roundtrip():
    th, al, be = 0.7, -0.3, 2.5
    a, b, c, d = affine_to_plane(th, al, be)
    assert abs(np.hypot(np.hypot(a, b), c) - 1.0) < 1e-9   # unit normal
    th2, al2, be2 = plane_to_affine((a, b, c, d))
    assert abs(np.angle(np.exp(1j*(th2-th)))) < 1e-6
    assert abs(al2-al) < 1e-6 and abs(be2-be) < 1e-6

def test_box_planes_to_mesh_watertight_extents():
    mesh, verts, edges = planes_to_mesh(_box_planes(3.0, 2.0, 1.0))
    assert mesh.is_watertight
    ext = mesh.bounding_box.extents
    assert np.allclose(sorted(ext), [2.0, 4.0, 6.0], atol=1e-6)

def test_merge_collapses_near_duplicates():
    recs = [dict(plane=(1,0,0,3.0), rms=0.01, source="t"),
            dict(plane=(1,0,0,3.02), rms=0.005, source="t"),  # ~dup, better rms
            dict(plane=(0,1,0,2.0), rms=0.01, source="t")]
    out = merge_planes(recs, merge_deg=6.0)
    assert len(out) == 2
    kept = [r for r in out if abs(r["plane"][0]-1) < 1e-9][0]
    assert kept["rms"] == 0.005   # keeps lower-rms of the merged pair

def test_planes_to_mesh_raises_valueerror_when_unbounded():
    # bounded in x,y but open in z -> not a closed region -> ValueError (not QhullError)
    open_planes = [(1,0,0,3.0),(-1,0,0,3.0),(0,1,0,2.0),(0,-1,0,2.0)]
    with pytest.raises(ValueError):
        planes_to_mesh(open_planes)

def test_extremal_caps_flags_table_skips_culet():
    import numpy as np
    from scratchpad.cleanroom.support_samples import SupportSamples
    from scratchpad.cleanroom.polytope import extremal_caps
    z = np.linspace(-2.0, 2.0, 81)
    theta = np.radians(np.arange(0, 360, 2.0))
    r = np.clip(2.0 * (2.0 - z) / 4.0, 0.02, None)   # ~2.0 wide at bottom -> ~0 at top
    h = np.tile(r[:, None], (1, len(theta)))
    s = SupportSamples(theta=theta, z=z, h=h, valid=np.ones_like(h, bool))
    caps = extremal_caps(s, width_frac=0.3)
    assert sorted(c["plane"][2] for c in caps) == [-1.0]   # exactly one cap, on the wide bottom (c<0)
