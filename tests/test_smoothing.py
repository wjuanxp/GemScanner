import trimesh
from gemscanner.smoothing import smooth_mesh


def test_zero_iterations_is_noop():
    box = trimesh.creation.box(extents=(2, 2, 2))
    out = smooth_mesh(box, 0)
    assert out is box
    assert smooth_mesh(box, None) is box


def test_taubin_preserves_topology_and_scale():
    # an icosphere is smooth already; Taubin should keep vertex/face counts,
    # stay watertight, and barely change extents (no Laplacian-style shrink)
    sphere = trimesh.creation.icosphere(subdivisions=3, radius=5.0)
    out = smooth_mesh(sphere, 10)
    assert len(out.vertices) == len(sphere.vertices)
    assert len(out.faces) == len(sphere.faces)
    assert out.is_watertight
    for a, b in zip(out.extents, sphere.extents):
        assert abs(a - b) < 0.2   # < 4% on a radius-5 sphere
