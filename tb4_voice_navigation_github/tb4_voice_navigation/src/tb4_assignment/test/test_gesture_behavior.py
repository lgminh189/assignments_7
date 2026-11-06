"""Safety/state transitions and complete measured trajectories, without hardware."""
import math
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from gesture_logic import BehaviorController, GestureGate, WaveDetector


def held(controller, label, now):
    controller.gesture(label, now)
    controller.gesture(label, now + .3)


def selected(label='Pointing_Up'):
    c = BehaviorController()
    c.observe_pose(0., 0., 0.)
    held(c, label, 0.)
    return c


def running(label='Pointing_Up'):
    c = selected(label)
    held(c, 'Thumb_Up', 1.)
    return c


def test_no_movement_without_confirmation():
    c = selected()
    assert c.pending == 'Pointing_Up'
    assert c.tick(.4) == (0., 0.)
    assert not c.plan
    held(c, 'Thumb_Up', 1.)
    assert c.tick(1.3)[0] > 0


def test_confirmation_without_selection_does_nothing():
    c = BehaviorController()
    held(c, 'Thumb_Up', 0.)
    assert not c.plan


@pytest.mark.parametrize('label', ['Open_Palm', 'Closed_Fist'])
def test_stop_and_cancel_are_immediate_and_clear_selection(label):
    c = running()
    c.gesture(label, 1.31)
    assert not c.plan and c.pending is None
    assert c.tick(1.31) == (0., 0.)
    held(c, 'Thumb_Up', 3.)
    assert not c.plan


@pytest.mark.parametrize('label', ['None', 'garbage'])
def test_invalid_heartbeats_do_not_keep_robot_moving(label):
    c = running()
    for now in (1.5, 1.8, 2.0, 2.2):
        c.gesture(label, now)
        c.tick(now)
    assert not c.plan
    assert 'signal lost' in c.status


def test_selection_expires_even_with_valid_heartbeats():
    c = selected()
    for now in range(1, 10):
        c.gesture('Pointing_Up', float(now))
        c.tick(float(now))
    held(c, 'Thumb_Up', 10.)
    assert not c.plan


@pytest.mark.parametrize('sensors_ok,obstacle', [(False, False), (True, True)])
def test_sensor_or_obstacle_fault_latches_stop(sensors_ok, obstacle):
    c = running()
    assert c.tick(1.3, sensors_ok, obstacle) == (0., 0.)
    assert not c.plan
    assert c.tick(1.4) == (0., 0.)


def test_filter_noise_hold_release_and_no_repeat():
    gate = GestureGate()
    assert gate.update('Victory', 0.) is None
    assert gate.update('Thumb_Up', .1) is None
    assert gate.update('Victory', .2) is None
    assert gate.update('Victory', .5) == 'Victory'
    assert gate.update('Victory', 5.) is None
    assert gate.update('No_Hand', 5.1) is None
    assert gate.update('No_Hand', 5.4) is None
    assert gate.update('Victory', 5.5) is None
    assert gate.update('Victory', 5.8) == 'Victory'


def test_wave_requires_alternating_strokes_not_static_palm_or_jitter():
    wave = WaveDetector()
    for i in range(20):
        assert wave.update('Open_Palm', .5 + .01 * (i % 2), i * .05) == 'Open_Palm'
    assert wave.update('Open_Palm', .7, 1.0) == 'Open_Palm'
    assert wave.update('Open_Palm', .3, 1.2) == 'Open_Palm'
    assert wave.update('Open_Palm', .7, 1.4) == 'Wave'
    assert wave.update('Open_Palm', .7, 1.5) == 'Wave'
    assert wave.update('Thumb_Up', None, 1.6) == 'Thumb_Up'
    assert wave.update('Open_Palm', .7, 1.7) == 'Open_Palm'


def test_wave_tracking_gap_resets_history():
    wave = WaveDetector()
    wave.update('Open_Palm', .3, 0.)
    wave.update('Open_Palm', .7, .1)
    wave.update('Open_Palm', .3, .2)
    assert wave.update('Open_Palm', .7, 1.) == 'Open_Palm'


