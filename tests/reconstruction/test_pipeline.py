from gemscanner.synthetic.generator import generate_ellipsoid_scan
from gemscanner.reconstruction.pipeline import reconstruct_dataset
from gemscanner.reconstruction.base import ReconstructionParams

def test_reconstruct_dataset_returns_mesh(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=4, ry=3, rz=5,
                                  n_views=120, mm_per_px=0.05, width=400, height=400)
    mesh = reconstruct_dataset(out)
    assert mesh.is_watertight
    assert mesh.volume > 0


def test_reconstruct_dataset_soft_hull_method(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=4, ry=3, rz=5,
                                  n_views=90, mm_per_px=0.08, width=260, height=260)
    mesh = reconstruct_dataset(out, ReconstructionParams(method="soft_hull"))
    assert mesh.is_watertight
    assert mesh.body_count == 1
