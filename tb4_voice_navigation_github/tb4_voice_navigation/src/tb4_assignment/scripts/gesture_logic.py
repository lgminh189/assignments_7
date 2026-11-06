"""Gesture filtering and measured motion state machine; independent of ROS/camera."""
from collections import deque
from dataclasses import dataclass
import math

GESTURES = {'Wave', 'Pointing_Up', 'Victory', 'Thumb_Up', 'Open_Palm', 'Closed_Fist'}


def open_palm_geometry(points):
    """Fallback for moving palms whose static category temporarily loses confidence."""
    if len(points) != 21:
        return False
    if not all(math.isfinite(p.x) and math.isfinite(p.y) for p in points):
        return False
    distance = lambda a, b: math.hypot(a.x - b.x, a.y - b.y)
    if distance(points[5], points[17]) < 0.04:
        return False
    extended = sum(distance(points[tip], points[0]) >
                   1.12 * distance(points[pip], points[0])
                   for pip, tip in [(6, 8), (10, 12), (14, 16), (18, 20)])
    return extended >= 3


class WaveDetector:
    """Track alternating palm strokes, tolerating short recognition dropouts."""
    def __init__(self, amplitude=0.06, window=3.0, gap_timeout=0.35):
        if not all(math.isfinite(v) and v > 0 for v in (amplitude, window, gap_timeout)):
            raise ValueError('Wave thresholds must be finite and positive')
        self.amplitude, self.window = amplitude, window
        self.gap_timeout = gap_timeout
        self.reset()

    def reset(self):
        self.anchor = None
        self.direction = 0
        self.turns = deque()
        self.latched = False
        self.last_time = None

    def update(self, label, x, now, palm_visible=None):
        if self.last_time is not None and now - self.last_time > self.gap_timeout:
            self.reset()
        if label in GESTURES - {'Open_Palm', 'Wave'} or label == 'Camera_Error':
            self.reset()
            return label
        visible = label == 'Open_Palm' if palm_visible is None else palm_visible
        if not visible or x is None or not math.isfinite(x):
            # Keep history briefly, but never publish a cached Wave on a frame
            # with no visible palm. A real tracking loss resets on the next call.
            return label
        self.last_time = now
        if self.anchor is None:
            self.anchor = x
        if self.direction == 0:
            delta = x - self.anchor
            if abs(delta) >= self.amplitude:
                self.direction = 1 if delta > 0 else -1
                self.turns.append(now)
                self.anchor = x
        else:
            # Keep the stroke extreme, so even slow, smooth reversals count.
            delta = (x - self.anchor) * self.direction
            if delta > 0:
                self.anchor = x
            elif delta <= -self.amplitude:
                self.direction *= -1
                self.turns.append(now)
                self.anchor = x
        while self.turns and now - self.turns[0] > self.window:
            self.turns.popleft()
        self.latched |= len(self.turns) >= 3
        return 'Wave' if self.latched else label


class GestureGate:
    """Stable hold + release + cooldown; safety gestures bypass the hold."""
    def __init__(self, hold=0.25, release=0.25, cooldown=0.7):
        self.hold, self.release, self.cooldown = hold, release, cooldown
        self.candidate = None
        self.since = 0.0
        self.latched = None
        self.last_event = -math.inf
        self.last_observation = -math.inf

    def update(self, label, now):
        if now - self.last_observation > 0.4:
            # A long camera/DDS gap cannot count toward a stable hold. Keep the
            # latch so reconnecting with the same held command cannot repeat it.
            self.candidate = None
        self.last_observation = now
        if label != self.candidate:
            self.candidate, self.since = label, now
        if label not in GESTURES:
            if now - self.since >= self.release:
                self.latched = None
            return None
        if label in {'Open_Palm', 'Closed_Fist'}:
            self.latched = label
            return label
        if (label != self.latched and now - self.since >= self.hold
                and now - self.last_event >= self.cooldown):
            self.latched, self.last_event = label, now
            return label
        return None


@dataclass(frozen=True)
class Segment:
    linear: float
    angular: float
    target: float  # metres when straight; radians otherwise


