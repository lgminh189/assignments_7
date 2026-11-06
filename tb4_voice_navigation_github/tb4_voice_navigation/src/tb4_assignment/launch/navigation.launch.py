#!/usr/bin/env python3

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    GroupAction,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import SetRemap


def generate_launch_description():
    pkg_turtlebot4_gz = get_package_share_directory('turtlebot4_gz_bringup')
    pkg_turtlebot4_navigation = get_package_share_directory('turtlebot4_navigation')
    pkg_nav2_bringup = get_package_share_directory('nav2_bringup')

    world_arg = DeclareLaunchArgument('world', default_value='warehouse')
    model_arg = DeclareLaunchArgument('model', default_value='standard', choices=['standard', 'lite'])
    rviz_arg = DeclareLaunchArgument('rviz', default_value='true', choices=['true', 'false'])
    gui_arg = DeclareLaunchArgument('gui', default_value='true', choices=['true', 'false'])
    map_arg = DeclareLaunchArgument('map', default_value=PathJoinSubstitution([
        get_package_share_directory('tb4_assignment'), 'maps', 'final_map.yaml'
    ]))
    auto_undock_arg = DeclareLaunchArgument(
        'auto_undock',
        default_value='false',
        choices=['true', 'false'],
        description='Undock automatically 15 seconds after launch when explicitly enabled',
    )
    x_arg = DeclareLaunchArgument('x', default_value='0.0')
    y_arg = DeclareLaunchArgument('y', default_value='0.0')
    z_arg = DeclareLaunchArgument('z', default_value='0.0')
    yaw_arg = DeclareLaunchArgument('yaw', default_value='0.0')

    pkg_tb4_assignment = get_package_share_directory('tb4_assignment')

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

    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([pkg_nav2_bringup, 'launch', 'localization_launch.py'])
        ),
        launch_arguments=[
            ('use_sim_time', 'true'),
            ('autostart', 'true'),
            ('use_composition', 'False'),
            ('params_file', PathJoinSubstitution([
                pkg_tb4_assignment,
                'config',
                'nav2_params.yaml'
            ])),
            ('map', LaunchConfiguration('map')),
        ],
    )

    # AMCL needs time to publish map->odom from its configured initial pose
    # before Nav2 costmaps are activated; otherwise their first activation fails.
    nav2 = TimerAction(
        period=25.0,
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([pkg_nav2_bringup, 'launch', 'navigation_launch.py'])
            ),
            launch_arguments=[
                ('use_sim_time', 'true'),
                ('autostart', 'true'),
                ('use_composition', 'False'),
                ('params_file', PathJoinSubstitution([
                    pkg_tb4_assignment,
                    'config',
                    'nav2_params.yaml'
                ])),
            ],
        )],
    )

    undock = TimerAction(
        period=15.0,
        actions=[ExecuteProcess(
            condition=IfCondition(LaunchConfiguration('auto_undock')),
            cmd=[
                'ros2', 'action', 'send_goal', '/undock',
                'irobot_create_msgs/action/Undock', '{}',
            ],
            output='screen',
        )],
    )

    return LaunchDescription([
        # Avoid CycloneDDS participant-index exhaustion seen when old ROS
        # sessions remain alive; keep every node in this launch on Fast DDS.
        SetEnvironmentVariable('RMW_IMPLEMENTATION', 'rmw_fastrtps_cpp'),
        world_arg,
        model_arg,
        rviz_arg,
        gui_arg,
        map_arg,
        auto_undock_arg,
        x_arg,
        y_arg,
        z_arg,
        yaw_arg,
        gazebo,
        robot,
        localization,
        nav2,
        undock,
    ])
