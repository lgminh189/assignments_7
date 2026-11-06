"""Empty arena and TurtleBot 4, without competing Nav2/teleop publishers."""
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import SetRemap


def generate_launch_description():
    share = get_package_share_directory('tb4_assignment')
    tb4 = get_package_share_directory('turtlebot4_gz_bringup')
    return LaunchDescription([
        # Controller spawners run from event handlers outside the spawn group.
        DeclareLaunchArgument('namespace', default_value=''),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('gui', default_value='true', choices=['true', 'false']),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(
            PathJoinSubstitution([share, 'launch', 'gz_ogre2.launch.py'])),
            launch_arguments={'world': 'gesture_arena',
                              'gui': LaunchConfiguration('gui')}.items()),
        GroupAction([
            SetRemap(src='/model/turtlebot4/tf', dst='/model/turtlebot4/ground_truth_tf'),
            IncludeLaunchDescription(PythonLaunchDescriptionSource(
                PathJoinSubstitution([tb4, 'launch', 'turtlebot4_spawn.launch.py'])),
                # Dock remains at the origin. Complete undocking before starting
                # the behavior node, so no action competes for /cmd_vel.
                launch_arguments={'model': 'standard', 'rviz': 'false',
                                  'x': '0.0', 'y': '0.0'}.items()),
        ]),
    ])
