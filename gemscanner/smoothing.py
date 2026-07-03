"""Optional Taubin mesh smoothing.

Reduces the per-slice terracing of the lofted visual hull (adjacent pixel-row
rings differ slightly, giving a layered look) without shrinking the mesh the way
Laplacian smoothing does. A no-op when ``iterations <= 0``. Open3D is imported
lazily so importing this module (and the reconstruction core) stays light.
"""
import numpy as np


def smooth_mesh(mesh, iterations=10):
    """Return a Taubin-smoothed copy of a trimesh ``mesh``.

    ``iterations`` of ``0`` (or less) returns the mesh unchanged. Taubin
    smoothing preserves volume/extents far better than Laplacian; keep the count
    modest (~10) — very high counts can break watertightness.
    """
    if not iterations or iterations <= 0:
        return mesh
    import open3d as o3d
    import trimesh

    om = o3d.geometry.TriangleMesh()
    om.vertices = o3d.utility.Vector3dVector(np.asarray(mesh.vertices, float))
    om.triangles = o3d.utility.Vector3iVector(np.asarray(mesh.faces, np.int32))
    om = om.filter_smooth_taubin(number_of_iterations=int(iterations))
    return trimesh.Trimesh(vertices=np.asarray(om.vertices),
                           faces=np.asarray(om.triangles), process=True)
