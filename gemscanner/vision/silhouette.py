# gemscanner/vision/silhouette.py
import numpy as np
import cv2


def extract_silhouette(image, threshold=None, holder_mask_rows=0):
    """Return a bool mask (True = object). Backlit: object is darker than background."""
    return extract_silhouette_with_threshold(image, threshold, holder_mask_rows)[0]


def extract_silhouette_with_threshold(image, threshold=None, holder_mask_rows=0):
    """``(mask, threshold)`` -- as ``extract_silhouette`` but also reports the
    grey level actually used, which Otsu picks per frame. ``row_spans_subpixel``
    needs it to locate the intensity crossing."""
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if threshold is None:
        t, binimg = cv2.threshold(image, 0, 255,
                                  cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        t, binimg = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY_INV)
    mask = binimg > 0
    if holder_mask_rows > 0:
        mask[-holder_mask_rows:, :] = False
    return _largest_component(mask), float(t)


def _largest_component(mask):
    m = mask.astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if num <= 1:
        return mask.copy()
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


def silhouette_row_spans(image, threshold=None, holder_mask_rows=0, subpixel=False):
    """Extract the silhouette and return its per-row [left, right] edge columns.

    ``subpixel=True`` locates each edge on the intensity crossing (float
    columns) instead of the nearest whole column; see ``row_spans_subpixel``.
    """
    mask, t = extract_silhouette_with_threshold(image, threshold, holder_mask_rows)
    if subpixel:
        return row_spans_subpixel(image, mask, t)
    return row_spans(mask)


def row_spans_subpixel(image, mask, threshold):
    """(H,2) float [left, right] silhouette edges, located to sub-pixel precision.

    ``row_spans`` quantises each edge to the nearest whole column, so two rows
    whose true edges differ by up to a pixel report the same span -- the source
    of the horizontal terracing in the carved hull. Here each edge is instead
    placed where the intensity profile crosses ``threshold``, by linear
    interpolation between the bracketing pair of pixels.

    Rows are left at the integer edge when the crossing cannot be bracketed:
    the object touches the image border, or the outside neighbour is itself
    below threshold (a neighbouring blob the largest-component filter dropped).
    Empty rows stay [-1, -1].
    """
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    img = np.asarray(image, dtype=float)
    spans = row_spans(mask).astype(float)
    t = float(threshold)
    h, w = img.shape
    rows = np.arange(h)
    valid = spans[:, 0] >= 0

    # left edge: outside neighbour above threshold, first object pixel at/below
    li = spans[:, 0].astype(int)
    sel = valid & (li > 0)
    r, c = rows[sel], li[sel]
    out, inn = img[r, c - 1], img[r, c]
    ok = (out > t) & (t >= inn)
    spans[r[ok], 0] = (c[ok] - 1) + (out[ok] - t) / (out[ok] - inn[ok])

    # right edge: mirror image of the above
    ri = spans[:, 1].astype(int)
    sel = valid & (ri < w - 1)
    r, c = rows[sel], ri[sel]
    inn, out = img[r, c], img[r, c + 1]
    ok = (inn <= t) & (t < out)
    spans[r[ok], 1] = c[ok] + (t - inn[ok]) / (out[ok] - inn[ok])

    return spans
