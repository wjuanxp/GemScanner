# tests/vision/test_silhouette.py
import numpy as np
from gemscanner.vision.silhouette import (extract_silhouette, row_spans,
                                          extract_silhouette_with_threshold,
                                          row_spans_subpixel)

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


# --- sub-pixel edge localisation -------------------------------------------

def _ramp_image():
    """20x20 backlit frame; row 10 has a partially-covered pixel on each edge."""
    img = np.full((20, 20), 200, dtype=np.uint8)
    img[5:15, 6:14] = 0
    img[10, 5] = 50       # left edge pixel, ~2/3 covered -> below a T=100 threshold
    img[10, 14] = 150     # right edge pixel, ~1/4 covered -> above T, stays background
    return img


def test_extract_with_threshold_reports_the_manual_threshold():
    _, t = extract_silhouette_with_threshold(make_image(), threshold=100)
    assert t == 100.0


def test_extract_with_threshold_reports_the_otsu_threshold():
    img = _ramp_image()             # has grey edge pixels, so Otsu is non-degenerate
    mask, t = extract_silhouette_with_threshold(img)
    assert mask[10, 10] and not mask[0, 0]
    assert 0.0 < t < 200.0          # splits the dark object from the bright bg
    assert np.all(img[mask] <= t)   # the reported level reproduces the mask


def test_subpixel_span_interpolates_across_the_threshold():
    img = _ramp_image()
    mask, t = extract_silhouette_with_threshold(img, threshold=100)
    spans = row_spans_subpixel(img, mask, t)
    # left: crossing between col 4 (200) and col 5 (50) -> 4 + (200-100)/(200-50)
    assert abs(spans[10, 0] - (4 + 100.0 / 150.0)) < 1e-9
    # right: crossing between col 13 (0) and col 14 (150) -> 13 + (100-0)/(150-0)
    assert abs(spans[10, 1] - (13 + 100.0 / 150.0)) < 1e-9


def test_subpixel_span_of_a_sharp_step_lands_on_the_pixel_boundary():
    img = make_image()              # hard 255 -> 0 step, object cols 6..13
    mask, _ = extract_silhouette_with_threshold(img, threshold=100)
    spans = row_spans_subpixel(img, mask, 100.0)
    # crossing sits midway between the last bg and first object pixel
    assert abs(spans[10, 0] - 5.607843) < 1e-5
    assert abs(spans[10, 1] - 13.392157) < 1e-5


def test_subpixel_resolves_edges_that_integer_spans_cannot_tell_apart():
    """The anti-terracing property: equal integer spans, different true edges."""
    img = np.full((4, 20), 200, dtype=np.uint8)
    img[1:3, 6:14] = 0
    img[1, 5] = 20                  # row 1 edge pixel nearly fully covered
    img[2, 5] = 90                  # row 2 edge pixel barely covered
    mask, _ = extract_silhouette_with_threshold(img, threshold=100)
    ints = row_spans(mask)
    assert ints[1, 0] == ints[2, 0] == 5           # integer spans identical
    subs = row_spans_subpixel(img, mask, 100.0)
    assert subs[1, 0] < subs[2, 0]                 # sub-pixel tells them apart
    assert abs(subs[2, 0] - subs[1, 0]) > 0.2


def test_subpixel_falls_back_to_the_integer_edge_at_the_image_border():
    img = np.full((4, 10), 200, dtype=np.uint8)
    img[1:3, 0:5] = 0               # object runs off the left border
    mask, _ = extract_silhouette_with_threshold(img, threshold=100)
    spans = row_spans_subpixel(img, mask, 100.0)
    assert spans[1, 0] == 0.0       # no outside pixel to interpolate against


def test_subpixel_leaves_empty_rows_marked_invalid():
    img = _ramp_image()
    mask, t = extract_silhouette_with_threshold(img, threshold=100)
    spans = row_spans_subpixel(img, mask, t)
    assert spans[0, 0] == -1 and spans[0, 1] == -1
