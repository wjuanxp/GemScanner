import os
import trimesh
from gemscanner.storage.mesh_io import export_mesh

def test_export_stl(tmp_path):
    mesh = trimesh.creation.box(extents=(2, 2, 2))
    out = tmp_path / "box.stl"
    export_mesh(mesh, str(out))
    assert os.path.exists(out)
    reloaded = trimesh.load(str(out))
    assert reloaded.is_watertight
