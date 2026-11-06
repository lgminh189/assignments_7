#!/usr/bin/env python3
"""Voice/text command → sequential Nav2 NavigateToPose goals."""
import argparse
from collections import deque
import json
import math
from pathlib import Path
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from rclpy.qos import QoSProfile, DurabilityPolicy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import Point, PoseStamped
from nav2_msgs.action import NavigateToPose
from std_msgs.msg import String
from visualization_msgs.msg import Marker, MarkerArray

from commands import CommandParser
from map_tools import load_regions


class VoiceNavigator(Node):
    def __init__(self, regions_file, timeout=180.0):
        super().__init__("voice_navigation")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("goal timeout phải > 0")
        self.data = load_regions(regions_file)
        self.regions = {region["id"]: region for region in self.data["regions"]}
        self.parser = CommandParser(self.data["regions"])
        self.timeout = timeout
        self.client = ActionClient(self, NavigateToPose, "navigate_to_pose")
        self.status_pub = self.create_publisher(String, "/voice_nav/status", 10)
        self.subscription = self.create_subscription(String, "/voice_nav/command", self.command, 10)
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.marker_pub = self.create_publisher(MarkerArray, "/voice_nav/markers", qos)
        self.busy = False
        self.goal_handle = None
        self.cancel_requested = False
        self.route = deque()
        self.current = None
        self.timer = self.create_timer(.1, self.tick, clock=Clock(clock_type=ClockType.STEADY_TIME))
        self.mark_regions()
        self.status("READY", "Đang chờ lệnh; cần Nav2 và AMCL hoạt động")

    def status(self, state, message, **extra):
        payload = dict(state=state, message=message, **extra)
        self.status_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
        self.get_logger().info(json.dumps(payload, ensure_ascii=False))

    def command(self, message):
        try:
            route = self.parser.parse(message.data)
        except ValueError as exc:
            self.status("INVALID_COMMAND", str(exc))
            return
        if not route:
            self.request_cancel("Người dùng hủy lệnh")
            return
        if self.busy:
            self.status("BUSY", "Đang chạy; hãy dừng/hủy và chờ kết quả trước khi gửi lệnh mới")
            return
        if not self.client.server_is_ready():
            self.status("NOT_READY", "Action /navigate_to_pose chưa sẵn sàng; lệnh chưa được lưu")
            return
        self.route = deque(route)
        self.busy = True
        self.cancel_requested = False
        self.mark_regions(route)
        self.status("ROUTE", " → ".join(route), command=message.data, route=route)
        self.send_next()

    def send_next(self):
        self.current = self.route.popleft()
        region = self.regions[self.current]
        pose = PoseStamped()
        pose.header.frame_id = "map"
        pose.header.stamp = self.get_clock().now().to_msg()
        goal = region["goal"]
        pose.pose.position.x, pose.pose.position.y = float(goal["x"]), float(goal["y"])
        pose.pose.orientation.z = math.sin(goal["yaw"]/2)
        pose.pose.orientation.w = math.cos(goal["yaw"]/2)
        request = NavigateToPose.Goal()
        request.pose = pose
        self.goal_handle = None
        self.started = time.monotonic()
        self.last_feedback = 0.0
        self.status("NAVIGATING", f"Đi đến {region['name']}", region=self.current)
        self.client.send_goal_async(request, feedback_callback=self.feedback).add_done_callback(self.accepted)

    def accepted(self, future):
        try:
            self.goal_handle = future.result()
            if not self.goal_handle.accepted:
                self.finish("REJECTED", "Nav2 từ chối đích; dừng toàn bộ hành trình")
                return
            self.goal_handle.get_result_async().add_done_callback(self.result)
            if self.cancel_requested:
                self.cancel_handle()
        except Exception as exc:
            # Keep the mission locked when the transport outcome is uncertain.
            self.status("TRANSPORT_ERROR", str(exc))
            self.request_cancel("Không xác định được trạng thái gửi goal")

    def result(self, future):
        try:
            result = future.result()
        except Exception as exc:
            self.status("TRANSPORT_ERROR", str(exc))
            self.request_cancel("Không nhận được kết quả; giữ khóa hành trình")
            return
        self.goal_handle = None
        if self.cancel_requested:
            self.finish("STOPPED", "Hành trình đã kết thúc sau yêu cầu hủy")
        elif result.status != GoalStatus.STATUS_SUCCEEDED or getattr(result.result, "error_code", 0) != 0:
            self.finish("FAILED", "Nav2 thất bại; không gửi các đích còn lại",
                        action_status=result.status, error_code=getattr(result.result, "error_code", 0))
        else:
            self.status("ARRIVED", f"Đã đến {self.current}", region=self.current)
            if self.route:
                self.send_next()
            else:
                self.finish("SUCCEEDED", "Đã hoàn thành hành trình")

    def request_cancel(self, reason):
        if not self.busy:
            self.status("IDLE", "Không có hành trình đang chạy")
            return
        if self.cancel_requested:
            return
        self.cancel_requested = True
        self.route.clear()
        self.status("CANCELING", reason)
        if self.goal_handle is not None:
            self.cancel_handle()

    def cancel_handle(self):
        self.goal_handle.cancel_goal_async().add_done_callback(self.canceled)

    def canceled(self, future):
        try:
            if not future.result().goals_canceling:
                self.status("CANCEL_PENDING", "Nav2 chưa chấp nhận hủy; chờ kết quả goal, không nhận lệnh mới")
        except Exception as exc:
            self.status("CANCEL_ERROR", str(exc))

    def finish(self, state, message, **extra):
        self.busy = False
        self.goal_handle = None
        self.route.clear()
        self.cancel_requested = False
        self.status(state, message, **extra)

    def feedback(self, message):
        if time.monotonic() - self.last_feedback >= 2:
            self.last_feedback = time.monotonic()
            self.status("FEEDBACK", f"Còn {message.feedback.distance_remaining:.2f} m", region=self.current)

    def tick(self):
        if self.busy and time.monotonic() - self.started >= self.timeout:
            self.request_cancel("Hết thời gian cho đích; hủy toàn bộ hành trình")

    def mark_regions(self, route=()):
        markers = MarkerArray()
        for index, region in enumerate(self.data["regions"]):
            marker = Marker()
            marker.header.frame_id = "map"
            marker.ns, marker.id, marker.type = "regions", index, Marker.TEXT_VIEW_FACING
            marker.action = Marker.ADD
            marker.pose.position.x = float(region["goal"]["x"])
            marker.pose.position.y = float(region["goal"]["y"])
            marker.pose.position.z = .5
            marker.pose.orientation.w = 1.0
            marker.scale.z = .5
            marker.color.r, marker.color.g, marker.color.b, marker.color.a = 1., 1., 0., 1.
            marker.text = region["name"]
            markers.markers.append(marker)
        line = Marker()
        line.header.frame_id = "map"
        line.ns, line.id, line.type, line.action = "route", 0, Marker.LINE_STRIP, Marker.ADD
        line.pose.orientation.w = 1.0
        line.scale.x = .06
        line.color.g, line.color.a = 1., 1.
        for ident in route:
            goal = self.regions[ident]["goal"]
            line.points.append(Point(x=float(goal["x"]), y=float(goal["y"]), z=.15))
        markers.markers.append(line)
        self.marker_pub.publish(markers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", default=str(Path(__file__).resolve().parent / "maps/regions.yaml"))
    parser.add_argument("--goal-timeout", type=float, default=180)
    args, ros_args = parser.parse_known_args()
    rclpy.init(args=ros_args, signal_handler_options=SignalHandlerOptions.NO)
    node = None
    try:
        node = VoiceNavigator(args.regions, args.goal_timeout)
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.request_cancel("Đóng chương trình")
            deadline = time.monotonic() + 3
            while node.busy and rclpy.ok() and time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=.1)
            if node.busy:
                node.get_logger().error("Chưa xác nhận dừng từ Nav2; kiểm tra robot trước khi đóng mô phỏng")
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
