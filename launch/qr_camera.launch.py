import os

from launch import LaunchDescription
from launch_ros.actions import Node

from ament_index_python.packages import get_package_share_directory

def generate_launch_description():

    params_file = os.path.join(
        get_package_share_directory("qr_camera"),
        "params",
        "server_config.yaml"
    )
    
    ld = LaunchDescription()
    
    node = Node(
        package="qr_camera",
        executable="qr_camera_node",
        name="qr_camera_node",
        output="screen",
        parameters=[params_file]
    )

    ld.add_action(node)

    return ld