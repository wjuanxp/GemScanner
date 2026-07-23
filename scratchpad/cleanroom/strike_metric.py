# scratchpad/cleanroom/strike_metric.py
import numpy as np


def strike_energy(mesh, n_azimuth=48, n_z=300):
    """Objective strike-line energy (µm) of a reconstructed surface.

    Casts outward horizontal rays from the vertical axis on an (azimuth, z)
    grid and records the surface radius r(z) at each azimuth. Strike-lines
    (independent per-z-row carving noise / terracing) make r(z) jitter from
    row to row, whereas a faceted surface is piecewise-linear in z (each
    facet a straight ramp, flat OR sloped). We measure the discrete second
    difference d2 = r[i-1] - 2 r[i] + r[i+1], which is exactly zero on any
    straight facet, spikes only at the O(#facets) sparse kinks, and is
    pervasive for per-row noise. Aggregating with the MEDIAN of |d2| makes a
    clean faceted stone read ~0 (sparse kinks are ignored by the median)
    while pervasive striping reads high. Returned in µm, averaged over
    azimuths. NaN only if no azimuth yields a usable radius profile."""
    zmin, zmax = mesh.bounds[0, 2], mesh.bounds[1, 2]
    zs = np.linspace(zmin + 1e-3, zmax - 1e-3, n_z)
    phis = np.linspace(0, 2 * np.pi, n_azimuth, endpoint=False)
    energies = []
    for phi in phis:
        d = np.array([np.cos(phi), np.sin(phi), 0.0])
        origins = np.column_stack([np.zeros(n_z), np.zeros(n_z), zs])
        dirs = np.tile(d, (n_z, 1))
        locs, idx_ray, _ = mesh.ray.intersects_location(
            origins, dirs, multiple_hits=True)
        r = np.full(n_z, np.nan)
        for j in range(n_z):
            hits = locs[idx_ray == j]
            if len(hits):
                r[j] = np.max(np.hypot(hits[:, 0], hits[:, 1]))
        good = np.isfinite(r)
        if good.sum() < 5:
            continue
        # restrict to the contiguous span between first and last hit, filling
        # interior gaps by linear interpolation so d2 is well defined
        lo, hi = np.flatnonzero(good)[[0, -1]]
        seg = r[lo:hi + 1].copy()
        gmask = np.isfinite(seg)
        if gmask.sum() < 5:
            continue
        seg[~gmask] = np.interp(np.flatnonzero(~gmask),
                                np.flatnonzero(gmask), seg[gmask])
        d2 = seg[:-2] - 2.0 * seg[1:-1] + seg[2:]
        energies.append(float(np.median(np.abs(d2))) * 1000.0)
    return float(np.mean(energies)) if energies else float("nan")
