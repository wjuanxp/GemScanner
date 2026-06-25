# gemscanner/storage/dataset.py
import os
import cv2
from gemscanner.storage.manifest import ScanManifest


class ScanDataset:
    def __init__(self, path, manifest):
        self.path = path
        self.manifest = manifest

    def frame_count(self):
        return len(self.manifest.frame_files)

    def load_frame(self, i):
        full = os.path.join(self.path, self.manifest.frame_files[i])
        img = cv2.imread(full, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise FileNotFoundError(full)
        return img

    def iter_frames(self):
        for i in range(self.frame_count()):
            yield self.manifest.angles_deg[i], self.load_frame(i)


def load_dataset(path):
    manifest = ScanManifest.load(os.path.join(path, "manifest.json"))
    return ScanDataset(path, manifest)
