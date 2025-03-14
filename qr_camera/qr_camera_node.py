
import socket
import threading

import rclpy

from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node

from smdps_msgs.msg import CameraState, CameraStatus, CameraTrigger


class QrCamera(Node):
    def __init__(self):
        super().__init__("qr_camera")
        self.declare_parameter("host", "127.0.0.1")
        self.declare_parameter("port", 52007)

        self.host = self.get_parameter("host").value
        self.port = self.get_parameter("port").value

        self.cam_tri_pub_ = self.create_publisher(CameraTrigger, "qr_camera_scan", 10)
        self.cam_status_pub_ = self.create_publisher(CameraStatus, "qr_camera_status", 10)
        self.status_timer = self.create_timer(1.0, self.status_cb)

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()

        self.get_logger().info(f"Server listening on {self.host}:{self.port}")

        self.client_threads = []
        self.client_threads_lock = threading.Lock()  # Add a lock for thread safety

        self.server_thread = threading.Thread(target=self.run_server)
        self.server_thread.start()

    def status_cb(self):
        # To be implemented
        pass

    def handle_client(self, client_socket, address):
        self.get_logger().info(f"New connection from {address}")

        while True:
            try:
                data = client_socket.recv(1024)
                if not data:
                    self.get_logger().info(f"Client {address} disconnected gracefully")
                    break
                raw_message = data.decode("utf-8").strip()

                # TODO: parse the raw_message
                parts = raw_message.split('#')
                if len(parts) != 2:
                    self.get_logger().error(f"Invalid message format from {address}: {raw_message}")
                    continue
                try:
                    msg = CameraTrigger()
                    msg.header.stamp = self.get_clock().now().to_msg()
                    msg.header.frame_id = "qr_scan"
                    msg.camera_id = int(parts[0])
                    msg.material_box_id = int(parts[1])
                    self.cam_tri_pub_.publish(msg)
                except ValueError as e:
                    self.get_logger().error(f"Invalid number format in message from {address}: {raw_message} - {e}")
                except Exception as e:
                    self.get_logger().error(f"Unexpected error processing message from {address}: {e}")

                self.get_logger().info(f"Received from {address}: {raw_message}")
            except (ConnectionError, ConnectionResetError) as e:
                self.get_logger().info(f"Connection lost from {address}: {e}")
                break
            except UnicodeDecodeError as e:
                self.get_logger().error(f"Failed to decode message from {address}: {e}")
                continue

        self.get_logger().info(f"Connection closed from {address}")
        client_socket.close()

        with self.client_threads_lock:
            self.client_threads.remove(threading.current_thread())
            self.get_logger().info(f"Removed a thread from client_threads")

    def run_server(self):
        try:
            while rclpy.ok():
                client_socket, address = self.server_socket.accept()
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket, address))
                client_thread.start()
                with self.client_threads_lock:
                    self.client_threads.append(client_thread)
        except KeyboardInterrupt:
            self.get_logger().info("Server shutting down...")
        finally:
            self.server_socket.close()
            with self.client_threads_lock:
                for thread in self.client_threads:
                    thread.join()


def main(args=None):
    try:
        rclpy.init(args=args)
        node = QrCamera()
        executor = MultiThreadedExecutor()
        executor.add_node(node)
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == "__main__":
    main()
