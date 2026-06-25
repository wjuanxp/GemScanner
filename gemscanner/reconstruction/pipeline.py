from gemscanner.storage.dataset import load_dataset
from gemscanner.reconstruction.strip_intersection import StripIntersectionReconstructor
from gemscanner.reconstruction.base import ReconstructionParams


def reconstruct_dataset(dataset_path, params=None):
    dataset = load_dataset(dataset_path)
    params = params if params is not None else ReconstructionParams()
    return StripIntersectionReconstructor().reconstruct(dataset, params)
