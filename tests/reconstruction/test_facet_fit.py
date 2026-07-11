import numpy as np
from gemscanner.reconstruction.facet_fit import plane_from_affine, fit_affine_support

def test_plane_from_affine_vertical_facet():
    # alpha=0 => vertical facet (c=0); theta*=0 => normal +x
    a, b, c, d = plane_from_affine(0.0, alpha=0.0, beta=5.0)
    assert np.allclose([a, b, c, d], [1.0, 0.0, 0.0, 5.0], atol=1e-9)

def test_plane_from_affine_45deg():
    # a 45-degree facet facing +x: normal ~ (cos45,0,sin45) with c>0 => alpha<0
    a, b, c, d = plane_from_affine(0.0, alpha=-1.0, beta=3.0)
    assert np.allclose([a, b, c], [np.sqrt(0.5), 0.0, np.sqrt(0.5)], atol=1e-9)
    assert np.isclose(a*a + b*b + c*c, 1.0)
    # d = beta*m with m=1/sqrt(1+alpha^2)=1/sqrt(2); verifies the d-scaling (m!=1 here)
    assert np.isclose(d, 3.0 / np.sqrt(2.0))

def test_fit_affine_robust_to_outliers():
    z = np.linspace(-4, 4, 60)
    h = 2.0 + 0.5 * z
    h[10] += 3.0; h[40] -= 2.5           # terracing-style outliers
    mask = np.ones_like(z, bool)
    alpha, beta, rms, n = fit_affine_support(z, h, mask)
    assert abs(alpha - 0.5) < 0.02 and abs(beta - 2.0) < 0.05
    assert n >= 50
    assert rms < 0.01
