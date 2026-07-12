from gemscanner.synthetic.toy_gem import make_toy_gem
from gemscanner.synthetic.generator import (generate_polyhedron_scan,
                                            generate_ellipsoid_scan)
from gemscanner.reconstruction.base import ReconstructionParams
from gemscanner.reconstruction.pipeline import reconstruct_dataset

def test_pipeline_facet_method(tmp_path):
    verts, _ = make_toy_gem(n=8)
    out = generate_polyhedron_scan(str(tmp_path / "gem"), verts, n_views=180,
                                   mm_per_px=0.05, width=500, height=500)
    mesh = reconstruct_dataset(out, ReconstructionParams(method="facet"))
    assert mesh.is_watertight and "facets" in mesh.metadata

def test_pipeline_facet_falls_back_on_non_faceted(tmp_path):
    # an ellipsoid has no stable facets -> fallback yields a (smooth) mesh, no crash
    out = generate_ellipsoid_scan(str(tmp_path / "ell"), rx=4, ry=4, rz=5,
                                  n_views=60, mm_per_px=0.05, width=400, height=400)
    p = ReconstructionParams(method="facet", facet_fallback=True)
    mesh = reconstruct_dataset(out, p)
    assert mesh.vertices.shape[0] > 0     # produced something instead of raising