class BehaviorController:
    def __init__(self, signal_timeout=0.8, selection_timeout=8.0,
                 linear_speed=0.12, angular_speed=0.35, leg_distance=0.35,
                 circle_radius=0.6):
        values = (signal_timeout, selection_timeout, linear_speed, angular_speed,
                  leg_distance, circle_radius)
        if not all(math.isfinite(v) and v > 0 for v in values):
            raise ValueError('Motion parameters must be finite and positive')
        if linear_speed > 0.25 or angular_speed > 0.8 or leg_distance > 1.0:
            raise ValueError('Speed/distance exceeds demo limits (0.25 m/s, 0.8 rad/s, 1 m)')
        if circle_radius < 0.3 or circle_radius > 1.5:
            raise ValueError('Circle radius must be within [0.3, 1.5] m')
        self.signal_timeout, self.selection_timeout = signal_timeout, selection_timeout
        self.speed, self.turn_speed = linear_speed, angular_speed
        self.distance, self.radius = leg_distance, circle_radius
        self.gate = GestureGate()
        self.last_signal = -math.inf
        self.pending = None
        self.selected_at = 0.0
        self.running = None
        self.plan = deque()
        self.pose = None
        self.origin = None
        self.angle = 0.0
        self.segment_started = None
        self.status = 'IDLE'

    def stop(self, reason):
        self.pending = self.running = None
        self.plan.clear()
        self.origin = None
        self.segment_started = None
        self.status = reason

    def observe_pose(self, x, y, yaw):
        if self.pose is not None and self.plan:
            self.angle += math.atan2(math.sin(yaw - self.pose[2]),
                                     math.cos(yaw - self.pose[2]))
        self.pose = (x, y, yaw)

    def gesture(self, label, now):
        # A processed frame with no hand is a healthy camera heartbeat. The
        # selected/confirmed behavior is remembered while the user lowers a hand.
        if label in GESTURES or label == 'No_Hand':
            self.last_signal = now
        event = self.gate.update(label, now)
        if label == 'Camera_Error':
            self.stop('STOPPED: camera unavailable')
        elif event in {'Open_Palm', 'Closed_Fist'}:
            self.stop('STOPPED' if event == 'Open_Palm' else 'IDLE: cancelled')
        elif event in {'Wave', 'Pointing_Up', 'Victory'} and not self.plan:
            self.pending, self.selected_at = event, now
            self.status = f'SELECTED: {event}; show Thumb_Up'
        elif event == 'Thumb_Up' and self.pending and not self.plan:
            if now - self.selected_at > self.selection_timeout:
                self.stop('IDLE: selection expired')
                return
            self.running, self.pending = self.pending, None
            v, w = self.speed, self.turn_speed
            if self.running == 'Pointing_Up':
                self.plan.extend([Segment(v, 0., self.distance),
                                  Segment(-v, 0., self.distance)] * 4)
            elif self.running == 'Victory':
                circle_speed = min(v, w * self.radius)
                self.plan.append(Segment(circle_speed, circle_speed / self.radius, 2 * math.pi))
            else:
                self.plan.extend(Segment(0., sign * w, angle) for sign, angle in
                                 [(1, .45), (-1, .9), (1, .9), (-1, .45)])
            self.origin = None
            self.status = f'RUNNING: {self.running}'

    def tick(self, now, sensors_ok=True, obstacle=False):
        if now - self.last_signal > self.signal_timeout:
            if self.pending or self.plan:
                self.stop('STOPPED: control signal lost')
        if self.pending and now - self.selected_at > self.selection_timeout:
            self.stop('IDLE: selection expired')
        if not self.plan:
            return 0., 0.
        if not sensors_ok or obstacle or self.pose is None:
            self.stop('STOPPED: obstacle or stale/invalid sensors')
            return 0., 0.
        segment = self.plan[0]
        if self.origin is None:
            self.origin, self.angle, self.segment_started = self.pose, 0., now
        expected = segment.target / (abs(segment.angular) or abs(segment.linear))
        if now - self.segment_started > expected * 3 + 3:
            self.stop('STOPPED: motion timeout')
            return 0., 0.
        if segment.angular:
            progress = self.angle * (1 if segment.angular > 0 else -1)
        else:
            dx, dy = self.pose[0] - self.origin[0], self.pose[1] - self.origin[1]
            progress = (dx * math.cos(self.origin[2]) + dy * math.sin(self.origin[2]))
            progress *= 1 if segment.linear > 0 else -1
        if progress >= segment.target:
            self.plan.popleft()
            self.origin = None
            if not self.plan:
                self.running = None
                self.status = 'IDLE: completed'
            return 0., 0.
        return segment.linear, segment.angular
