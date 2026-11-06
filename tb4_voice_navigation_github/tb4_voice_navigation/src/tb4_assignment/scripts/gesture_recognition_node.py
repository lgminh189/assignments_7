#!/usr/bin/env python3
"""Laptop webcam + MediaPipe Tasks Gesture Recognizer (VIDEO mode)."""
from pathlib import Path
import time

import cv2
import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import String

from gesture_logic import GESTURES, WaveDetector, open_palm_geometry


class GestureRecognitionNode(Node):
    def __init__(self):
        super().__init__('gesture_recognition_node')
        for key, value in dict(camera_index=0, model_path='', confidence=0.65,
                               show_window=True, webcam_only=False, frame_rate=15.0,
                               wave_amplitude=0.06, wave_window=3.0,
                               wave_min_confidence=0.45).items():
            self.declare_parameter(key, value)
        p = lambda name: self.get_parameter(name).value
        self.threshold, self.show = p('confidence'), p('show_window')
        rate = p('frame_rate')
        if not 0 < self.threshold <= 1 or not 1 <= rate <= 60:
            raise ValueError('confidence in (0, 1]; frame_rate in [1, 60]')
        self.publisher = self.create_publisher(String, '/detected_gesture', 1)
        self.state = 'IDLE'
        self.create_subscription(String, '/robot_behavior/state',
                                 lambda msg: setattr(self, 'state', msg.data), 1)
        self.wave = WaveDetector(amplitude=p('wave_amplitude'), window=p('wave_window'))
        self.wave_threshold = p('wave_min_confidence')
        if not 0 < self.wave_threshold <= 1:
            raise ValueError('wave_min_confidence must be in (0, 1]')
        self.previous_label = None
        self.recognizer = None
        self.capture = None
        self.mp = None
        self.last_timestamp = -1
        self.failed_frames = 0
        self.closed = False
        if not p('webcam_only'):
            model = Path(p('model_path')).expanduser()
            if not model.is_file():
                raise FileNotFoundError('Set model_path to gesture_recognizer.task; see README')
            import mediapipe as mp
            self.mp = mp
            options = mp.tasks.vision.GestureRecognizerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_hands=1, min_hand_detection_confidence=0.6,
                min_hand_presence_confidence=0.6, min_tracking_confidence=0.6)
            self.recognizer = mp.tasks.vision.GestureRecognizer.create_from_options(options)
        self.capture = cv2.VideoCapture(p('camera_index'), cv2.CAP_V4L2)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.capture.isOpened():
            self.close()
            raise RuntimeError('Cannot open laptop webcam; check camera_index and permissions')
        self.create_timer(1.0 / rate, self.on_frame,
                          clock=Clock(clock_type=ClockType.STEADY_TIME))
        self.get_logger().info('Webcam ready. Show one hand; remove it to rearm a command.')

    def on_frame(self):
        ok, frame = self.capture.read()
        now = time.monotonic()
        label, score, palm_x = 'No_Hand', 0., None
        raw_label, palm_visible = 'None', False
        if not ok:
            self.failed_frames += 1
            self.wave.reset()
            self.publisher.publish(String(data='Camera_Error'))
            if self.failed_frames == 1:
                self.get_logger().error('Webcam frame missing; control heartbeat invalidated')
            return
        self.failed_frames = 0
        frame = cv2.flip(frame, 1)
        if self.recognizer is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
            timestamp = max(self.last_timestamp + 1, int(now * 1000))
            self.last_timestamp = timestamp
            result = self.recognizer.recognize_for_video(image, timestamp)
            if result.gestures and result.gestures[0]:
                category = result.gestures[0][0]
                raw_label = category.category_name
                score = float(category.score)
                if score >= self.threshold and category.category_name in GESTURES:
                    label = category.category_name
            # Landmarks are useful even when the moving hand's category is None
            # or falls below the threshold used for static robot commands.
            if result.hand_landmarks:
                points = result.hand_landmarks[0]
                palm_x = sum(points[i].x for i in (0, 5, 9, 13, 17)) / 5
                palm_visible = (label == 'Open_Palm'
                                or (raw_label == 'Open_Palm' and score >= self.wave_threshold)
                                or open_palm_geometry(points))
                h, w = frame.shape[:2]
                for point in points:
                    cv2.circle(frame, (int(point.x*w), int(point.y*h)), 3, (0, 255, 0), -1)
        label = self.wave.update(label, palm_x, now, palm_visible=palm_visible)
        if self.recognizer is None:
            # Preview mode cannot certify that recognition/stop detection works.
            label = 'Camera_Error'
        # Every processed frame publishes a fresh result, including No_Hand. No
        # independent heartbeat may keep the robot moving when inference freezes.
        self.publisher.publish(String(data=label))
        if label == 'Wave' and self.previous_label != 'Wave':
            self.get_logger().info('Wave detected; hold palm briefly, then show Thumb_Up to confirm')
        self.previous_label = label
        if self.show:
            cv2.putText(frame, f'{label}  AI: {raw_label} {score:.2f}', (12, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 255, 255), 2)
            cv2.putText(frame, self.state, (12, 60), cv2.FONT_HERSHEY_SIMPLEX,
                        .5, (0, 255, 255), 1)
            progress = min(len(self.wave.turns), 3)
            hint = ('Wave OK: hold briefly, then Thumb Up' if self.wave.latched else
                    f'Wave: {progress}/3 strokes | open palm, move LEFT-RIGHT-LEFT')
            cv2.putText(frame, hint, (12, 90), cv2.FONT_HERSHEY_SIMPLEX,
                        .48, (0, 255, 0) if self.wave.latched else (0, 255, 255), 1)
            cv2.imshow('TurtleBot 4 - Webcam gestures', frame)
            cv2.waitKey(1)  # GUI event processing only; no keyboard motion controls.
            if cv2.getWindowProperty('TurtleBot 4 - Webcam gestures', cv2.WND_PROP_VISIBLE) < 1:
                self.close()
                raise SystemExit(0)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if rclpy.ok():
            self.publisher.publish(String(data='Camera_Error'))
        if self.capture is not None:
            self.capture.release()
        if self.recognizer is not None:
            self.recognizer.close()
        if self.show:
            cv2.destroyAllWindows()


def main(args=None):
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = None
    try:
        node = GestureRecognitionNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