@pytest.mark.parametrize('label', ['Pointing_Up', 'Victory', 'Wave'])
@pytest.mark.parametrize('heartbeat', ['Thumb_Up', 'No_Hand'])
def test_complete_motion_and_held_confirmation_does_not_repeat(label, heartbeat):
    c = running(label)
    x = y = yaw = 0.
    now, dt = 1.3, .02
    segments = []
    last_len = len(c.plan)
    for _ in range(10000):
        c.gesture(heartbeat, now)
        v, w = c.tick(now)
        if v or w:
            if len(c.plan) == last_len:
                if not segments or segments[-1] != (v, w):
                    segments.append((v, w))
            x += v * math.cos(yaw + w*dt/2) * dt
            y += v * math.sin(yaw + w*dt/2) * dt
            yaw += w * dt
            c.observe_pose(x, y, math.atan2(math.sin(yaw), math.cos(yaw)))
        last_len = len(c.plan)
        now += dt
        if not c.plan:
            break
    assert c.status == 'IDLE: completed'
    assert abs(x) < .05 and abs(y) < .05 and abs(yaw - (2*math.pi if label == 'Victory' else 0)) < .05
    if label == 'Pointing_Up':
        assert [math.copysign(1, v) for v, _ in segments] == [1, -1] * 4
    for _ in range(100):
        c.gesture('Thumb_Up', now)
        assert c.tick(now) == (0., 0.)
        now += dt


def test_motion_timeout_when_odometry_stuck():
    c = running()
    c.tick(1.3)
    for now in range(2, 20):
        c.gesture('Thumb_Up', float(now))
        c.tick(float(now))
    assert not c.plan
    assert 'motion timeout' in c.status


def test_camera_gap_does_not_count_as_stable_hold():
    gate = GestureGate()
    assert gate.update('Victory', 0.) is None
    assert gate.update('Victory', 2.) is None
    assert gate.update('Victory', 2.3) == 'Victory'


def test_circle_respects_angular_speed_limit():
    c = BehaviorController(linear_speed=.25, angular_speed=.35, circle_radius=.3)
    c.observe_pose(0., 0., 0.)
    held(c, 'Victory', 0.)
    held(c, 'Thumb_Up', 1.)
    v, w = c.tick(1.3)
    assert w <= .35
    assert v / w == pytest.approx(.3)


@pytest.mark.parametrize('ranges,blocked', [
    ([2.] * 360, False), ([math.inf] * 360, False),
    ([math.nan] * 360, True), ([0.] * 360, True),
    ([.2] * 360, True), ([], True),
])
def test_scan_invalid_or_near_obstacle(ranges, blocked):
    from types import SimpleNamespace
    from sensor_msgs.msg import LaserScan
    from robot_behavior_node import RobotBehaviorNode
    scan = LaserScan(angle_min=-math.pi, angle_increment=2*math.pi/360,
                     range_min=.16, range_max=12., ranges=ranges)
    fake = SimpleNamespace(scan=scan, controller=running(), clearance=.55)
    assert RobotBehaviorNode.obstacle(fake) is blocked


def test_reverse_motion_checks_rear_sector():
    from types import SimpleNamespace
    from sensor_msgs.msg import LaserScan
    from robot_behavior_node import RobotBehaviorNode
    c = running()
    c.plan.popleft()  # Reverse segment after first forward leg.
    ranges = [2.] * 360
    ranges[0] = .2  # Rear, angle=-pi.
    scan = LaserScan(angle_min=-math.pi, angle_increment=2*math.pi/360,
                     range_min=.16, range_max=12., ranges=ranges)
    fake = SimpleNamespace(scan=scan, controller=c, clearance=.55)
    assert RobotBehaviorNode.obstacle(fake)
    c.plan.popleft()  # Next forward segment must not react to rear-only obstacle.
    assert not RobotBehaviorNode.obstacle(fake)


def test_remembers_selection_while_hand_is_lowered():
    c = selected()
    for i in range(1, 31):
        now = .3 + i * .1
        c.gesture('No_Hand', now)
        assert c.tick(now) == (0., 0.)
        assert c.pending == 'Pointing_Up'
    held(c, 'Thumb_Up', 3.5)
    assert c.tick(3.8)[0] > 0


