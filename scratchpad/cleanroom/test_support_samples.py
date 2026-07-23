import numpy as np
from scratchpad.cleanroom.support_samples import synthetic_support_from_planes
from scratchpad.cleanroom.support_samples import build_support_samples


def _box_planes(hx, hy, hz):
    # axis-aligned box |x|<=hx, |y|<=hy, |z|<=hz as 6 unit half-spaces
    return [(1,0,0,hx),(-1,0,0,hx),(0,1,0,hy),(0,-1,0,hy),(0,0,1,hz),(0,0,-1,hz)]


def test_box_support_matches_closed_form():
    planes = _box_planes(3.0, 2.0, 1.0)
    thetas = np.radians([0.0, 90.0, 180.0, 270.0])
    zs = np.array([-0.5, 0.0, 0.5])
    s = synthetic_support_from_planes(planes, thetas, zs)
    # direction u(theta)=(cos, -sin). theta=0 -> +x, support = hx = 3
    # theta=90 -> (0,-1) i.e. -y, support = hy = 2
    assert s.h.shape == (3, 4)
    assert np.allclose(s.h[:, 0], 3.0, atol=1e-4)   # +x
    assert np.allclose(s.h[:, 1], 2.0, atol=1e-4)   # -y
    assert np.allclose(s.h[:, 2], 3.0, atol=1e-4)   # -x
    assert np.allclose(s.h[:, 3], 2.0, atol=1e-4)   # +y
    assert s.valid.all()


def test_build_from_gem04_shapes():
    from gemscanner.storage.dataset import load_dataset
    ds = load_dataset("scans/gem04")
    s = build_support_samples(ds, holder_mask_rows=705)
    assert s.h.shape[1] == ds.frame_count()
    assert s.valid.any()
    # gem is a few mm; support should be within a sane physical range
    assert 0.5 < np.nanmax(s.h) < 25.0
