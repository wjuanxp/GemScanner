# tests/vision/test_silhouette.py
import numpy as np
from gemscanner.vision.silhouette import extract_silhouette, row_spans

def make_image():
    img = np.full((20, 20), 255, dtype=np.uint8)
    img[5:15, 6:14] = 0          # dark rectangle = object
    return img

def test_extract_marks_dark_region():
    mask = extract_silhouette(make_image())
    assert mask[10, 10]            # inside object
    assert not mask[0, 0]          # background

def test_largest_component_drops_specks():
    img = make_image()
    img[1, 1] = 0                  # tiny speck
    mask = extract_silhouette(img)
    assert not mask[1, 1]

def test_row_spans():
    mask = extract_silhouette(make_image())
    spans = row_spans(mask)
    assert tuple(spans[10]) == (6, 13)
    assert tuple(spans[0]) == (-1, -1)

def test_holder_mask_clears_bottom_rows():
    mask = extract_silhouette(make_image(), holder_mask_rows=6)
    assert not mask[14].any()      # row 14 is within bottom 6 rows
