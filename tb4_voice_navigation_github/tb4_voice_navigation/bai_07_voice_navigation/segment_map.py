#!/usr/bin/env python3
"""Generate labelled functional regions from a ROS map.yaml."""
import argparse
import json
from pathlib import Path
from map_tools import OccupancyMap, save_segmentation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parent
    parser.add_argument("--map", default=str(root / "maps/original.yaml"))
    parser.add_argument("--out", default=str(root / "maps"))
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--clearance", type=float, default=.35)
    parser.add_argument("--seeds", help='JSON file chứa [[u,v], ...] theo pixel ảnh (gốc trên trái)')
    args = parser.parse_args()
    seeds = json.loads(Path(args.seeds).read_text()) if args.seeds else None
    data = save_segmentation(OccupancyMap(args.map), args.out, args.count, args.clearance, seeds)
    for region in data["regions"]:
        print(region["id"], region["goal"])


if __name__ == "__main__":
    main()
