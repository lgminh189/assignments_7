"""Occupancy-map geometry and reproducible functional-area segmentation."""
from collections import deque
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
import yaml


class OccupancyMap:
    def __init__(self, filename):
        self.path = Path(filename).resolve()
        self.meta = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        if self.meta.get("mode", "trinary") != "trinary":
            raise ValueError("Chỉ hỗ trợ map mode: trinary")
        self.image_path = self.path.parent / self.meta["image"]
        self.image = cv2.imread(str(self.image_path), cv2.IMREAD_GRAYSCALE)
        if self.image is None:
            raise ValueError(f"Không đọc được ảnh: {self.image_path}")
        self.resolution = float(self.meta["resolution"])
        self.origin = tuple(float(v) for v in self.meta["origin"])
        if (len(self.origin) != 3 or not all(math.isfinite(v) for v in self.origin)
                or not math.isfinite(self.resolution) or self.resolution <= 0):
            raise ValueError("Resolution/origin không hợp lệ")
        probability = self.image.astype(float) / 255
        if not self.meta.get("negate", 0):
            probability = 1 - probability
        self.free = probability < float(self.meta["free_thresh"])
        # Padding treats the edge of the image as an obstacle too.
        self.clearance = cv2.distanceTransform(
            np.pad(self.free.astype(np.uint8), 1), cv2.DIST_L2, cv2.DIST_MASK_PRECISE
        )[1:-1, 1:-1] * self.resolution

    def pixel_to_world(self, u, v):
        x = (u + .5) * self.resolution
        y = (self.image.shape[0] - v - .5) * self.resolution
        c, s = math.cos(self.origin[2]), math.sin(self.origin[2])
        return self.origin[0] + c*x - s*y, self.origin[1] + s*x + c*y

    def world_to_pixel(self, x, y):
        dx, dy = x - self.origin[0], y - self.origin[1]
        c, s = math.cos(self.origin[2]), math.sin(self.origin[2])
        return (math.floor((c*dx + s*dy) / self.resolution),
                self.image.shape[0] - 1 - math.floor((-s*dx + c*dy) / self.resolution))

    def safe(self, x, y, clearance):
        if not all(math.isfinite(v) for v in (x, y, clearance)) or clearance <= 0:
            return False
        u, v = self.world_to_pixel(x, y)
        return (0 <= v < self.image.shape[0] and 0 <= u < self.image.shape[1]
                and self.free[v, u] and self.clearance[v, u] >= clearance)

    def fingerprint(self):
        digest = hashlib.sha256(self.image.tobytes())
        digest.update(json.dumps(self.meta, sort_keys=True).encode())
        return digest.hexdigest()


def largest_component(mask):
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=4)
    if n <= 1:
        raise ValueError("Không có vùng trống đủ clearance")
    return labels == (1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])))


def partition(mask, seeds):
    """Multi-source BFS: geodesic Voronoi; cannot cross walls or unknown cells."""
    labels = np.zeros(mask.shape, dtype=np.uint16)
    queue = deque()
    for label, (u, v) in enumerate(seeds, 1):
        if not (0 <= v < mask.shape[0] and 0 <= u < mask.shape[1] and mask[v, u]):
            raise ValueError(f"Seed {label} ngoài vùng đi được")
        if labels[v, u]:
            raise ValueError("Các seed phải khác nhau")
        labels[v, u] = label
        queue.append((u, v))
    while queue:
        u, v = queue.popleft()
        for x, y in ((u-1, v), (u+1, v), (u, v-1), (u, v+1)):
            if 0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and mask[y, x] and not labels[y, x]:
                labels[y, x] = labels[v, u]
                queue.append((x, y))
    return labels


