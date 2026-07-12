"""M0609 RG2 bringup, 종이 센서, 작업 관리자를 함께 실행하는 통합 launch."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    mode = LaunchConfiguration('mode')
    host = LaunchConfiguration('host')
    port = LaunchConfiguration('port')
    sensor_port = LaunchConfiguration('sensor_port')
    sensor_baudrate = LaunchConfiguration('sensor_baudrate')

    bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare('m0609_rg2_bringup'),
                'launch',
                'bringup.launch.py',
            ])
        ),
        launch_arguments={
            'mode': mode,
            'host': host,
            'port': port,
        }.items(),
    )

    paper_sensor = Node(
        package='cobot_writing',
        executable='paper_sensor_publisher',
        name='paper_sensor_publisher',
        output='screen',
        parameters=[{
            'port': sensor_port,
            'baudrate': sensor_baudrate,
            'topic': 'paper_sensor',
        }],
    )

    task_manager = Node(
        package='cobot_writing',
        executable='task_manager',
        name='task_manager_launcher',
        output='screen',
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'mode',
            default_value='virtual',
            description='Robot operation mode passed to m0609_rg2_bringup: real | virtual',
        ),
        DeclareLaunchArgument(
            'host',
            default_value='127.0.0.1',
            description='Robot IP address in real mode',
        ),
        DeclareLaunchArgument(
            'port',
            default_value='12345',
            description='Robot controller port',
        ),
        DeclareLaunchArgument(
            'sensor_port',
            default_value='/dev/ttyACM0',
            description='Arduino paper sensor serial port',
        ),
        DeclareLaunchArgument(
            'sensor_baudrate',
            default_value='9600',
            description='Arduino paper sensor serial baudrate',
        ),
        bringup,
        paper_sensor,
        TimerAction(period=5.0, actions=[task_manager]),
    ])
