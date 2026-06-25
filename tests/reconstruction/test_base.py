from gemscanner.reconstruction.base import ReconstructionParams, SliceResult

def test_defaults():
    p = ReconstructionParams()
    assert p.n_radial == 180
    assert p.bbox_mm == 50.0
    s = SliceResult(z_mm=1.5)
    assert s.z_mm == 1.5
    assert s.polygon is None