def segment(occupancy, count=3, clearance=.35, seeds=None):
    if not math.isfinite(clearance) or clearance <= 0 or not 3 <= count <= 26:
        raise ValueError("Cần 3–26 vùng và clearance > 0")
    mask = largest_component(occupancy.free & (occupancy.clearance >= clearance))
    if seeds is None:
        # Deterministic farthest-point seeds in the same traversable component.
        v, u = np.unravel_index(np.argmax(np.where(mask, occupancy.clearance, -1)), mask.shape)
        seeds = [(int(u), int(v))]
        yy, xx = np.indices(mask.shape)
        distance = np.full(mask.shape, np.inf)
        for _ in range(count-1):
            u, v = seeds[-1]
            distance = np.minimum(distance, (xx-u)**2 + (yy-v)**2)
            v, u = np.unravel_index(np.argmax(np.where(mask, distance, -1)), mask.shape)
            seeds.append((int(u), int(v)))
    if len(seeds) != count:
        raise ValueError("Số seed phải bằng số vùng")
    labels = partition(mask, seeds)
    regions = []
    for index in range(1, count+1):
        region_mask = labels == index
        if not region_mask.any():
            raise ValueError("Vùng rỗng")
        # Pick an interior point rather than a centroid that may lie in a wall.
        interior = cv2.distanceTransform(np.pad(region_mask.astype(np.uint8), 1),
                                        cv2.DIST_L2, cv2.DIST_MASK_PRECISE)[1:-1, 1:-1]
        v, u = np.unravel_index(np.argmax(interior), labels.shape)
        x, y = occupancy.pixel_to_world(int(u), int(v))
        letter = chr(64+index)
        aliases = [f"vùng {letter}"]
        # Distinct multi-syllable names are easier for Vietnamese ASR than letters.
        aliases.extend({
            "A": ["phòng học", "khu vực một", "vùng một"],
            "B": ["phòng thí nghiệm", "khu vực hai", "vùng hai"],
            "C": ["hành lang", "khu vực ba", "vùng ba"],
        }.get(letter, []))
        for spoken in {"B": ["bê"], "C": ["xê", "cê"]}.get(letter, []):
            aliases.extend([spoken, f"khu vực {spoken}", f"phòng {spoken}", f"vùng {spoken}"])
        regions.append(dict(id=letter, name=f"Khu vực {letter}", aliases=aliases,
                            pixel=[int(u), int(v)], goal=dict(x=x, y=y, yaw=0.0),
                            area_m2=float(region_mask.sum()*occupancy.resolution**2)))
    return labels, regions


def save_segmentation(occupancy, out, count=3, clearance=.35, seeds=None):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    labels, regions = segment(occupancy, count, clearance, seeds)
    import os
    data = dict(frame_id="map", map_yaml=os.path.relpath(occupancy.path, out),
                map_sha256=occupancy.fingerprint(), clearance_m=clearance,
                method="geodesic_voronoi_on_largest_clearance_component", regions=regions)
    (out / "regions.yaml").write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    cv2.imwrite(str(out / "labels.png"), labels)
    preview = cv2.cvtColor(occupancy.image, cv2.COLOR_GRAY2BGR)
    colors = [(80, 190, 70), (220, 140, 50), (80, 90, 230), (190, 70, 160)]
    for i, region in enumerate(regions, 1):
        selected = labels == i
        preview[selected] = (.45*preview[selected] + .55*np.array(colors[(i-1) % len(colors)])).astype(np.uint8)
        u, v = region["pixel"]
        cv2.circle(preview, (u, v), 8, (0, 0, 0), -1)
        cv2.putText(preview, region["id"], (u+12, v), cv2.FONT_HERSHEY_SIMPLEX, .9, (0, 0, 0), 2)
    cv2.imwrite(str(out / "segmented_map.png"), preview)
    return data


def load_regions(filename):
    path = Path(filename).resolve()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("frame_id") != "map" or not data.get("regions"):
        raise ValueError("Cần frame_id: map và danh sách regions")
    occupancy = OccupancyMap(path.parent / data["map_yaml"])
    if data.get("map_sha256") != occupancy.fingerprint():
        raise ValueError("Bản đồ đã thay đổi; hãy tạo lại phân vùng")
    clearance = float(data["clearance_m"])
    component = largest_component(occupancy.free & (occupancy.clearance >= clearance))
    ids = set()
    for region in data["regions"]:
        if not region.get("id") or region["id"] in ids:
            raise ValueError("ID vùng rỗng hoặc trùng")
        ids.add(region["id"])
        goal = region["goal"]
        x, y, yaw = (float(goal[key]) for key in ("x", "y", "yaw"))
        goal.update(x=x, y=y, yaw=yaw)
        if not math.isfinite(yaw) or not occupancy.safe(x, y, clearance):
            raise ValueError(f"Đích không an toàn: {region['id']}")
        u, v = occupancy.world_to_pixel(x, y)
        if not component[v, u]:
            raise ValueError(f"Đích ngoài thành phần liên thông chính: {region['id']}")
    return data
