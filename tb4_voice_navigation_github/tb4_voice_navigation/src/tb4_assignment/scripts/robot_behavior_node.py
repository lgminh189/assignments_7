#!/usr/bin/env python3
"""Confirmed hand commands -> TurtleBot 4 TwistStamped, with steady watchdogs."""
import math
import time

import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from rclpy.qos import qos_profile_sensor_data, QoSProfile, HistoryPolicy
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String

from gesture_logic import BehaviorController


class RobotBehaviorNode(Node):
    def __init__(self):
        super().__init__('robot_behavior_node')
        defaults = dict(signal_timeout=0.8, selection_timeout=8.0, linear_speed=0.12,
                        angular_speed=0.35, leg_distance=0.35, circle_radius=0.6,
                        sensor_timeout=0.8, obstacle_distance=0.55)
        for name, value in defaults.items():
            self.declare_parameter(name, value)
        p = lambda name: self.get_parameter(name).value
        self.controller = BehaviorController(**{k: p(k) for k in defaults
                                               if k not in {'sensor_timeout', 'obstacle_distance'}})
        self.sensor_timeout, self.clearance = p('sensor_timeout'), p('obstacle_distance')
        if not (0 < self.sensor_timeout <= 2 and self.clearance >= 0.35):
            raise ValueError('sensor_timeout must be in (0, 2]; obstacle_distance >= 0.35 m')
        self.odom_at = self.scan_at = -math.inf
        self.scan = None
        self.last_status = None
        self.velocity = self.create_publisher(TwistStamped, '/cmd_vel', 1)
        self.state_pub = self.create_publisher(String, '/robot_behavior/state', 1)
        self.create_subscription(String, '/detected_gesture', self.on_gesture,
                                 QoSProfile(depth=1, history=HistoryPolicy.KEEP_LAST))
        self.create_subscription(Odometry, '/odom', self.on_odom, qos_profile_sensor_data)
        self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)
        self.create_timer(0.05, self.on_tick, clock=Clock(clock_type=ClockType.STEADY_TIME))
        self.get_logger().info('Waiting for gesture selection + Thumb_Up, /scan and /odom')

    def on_gesture(self, msg):
        self.controller.gesture(msg.data, time.monotonic())
        # Stop in the subscription callback, without waiting for the next tick.
        if msg.data in {'Open_Palm', 'Closed_Fist', 'Camera_Error'}:
            self.publish_velocity(0., 0.)

    def on_odom(self, msg):
        pos, q = msg.pose.pose.position, msg.pose.pose.orientation
        if not all(math.isfinite(v) for v in (pos.x, pos.y, q.x, q.y, q.z, q.w)):
            return
        if not 0.9 <= q.x*q.x + q.y*q.y + q.z*q.z + q.w*q.w <= 1.1:
            return
        yaw = math.atan2(2 * (q.w*q.z + q.x*q.y), 1 - 2 * (q.y*q.y + q.z*q.z))
        self.controller.observe_pose(pos.x, pos.y, yaw)
        self.odom_at = time.monotonic()

    def on_scan(self, msg):
        self.scan, self.scan_at = msg, time.monotonic()

    def obstacle(self):
        scan = self.scan
        if (scan is None or not scan.ranges
                or not all(math.isfinite(v) for v in
                           (scan.angle_min, scan.angle_increment, scan.range_min, scan.range_max))
                or scan.angle_increment <= 0 or not 0 <= scan.range_min < scan.range_max):
            return True
        # Curved movement/rotation checks the full footprint; straight travel checks
        # the direction of motion. Laser is near the centre of the robot.
        segment = self.controller.plan[0] if self.controller.plan else None
        full = segment is None or segment.angular != 0
        rear = segment is not None and segment.linear < 0
        samples = []
        for i, distance in enumerate(scan.ranges):
            angle = scan.angle_min + i * scan.angle_increment - (math.pi if rear else 0)
            angle = math.atan2(math.sin(angle), math.cos(angle))
            if full or abs(angle) < 0.8:
                samples.append(distance)
        if not samples or any(math.isnan(d) or d == -math.inf or d < scan.range_min
                              for d in samples):
            return True
        return any(math.isfinite(d) and d < self.clearance for d in samples)

    def publish_velocity(self, linear, angular):
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'
        msg.twist.linear.x, msg.twist.angular.z = float(linear), float(angular)
        self.velocity.publish(msg)

    def on_tick(self):
        now = time.monotonic()
        fresh = now - min(self.scan_at, self.odom_at) <= self.sensor_timeout
        v, w = self.controller.tick(now, fresh, self.obstacle())
        self.publish_velocity(v, w)
        if self.controller.status != self.last_status:
            self.last_status = self.controller.status
            self.get_logger().info(self.last_status)
        self.state_pub.publish(String(data=self.controller.status))


def main(args=None):
    # Keep the ROS context alive during KeyboardInterrupt cleanup so zero can
    # actually be published before launch tears down this process.
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = None
    try:
        node = RobotBehaviorNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            if rclpy.ok():
                node.publish_velocity(0., 0.)
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
