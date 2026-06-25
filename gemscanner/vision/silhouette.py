# gemscanner/vision/silhouette.py
import numpy as np
import cv2


def extract_silhouette(image, threshold=None, holder_mask_rows=0):
    """Return a bool mask (True = object). Backlit: object is darker than background."""
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if threshold is None:
        _, binimg = cv2.threshold(image, 0, 255,
                                  cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        _, binimg = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY_INV)
    mask = binimg > 0
    if holder_mask_rows > 0:
        mask[-holder_mask_rows:, :] = False
    return _largest_component(mask)


def _largest_component(mask):
    m = mask.astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if num <= 1:
        return mask
    areas = stats[1:, cv2.CC_STAT_AREA]
    largest = 1 + int(np.argmax(areas))
    return labels == largest


def row_spans(mask):
    """(H,2) int array of [left, right] foreground columns per row; [-1,-1] if empty."""
    h = mask.shape[0]
    spans = np.full((h, 2), -1, dtype=int)
    for v in range(h):
        cols = np.where(mask[v])[0]
        if cols.size:
            spans[v] = (cols[0], cols[-1])
    return spans
