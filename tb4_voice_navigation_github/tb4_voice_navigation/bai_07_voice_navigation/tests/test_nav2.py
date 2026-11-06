"""Real ROS action transport against a fake Nav2 server, no Gazebo/motion.

Run in its own process: uses ROS_DOMAIN_ID=87 to isolate test command topics.
"""
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest

os.environ["ROS_DOMAIN_ID"] = "87"
os.environ["RMW_IMPLEMENTATION"] = "rmw_fastrtps_cpp"
import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from nav2_msgs.action import NavigateToPose
from std_msgs.msg import String

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from navigation_node import VoiceNavigator


class Nav2TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def setUp(self):
        self.mode = "success"
        self.goals = []
        self.states = []
        self.server_node = Node("fake_nav2")
        self.server = ActionServer(
            self.server_node, NavigateToPose, "navigate_to_pose", self.execute,
            goal_callback=lambda _: GoalResponse.REJECT if self.mode == "reject" else GoalResponse.ACCEPT,
            cancel_callback=lambda _: CancelResponse.ACCEPT,
            callback_group=ReentrantCallbackGroup())
        self.nav = VoiceNavigator(ROOT / "maps/regions.yaml", timeout=2.)
        self.pub = self.server_node.create_publisher(String, "/voice_nav/command", 10)
        self.sub = self.server_node.create_subscription(
            String, "/voice_nav/status", lambda msg: self.states.append(json.loads(msg.data)), 100)
        self.executor = MultiThreadedExecutor(num_threads=4)
        self.executor.add_node(self.server_node)
        self.executor.add_node(self.nav)
        self.thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.thread.start()
        self.wait_for(lambda: self.pub.get_subscription_count() > 0 and self.nav.client.server_is_ready())

    def tearDown(self):
        self.nav.request_cancel("Test cleanup")
        if self.nav.busy:
            self.wait_for(lambda: not self.nav.busy)
        self.executor.shutdown(timeout_sec=4)
        self.thread.join(timeout=4)
        self.server.destroy()
        self.nav.destroy_node()
        self.server_node.destroy_node()

    def wait_for(self, predicate, timeout=5.):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(.01)
        self.fail(f"Timeout; states={self.states}")

    def state(self, name):
        return any(state["state"] == name for state in self.states)

    def execute(self, handle):
        self.goals.append(handle.request.pose)
        started = time.monotonic()
        while time.monotonic()-started < (4 if self.mode == "hold" else .15):
            if handle.is_cancel_requested:
                handle.canceled()
                return NavigateToPose.Result()
            time.sleep(.01)
        result = NavigateToPose.Result()
        if self.mode == "fail":
            handle.abort()
            result.error_code = 1
        else:
            handle.succeed()
        return result

    def test_a_then_b_only_after_success(self):
        self.pub.publish(String(data="Di chuyển từ khu vực A đến khu vực B"))
        self.wait_for(lambda: self.state("SUCCEEDED"))
        self.assertEqual(len(self.goals), 2)
        for pose, ident in zip(self.goals, ["A", "B"]):
            self.assertEqual(pose.header.frame_id, "map")
            self.assertAlmostEqual(pose.pose.position.x, self.nav.regions[ident]["goal"]["x"])
        self.assertEqual([s["region"] for s in self.states if s["state"] == "ARRIVED"], ["A", "B"])

    def test_unknown_region_sends_nothing(self):
        self.pub.publish(String(data="Đi từ A đến vùng không tồn tại"))
        self.wait_for(lambda: self.state("INVALID_COMMAND"))
        self.assertFalse(self.goals)
        self.assertFalse(self.nav.busy)

    def test_failure_prevents_second_goal(self):
        self.mode = "fail"
        self.pub.publish(String(data="Đi từ A đến B"))
        self.wait_for(lambda: self.state("FAILED"))
        self.assertEqual(len(self.goals), 1)

    def test_rejected_goal_stops_route(self):
        self.mode = "reject"
        self.pub.publish(String(data="Đi từ A đến B"))
        self.wait_for(lambda: self.state("REJECTED"))
        self.assertFalse(self.goals)
        self.assertFalse(self.nav.busy)

    def test_busy_and_cancel(self):
        self.mode = "hold"
        self.pub.publish(String(data="Đi từ A đến B"))
        self.wait_for(lambda: len(self.goals) == 1)
        self.pub.publish(String(data="Đi đến C"))
        self.wait_for(lambda: self.state("BUSY"))
        self.pub.publish(String(data="Dừng lại"))
        self.wait_for(lambda: self.state("STOPPED"))
        self.assertEqual(len(self.goals), 1)
        self.assertFalse(self.nav.busy)

    def test_timeout_cancels_without_next_goal(self):
        self.mode = "hold"
        self.nav.timeout = .2
        self.pub.publish(String(data="Đi từ A đến B"))
        self.wait_for(lambda: self.state("STOPPED"))
        self.assertEqual(len(self.goals), 1)
        self.assertTrue(self.state("CANCELING"))


if __name__ == "__main__":
    unittest.main()