def test_stream_loss_still_stops_after_lowering_hand():
    c = running()
    c.gesture('No_Hand', 1.5)
    assert c.tick(1.5)[0] > 0
    assert c.tick(2.4) == (0., 0.)
    assert not c.plan and 'signal lost' in c.status
    c.gesture('No_Hand', 2.5)
    assert c.tick(2.5) == (0., 0.)  # Reconnection must not resume.


@pytest.mark.parametrize('label', ['Open_Palm', 'Closed_Fist', 'Camera_Error'])
def test_stop_after_hand_has_been_lowered(label):
    c = running()
    c.gesture('No_Hand', 1.5)
    assert c.tick(1.5)[0] > 0
    c.gesture(label, 1.51)
    assert c.tick(1.51) == (0., 0.)
    assert not c.plan and c.pending is None


def test_no_hand_cannot_confirm_selection():
    c = selected()
    for i in range(1, 21):
        now = .3 + i * .1
        c.gesture('No_Hand', now)
        assert c.tick(now) == (0., 0.)
    assert c.pending == 'Pointing_Up' and not c.plan


def test_wave_survives_brief_missing_or_low_confidence_categories():
    wave = WaveDetector()
    assert wave.update('Open_Palm', .4, 0.) == 'Open_Palm'
    assert wave.update('Open_Palm', .5, .15) == 'Open_Palm'
    assert wave.update('No_Hand', None, .2) == 'No_Hand'
    assert wave.update('No_Hand', .4, .35, palm_visible=True) == 'No_Hand'
    assert wave.update('No_Hand', .5, .55, palm_visible=True) == 'Wave'
    # Keep the palm visible briefly to pass the command stability filter.
    assert wave.update('No_Hand', .5, .8, palm_visible=True) == 'Wave'


def test_wave_uses_full_stroke_extreme_for_slow_reversal():
    wave = WaveDetector()
    xs = [.40, .44, .48, .52, .55, .53, .50, .47, .44, .42, .45, .48, .51]
    labels = [wave.update('Open_Palm', x, i*.15) for i, x in enumerate(xs)]
    assert labels[-1] == 'Wave'


def test_one_way_sweep_is_not_a_wave():
    wave = WaveDetector()
    for i in range(20):
        assert wave.update('Open_Palm', .2 + i*.025, i*.1) == 'Open_Palm'
    assert len(wave.turns) == 1


@pytest.mark.parametrize('label', ['Thumb_Up', 'Victory', 'Pointing_Up', 'Closed_Fist', 'Camera_Error'])
def test_other_command_resets_wave_even_when_geometry_looks_open(label):
    wave = WaveDetector()
    wave.update('Open_Palm', .4, 0.)
    wave.update('Open_Palm', .5, .1)
    wave.update('Open_Palm', .4, .2)
    assert wave.update(label, .5, .3, palm_visible=True) == label
    assert not wave.turns and not wave.latched


def test_open_palm_geometry_fallback_rejects_folded_fingers():
    from types import SimpleNamespace
    from gesture_logic import open_palm_geometry
    points = [SimpleNamespace(x=.5, y=.8) for _ in range(21)]
    points[5].x, points[17].x = .4, .6
    for pip, tip in [(6, 8), (10, 12), (14, 16), (18, 20)]:
        points[pip].y, points[tip].y = .6, .4
    assert open_palm_geometry(points)
    for tip in [8, 12, 16]:
        points[tip].y = .75
    assert not open_palm_geometry(points)


def test_wave_pipeline_selects_after_brief_classification_loss_and_requires_confirmation():
    wave, c = WaveDetector(), BehaviorController()
    c.observe_pose(0., 0., 0.)
    samples = [(0., .4, 'Open_Palm', True), (.15, .5, 'No_Hand', True),
               (.3, None, 'No_Hand', False), (.45, .4, 'No_Hand', True),
               (.6, .5, 'No_Hand', True), (.75, .5, 'No_Hand', True),
               (.9, .5, 'No_Hand', True)]
    for now, x, label, visible in samples:
        c.gesture(wave.update(label, x, now, palm_visible=visible), now)
        assert c.tick(now) == (0., 0.)
    assert c.pending == 'Wave'
    held(c, 'Thumb_Up', 1.5)
    assert c.tick(1.8)[1] > 0
