# Plan A — Reconstruction + Vision Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure-Python heart of the gemstone scanner — silhouette extraction plus Approach-A (per-slice strip-intersection) visual-hull reconstruction with mesh export — validated end-to-end against synthetic silhouette stacks, with zero hardware.

**Architecture:** A telecentric lens gives an orthographic projection, so each image row is a fixed object height and each silhouette is a parallel "slab" in the object's rotating frame. For every row, we intersect the back-projected slabs from all rotation angles (convex-polygon clipping) to get a cross-section, then loft the stack of cross-sections into a watertight mesh. Reconstruction reads only a stored dataset (frames + `manifest.json`), so it is fully decoupled from capture and re-runnable offline. A synthetic ellipsoid generator produces ground-truth datasets for testing.

**Tech Stack:** Python 3.11+, NumPy, OpenCV (`opencv-python`), trimesh, pytest. (Open3D viewer and live UI are Plan C, not here.)

## Global Constraints

- Python **3.11+**; Windows host.
- Dependencies limited to: `numpy`, `opencv-python`, `trimesh`, `pytest`. No Open3D, no Shapely in Plan A.
- Reconstruction reads **only** a dataset folder (`frames/*.png` + `manifest.json`); it never talks to hardware.
- **Frames are registered to the calibrated rotation axis, never re-centered** (off-center support depends on this).
- Backlit convention: **object is dark, background is bright** (silhouette = dark pixels).
- Horizontal pixel↔mm and row↔height mappings live in **one** module (`gemscanner/coords.py`) and are shared by the generator and the reconstructor — never duplicated.
- All geometry in millimeters in the object (gem-fixed) frame.
- Package import root is `gemscanner`; tests live under `tests/` mirroring the package.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `gemscanner/__init__.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: importable `gemscanner` package; `pytest` runnable.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smoke.py
def test_package_imports():
    import gemscanner
    assert gemscanner.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_smoke.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'gemscanner'`)

- [ ] **Step 3: Create the package and config**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "gemscanner"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["numpy", "opencv-python", "trimesh", "pytest"]

