import math
from pathlib import Path
import sys
import tempfile
import unittest

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from commands import CommandParser
from map_tools import OccupancyMap, largest_component, load_regions, partition, save_segmentation


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.parser = CommandParser([
            dict(id="A", name="Khu vực A", aliases=["phòng học", "a", "vùng A"]),
            dict(id="B", name="Khu vực B", aliases=["phòng thí nghiệm", "bê"]),
            dict(id="C", name="Hành lang C", aliases=["hành lang", "xê"]),
        ])

    def test_single_commands(self):
        for text, route in [("Đi đến khu vực A.", ["A"]), ("Đi đến phòng thí nghiệm.", ["B"]),
                            ("đến hành lang", ["C"]), ("DI DEN PHONG HOC!", ["A"]),
                            ("Đi đến bê", ["B"])]:
            with self.subTest(text=text):
                self.assertEqual(self.parser.parse(text), route)

    def test_routes(self):
        for text, route in [("Di chuyển từ khu vực A đến khu vực B.", ["A", "B"]),
                            ("Đi từ phòng A qua hành lang C rồi đến phòng B", ["A", "C", "B"]),
                            ("Đi đến A rồi đến B rồi đến C", ["A", "B", "C"])]:
            with self.subTest(text=text):
                self.assertEqual(self.parser.parse(text), route)

    def test_invalid_entire_route(self):
        for text in ["Đi đến D", "Đi từ A đến D", "Đi từ D đến B", "Đi từ A", "Đi đến A và B",
                     "không đi đến A", "xin chào", "Đi đến A rồi đến", "", "Đi đến A B"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.parser.parse(text)

    def test_cancel(self):
        for text in ["Dừng lại!", "hủy lệnh", "dừng", "hủy"]:
            self.assertEqual(self.parser.parse(text), [])

    def test_conflicting_alias(self):
        with self.assertRaises(ValueError):
            CommandParser([dict(id="A", name="Phòng học"), dict(id="B", name="phong hoc")])


class MapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        image = np.full((100, 120), 254, np.uint8)
        image[:3] = image[-3:] = 0
        image[:, :3] = image[:, -3:] = 0
        image[15:80, 58:62] = 0
        image[10:20, 15:25] = 205  # Unknown, not free.
        cv2.imwrite(str(self.root / "map.pgm"), image)
        self.meta = dict(image="map.pgm", resolution=.1, origin=[-2., -3., math.pi/3],
                         mode="trinary", negate=0, free_thresh=.196, occupied_thresh=.65)
        self.write_map()

    def tearDown(self):
        self.temp.cleanup()

    def write_map(self):
        (self.root / "map.yaml").write_text(yaml.safe_dump(self.meta))
        self.map = OccupancyMap(self.root / "map.yaml")

    def test_rotated_roundtrip_and_pixel_centers(self):
        for u, v in [(0, 0), (23, 71), (119, 99)]:
            self.assertEqual(self.map.world_to_pixel(*self.map.pixel_to_world(u, v)), (u, v))

    def test_unknown_obstacles_and_negate(self):
        self.assertFalse(self.map.safe(*self.map.pixel_to_world(20, 15), .2))
        self.assertFalse(self.map.safe(*self.map.pixel_to_world(60, 40), .2))
        self.assertFalse(self.map.safe(999, 999, .2))
        self.assertFalse(self.map.safe(float("nan"), 1, .2))
        self.meta["negate"] = 1
        self.write_map()
        self.assertFalse(self.map.free[50, 30])
        self.assertTrue(self.map.free[40, 60])

    def test_partition_cannot_cross_obstacle(self):
        mask = np.ones((9, 13), bool)
        mask[:, 6] = False
        labels = partition(mask, [(2, 4), (10, 4)])
        self.assertTrue((labels[:, :6] == 1).all())
        self.assertTrue((labels[:, 7:] == 2).all())
        self.assertTrue((labels[:, 6] == 0).all())

    def test_four_connectivity(self):
        self.assertEqual(int(largest_component(np.eye(4, dtype=bool)).sum()), 1)

    def test_generate_reload_and_safe_goals(self):
        data = save_segmentation(self.map, self.root / "result")
        self.assertEqual(len(data["regions"]), 3)
        self.assertEqual(load_regions(self.root / "result/regions.yaml"), data)
        labels = cv2.imread(str(self.root / "result/labels.png"), cv2.IMREAD_UNCHANGED)
        self.assertEqual(set(np.unique(labels)), {0, 1, 2, 3})
        for region in data["regions"]:
            self.assertTrue(self.map.safe(region["goal"]["x"], region["goal"]["y"], .35))
        self.assertFalse((labels[~self.map.free] > 0).any())

    def test_changed_map_rejected(self):
        save_segmentation(self.map, self.root / "result")
        image = cv2.imread(str(self.root / "map.pgm"), 0)
        image[30, 30] = 0
        cv2.imwrite(str(self.root / "map.pgm"), image)
        with self.assertRaisesRegex(ValueError, "thay đổi"):
            load_regions(self.root / "result/regions.yaml")

    def test_invalid_seed_and_clearance(self):
        with self.assertRaises(ValueError):
            partition(np.ones((4, 4), bool), [(0, 0), (0, 0)])
        with self.assertRaises(ValueError):
            save_segmentation(self.map, self.root / "bad", clearance=-1)

    def test_delivered_map(self):
        data = load_regions(ROOT / "maps/regions.yaml")
        self.assertGreaterEqual(len(data["regions"]), 3)

    def test_delivered_spoken_names(self):
        parser = CommandParser(load_regions(ROOT / "maps/regions.yaml")["regions"])
        for text, route in [("Đi đến phòng học", ["A"]), ("Đi đến phòng thí nghiệm", ["B"]),
                            ("Đi đến hành lang", ["C"]), ("Đi đến khu vực một", ["A"]),
                            ("Đi từ phòng học đến phòng thí nghiệm", ["A", "B"])]:
            with self.subTest(text=text):
                self.assertEqual(parser.parse(text), route)


if __name__ == "__main__":
    unittest.main()
