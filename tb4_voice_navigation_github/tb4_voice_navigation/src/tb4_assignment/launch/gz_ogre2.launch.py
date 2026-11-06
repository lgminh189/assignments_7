#!/usr/bin/env python3

import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node


def generate_launch_description():
    pkg_gz_bringup = get_package_share_directory('turtlebot4_gz_bringup')
    pkg_description = get_package_share_directory('turtlebot4_description')
    pkg_create_description = get_package_share_directory('irobot_create_description')
    pkg_create_gz_bringup = get_package_share_directory('irobot_create_gz_bringup')
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')

    world_arg = DeclareLaunchArgument('world', default_value='warehouse')
    model_arg = DeclareLaunchArgument('model', default_value='standard')
    gui_arg = DeclareLaunchArgument('gui', default_value='true', choices=['true', 'false'])

    resource_path = ':'.join([
        os.path.join(get_package_share_directory('tb4_assignment'), 'worlds'),
        os.path.join(pkg_gz_bringup, 'worlds'),
        os.path.join(pkg_create_gz_bringup, 'worlds'),
        str(Path(pkg_description).parent.resolve()),
        str(Path(pkg_create_description).parent.resolve()),
    ])
    gui_plugin_path = ':'.join([
        os.path.join(get_package_share_directory('turtlebot4_gz_gui_plugins'), 'lib'),
        os.path.join(get_package_share_directory('irobot_create_gz_plugins'), 'lib'),
    ])

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py'])
        ),
        launch_arguments={
            'gz_args': [
                LaunchConfiguration('world'), '.sdf -r -v 4 --render-engine ogre2 -s',
            ],
        }.items(),
    )

    # Keep the GUI in a separate process. A GUI/OpenGL crash must not tear down
    # the Gazebo server that owns physics and GPU LiDAR sensors.
    gazebo_gui = TimerAction(
        period=3.0,
        actions=[ExecuteProcess(
            cmd=[
                'gz', 'sim', '-g', '--render-engine', 'ogre2',
                '--gui-config', PathJoinSubstitution([
                    pkg_gz_bringup, 'gui', LaunchConfiguration('model'), 'gui.config'
                ]),
            ],
            condition=IfCondition(LaunchConfiguration('gui')),
            output='screen',
        )],
    )

    clock_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='clock_bridge',
        output='screen',
        arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'],
    )

    return LaunchDescription([
        world_arg,
        model_arg,
        gui_arg,
        SetEnvironmentVariable('GZ_SIM_RESOURCE_PATH', resource_path),
        SetEnvironmentVariable('GZ_GUI_PLUGIN_PATH', gui_plugin_path),
        gazebo,
        gazebo_gui,
        clock_bridge,
    ])
