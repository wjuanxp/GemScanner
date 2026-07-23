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


def test_reconstruct_subpixel_edges_flag_reaches_the_reconstructor(monkeypatch, tmp_path):
    seen = {}

    def fake(dataset_path, params=None):
        seen["subpixel"] = params.subpixel_edges
        import trimesh
        return trimesh.creation.box((1, 1, 1))

    monkeypatch.setattr("gemscanner.cli.reconstruct_dataset", fake)
    main(["reconstruct", "ds", "-o", str(tmp_path / "x.stl"), "--subpixel-edges"])
    assert seen["subpixel"] is True


def test_reconstruct_defaults_to_subpixel_edges(monkeypatch, tmp_path):
    seen = {}

    def fake(dataset_path, params=None):
        seen["subpixel"] = params.subpixel_edges
        import trimesh
        return trimesh.creation.box((1, 1, 1))

    monkeypatch.setattr("gemscanner.cli.reconstruct_dataset", fake)
    main(["reconstruct", "ds", "-o", str(tmp_path / "y.stl")])
    assert seen["subpixel"] is True


def test_reconstruct_no_subpixel_edges_flag_disables(monkeypatch, tmp_path):
    seen = {}

    def fake(dataset_path, params=None):
        seen["subpixel"] = params.subpixel_edges
        import trimesh
        return trimesh.creation.box((1, 1, 1))

    monkeypatch.setattr("gemscanner.cli.reconstruct_dataset", fake)
    main(["reconstruct", "ds", "-o", str(tmp_path / "z.stl"), "--no-subpixel-edges"])
    assert seen["subpixel"] is False


def _capture_params(monkeypatch):
    seen = {}

    def fake(dataset_path, params=None):
        seen["params"] = params
        import trimesh
        return trimesh.creation.box((1, 1, 1))

    monkeypatch.setattr("gemscanner.cli.reconstruct_dataset", fake)
    return seen


def test_reconstruct_method_flag_reaches_the_reconstructor(monkeypatch, tmp_path):
    seen = _capture_params(monkeypatch)
    main(["reconstruct", "ds", "-o", str(tmp_path / "x.stl"), "--method", "facet"])
    assert seen["params"].method == "facet"


def test_reconstruct_defaults_to_strip_method(monkeypatch, tmp_path):
    seen = _capture_params(monkeypatch)
    main(["reconstruct", "ds", "-o", str(tmp_path / "y.stl")])
    assert seen["params"].method == "strip"


def test_reconstruct_rejects_unknown_method(tmp_path):
    import pytest
    with pytest.raises(SystemExit):
        main(["reconstruct", "ds", "-o", str(tmp_path / "z.stl"),
              "--method", "bogus"])


def test_reconstruct_holder_mask_rows_flag_reaches_the_reconstructor(monkeypatch, tmp_path):
    seen = _capture_params(monkeypatch)
    main(["reconstruct", "ds", "-o", str(tmp_path / "x.stl"),
          "--holder-mask-rows", "705"])
    assert seen["params"].holder_mask_rows == 705


def test_reconstruct_defaults_to_zero_holder_mask_rows(monkeypatch, tmp_path):
    seen = _capture_params(monkeypatch)
    main(["reconstruct", "ds", "-o", str(tmp_path / "y.stl")])
    assert seen["params"].holder_mask_rows == 0