[tool.setuptools.packages.find]
include = ["gemscanner*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

```python
# gemscanner/__init__.py
__version__ = "0.1.0"
```

- [ ] **Step 4: Install and run the test to verify it passes**

Run: `pip install -e . && pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git init
git add pyproject.toml gemscanner/__init__.py tests/test_smoke.py
git commit -m "chore: scaffold gemscanner package"
```

---

### Task 2: Coordinate mappings (`coords.py`)

**Files:**
- Create: `gemscanner/coords.py`
- Test: `tests/test_coords.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `row_to_z(v: float, height: int, mm_per_px: float) -> float`
  - `z_to_row(z: float, height: int, mm_per_px: float) -> float`
  - `axis_column_at_row(axis_column: float, axis_tilt_rad: float, v: float, height: int) -> float`
  - `projection_to_column(p_mm: float, axis_col: float, mm_per_px: float) -> float`
  - `column_to_projection(u: float, axis_col: float, mm_per_px: float) -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_coords.py
import math
from gemscanner.coords import (
    row_to_z, z_to_row, axis_column_at_row,
    projection_to_column, column_to_projection,
)

def test_row_z_roundtrip():
    z = row_to_z(120, height=400, mm_per_px=0.05)
    assert math.isclose(z_to_row(z, 400, 0.05), 120, abs_tol=1e-9)

def test_projection_roundtrip():
    u = projection_to_column(1.3, axis_col=199.5, mm_per_px=0.05)
    assert math.isclose(column_to_projection(u, 199.5, 0.05), 1.3, abs_tol=1e-9)

def test_axis_tilt_shifts_columns():
    # zero tilt => constant axis column
    assert axis_column_at_row(199.5, 0.0, v=0, height=400) == 199.5
    # positive tilt => columns shift linearly around vertical center
    v0 = (400 - 1) / 2
    expected = 199.5 + math.tan(0.01) * (10 - v0)
    assert math.isclose(axis_column_at_row(199.5, 0.01, 10, 400), expected, abs_tol=1e-9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_coords.py -v`
Expected: FAIL (`ModuleNotFoundError: gemscanner.coords`)

- [ ] **Step 3: Write the implementation**

```python
# gemscanner/coords.py
import math


def row_to_z(v, height, mm_per_px):
    """Map image row v (0 at top) to object height z in mm (increasing upward)."""
    return (height - 1 - v) * mm_per_px


def z_to_row(z, height, mm_per_px):
    return (height - 1) - z / mm_per_px


def axis_column_at_row(axis_column, axis_tilt_rad, v, height):
    """Rotation-axis pixel column at row v, accounting for small axis tilt."""
    v0 = (height - 1) / 2.0
    return axis_column + math.tan(axis_tilt_rad) * (v - v0)


def projection_to_column(p_mm, axis_col, mm_per_px):
    """Horizontal object coordinate (mm, relative to axis) -> pixel column."""
    return axis_col + p_mm / mm_per_px


def column_to_projection(u, axis_col, mm_per_px):
    """Pixel column -> horizontal object coordinate (mm, relative to axis)."""
    return (u - axis_col) * mm_per_px
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_coords.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gemscanner/coords.py tests/test_coords.py
git commit -m "feat: coordinate mappings between pixels, height, and object mm"
```

---

### Task 3: Convex polygon half-plane clipping (`geometry/halfplane.py`)

**Files:**
- Create: `gemscanner/geometry/__init__.py`
- Create: `gemscanner/geometry/halfplane.py`
- Test: `tests/geometry/test_halfplane.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `clip_convex_polygon(polygon: np.ndarray, normal, offset: float) -> np.ndarray`
  keeps the region where `dot(normal, point) <= offset`; returns an `(M,2)` float array, or an empty `(0,2)` array if fully clipped.

- [ ] **Step 1: Write the failing test**

```python
# tests/geometry/test_halfplane.py
import numpy as np
from gemscanner.geometry.halfplane import clip_convex_polygon

SQUARE = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], dtype=float)

def test_clip_keeps_left_half():
    # keep x <= 0  => normal (1,0), offset 0
    out = clip_convex_polygon(SQUARE, [1.0, 0.0], 0.0)
    assert out[:, 0].max() <= 1e-9
    assert np.isclose(out[:, 0].min(), -1.0)

def test_clip_empty_when_fully_outside():
    out = clip_convex_polygon(SQUARE, [1.0, 0.0], -5.0)
    assert out.shape == (0, 2)

def test_clip_noop_when_fully_inside():
    out = clip_convex_polygon(SQUARE, [1.0, 0.0], 5.0)
    assert len(out) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/geometry/test_halfplane.py -v`
Expected: FAIL (`ModuleNotFoundError: gemscanner.geometry.halfplane`)

- [ ] **Step 3: Write the implementation**

```python
# gemscanner/geometry/__init__.py
```

```python
# gemscanner/geometry/halfplane.py
import numpy as np


def clip_convex_polygon(polygon, normal, offset):
    """Sutherland-Hodgman clip of a convex polygon by a single half-plane.

    Keeps the region where dot(normal, point) <= offset.
    Returns an (M,2) float array, or an empty (0,2) array if fully clipped.
    """
    polygon = np.asarray(polygon, dtype=float)
    if len(polygon) == 0:
        return polygon
    normal = np.asarray(normal, dtype=float)
    result = []
    n = len(polygon)
    for i in range(n):
        cur = polygon[i]
        nxt = polygon[(i + 1) % n]
        cur_in = np.dot(normal, cur) <= offset
        nxt_in = np.dot(normal, nxt) <= offset
        if cur_in:
            result.append(cur)
        if cur_in != nxt_in:
            d = np.dot(normal, nxt - cur)
            if abs(d) > 1e-12:
                t = (offset - np.dot(normal, cur)) / d
                result.append(cur + t * (nxt - cur))
    if not result:
        return np.empty((0, 2), dtype=float)
    return np.array(result, dtype=float)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/geometry/test_halfplane.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gemscanner/geometry/__init__.py gemscanner/geometry/halfplane.py tests/geometry/test_halfplane.py
git commit -m "feat: convex polygon half-plane clipping"
```

---

### Task 4: Polygon helpers (`geometry/polygon.py`)

**Files:**
- Create: `gemscanner/geometry/polygon.py`
- Test: `tests/geometry/test_polygon.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `polygon_area(polygon: np.ndarray) -> float`
  - `polygon_centroid(polygon: np.ndarray) -> np.ndarray` (shape `(2,)`, interior for convex polygons)
  - `ray_radius(polygon: np.ndarray, center, angle: float) -> float` — distance from an interior `center` to the boundary along direction `(cos angle, sin angle)`; returns `0.0` if no forward hit.

- [ ] **Step 1: Write the failing test**

```python
# tests/geometry/test_polygon.py
import math
import numpy as np
from gemscanner.geometry.polygon import polygon_area, polygon_centroid, ray_radius

SQUARE = np.array([[-2, -2], [2, -2], [2, 2], [-2, 2]], dtype=float)

def test_area():
    assert math.isclose(polygon_area(SQUARE), 16.0, abs_tol=1e-9)

def test_centroid():
    c = polygon_centroid(SQUARE)
    assert np.allclose(c, [0.0, 0.0], atol=1e-9)

def test_ray_radius_hits_right_edge():
    r = ray_radius(SQUARE, [0.0, 0.0], 0.0)   # +x direction
    assert math.isclose(r, 2.0, abs_tol=1e-9)

def test_ray_radius_diagonal():
    r = ray_radius(SQUARE, [0.0, 0.0], math.radians(45))
    assert math.isclose(r, 2.0 * math.sqrt(2), abs_tol=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/geometry/test_polygon.py -v`
Expected: FAIL (`ModuleNotFoundError: gemscanner.geometry.polygon`)

- [ ] **Step 3: Write the implementation**

```python
# gemscanner/geometry/polygon.py
import numpy as np


def polygon_area(polygon):
    x = polygon[:, 0]
    y = polygon[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def polygon_centroid(polygon):
    x = polygon[:, 0]
    y = polygon[:, 1]
    x1 = np.roll(x, -1)
    y1 = np.roll(y, -1)
    cross = x * y1 - x1 * y
    a = cross.sum() / 2.0
    if abs(a) < 1e-12:
        return polygon.mean(axis=0)
    cx = ((x + x1) * cross).sum() / (6 * a)
    cy = ((y + y1) * cross).sum() / (6 * a)
    return np.array([cx, cy])


def ray_radius(polygon, center, angle):
    """Distance from interior `center` to the boundary along (cos, sin)."""
    d = np.array([np.cos(angle), np.sin(angle)])
    center = np.asarray(center, dtype=float)
    n = len(polygon)
    best = None
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        e = b - a
        # solve center + t*d = a + s*e  =>  [d | -e] [t, s]^T = a - center
        denom = d[0] * (-e[1]) - d[1] * (-e[0])
        if abs(denom) < 1e-12:
            continue
        diff = a - center
        t = (diff[0] * (-e[1]) - diff[1] * (-e[0])) / denom
        s = (d[0] * diff[1] - d[1] * diff[0]) / denom
        if t >= -1e-9 and -1e-9 <= s <= 1 + 1e-9:
            if best is None or t < best:
                best = t
    return float(best) if best is not None else 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/geometry/test_polygon.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gemscanner/geometry/polygon.py tests/geometry/test_polygon.py
git commit -m "feat: polygon area, centroid, and interior ray-radius helpers"
```

---

### Task 5: Scan manifest (`storage/manifest.py`)

**Files:**
- Create: `gemscanner/storage/__init__.py`
- Create: `gemscanner/storage/manifest.py`
- Test: `tests/storage/test_manifest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ScanManifest` dataclass with fields
  `angles_deg: list[float]`, `mm_per_px: float`, `axis_column: float`,
  `axis_tilt_rad: float = 0.0`, `eccentricity_mm: float | None = None`,
  `image_width: int = 0`, `image_height: int = 0`,
  `frame_files: list[str] = []`, `metadata: dict = {}`;
  methods `save(path)` and classmethod `load(path)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_manifest.py
from gemscanner.storage.manifest import ScanManifest

def test_manifest_roundtrip(tmp_path):
    m = ScanManifest(
        angles_deg=[0.0, 2.0, 4.0], mm_per_px=0.05, axis_column=199.5,
        image_width=400, image_height=400, frame_files=["frames/0000.png"],
        metadata={"shape": "ellipsoid"},
    )
    p = tmp_path / "manifest.json"
    m.save(p)
    loaded = ScanManifest.load(p)
    assert loaded.angles_deg == [0.0, 2.0, 4.0]
    assert loaded.mm_per_px == 0.05
    assert loaded.metadata["shape"] == "ellipsoid"
    assert loaded.axis_tilt_rad == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/storage/test_manifest.py -v`
Expected: FAIL (`ModuleNotFoundError: gemscanner.storage.manifest`)

- [ ] **Step 3: Write the implementation**

```python
# gemscanner/storage/__init__.py
```

```python
# gemscanner/storage/manifest.py
from dataclasses import dataclass, field, asdict
import json


@dataclass
class ScanManifest:
    angles_deg: list
    mm_per_px: float
    axis_column: float
    axis_tilt_rad: float = 0.0
    eccentricity_mm: float = None
    image_width: int = 0
    image_height: int = 0
    frame_files: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/storage/test_manifest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gemscanner/storage/__init__.py gemscanner/storage/manifest.py tests/storage/test_manifest.py
git commit -m "feat: ScanManifest load/save"
```

---

### Task 6: Synthetic ellipsoid scan generator (`synthetic/generator.py`)

**Files:**
- Create: `gemscanner/synthetic/__init__.py`
- Create: `gemscanner/synthetic/generator.py`
- Test: `tests/synthetic/test_generator.py`

**Interfaces:**
- Consumes: `coords.projection_to_column`, `storage.manifest.ScanManifest`.
- Produces: `generate_ellipsoid_scan(out_dir, rx, ry, rz, n_views=180, mm_per_px=0.05, width=400, height=400, center_offset=(0.0, 0.0)) -> str` (returns `out_dir`). Writes `out_dir/frames/NNNN.png` (dark ellipsoid silhouette on bright background) and `out_dir/manifest.json`. Ground-truth `rx, ry, rz, center_offset` are stored in `manifest.metadata`.

- [ ] **Step 1: Write the failing test**

```python
# tests/synthetic/test_generator.py
import os
import numpy as np
import cv2
from gemscanner.synthetic.generator import generate_ellipsoid_scan
from gemscanner.storage.manifest import ScanManifest

def test_generates_frames_and_manifest(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=4, ry=3, rz=5,
                                  n_views=18, mm_per_px=0.05, width=400, height=400)
    m = ScanManifest.load(os.path.join(out, "manifest.json"))
    assert len(m.frame_files) == 18
    assert m.metadata["rx"] == 4
    img = cv2.imread(os.path.join(out, m.frame_files[0]), cv2.IMREAD_GRAYSCALE)
    assert img.shape == (400, 400)
    # silhouette is dark on bright background: both extremes present
    assert img.min() == 0 and img.max() == 255

def test_widest_view_matches_major_axis(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=5, ry=2, rz=5,
                                  n_views=4, mm_per_px=0.05, width=400, height=400)
    m = ScanManifest.load(os.path.join(out, "manifest.json"))
    img = cv2.imread(os.path.join(out, m.frame_files[0]), cv2.IMREAD_GRAYSCALE)  # theta=0
    dark_cols = np.where((img == 0).any(axis=0))[0]
    width_px = dark_cols[-1] - dark_cols[0] + 1
    # theta=0 view shows full 2*rx width => 2*5 / 0.05 = 200 px (within rounding)
    assert abs(width_px - 200) <= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/synthetic/test_generator.py -v`
Expected: FAIL (`ModuleNotFoundError: gemscanner.synthetic.generator`)

- [ ] **Step 3: Write the implementation**

```python
# gemscanner/synthetic/__init__.py
```

```python
# gemscanner/synthetic/generator.py
import os
import math
import numpy as np
import cv2
from gemscanner.coords import projection_to_column
from gemscanner.storage.manifest import ScanManifest


def generate_ellipsoid_scan(out_dir, rx, ry, rz, n_views=180, mm_per_px=0.05,
                            width=400, height=400, center_offset=(0.0, 0.0)):
    """Render orthographic silhouettes of an ellipsoid rotating about the vertical
    axis. The ellipsoid center sits at object-frame (cx, cy) and rotates with the
    object (eccentric placement). Background is bright (255), silhouette dark (0)."""
    os.makedirs(os.path.join(out_dir, "frames"), exist_ok=True)
    axis_column = (width - 1) / 2.0
    v0 = (height - 1) / 2.0
    cx, cy = center_offset
    angles = [i * 360.0 / n_views for i in range(n_views)]
    frame_files = []
    for i, ang in enumerate(angles):
        th = math.radians(ang)
        img = np.full((height, width), 255, dtype=np.uint8)
        p_c = cx * math.cos(th) - cy * math.sin(th)        # projected center swing
        for v in range(height):
            z = (v0 - v) * mm_per_px
            if abs(z) >= rz:
                continue
            s = math.sqrt(max(0.0, 1.0 - (z / rz) ** 2))
            half = s * math.sqrt((rx * math.cos(th)) ** 2 + (ry * math.sin(th)) ** 2)
            left = projection_to_column(p_c - half, axis_column, mm_per_px)
            right = projection_to_column(p_c + half, axis_column, mm_per_px)
            lo = max(0, int(math.ceil(left)))
            hi = min(width - 1, int(math.floor(right)))
            if hi >= lo:
                img[v, lo:hi + 1] = 0
        fname = f"{i:04d}.png"
        cv2.imwrite(os.path.join(out_dir, "frames", fname), img)
        frame_files.append(f"frames/{fname}")
    manifest = ScanManifest(
        angles_deg=angles, mm_per_px=mm_per_px, axis_column=axis_column,
        axis_tilt_rad=0.0, image_width=width, image_height=height,
        frame_files=frame_files,
        metadata={"shape": "ellipsoid", "rx": rx, "ry": ry, "rz": rz,
                  "center_offset": [cx, cy]},
    )
    manifest.save(os.path.join(out_dir, "manifest.json"))
    return out_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/synthetic/test_generator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gemscanner/synthetic/__init__.py gemscanner/synthetic/generator.py tests/synthetic/test_generator.py
git commit -m "feat: synthetic ellipsoid silhouette scan generator"
```

---

### Task 7: Silhouette extraction (`vision/silhouette.py`)

**Files:**
- Create: `gemscanner/vision/__init__.py`
- Create: `gemscanner/vision/silhouette.py`
- Test: `tests/vision/test_silhouette.py`

**Interfaces:**
- Consumes: nothing (operates on a grayscale `np.ndarray`).
- Produces:
  - `extract_silhouette(image, threshold=None, holder_mask_rows=0) -> np.ndarray` (bool mask, `True` = object). Backlit convention: object is darker; uses Otsu when `threshold is None`. Keeps only the largest connected component. `holder_mask_rows` forces the bottom N rows to background.
  - `row_spans(mask) -> np.ndarray` shape `(H, 2)` int array of `[left, right]` foreground columns per row; `[-1, -1]` for empty rows.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/vision/test_silhouette.py -v`
Expected: FAIL (`ModuleNotFoundError: gemscanner.vision.silhouette`)

- [ ] **Step 3: Write the implementation**

```python
# gemscanner/vision/__init__.py
```

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/vision/test_silhouette.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gemscanner/vision/__init__.py gemscanner/vision/silhouette.py tests/vision/test_silhouette.py
git commit -m "feat: silhouette extraction and per-row spans"
```

---

### Task 8: Dataset loader (`storage/dataset.py`)

**Files:**
- Create: `gemscanner/storage/dataset.py`
- Test: `tests/storage/test_dataset.py`

**Interfaces:**
- Consumes: `storage.manifest.ScanManifest`.
- Produces:
  - `ScanDataset` with `.path`, `.manifest`, `frame_count() -> int`, `load_frame(i) -> np.ndarray` (grayscale), `iter_frames() -> Iterator[tuple[float, np.ndarray]]` yielding `(angle_deg, image)`.
  - `load_dataset(path) -> ScanDataset`.

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_dataset.py
from gemscanner.synthetic.generator import generate_ellipsoid_scan
from gemscanner.storage.dataset import load_dataset

def test_load_and_iterate(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=4, ry=3, rz=5,
                                  n_views=6, mm_per_px=0.05, width=200, height=200)
    ds = load_dataset(out)
    assert ds.frame_count() == 6
    frames = list(ds.iter_frames())
    assert len(frames) == 6
    angle, img = frames[0]
    assert angle == 0.0
    assert img.shape == (200, 200)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/storage/test_dataset.py -v`
Expected: FAIL (`ModuleNotFoundError: gemscanner.storage.dataset`)

- [ ] **Step 3: Write the implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/storage/test_dataset.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gemscanner/storage/dataset.py tests/storage/test_dataset.py
git commit -m "feat: scan dataset loader"
```

---

### Task 9: Reconstruction params & slice dataclasses (`reconstruction/base.py`)

**Files:**
- Create: `gemscanner/reconstruction/__init__.py`
- Create: `gemscanner/reconstruction/base.py`
- Test: `tests/reconstruction/test_base.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ReconstructionParams` dataclass: `n_radial: int = 180`, `holder_mask_rows: int = 0`, `threshold: int | None = None`, `bbox_mm: float = 50.0`.
  - `SliceResult` dataclass: `z_mm: float`, `polygon: np.ndarray | None = None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/reconstruction/test_base.py
from gemscanner.reconstruction.base import ReconstructionParams, SliceResult

def test_defaults():
    p = ReconstructionParams()
    assert p.n_radial == 180
    assert p.bbox_mm == 50.0
    s = SliceResult(z_mm=1.5)
    assert s.z_mm == 1.5
    assert s.polygon is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reconstruction/test_base.py -v`
Expected: FAIL (`ModuleNotFoundError: gemscanner.reconstruction.base`)

- [ ] **Step 3: Write the implementation**

```python
# gemscanner/reconstruction/__init__.py
```

```python
# gemscanner/reconstruction/base.py
from dataclasses import dataclass


@dataclass
class ReconstructionParams:
    n_radial: int = 180
    holder_mask_rows: int = 0
    threshold: int = None
    bbox_mm: float = 50.0


@dataclass
class SliceResult:
    z_mm: float
    polygon: object = None     # np.ndarray (N,2) in object-frame mm, or None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reconstruction/test_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gemscanner/reconstruction/__init__.py gemscanner/reconstruction/base.py tests/reconstruction/test_base.py
git commit -m "feat: reconstruction params and slice result types"
```

---

### Task 10: Strip-intersection cross-sections (`reconstruction/strip_intersection.py`)

**Files:**
- Create: `gemscanner/reconstruction/strip_intersection.py`
- Test: `tests/reconstruction/test_strip_intersection.py`

**Interfaces:**
- Consumes: `coords.{row_to_z, axis_column_at_row, column_to_projection}`, `vision.silhouette.{extract_silhouette, row_spans}`, `geometry.halfplane.clip_convex_polygon`, `reconstruction.base.{ReconstructionParams, SliceResult}`, `storage.dataset.ScanDataset`.
- Produces:
  - `StripIntersectionReconstructor` with
    `slice_cross_sections(dataset, params=None) -> list[SliceResult]` and
    `reconstruct(dataset, params=None) -> trimesh.Trimesh` (delegates to `mesh.loft_slices_to_mesh`, built in Task 11).

**Math:** For frame `i` at angle θ, the slab normal is `n = (cos θ, -sin θ)`. A foreground span `[L, R]` at row `v` maps to object-frame projection bounds `pmin = column_to_projection(L, axis_col_v)`, `pmax = column_to_projection(R, axis_col_v)`. The cross-section is `{p : pmin_i ≤ n_i·p ≤ pmax_i for all i}` — start from a `bbox_mm` square and clip by each pair of half-planes. If **any** frame has no foreground at row `v`, the object does not reach that height → the slice is empty.

- [ ] **Step 1: Write the failing test**

```python
# tests/reconstruction/test_strip_intersection.py
import numpy as np
from gemscanner.synthetic.generator import generate_ellipsoid_scan
from gemscanner.storage.dataset import load_dataset
from gemscanner.reconstruction.strip_intersection import StripIntersectionReconstructor
from gemscanner.geometry.polygon import polygon_area

def test_midplane_cross_section_matches_ellipse_area(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=4, ry=3, rz=5,
                                  n_views=180, mm_per_px=0.05, width=400, height=400)
    ds = load_dataset(out)
    slices = StripIntersectionReconstructor().slice_cross_sections(ds)
    # mid-height slice (z ~ 0) should approximate the equatorial ellipse pi*rx*ry
    mids = [s for s in slices if s.polygon is not None and abs(s.z_mm) < 0.05]
    assert mids, "expected a near-equatorial non-empty slice"
    area = polygon_area(mids[0].polygon)
    assert abs(area - np.pi * 4 * 3) < 1.0     # within 1 mm^2

def test_slices_empty_above_top(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=4, ry=3, rz=5,
                                  n_views=60, mm_per_px=0.05, width=400, height=400)
    ds = load_dataset(out)
    slices = StripIntersectionReconstructor().slice_cross_sections(ds)
    tops = [s for s in slices if s.z_mm > 5.2]
    assert all(s.polygon is None for s in tops)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reconstruction/test_strip_intersection.py -v`
Expected: FAIL (`ModuleNotFoundError: gemscanner.reconstruction.strip_intersection`)

- [ ] **Step 3: Write the implementation**

```python
# gemscanner/reconstruction/strip_intersection.py
import math
import numpy as np
from gemscanner.coords import row_to_z, axis_column_at_row, column_to_projection
from gemscanner.vision.silhouette import extract_silhouette, row_spans
from gemscanner.geometry.halfplane import clip_convex_polygon
from gemscanner.reconstruction.base import ReconstructionParams, SliceResult


class StripIntersectionReconstructor:
    def slice_cross_sections(self, dataset, params=None):
        params = params or ReconstructionParams()
        m = dataset.manifest
        H = m.image_height
        mmpp = m.mm_per_px

        frames = []
        for i in range(dataset.frame_count()):
            img = dataset.load_frame(i)
            mask = extract_silhouette(img, params.threshold, params.holder_mask_rows)
            spans = row_spans(mask)
            th = math.radians(m.angles_deg[i])
            normal = np.array([math.cos(th), -math.sin(th)])
            frames.append((spans, normal))

        slices = []
        for v in range(H):
            z = row_to_z(v, H, mmpp)
            axis_col = axis_column_at_row(m.axis_column, m.axis_tilt_rad, v, H)
            b = params.bbox_mm
            poly = np.array([[-b, -b], [b, -b], [b, b], [-b, b]], dtype=float)
            empty = False
            for spans, normal in frames:
                L, R = spans[v]
                if L < 0:
                    empty = True
                    break
                pmin = column_to_projection(L, axis_col, mmpp)
                pmax = column_to_projection(R, axis_col, mmpp)
                poly = clip_convex_polygon(poly, normal, pmax)
                if len(poly) == 0:
                    empty = True
                    break
                poly = clip_convex_polygon(poly, -normal, -pmin)
                if len(poly) == 0:
                    empty = True
                    break
            if empty or len(poly) < 3:
                slices.append(SliceResult(z, None))
            else:
                slices.append(SliceResult(z, poly))
        return slices

    def reconstruct(self, dataset, params=None):
        from gemscanner.reconstruction.mesh import loft_slices_to_mesh
        params = params or ReconstructionParams()
        slices = self.slice_cross_sections(dataset, params)
        return loft_slices_to_mesh(slices, params.n_radial)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reconstruction/test_strip_intersection.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gemscanner/reconstruction/strip_intersection.py tests/reconstruction/test_strip_intersection.py
git commit -m "feat: per-slice strip-intersection cross-sections"
```

---

### Task 11: Loft slices into a mesh (`reconstruction/mesh.py`)

**Files:**
- Create: `gemscanner/reconstruction/mesh.py`
- Test: `tests/reconstruction/test_mesh.py`

**Interfaces:**
- Consumes: `geometry.polygon.{polygon_centroid, polygon_area, ray_radius}`, `reconstruction.base.SliceResult`, `trimesh`.
- Produces: `loft_slices_to_mesh(slices: list[SliceResult], n_radial=180) -> trimesh.Trimesh`. Keeps the largest contiguous run of non-empty slices, radially resamples each slice around its centroid into `n_radial` ring points, connects adjacent rings into side triangles, and caps top and bottom with centroid fans. Raises `ValueError` if fewer than two non-empty slices.

- [ ] **Step 1: Write the failing test**

```python
# tests/reconstruction/test_mesh.py
import numpy as np
import pytest
from gemscanner.reconstruction.base import SliceResult
from gemscanner.reconstruction.mesh import loft_slices_to_mesh

def square(half):
    return np.array([[-half, -half], [half, -half], [half, half], [-half, half]], float)

def test_lofts_watertight_box():
    slices = [SliceResult(z_mm=z, polygon=square(2.0)) for z in (0.0, 1.0, 2.0)]
    mesh = loft_slices_to_mesh(slices, n_radial=64)
    assert mesh.is_watertight
    assert mesh.volume > 0
    ext = mesh.bounding_box.extents
    assert abs(ext[0] - 4.0) < 0.2 and abs(ext[1] - 4.0) < 0.2
    assert abs(ext[2] - 2.0) < 1e-6

def test_raises_with_too_few_slices():
    with pytest.raises(ValueError):
        loft_slices_to_mesh([SliceResult(z_mm=0.0, polygon=square(2.0))])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reconstruction/test_mesh.py -v`
Expected: FAIL (`ModuleNotFoundError: gemscanner.reconstruction.mesh`)

- [ ] **Step 3: Write the implementation**

```python
# gemscanner/reconstruction/mesh.py
import numpy as np
import trimesh
from gemscanner.geometry.polygon import polygon_centroid, polygon_area, ray_radius


def _largest_contiguous(slices):
    best = (0, 0)
    cur_start = None
    for i, s in enumerate(slices):
        if s.polygon is not None and polygon_area(s.polygon) > 1e-9:
            if cur_start is None:
                cur_start = i
            if i - cur_start + 1 > best[1] - best[0]:
                best = (cur_start, i + 1)
        else:
            cur_start = None
    return slices[best[0]:best[1]]


def loft_slices_to_mesh(slices, n_radial=180):
    run = _largest_contiguous(slices)
    if len(run) < 2:
        raise ValueError("need at least two non-empty slices to build a mesh")

    angles = np.linspace(0, 2 * np.pi, n_radial, endpoint=False)
    rings = []
    for s in run:
        c = polygon_centroid(s.polygon)
        pts = np.array([
            c + ray_radius(s.polygon, c, a) * np.array([np.cos(a), np.sin(a)])
            for a in angles
        ])
        rings.append(np.column_stack([pts[:, 0], pts[:, 1],
                                      np.full(n_radial, s.z_mm)]))
    rings = np.array(rings)               # (M, n_radial, 3)
    M = len(rings)
    vertices = rings.reshape(-1, 3)

    faces = []
    for k in range(M - 1):
        for j in range(n_radial):
            j2 = (j + 1) % n_radial
            a = k * n_radial + j
            b = k * n_radial + j2
            c = (k + 1) * n_radial + j
            d = (k + 1) * n_radial + j2
            faces.append([a, b, d])
            faces.append([a, d, c])

    bottom_c = len(vertices)
    top_c = bottom_c + 1
    bottom_center = np.array([rings[0, :, 0].mean(), rings[0, :, 1].mean(),
                              rings[0, 0, 2]])
    top_center = np.array([rings[-1, :, 0].mean(), rings[-1, :, 1].mean(),
                           rings[-1, 0, 2]])
    vertices = np.vstack([vertices, bottom_center, top_center])

    base = (M - 1) * n_radial
    for j in range(n_radial):
        j2 = (j + 1) % n_radial
        faces.append([bottom_c, j2, j])               # bottom cap
        faces.append([top_c, base + j, base + j2])    # top cap

    mesh = trimesh.Trimesh(vertices=vertices, faces=np.array(faces), process=True)
    mesh.fix_normals()
    return mesh
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reconstruction/test_mesh.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gemscanner/reconstruction/mesh.py tests/reconstruction/test_mesh.py
git commit -m "feat: loft slice cross-sections into a watertight mesh"
```

---

### Task 12: Pipeline + mesh export (`reconstruction/pipeline.py`, `storage/mesh_io.py`)

**Files:**
- Create: `gemscanner/storage/mesh_io.py`
- Create: `gemscanner/reconstruction/pipeline.py`
- Test: `tests/storage/test_mesh_io.py`
- Test: `tests/reconstruction/test_pipeline.py`

**Interfaces:**
- Consumes: `storage.dataset.load_dataset`, `reconstruction.strip_intersection.StripIntersectionReconstructor`, `reconstruction.base.ReconstructionParams`, `trimesh`.
- Produces:
  - `export_mesh(mesh, path)` — writes `.stl` / `.ply` / `.obj` by extension.
  - `reconstruct_dataset(dataset_path, params=None) -> trimesh.Trimesh`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/storage/test_mesh_io.py
import os
import trimesh
from gemscanner.storage.mesh_io import export_mesh

def test_export_stl(tmp_path):
    mesh = trimesh.creation.box(extents=(2, 2, 2))
    out = tmp_path / "box.stl"
    export_mesh(mesh, str(out))
    assert os.path.exists(out)
    reloaded = trimesh.load(str(out))
    assert reloaded.is_watertight
```

```python
# tests/reconstruction/test_pipeline.py
from gemscanner.synthetic.generator import generate_ellipsoid_scan
from gemscanner.reconstruction.pipeline import reconstruct_dataset

def test_reconstruct_dataset_returns_mesh(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=4, ry=3, rz=5,
                                  n_views=120, mm_per_px=0.05, width=400, height=400)
    mesh = reconstruct_dataset(out)
    assert mesh.is_watertight
    assert mesh.volume > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/storage/test_mesh_io.py tests/reconstruction/test_pipeline.py -v`
Expected: FAIL (`ModuleNotFoundError` for `mesh_io` / `pipeline`)

- [ ] **Step 3: Write the implementations**

```python
# gemscanner/storage/mesh_io.py
def export_mesh(mesh, path):
    """Write a mesh to .stl/.ply/.obj (format inferred from the file extension)."""
    mesh.export(path)
```

```python
# gemscanner/reconstruction/pipeline.py
from gemscanner.storage.dataset import load_dataset
from gemscanner.reconstruction.strip_intersection import StripIntersectionReconstructor
from gemscanner.reconstruction.base import ReconstructionParams


def reconstruct_dataset(dataset_path, params=None):
    dataset = load_dataset(dataset_path)
    params = params or ReconstructionParams()
    return StripIntersectionReconstructor().reconstruct(dataset, params)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/storage/test_mesh_io.py tests/reconstruction/test_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gemscanner/storage/mesh_io.py gemscanner/reconstruction/pipeline.py tests/storage/test_mesh_io.py tests/reconstruction/test_pipeline.py
git commit -m "feat: reconstruction pipeline and mesh export"
```

---

### Task 13: End-to-end accuracy (centered, off-center, asymmetric)

**Files:**
- Test: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: `synthetic.generator.generate_ellipsoid_scan`, `reconstruction.pipeline.reconstruct_dataset`.
- Produces: nothing (verification only). Proves the spec's §9 success criteria for dimensional accuracy, off-center, and asymmetric gems.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_end_to_end.py
import numpy as np
from gemscanner.synthetic.generator import generate_ellipsoid_scan
from gemscanner.reconstruction.pipeline import reconstruct_dataset

TOL = 0.3   # mm; ~6 px at 0.05 mm/px, covers discretization + radial resampling

def _extents(out):
    return reconstruct_dataset(out).bounding_box.extents

def test_centered_dimensions(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "c"), rx=4, ry=3, rz=5,
                                  n_views=180, mm_per_px=0.05, width=400, height=400)
    ext = _extents(out)
    assert abs(ext[0] - 8.0) < TOL
    assert abs(ext[1] - 6.0) < TOL
    assert abs(ext[2] - 10.0) < TOL

def test_off_center_recovers_size_and_offset(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "o"), rx=4, ry=3, rz=5,
                                  n_views=180, mm_per_px=0.05, width=400, height=400,
                                  center_offset=(2.0, 1.0))
    mesh = reconstruct_dataset(out)
    ext = mesh.bounding_box.extents
    assert abs(ext[0] - 8.0) < TOL and abs(ext[1] - 6.0) < TOL
    # reconstruction is in the object frame: center recovered at the offset
    cx, cy, _ = mesh.bounding_box.centroid
    assert abs(cx - 2.0) < TOL and abs(cy - 1.0) < TOL

def test_asymmetric_shape(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "a"), rx=5, ry=2, rz=5,
                                  n_views=180, mm_per_px=0.05, width=400, height=400)
    ext = _extents(out)
    assert abs(ext[0] - 10.0) < TOL
    assert abs(ext[1] - 4.0) < TOL
```

- [ ] **Step 2: Run test to verify it fails (or passes if all prior tasks complete)**

Run: `pytest tests/test_end_to_end.py -v`
Expected: PASS once Tasks 1–12 are implemented. If any assertion fails, debug the responsible module (do **not** loosen `TOL` without cause).

- [ ] **Step 3: Run the full suite**

Run: `pytest -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_end_to_end.py
git commit -m "test: end-to-end reconstruction accuracy for centered, off-center, asymmetric gems"
```

---

## Self-Review

**Spec coverage (against the design spec §4–§9):**
- §4.1 Approach A strip intersection → Tasks 3, 4, 10, 11.
- §4.3 off-center & asymmetric, registered-to-axis (never re-centered) → Task 13 (`test_off_center_*`, `test_asymmetric_shape`); reconstruction works in the object frame with no per-frame recentering.
- §4.2 Approach-B seam → `Reconstructor` is duck-typed (`reconstruct(dataset, params)`); a future `VoxelCarver` implements the same method, consumed by `pipeline.reconstruct_dataset` unchanged.
- §5.3 dataset = frames + `manifest.json` → Tasks 5, 8.
- §7 calibration fields (mm_per_px, axis_column, axis_tilt, eccentricity) live in `ScanManifest` and are consumed by `coords`/`strip_intersection` (Tasks 2, 10).
- Mesh export STL/PLY/OBJ → Task 12.
- **Deferred to Plan C (correctly out of scope here):** real camera backends, motion/ESP32, `ScanController`, pre-scan FoV check, live calibration capture, CLI/Open3D viewer. The `vision.extract_silhouette(holder_mask_rows=…)` hook and `ReconstructionParams.holder_mask_rows` are present so Plan C can supply holder masking without reopening this code.

**Placeholder scan:** No TBD/TODO; every code step contains complete implementations and concrete test assertions.

**Type consistency:** Verified `clip_convex_polygon(polygon, normal, offset)`, `ray_radius(polygon, center, angle)`, `extract_silhouette(image, threshold, holder_mask_rows)`, `row_spans(mask)`, `SliceResult(z_mm, polygon)`, `ReconstructionParams(n_radial, holder_mask_rows, threshold, bbox_mm)`, and `loft_slices_to_mesh(slices, n_radial)` are used with identical names/signatures across producing and consuming tasks. The slab normal `(cos θ, -sin θ)` and the `projection_to_column`/`column_to_projection` pair are shared between the generator (Task 6) and reconstructor (Task 10), guaranteeing the forward/inverse models match.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-24-plan-a-reconstruction-core.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
