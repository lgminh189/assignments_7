#!/usr/bin/env python3
"""Detect RGB camera objects and publish an annotated ROS Image for RViz."""
import json
import math
import time

import cv2
from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import String


class YoloDetector(Node):
    def __init__(self):
        super().__init__('yolo_detector')
        defaults = dict(
            image_topic='/oakd/rgb/preview/image_raw',
            annotated_topic='/yolo/annotated_image', model='yolov8n.pt',
            confidence=0.45, inference_rate=2.0, device='cpu',
            show_window=False, log_interval=2.0,
        )
        for name, value in defaults.items():
            self.declare_parameter(name, value)
        self.confidence = float(self.get_parameter('confidence').value)
        rate = float(self.get_parameter('inference_rate').value)
        self.log_interval = float(self.get_parameter('log_interval').value)
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError('confidence must be between 0 and 1')
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError('inference_rate must be finite and positive')
        if not math.isfinite(self.log_interval) or self.log_interval <= 0:
            raise ValueError('log_interval must be finite and positive')
        from ultralytics import YOLO
        self.model = YOLO(self.get_parameter('model').value)
        self.device = self.get_parameter('device').value
        self.show_window = self.get_parameter('show_window').value
        self.bridge = CvBridge()
        self.latest = None
        self.last_log = -math.inf
        self.started = time.monotonic()
        self.last_warning = self.started
        self.publisher = self.create_publisher(
            Image, self.get_parameter('annotated_topic').value, qos_profile_sensor_data)
        self.detections = self.create_publisher(String, '/yolo/detections', 10)
        # Depth 1 keeps inference working on recent frames when the camera is faster.
        self.subscription = self.create_subscription(
            Image, self.get_parameter('image_topic').value, self.receive,
            rclpy.qos.QoSProfile(depth=1, reliability=rclpy.qos.ReliabilityPolicy.BEST_EFFORT))
        self.create_timer(1.0 / rate, self.detect)
        self.get_logger().info('YOLO ready; annotated image: '
                               + self.get_parameter('annotated_topic').value)

    def receive(self, msg):
        self.latest = msg

    def detect(self):
        if self.latest is None:
            if time.monotonic() - self.last_warning > 10:
                self.get_logger().warning('No new RGB frame; check camera topic and Gazebo Play')
                self.last_warning = time.monotonic()
            return
        msg, self.latest = self.latest, None
        try:
            image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            result = self.model.predict(
                source=image, conf=self.confidence, device=self.device, verbose=False)[0]
            objects = []
            if result.boxes is not None:
                for box in result.boxes:
                    objects.append(dict(
                        class_id=int(box.cls.item()),
                        name=result.names[int(box.cls.item())],
                        confidence=round(float(box.conf.item()), 4),
                        xyxy=box.xyxy[0].cpu().tolist(),
                    ))
            annotated = result.plot()
            output = self.bridge.cv2_to_imgmsg(annotated, encoding='bgr8')
            output.header = msg.header
            self.publisher.publish(output)
            report = dict(frame_id=msg.header.frame_id,
                          stamp=dict(sec=msg.header.stamp.sec, nanosec=msg.header.stamp.nanosec),
                          detections=objects)
            self.detections.publish(String(data=json.dumps(report)))
            if time.monotonic() - self.last_log >= self.log_interval:
                summary = ', '.join(f"{o['name']} {o['confidence']:.2f}" for o in objects)
                self.get_logger().info(summary or 'No objects above confidence threshold')
                self.last_log = time.monotonic()
            if self.show_window:
                cv2.imshow('TurtleBot 4 YOLO', annotated)
                cv2.waitKey(1)
        except Exception as exc:
            self.get_logger().error(f'Image/inference error: {exc}', throttle_duration_sec=5.0)


def main():
    rclpy.init()
    node = None
    code = 0
    try:
        node = YoloDetector()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        rclpy.logging.get_logger('yolo_detector').error(
            str(exc))
        code = 1
    finally:
        if node is not None:
            if node.show_window:
                cv2.destroyAllWindows()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return code


if __name__ == '__main__':
    raise SystemExit(main())
