import warnings
from gemscanner.storage.dataset import load_dataset
from gemscanner.reconstruction.strip_intersection import StripIntersectionReconstructor
from gemscanner.reconstruction.base import ReconstructionParams


def reconstruct_dataset(dataset_path, params=None):
    dataset = load_dataset(dataset_path)
    params = params if params is not None else ReconstructionParams()
    if params.method == "facet":
        from gemscanner.reconstruction.facet_fit import FacetReconstructor
        try:
            return FacetReconstructor().reconstruct(dataset, params)
        except Exception as exc:
            if not params.facet_fallback:
                raise
            # facet is the highest-quality tier; degrade to the smooth
            # metrology method (soft_hull), and never fail silently so a real
            # regression (or a non-faceted stone) is visible, not masked.
            warnings.warn(f"facet reconstruction failed ({exc}); falling back "
                          "to soft_hull", RuntimeWarning)
            from gemscanner.reconstruction.soft_hull import SoftHullReconstructor
            return SoftHullReconstructor().reconstruct(dataset, params)
    if params.method == "soft_hull":
        from gemscanner.reconstruction.soft_hull import SoftHullReconstructor
        return SoftHullReconstructor().reconstruct(dataset, params)
    return StripIntersectionReconstructor().reconstruct(dataset, params)
