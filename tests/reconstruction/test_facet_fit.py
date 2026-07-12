import numpy as np
from gemscanner.reconstruction.facet_fit import plane_from_affine, fit_affine_support, seed_facets, segment_support, cluster_segments
from gemscanner.synthetic.toy_gem import make_toy_gem
import trimesh

def test_plane_from_affine_vertical_facet():
    # alpha=0 => vertical facet (c=0); theta*=0 => normal +x
    a, b, c, d = plane_from_affine(0.0, alpha=0.0, beta=5.0)
    assert np.allclose([a, b, c, d], [1.0, 0.0, 0.0, 5.0], atol=1e-9)

def test_plane_from_affine_45deg():
    # a 45-degree facet facing +x: normal ~ (cos45,0,sin45) with c>0 => alpha<0
    a, b, c, d = plane_from_affine(0.0, alpha=-1.0, beta=3.0)
    assert np.allclose([a, b, c], [np.sqrt(0.5), 0.0, np.sqrt(0.5)], atol=1e-9)
    assert np.isclose(a*a + b*b + c*c, 1.0)
    # d = beta*m with m=1/sqrt(1+alpha^2)=1/sqrt(2); verifies the d-scaling (m!=1 here)
    assert np.isclose(d, 3.0 / np.sqrt(2.0))

def test_fit_affine_robust_to_outliers():
    z = np.linspace(-4, 4, 60)
    h = 2.0 + 0.5 * z
    h[10] += 3.0; h[40] -= 2.5           # terracing-style outliers
    mask = np.ones_like(z, bool)
    alpha, beta, rms, n = fit_affine_support(z, h, mask)
    assert abs(alpha - 0.5) < 0.02 and abs(beta - 2.0) < 0.05
    assert n >= 50
    assert rms < 0.01

def test_seed_facets_recovers_distinct_orientations():
    verts, planes = make_toy_gem(n=8)
    hull = trimesh.Trimesh(vertices=verts).convex_hull
    seeds = seed_facets(hull, merge_deg=8.0)
    # ~ table(1) + girdle(8) + crown(8) + pavilion(8) distinct orientations
    assert 20 <= len(seeds) <= 30
    # a near +z table orientation is present
    assert any(s["normal"][2] > 0.95 for s in seeds)
    # azimuth maps back to the normal's horizontal direction (skip nearly-vertical normals)
    for s in seeds[:5]:
        a, b = s["normal"][0], s["normal"][1]
        horiz_len = np.hypot(a, b)
        if horiz_len > 1e-6:  # only check when horizontal component is significant
            assert abs(np.cos(s["azimuth"]) - a / horiz_len) < 1e-6
            assert abs(np.sin(s["azimuth"]) + b / horiz_len) < 1e-6

def test_segment_support_splits_piecewise_affine():
    # three affine pieces: slopes +1.5, -0.5, -1.2 over z bands of 2mm each
    z = np.linspace(-3, 3, 240)
    h = np.where(z < -1, 4.0 + 1.5 * (z + 1),
        np.where(z < 1, 4.0 - 0.5 * (z + 1), 3.0 - 1.2 * (z - 1)))
    rng = np.random.default_rng(0)
    h = h + rng.normal(0, 0.003, h.size)          # 3um noise
    h[40] += 0.08; h[150] -= 0.06                 # terracing-style outliers
    segs = segment_support(z, h)
    assert len(segs) == 3
    slopes = sorted(s["alpha"] for s in segs)
    assert abs(slopes[0] - (-1.2)) < 0.06
    assert abs(slopes[1] - (-0.5)) < 0.06
    assert abs(slopes[2] - 1.5) < 0.06
    for s in segs:
        assert s["rms"] < 0.01                    # fits are ~noise-level
        assert s["z_hi"] > s["z_lo"]

def test_segment_support_handles_nans_and_tiny_input():
    z = np.linspace(-1, 1, 50)
    h = 2.0 + 0.3 * z
    h[10:20] = np.nan
    segs = segment_support(z, h)
    assert len(segs) >= 1 and abs(segs[0]["alpha"] - 0.3) < 0.05
    assert segment_support(z[:3], h[:3]) == []

def _seg(z_lo, z_hi, alpha, rms=0.005, n=20):
    return {"z_lo": z_lo, "z_hi": z_hi, "alpha": alpha,
            "beta": 0.0, "rms": rms, "n": n}

def test_cluster_segments_chains_across_views_with_wraparound():
    V = 12
    segs = [[] for _ in range(V)]
    # facet A: views 10,11,0,1,2 (wraps), z [0,2]; widest+cleanest at view 0
    for i, (span, rms) in zip([10, 11, 0, 1, 2],
                              [(1.6, .01), (1.8, .008), (2.0, .003),
                               (1.8, .008), (1.6, .01)]):
        segs[i].append(_seg(0.0, span, alpha=-0.5 + 0.01 * i % 3, rms=rms))
    # facet B: views 5,6,7, z [-2,-0.5], different slope
    for i in [5, 6, 7]:
        segs[i].append(_seg(-2.0, -0.5, alpha=1.2, rms=0.005))
    # noise: lone segment in view 3 (chain too short)
    segs[3].append(_seg(0.5, 1.0, alpha=0.9))
    chains = cluster_segments(segs, min_views=3)
    assert len(chains) == 2
    a = next(c for c in chains if c["seg"]["alpha"] < 0)
    b = next(c for c in chains if c["seg"]["alpha"] > 1)
    assert a["view"] == 0                      # max z-span member wins
    assert set(a["views"]) == {10, 11, 0, 1, 2}
    assert set(b["views"]) == {5, 6, 7}

def test_cluster_segments_separates_stacked_facets_same_azimuth():
    # step cut: two tiers at the SAME views, different z bands -> two chains
    V = 6
    segs = [[_seg(-2.0, -0.8, alpha=0.5), _seg(-0.6, 0.8, alpha=-0.9)]
            for _ in range(V)]
    chains = cluster_segments(segs, min_views=3)
    assert len(chains) == 2
    zl = sorted(c["seg"]["z_lo"] for c in chains)
    assert zl[0] == -2.0 and zl[1] == -0.6
