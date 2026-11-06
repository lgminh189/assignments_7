"""Mission logic checks without running a simulator."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from nav2_simple_commander.robot_navigator import TaskResult
import yaml

spec = importlib.util.spec_from_file_location(
    'navigate_goals', Path(__file__).parents[1] / 'scripts' / 'navigate_goals.py')
mission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mission)
GOALS = [dict(x=1.0, y=2.0, yaw=0.0), dict(x=3.0, y=4.0, yaw=1.57),
         dict(x=5.0, y=6.0, yaw=-3.14)]


def fake_navigator():
    nav = Mock()
    nav.goToPose.return_value = True
    nav.isTaskComplete.return_value = True
    nav.getResult.return_value = TaskResult.SUCCEEDED
    nav.get_clock.return_value.now.return_value.to_msg.return_value = mission.PoseStamped().header.stamp
    return nav


def test_three_goals_in_order_and_quaternion():
    nav = fake_navigator()
    assert mission.navigate(nav, GOALS, 180.0)
    poses = [call.args[0] for call in nav.goToPose.call_args_list]
    assert [pose.pose.position.x for pose in poses] == [1.0, 3.0, 5.0]
    assert all(pose.header.frame_id == 'map' for pose in poses)
    import math
    assert poses[1].pose.orientation.z == pytest.approx(math.sin(1.57 / 2))
    assert poses[1].pose.orientation.w == pytest.approx(math.cos(1.57 / 2))


@pytest.mark.parametrize('result', [TaskResult.FAILED, TaskResult.CANCELED, TaskResult.UNKNOWN])
def test_failed_goal_stops_mission(result):
    nav = fake_navigator()
    nav.getResult.return_value = result
    assert not mission.navigate(nav, GOALS, 180.0)
    assert nav.goToPose.call_count == 1


def test_rejection_stops_mission():
    nav = fake_navigator()
    nav.goToPose.return_value = False
    assert not mission.navigate(nav, GOALS, 180.0)
    nav.isTaskComplete.assert_not_called()
    assert nav.goToPose.call_count == 1


def test_timeout_cancels_without_sending_next_goal():
    nav = fake_navigator()
    nav.isTaskComplete.return_value = False
    with patch.object(mission.time, 'monotonic', side_effect=[0.0, 181.0]):
        assert not mission.navigate(nav, GOALS, 180.0)
    nav.cancelTask.assert_called_once()
    assert nav.goToPose.call_count == 1


@pytest.mark.parametrize('data', [None, {}, {'frame_id': 'odom', 'goals': GOALS},
                                   {'frame_id': 'map', 'goals': GOALS[:2]},
                                   {'frame_id': 'map', 'goals': [dict(x=float('nan'), y=0, yaw=0)] * 3},
                                   {'frame_id': 'map', 'goals': [dict(x=True, y=0, yaw=0)] * 3}])
def test_invalid_goal_file_rejected(tmp_path, data):
    path = tmp_path / 'mission.yaml'
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        mission.load_goals(path)


def test_load_surveyed_goals(tmp_path):
    path = tmp_path / 'mission.yaml'
    path.write_text(yaml.safe_dump(dict(frame_id='map', goals=GOALS)))
    assert mission.load_goals(path) == GOALS


def test_recorded_points_preserve_order_frame_and_yaw(tmp_path):
    import rclpy
    from geometry_msgs.msg import PointStamped
    recorder_spec = importlib.util.spec_from_file_location(
        'record_goals', Path(__file__).parents[1] / 'scripts' / 'record_goals.py')
    recorder_module = importlib.util.module_from_spec(recorder_spec)
    recorder_spec.loader.exec_module(recorder_module)
    output = tmp_path / 'surveyed.yaml'
    rclpy.init(args=['--ros-args', '-p', f'output:={output}', '-p', 'yaw:=1.5708'])
    node = None
    try:
        node = recorder_module.GoalRecorder()
        point = PointStamped()
        point.header.frame_id = 'odom'
        node.clicked(point)
        assert not output.exists()
        point.header.frame_id = 'map'
        for index in range(3):
            point.point.x = float(index)
            point.point.y = float(index + 2)
            node.clicked(point)
        result = mission.load_goals(output)
        assert [p['x'] for p in result] == [0.0, 1.0, 2.0]
        assert all(p['yaw'] == 1.5708 for p in result)
        node.destroy_node()
        node = None
        with pytest.raises(ValueError, match='already exists'):
            recorder_module.GoalRecorder()
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()
