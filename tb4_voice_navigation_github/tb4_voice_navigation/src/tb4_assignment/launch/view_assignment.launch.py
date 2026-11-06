"""RViz view with map, robot, scan, RGB and annotated YOLO image."""
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    config = get_package_share_directory('tb4_assignment') + '/config/assignment.rviz'
    return LaunchDescription([
        Node(package='rviz2', executable='rviz2', name='assignment_rviz',
             arguments=['-d', config], parameters=[{'use_sim_time': True}], output='screen'),
    ])
