"""Insert a person mesh for camera detection, away from the sample mission path."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    sdf = ('<sdf version="1.9"><include>'
           '<uri>https://fuel.gazebosim.org/1.0/Plateau/models/Casual Female</uri>'
           '<name>assignment_person</name></include></sdf>')
    return LaunchDescription([
        DeclareLaunchArgument('world', default_value='warehouse'),
        DeclareLaunchArgument('x', default_value='5.0'),
        DeclareLaunchArgument('y', default_value='5.5'),
        ExecuteProcess(cmd=[
            'ros2', 'run', 'ros_gz_sim', 'create',
            '-world', LaunchConfiguration('world'), '-name', 'assignment_person',
            '-string', sdf, '-x', LaunchConfiguration('x'), '-y', LaunchConfiguration('y'),
            '-Y', '3.14',
        ], output='screen'),
    ])
