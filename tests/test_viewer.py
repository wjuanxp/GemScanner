import trimesh
from gemscanner.viewer import trimesh_to_open3d


def test_conversion_preserves_counts():
    box = trimesh.creation.box(extents=(2, 2, 2))
    o3d_mesh = trimesh_to_open3d(box)
    assert len(o3d_mesh.vertices) == len(box.vertices)
    assert len(o3d_mesh.triangles) == len(box.faces)
