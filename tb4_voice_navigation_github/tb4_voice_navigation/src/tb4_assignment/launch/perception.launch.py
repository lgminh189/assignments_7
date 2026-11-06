"""Run perception separately so inference does not block navigation."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('image_topic', default_value='/oakd/rgb/preview/image_raw'),
        DeclareLaunchArgument('model', default_value='yolov8n.pt'),
        DeclareLaunchArgument('confidence', default_value='0.45'),
        DeclareLaunchArgument('inference_rate', default_value='2.0'),
        DeclareLaunchArgument('device', default_value='cpu'),
        DeclareLaunchArgument('show_window', default_value='false'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        Node(package='tb4_assignment', executable='yolo_detector.py', output='screen',
             parameters=[{
                 key: ParameterValue(LaunchConfiguration(key), value_type=value_type)
                 for key, value_type in (
                     ('image_topic', str), ('model', str), ('confidence', float),
                     ('inference_rate', float), ('device', str),
                     ('show_window', bool), ('use_sim_time', bool))
             }]),
    ])
