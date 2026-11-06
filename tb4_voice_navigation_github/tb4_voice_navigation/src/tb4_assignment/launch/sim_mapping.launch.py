#!/usr/bin/env python3

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    GroupAction,
    IncludeLaunchDescription,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import SetRemap


def generate_launch_description():
    pkg_tb4_assignment = get_package_share_directory('tb4_assignment')
    pkg_turtlebot4_gz = get_package_share_directory('turtlebot4_gz_bringup')
    pkg_turtlebot4_navigation = get_package_share_directory('turtlebot4_navigation')

    world_arg = DeclareLaunchArgument('world', default_value='warehouse')
    model_arg = DeclareLaunchArgument('model', default_value='standard', choices=['standard', 'lite'])
    rviz_arg = DeclareLaunchArgument('rviz', default_value='true', choices=['true', 'false'])
    gui_arg = DeclareLaunchArgument('gui', default_value='true', choices=['true', 'false'])
    x_arg = DeclareLaunchArgument('x', default_value='0.0')
    y_arg = DeclareLaunchArgument('y', default_value='0.0')
    z_arg = DeclareLaunchArgument('z', default_value='0.0')
    yaw_arg = DeclareLaunchArgument('yaw', default_value='0.0')

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([pkg_tb4_assignment, 'launch', 'gz_ogre2.launch.py'])
        ),
        launch_arguments=[
            ('world', LaunchConfiguration('world')),
            ('model', LaunchConfiguration('model')),
            ('gui', LaunchConfiguration('gui')),
        ],
    )

    robot = GroupAction(
        actions=[
            # Keep Gazebo ground truth TF separate from diffdrive_controller's
            # authoritative odom -> base_link transform.
            SetRemap(
                src='/model/turtlebot4/tf',
                dst='/model/turtlebot4/ground_truth_tf',
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    PathJoinSubstitution([
                        pkg_turtlebot4_gz, 'launch', 'turtlebot4_spawn.launch.py'
                    ])
                ),
                launch_arguments=[
                    ('model', LaunchConfiguration('model')),
                    ('rviz', LaunchConfiguration('rviz')),
                    ('x', LaunchConfiguration('x')),
                    ('y', LaunchConfiguration('y')),
                    ('z', LaunchConfiguration('z')),
                    ('yaw', LaunchConfiguration('yaw')),
                ],
            ),
        ]
    )

    slam = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([pkg_turtlebot4_navigation, 'launch', 'slam.launch.py'])
        ),
        launch_arguments=[
            ('use_sim_time', 'true'),
            ('sync', 'true'),
            ('params', PathJoinSubstitution([
                pkg_tb4_assignment,
                'config',
                'slam_params.yaml'
            ])),
        ],
    )

    undock = TimerAction(
        period=15.0,
        actions=[ExecuteProcess(
            cmd=[
                'ros2', 'action', 'send_goal', '/undock',
                'irobot_create_msgs/action/Undock', '{}',
            ],
            output='screen',
        )],
    )

    return LaunchDescription([
        world_arg,
        model_arg,
        rviz_arg,
        gui_arg,
        x_arg,
        y_arg,
        z_arg,
        yaw_arg,
        gazebo,
        robot,
        slam,
        undock,
    ])
