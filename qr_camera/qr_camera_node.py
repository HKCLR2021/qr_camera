import sys
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
        self.declare_parameter("port", 12345)

        self.host = self.get_parameter("host").value
        self.port = self.get_parameter("port").value

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()

        self.get_logger().info(f"Server listening on {self.host}:{self.port}")

        self.client_threads = []
        self.client_threads_lock = threading.Lock()
        self.client_sockets = []  # Added to track client sockets
        self.client_sockets_lock = threading.Lock()  # Lock for client sockets
        self.shutting_down_event = threading.Event()  # Event to signal shutdown

        self.server_thread = threading.Thread(target=self.run_server)
        self.server_thread.start()

        # Publishers
        self.cam_tri_pub_ = self.create_publisher(CameraTrigger, "qr_camera_scan", 10)
        self.cam_status_pub_ = self.create_publisher(CameraStatus, "qr_camera_status", 10)

        # Timers
        self.status_timer = self.create_timer(1.0, self.status_cb)

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
        try:
            client_socket.close()
        except OSError:
            pass  # Socket might already be closed during shutdown

        with self.client_sockets_lock:
            if client_socket in self.client_sockets:
                self.client_sockets.remove(client_socket)
                
        with self.client_threads_lock:
            if threading.current_thread() in self.client_threads:
                self.client_threads.remove(threading.current_thread())

        self.get_logger().info(f"Connection closed and cleaned up for {address}")

    def run_server(self):
        try:
            while not self.shutting_down_event.is_set() and rclpy.ok():
                try:
                    client_socket, address = self.server_socket.accept()
                    with self.client_sockets_lock:
                        self.client_sockets.append(client_socket)
                    client_thread = threading.Thread(target=self.handle_client, args=(client_socket, address))
                    client_thread.start()
                    with self.client_threads_lock:
                            self.client_threads.append(client_thread)

                except OSError as e:
                    if self.shutting_down_event.is_set():
                        break  # Expected during shutdown when server socket is closed
                    self.get_logger().error(f"Error accepting connection: {e}")           
        except KeyboardInterrupt:
            self.get_logger().info("Server shutting down...")
        finally:
            try:
                self.server_socket.close()
            except OSError:
                pass

            # Close all client sockets to unblock threads
            with self.client_sockets_lock:
                for client_socket in self.client_sockets[:]:  # Copy list to avoid modification issues
                    try:
                        client_socket.close()
                    except OSError:
                        pass  # Socket might already be closed
                self.client_sockets.clear()

            with self.client_threads_lock:
                for thread in self.client_threads[:]:  # Copy list to avoid modification issues
                    thread.join()
                self.client_threads.clear()

            self.get_logger().info("Server shutdown complete")

    def destroy_node(self):
        self.shutting_down_event.set()
        try:
            self.server_socket.close()  # Close server socket to break accept()
        except OSError:
            pass
        self.server_thread.join()

        self.get_logger().info("destroy_node is called")
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    try:
        node = QrCamera()
        executor = MultiThreadedExecutor()
        executor.add_node(node)
        try:
            executor.spin()
        finally:
            executor.shutdown()
            node.destroy_node()
    except KeyboardInterrupt:
        pass
    except ExternalShutdownException:
        sys.exit(1)
    finally:
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
