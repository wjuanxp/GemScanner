import os
from gemscanner.synthetic.generator import generate_ellipsoid_scan
from gemscanner.cli import main


def test_reconstruct_subcommand(tmp_path):
    ds = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=4, ry=3, rz=5,
                                 n_views=60, mm_per_px=0.05, width=200, height=200)
    out = tmp_path / "gem.stl"
    rc = main(["reconstruct", ds, "-o", str(out)])
    assert rc == 0
    assert os.path.exists(out)
