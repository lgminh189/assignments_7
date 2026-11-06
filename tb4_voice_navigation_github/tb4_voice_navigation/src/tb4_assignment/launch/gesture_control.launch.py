"""Camera recognizer in its venv and behavior controller in the ROS interpreter."""
from ament_index_python.packages import get_package_prefix
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, RegisterEventHandler, EmitEvent
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from pathlib import Path


def generate_launch_description():
    scripts = Path(get_package_prefix('tb4_assignment')) / 'lib' / 'tb4_assignment'
    camera = ExecuteProcess(
        cmd=[LaunchConfiguration('python_executable'), str(scripts / 'gesture_recognition_node.py'),
             '--ros-args', '-p', ['model_path:=', LaunchConfiguration('model_path')],
             '-p', ['camera_index:=', LaunchConfiguration('camera_index')],
             '-p', ['wave_amplitude:=', LaunchConfiguration('wave_amplitude')],
             '-p', ['wave_window:=', LaunchConfiguration('wave_window')],
             '-p', ['show_window:=', LaunchConfiguration('show_window')]], output='screen')
    behavior = Node(package='tb4_assignment', executable='robot_behavior_node.py',
                    output='screen', parameters=[{'use_sim_time': ParameterValue(
                        LaunchConfiguration('use_sim_time'), value_type=bool)}])
    return LaunchDescription([
        DeclareLaunchArgument('python_executable', default_value='/usr/bin/python3',
                              description='Python with MediaPipe, OpenCV and rclpy'),
        DeclareLaunchArgument('model_path', description='Absolute path to gesture_recognizer.task'),
        DeclareLaunchArgument('camera_index', default_value='0'),
        DeclareLaunchArgument('wave_amplitude', default_value='0.06'),
        DeclareLaunchArgument('wave_window', default_value='3.0'),
        DeclareLaunchArgument('show_window', default_value='true', choices=['true', 'false']),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        RegisterEventHandler(OnProcessExit(target_action=camera, on_exit=[EmitEvent(
            event=Shutdown(reason='Webcam recognizer exited'))])),
        RegisterEventHandler(OnProcessExit(target_action=behavior, on_exit=[EmitEvent(
            event=Shutdown(reason='Behavior controller exited'))])),
        behavior, camera,
    ])
