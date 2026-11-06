#!/usr/bin/env python3
"""Visit surveyed map poses in order; stop on rejection, failure or timeout."""
import math
from pathlib import Path
import time

from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
import rclpy
from rclpy.signals import SignalHandlerOptions
import yaml


def load_goals(filename):
    with Path(filename).expanduser().open(encoding='utf-8') as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict) or data.get('frame_id') != 'map':
        raise ValueError('Goal file must contain frame_id: map')
    goals = data.get('goals')
    if not isinstance(goals, list) or len(goals) < 3:
        raise ValueError('Record at least 3 surveyed goals with record_goals.py first')
    for goal in goals:
        if not isinstance(goal, dict):
            raise ValueError('Each goal must contain x, y, yaw (radians)')
        for key in ('x', 'y', 'yaw'):
            value = goal.get(key)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError(f'Goal {key} must be a finite number')
    return goals


def make_pose(navigator, goal):
    pose = PoseStamped()
    pose.header.frame_id = 'map'
    pose.header.stamp = navigator.get_clock().now().to_msg()
    pose.pose.position.x = float(goal['x'])
    pose.pose.position.y = float(goal['y'])
    pose.pose.orientation.z = math.sin(goal['yaw'] / 2.0)
    pose.pose.orientation.w = math.cos(goal['yaw'] / 2.0)
    return pose


def navigate(navigator, goals, timeout):
    for index, goal in enumerate(goals, 1):
        navigator.get_logger().info(f'Goal {index}/{len(goals)}: {goal}')
        if not navigator.goToPose(make_pose(navigator, goal)):
            navigator.get_logger().error(f'Goal {index} rejected; mission stopped')
            return False
        started = time.monotonic()
        last_log = started
        while not navigator.isTaskComplete():
            now = time.monotonic()
            if now - started >= timeout:
                navigator.cancelTask()
                navigator.get_logger().error(f'Goal {index} timed out; mission stopped')
                return False
            if now - last_log >= 2.0:
                feedback = navigator.getFeedback()
                if feedback is not None:
                    navigator.get_logger().info(
                        f'Goal {index}: {feedback.distance_remaining:.2f} m remaining')
                last_log = now
            time.sleep(0.05)
        result = navigator.getResult()
        if result != TaskResult.SUCCEEDED:
            navigator.get_logger().error(f'Goal {index}: {result.name}; mission stopped')
            return False
        navigator.get_logger().info(f'Goal {index} SUCCEEDED')
    navigator.get_logger().info('All goals completed')
    return True


def main():
    # Keep ROS alive on Ctrl-C long enough to cancel the current Nav2 action.
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    navigator = BasicNavigator(node_name='autonomous_navigation')
    code = 1
    try:
        navigator.declare_parameter('goals_file', str(
            Path(get_package_share_directory('tb4_assignment')) / 'config' / 'goals.yaml'))
        navigator.declare_parameter('goal_timeout', 180.0)
        navigator.declare_parameter('localization_timeout', 120.0)
        goals = load_goals(navigator.get_parameter('goals_file').value)
        timeout = float(navigator.get_parameter('goal_timeout').value)
        localization_timeout = float(navigator.get_parameter('localization_timeout').value)
        if not all(math.isfinite(v) and v > 0 for v in (timeout, localization_timeout)):
            raise ValueError('Timeouts must be finite and positive')
        navigator.get_logger().info('Waiting for AMCL pose; set 2D Pose Estimate in RViz if needed')
        deadline = time.monotonic() + localization_timeout
        # Do not let BasicNavigator replace an established RViz pose with its default (0,0).
        while rclpy.ok() and not navigator.initial_pose_received:
            if time.monotonic() >= deadline:
                raise RuntimeError('No AMCL pose received before localization_timeout')
            rclpy.spin_once(navigator, timeout_sec=0.2)
        navigator.waitUntilNav2Active()
        code = 0 if navigate(navigator, goals, timeout) else 1
    except KeyboardInterrupt:
        navigator.get_logger().info('Interrupted; canceling navigation')
        if navigator.goal_handle is not None:
            navigator.cancelTask()
        code = 130
    except Exception as exc:
        navigator.get_logger().error(str(exc))
        if navigator.goal_handle is not None and rclpy.ok():
            navigator.cancelTask()
    finally:
        navigator.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return code


if __name__ == '__main__':
    raise SystemExit(main())
