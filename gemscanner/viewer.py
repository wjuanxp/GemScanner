import numpy as np


def trimesh_to_open3d(mesh):
    import open3d as o3d
    m = o3d.geometry.TriangleMesh()
    m.vertices = o3d.utility.Vector3dVector(np.asarray(mesh.vertices, float))
    m.triangles = o3d.utility.Vector3iVector(np.asarray(mesh.faces, np.int32))
    m.compute_vertex_normals()
    return m


def show_mesh(mesh_or_path):
    import trimesh
    import open3d as o3d
    mesh = mesh_or_path if hasattr(mesh_or_path, "vertices") else trimesh.load(mesh_or_path)
    o3d.visualization.draw_geometries([trimesh_to_open3d(mesh)])
