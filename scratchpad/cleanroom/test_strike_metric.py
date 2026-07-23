# scratchpad/cleanroom/test_strike_metric.py
import numpy as np
import trimesh
from scratchpad.cleanroom.strike_metric import strike_energy


def _tube_mesh(radius_fn, n_z=200, n_theta=64, z0=-3.0, z1=3.0):
    """Lofted-ring tube: n_z rings of n_theta points, radius r(z). Open ends
    (rays cast from the axis exit through the side wall cleanly)."""
    zs = np.linspace(z0, z1, n_z)
    thetas = np.linspace(0, 2*np.pi, n_theta, endpoint=False)
    verts = []
    for z in zs:
        r = radius_fn(z)
        for t in thetas:
            verts.append([r*np.cos(t), r*np.sin(t), z])
    verts = np.array(verts)
    faces = []
    for i in range(n_z - 1):
        for j in range(n_theta):
            a = i*n_theta + j
            b = i*n_theta + (j+1) % n_theta
            c = (i+1)*n_theta + j
            d = (i+1)*n_theta + (j+1) % n_theta
            faces.append([a, b, d]); faces.append([a, d, c])
    return trimesh.Trimesh(vertices=verts, faces=np.array(faces), process=False)


def test_clean_tube_low_strike_striped_high():
    clean = _tube_mesh(lambda z: 3.0)
    striped = _tube_mesh(lambda z: 3.0 * (1.0 + 0.03*np.sin(z*40.0)))
    e_clean = strike_energy(clean)
    e_striped = strike_energy(striped)
    print(f"e_clean={e_clean:.4f} um  e_striped={e_striped:.4f} um")
    assert e_striped > 5.0 * e_clean + 1.0
