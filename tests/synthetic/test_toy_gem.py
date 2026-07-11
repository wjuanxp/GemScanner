import numpy as np
from gemscanner.synthetic.toy_gem import make_toy_gem, unique_face_planes

def test_toy_gem_has_expected_facets():
    n = 8
    verts, planes = make_toy_gem(n=n)
    normals = np.array([p[0] for p in planes])
    # exactly one horizontal top facet (the table), normal ~ +z
    top = [p for p in planes if p[0][2] > 0.99]
    assert len(top) == 1
    # n vertical girdle facets (normal z-component ~ 0)
    vertical = [p for p in planes if abs(p[0][2]) < 0.05]
    assert len(vertical) == n
    # all normals unit length
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0, atol=1e-6)

def test_unique_face_planes_dedupes_coplanar_triangles():
    verts, _ = make_toy_gem(n=6)
    import trimesh
    hull = trimesh.Trimesh(vertices=verts).convex_hull
    planes = unique_face_planes(hull)
    # a hexagonal toy gem: 1 table + 6 girdle + 6 crown + 6 pavilion = 19 distinct planes
    assert 15 <= len(planes) <= 21
