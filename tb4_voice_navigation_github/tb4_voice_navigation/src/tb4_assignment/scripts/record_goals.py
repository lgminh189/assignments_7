#!/usr/bin/env python3
"""Record RViz Publish Point clicks as a YAML mission without sending actions."""
import math
from pathlib import Path

from geometry_msgs.msg import PointStamped
import rclpy
from rclpy.node import Node
import yaml


class GoalRecorder(Node):
    def __init__(self):
        super().__init__('goal_recorder')
        self.declare_parameter('output', 'goals.yaml')
        self.declare_parameter('yaw', 0.0)
        self.declare_parameter('count', 3)
        self.output = Path(self.get_parameter('output').value).expanduser()
        self.count = self.get_parameter('count').value
        if self.count < 3:
            raise ValueError('count must be at least 3')
        if self.output.exists():
            raise ValueError(f'{self.output} already exists; choose a new output file')
        self.goals = []
        self.create_subscription(PointStamped, '/clicked_point', self.clicked, 10)
        self.get_logger().info(
            f'RViz Fixed Frame=map; click {self.count} free points using Publish Point. '
            'Yaw is in radians; change with ros2 param set /goal_recorder yaw VALUE.')

    def clicked(self, msg):
        if len(self.goals) >= self.count:
            return
        if msg.header.frame_id != 'map':
            self.get_logger().error('Point ignored: set RViz Fixed Frame to map')
            return
        yaw = float(self.get_parameter('yaw').value)
        if not all(math.isfinite(v) for v in (msg.point.x, msg.point.y, yaw)):
            self.get_logger().error('Point ignored: x/y/yaw must be finite')
            return
        self.goals.append(dict(x=msg.point.x, y=msg.point.y, yaw=yaw))
        self.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.output.with_suffix(self.output.suffix + '.tmp')
        temporary.write_text(yaml.safe_dump(
            dict(frame_id='map', goals=self.goals), sort_keys=False), encoding='utf-8')
        temporary.replace(self.output)
        self.get_logger().info(f'Goal {len(self.goals)} saved: {self.goals[-1]} -> {self.output}')


def main():
    rclpy.init()
    node = None
    try:
        node = GoalRecorder()
        while rclpy.ok() and len(node.goals) < node.count:
            rclpy.spin_once(node, timeout_sec=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
