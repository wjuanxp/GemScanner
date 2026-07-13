import numpy as np
import trimesh
from gemscanner.synthetic.toy_gem import make_toy_gem
from gemscanner.synthetic.generator import generate_polyhedron_scan
from gemscanner.storage.dataset import load_dataset
from gemscanner.reconstruction.base import ReconstructionParams
from gemscanner.reconstruction.facet_fit import FacetReconstructor

def _min_normal_error_deg(recovered, gt):
    errs = []
    for nr in recovered:
        c = max(abs(float(np.dot(nr, g))) for g in gt)
        errs.append(np.degrees(np.arccos(min(1.0, c))))
    return np.array(errs)

def test_facet_reconstruction_matches_ground_truth(tmp_path):
    verts, gt_planes = make_toy_gem(n=8)
    gt_normals = [p[0] for p in gt_planes]
    out = generate_polyhedron_scan(str(tmp_path / "gem"), verts, n_views=180,
                                   mm_per_px=0.05, width=500, height=500)
    mesh = FacetReconstructor().reconstruct(load_dataset(out), ReconstructionParams())
    assert mesh.is_watertight
    rec_normals = [p[:3] / np.linalg.norm(p[:3])
                   for p in mesh.metadata["facets"]["planes"]]
    errs = _min_normal_error_deg(rec_normals, gt_normals)
    # every recovered non-axial facet matches some GT facet closely
    assert np.median(errs) < 1.0
    # volume within a few percent of the true solid
    truth = trimesh.Trimesh(vertices=verts).convex_hull
    assert abs(mesh.volume - truth.volume) / truth.volume < 0.05
    # meet-points and edges are populated
    assert len(mesh.metadata["facets"]["vertices"]) >= 6
    assert len(mesh.metadata["facets"]["edges"]) >= 9
    # v2.3: extended azimuth bands + two-scale tiers + girdle-band recovery
    # should reach the full 25-plane toy-gate count (locks in the improvement)
    planes = mesh.metadata["facets"]["planes"]
    assert len(planes) >= 24
    girdle_like = sum(1 for p in planes if abs(p[2]) < 0.1)
    assert girdle_like >= 6
