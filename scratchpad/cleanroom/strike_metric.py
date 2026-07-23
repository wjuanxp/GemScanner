import numpy as np
from scipy.ndimage import median_filter


def strike_energy(mesh, n_azimuth=48, n_z=300, r_max=20.0, hp_rows=9):
    """Cast outward horizontal rays on a grid of (azimuth, z); record hit
    radius r(z); high-pass along z (r - median_filter) and RMS. Averaged over
    azimuths. A clean faceted polytope -> ~0; per-z-row noise -> elevated."""
    zmin, zmax = mesh.bounds[0, 2], mesh.bounds[1, 2]
    zs = np.linspace(zmin + 1e-3, zmax - 1e-3, n_z)
    phis = np.linspace(0, 2*np.pi, n_azimuth, endpoint=False)
    energies = []
    for phi in phis:
        d = np.array([np.cos(phi), np.sin(phi), 0.0])
        origins = np.column_stack([np.zeros(n_z), np.zeros(n_z), zs])
        dirs = np.tile(d, (n_z, 1))
        locs, idx_ray, _ = mesh.ray.intersects_location(origins, dirs,
                                                        multiple_hits=True)
        r = np.full(n_z, np.nan)
        for j in range(n_z):
            hits = locs[idx_ray == j]
            if len(hits):
                r[j] = np.max(np.hypot(hits[:, 0], hits[:, 1]))
        good = np.isfinite(r)
        if good.sum() < hp_rows + 2:
            continue
        rr = r.copy()
        rr[~good] = np.interp(np.flatnonzero(~good), np.flatnonzero(good), r[good])
        hp = rr - median_filter(rr, size=hp_rows)
        energies.append(np.sqrt(np.mean(hp[good]**2)) * 1000.0)  # µm
    return float(np.mean(energies)) if energies else float("nan")
