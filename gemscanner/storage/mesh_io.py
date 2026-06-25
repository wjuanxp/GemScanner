def export_mesh(mesh, path):
    """Write a mesh to .stl/.ply/.obj (format inferred from the file extension)."""
    mesh.export(path)
