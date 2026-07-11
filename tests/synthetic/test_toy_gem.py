import numpy as np
from gemscanner.synthetic.toy_gem import make_toy_gem, unique_face_planes

def test_toy_gem_has_all_four_facet_families():
    n = 8
    verts, planes = make_toy_gem(n=n)
    normals = np.array([p[0] for p in planes])
    # all normals unit length
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0, atol=1e-6)
    # exactly one horizontal top facet (the table), normal ~ +z
    top = [p for p in planes if p[0][2] > 0.99]
    # n vertical girdle facets (normal z-component ~ 0)
    vertical = [p for p in planes if abs(p[0][2]) < 0.05]
    # n crown facets (tilted up, not the table) and n pavilion facets (tilted down)
    crown = [p for p in planes if 0.05 <= p[0][2] <= 0.99]
    pavilion = [p for p in planes if p[0][2] < -0.05]
    assert len(top) == 1
    assert len(vertical) == n
    assert len(crown) == n
    assert len(pavilion) == n
    # all four families and nothing else: exactly 3n+1 distinct planes
    assert len(planes) == 3 * n + 1

def test_unique_face_planes_dedupes_coplanar_triangles():
    verts, _ = make_toy_gem(n=6)
    import trimesh
    hull = trimesh.Trimesh(vertices=verts).convex_hull
    planes = unique_face_planes(hull)
    # a hexagonal toy gem: 1 table + 6 girdle + 6 crown + 6 pavilion = 19 distinct planes
    assert len(planes) == 19
