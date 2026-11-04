import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from gesture_core import (
    EventType,
    Finger,
    GestureConfig,
    Hand,
    LaptopGestureEngine,
    OneEuroFilter,
    Operation,
)

FRAME_MS = 33
PALM = 0.1


def make_hand(x=0.5, y=0.5, index=1.0, middle=1.0, handedness=None, aspect=1.0):
    """Index and middle give the thumb-to-tip distance, in palm widths."""
    points = [(x, y)] * 21
    points = list(points)
    half = PALM / 2 / aspect
    points[0] = (x, y + 0.2)  # wrist
    points[5] = (x - half, y)  # index base
    points[9] = (x, y)  # middle base
    points[17] = (x + half, y)  # pinky base
    points[3] = (x - 0.08, y + 0.05)  # thumb joint
    points[4] = (x, y)  # thumb tip
    points[6] = (x - 0.03, y - 0.05)
    points[8] = (x, y - index * PALM)
    points[10] = (x + 0.01, y - 0.05)
    points[12] = (x + middle * PALM, y)
    # Ring and pinky stay up, so this hand is neither open nor a fist.
    set_finger(points, 13, (x + 0.03, y), (x + 0.03, y - 0.09))
    set_finger(points, 17, (x + half, y), (x + half, y - 0.09))
    return Hand(tuple(points), aspect=aspect, handedness=handedness)


def set_finger(points, base_index, base, tip):
    """Puts a finger's four joints on a straight line from base to tip."""
    for step in range(4):
        points[base_index + step] = (
            base[0] + (tip[0] - base[0]) * step / 3,
            base[1] + (tip[1] - base[1]) * step / 3,
        )


def open_hand(x=0.5, y=0.5, handedness=None):
    points = list(make_hand(x, y, handedness=handedness).landmarks)
    points[4] = (x - 0.12, y + 0.02)
    set_finger(points, 5, (x - 0.05, y), (x - 0.04, y - 0.15))
    set_finger(points, 9, (x, y), (x, y - 0.17))
    set_finger(points, 13, (x + 0.03, y), (x + 0.03, y - 0.15))
    set_finger(points, 17, (x + 0.05, y), (x + 0.06, y - 0.12))
    return Hand(tuple(points), handedness=handedness)


def fist_hand(x=0.5, y=0.5, handedness=None):
    points = list(make_hand(x, y, handedness=handedness).landmarks)
    for base_index, offset in ((5, -0.05), (9, -0.02), (13, 0.02), (17, 0.05)):
        points[base_index] = (x + offset, y)
        points[base_index + 1] = (x + offset, y - 0.04)  # knuckle up
        points[base_index + 2] = (x + offset, y - 0.01)  # folding back
        points[base_index + 3] = (x + offset, y + 0.03)  # tip in the palm
    return Hand(tuple(points), handedness=handedness)


def point_hand(x=0.5, y=0.5, handedness=None):
    """Index straight with its tip where make_hand has it, other fingers folded."""
    points = list(fist_hand(x, y, handedness=handedness).landmarks)
    set_finger(points, 5, (x - 0.05, y), (x, y - PALM))
    return Hand(tuple(points), handedness=handedness)


def scaled(hand, factor):
    """The same hand, looking bigger or smaller around its wrist."""
    wrist_x, wrist_y = hand.landmarks[0]
    points = tuple(
        (wrist_x + (px - wrist_x) * factor, wrist_y + (py - wrist_y) * factor)
        for px, py in hand.landmarks
    )
    return Hand(points, aspect=hand.aspect, handedness=hand.handedness)


class Sim:
    def __init__(self, config=None):
        self.engine = LaptopGestureEngine(config)
        self.t = 0
        self.events = []
        self.result = None

    def step(self, hands):
        self.t += FRAME_MS
        self.result = self.engine.update(hands, self.t)
        self.events.extend(self.result.events)
        return self.result

    def hold(self, hand, ms):
        for _ in range(max(1, ms // FRAME_MS)):
            self.step([hand] if hand else [])

    def activate(self):
        self.hold(open_hand(), 1100)
        assert self.engine.active
        self.hold(make_hand(), 200)  # Long enough for the skeleton to accept the new pose.
        self.events.clear()

    def types(self):
        return [event.type for event in self.events]


@pytest.fixture
def sim():
    s = Sim()
    s.activate()
    return s


def pinch_index(x=0.5, y=0.5):
    return make_hand(x, y, index=0.1)


def pinch_middle(x=0.5, y=0.5):
    return make_hand(x, y, middle=0.1)


# Turning on and off


def test_open_palm_held_one_second_activates():
    s = Sim()
    s.hold(open_hand(), 800)
    assert not s.engine.active
    s.hold(open_hand(), 300)
    assert s.engine.active
    assert s.types() == [EventType.ACTIVATED]


def test_moving_the_open_palm_restarts_activation():
    s = Sim()
    s.hold(open_hand(0.3), 800)
    s.hold(open_hand(0.6), 800)
    assert not s.engine.active


def test_closed_hand_does_not_activate():
    s = Sim()
    s.hold(make_hand(), 1500)
    assert not s.engine.active


def test_two_seconds_without_a_hand_deactivates(sim):
    sim.hold(None, 1800)
    assert sim.engine.active
    sim.hold(None, 300)
    assert not sim.engine.active
    assert sim.types() == [EventType.DEACTIVATED]


# Pinch detection


def test_hysteresis_keeps_pinch_between_thresholds(sim):
    sim.hold(pinch_index(), 200)
    sim.hold(make_hand(index=0.3), 200)
    assert sim.engine.operation is Operation.PINCH_HOLD
    sim.hold(make_hand(index=0.5), 50)
    assert sim.engine.operation is Operation.IDLE


def test_value_between_thresholds_does_not_start_pinch(sim):
    sim.hold(make_hand(index=0.3), 300)
    assert sim.engine.operation is Operation.IDLE


def test_pinch_shorter_than_confirmation_is_rejected(sim):
    sim.hold(pinch_index(), 66)
    sim.hold(make_hand(), 33)
    assert sim.types() == [EventType.PINCH_REJECTED]


def test_closest_finger_decides_and_restarts_confirmation(sim):
    sim.hold(pinch_index(), 100)
    sim.hold(pinch_middle(), 100)
    assert sim.result.pinch_finger is Finger.MIDDLE
    assert sim.engine.operation is Operation.PINCH_PENDING
    sim.hold(pinch_middle(), 100)
    assert sim.engine.operation is Operation.PINCH_HOLD


# Click and double click by holding the cursor still


def arrive_at(sim, x=0.45):
    """Moves the hand to a new spot and waits until the cursor has settled there."""
    sim.hold(point_hand(0.35), 700)
    for step in range(1, 6):
        sim.step([point_hand(0.35 + (x - 0.35) * step / 5)])
    for _ in range(100):
        if sim.result.dwell_progress > 0 and not settling(sim, x):
            break
        sim.step([point_hand(x)])
    else:
        raise AssertionError("The ring never started")
    sim.events.clear()


def settling(sim, x):
    target = (x - 0.3) / 0.4
    return abs(sim.result.cursor[0] - target) > 0.02


def leave(sim, x=0.6, frames=10):
    for step in range(1, frames + 1):
        sim.step([point_hand(x + step * 0.01)])


def test_cursor_resting_after_activation_does_not_click():
    s = Sim()
    s.hold(open_hand(), 2200)
    assert s.types() == [EventType.ACTIVATED]
    assert s.result.dwell_progress == 0


def test_first_ring_clicks_at_the_dwell_spot_without_moving(sim):
    arrive_at(sim)
    spot = sim.result.cursor
    sim.hold(point_hand(0.45), 800)
    assert sim.types() == []
    sim.hold(point_hand(0.45), 400)
    assert sim.types() == [EventType.TAP]
    assert sim.events[0].cursor == pytest.approx(spot, abs=0.03)


def test_leaving_after_the_click_sends_nothing_more(sim):
    arrive_at(sim)
    sim.hold(point_hand(0.45), 1200)
    leave(sim)
    assert sim.types() == [EventType.TAP]


def test_a_short_thinking_pause_sends_nothing(sim):
    leave(sim, 0.35, frames=5)
    sim.events.clear()
    sim.hold(point_hand(0.45), 800)
    leave(sim, 0.5)
    assert sim.types() == []


def test_second_ring_sends_a_double_click_after_the_click(sim):
    arrive_at(sim)
    sim.hold(point_hand(0.45), 2200)
    assert sim.types() == [EventType.TAP, EventType.DOUBLE_TAP]
    leave(sim)
    assert sim.types() == [EventType.TAP, EventType.DOUBLE_TAP]


def test_cursor_must_leave_before_rings_start_again(sim):
    arrive_at(sim)
    sim.hold(point_hand(0.45), 5000)
    assert sim.types() == [EventType.TAP, EventType.DOUBLE_TAP]
    assert sim.result.dwell_progress == 0


def test_rings_report_their_progress(sim):
    arrive_at(sim)
    sim.hold(point_hand(0.45), 500)
    assert 0 < sim.result.dwell_progress < 1
    sim.hold(point_hand(0.45), 1000)
    assert 1 < sim.result.dwell_progress < 2


def test_losing_the_hand_during_the_first_ring_sends_no_click(sim):
    arrive_at(sim)
    sim.hold(point_hand(0.45), 500)
    sim.step([])
    sim.hold(point_hand(0.45), 1200)
    assert EventType.TAP not in sim.types()


def test_pinching_during_the_first_ring_sends_no_click(sim):
    arrive_at(sim)
    sim.hold(point_hand(0.45), 500)
    sim.hold(pinch_index(0.45), 200)
    sim.hold(point_hand(0.45), 33)
    assert sim.types() == []


def test_pausing_after_a_scroll_does_not_click(sim):
    sim.hold(pinch_index(), 200)
    for step in range(1, 12):
        sim.step([pinch_index(0.5, 0.5 - step * 0.015)])
    assert sim.engine.operation is Operation.SCROLLING
    sim.events.clear()
    sim.hold(point_hand(0.5, 0.335), 3000)
    assert sim.types() == []
    assert sim.result.dwell_progress == 0


def test_resting_open_hand_never_clicks(sim):
    sim.hold(open_hand(0.35), 300)
    for step in range(1, 6):
        sim.step([open_hand(0.35 + step * 0.03)])
    sim.events.clear()
    sim.hold(open_hand(0.5), 3000)
    assert sim.types() == []
    assert sim.result.dwell_progress == 0


def test_resting_half_closed_hand_never_clicks(sim):
    for step in range(1, 6):
        sim.step([make_hand(0.35 + step * 0.03)])
    sim.events.clear()
    sim.hold(make_hand(0.5), 3000)
    assert sim.types() == []


def test_resting_fist_never_clicks(sim):
    sim.hold(fist_hand(), 3000)
    assert EventType.TAP not in sim.types()
    assert EventType.DOUBLE_TAP not in sim.types()


def test_closing_and_opening_the_hand_repeatedly_never_clicks(sim):
    for _ in range(4):
        sim.hold(open_hand(), 500)
        sim.hold(fist_hand(), 500)
    sim.hold(open_hand(), 1500)
    assert EventType.TAP not in sim.types()
    assert EventType.DOUBLE_TAP not in sim.types()


def test_pointing_after_an_open_hand_clicks_without_moving(sim):
    sim.hold(open_hand(), 800)
    sim.events.clear()
    sim.hold(point_hand(), 600)
    assert sim.types() == []
    assert sim.result.pointing
    sim.hold(point_hand(), 900)
    assert sim.types() == [EventType.TAP]


def test_pose_must_be_steady_before_the_ring_starts(sim):
    sim.hold(open_hand(), 800)
    sim.hold(point_hand(), 200)
    assert not sim.result.pointing
    assert sim.result.dwell_progress == 0


def test_opening_the_hand_during_the_ring_cancels_the_click(sim):
    sim.hold(open_hand(), 800)
    sim.events.clear()
    sim.hold(point_hand(), 900)
    sim.hold(open_hand(), 1000)
    assert sim.types() == []
    assert sim.result.dwell_progress == 0


def test_flickering_pose_restarts_the_count(sim):
    sim.hold(open_hand(), 800)
    sim.events.clear()
    for _ in range(4):
        sim.hold(point_hand(), 600)
        sim.step([make_hand()])
    assert sim.types() == []


def test_changing_pose_allows_a_new_click_after_a_double_click(sim):
    sim.hold(open_hand(), 800)
    sim.events.clear()
    sim.hold(point_hand(), 2600)
    assert sim.types() == [EventType.TAP, EventType.DOUBLE_TAP]
    sim.hold(open_hand(), 800)
    sim.hold(point_hand(), 1500)
    assert sim.types() == [EventType.TAP, EventType.DOUBLE_TAP, EventType.TAP]


def test_pinch_ending_in_the_pointing_pose_needs_a_move_before_clicking(sim):
    sim.hold(pinch_index(), 200)
    sim.hold(make_hand(), 100)
    sim.events.clear()
    sim.hold(point_hand(), 3000)
    assert sim.types() == []


def test_opening_a_fist_into_the_pointing_pose_needs_a_move_before_clicking(sim):
    sim.hold(fist_hand(), 300)
    sim.events.clear()
    sim.hold(point_hand(), 3000)
    assert sim.types() == []


# Fist


def test_all_four_fingers_curled_is_a_fist_after_confirmation():
    s = Sim()
    s.step([fist_hand()])
    assert not s.result.fist
    s.hold(fist_hand(), 200)
    assert s.result.fist


def test_open_hand_and_pinch_are_not_a_fist():
    s = Sim()
    s.hold(open_hand(), 500)
    assert not s.result.fist
    s.hold(pinch_index(), 500)
    assert not s.result.fist


def test_pinching_finger_bent_but_away_from_the_palm_is_not_curled():
    points = list(make_hand().landmarks)
    points[5], points[6], points[7], points[8] = (
        (0.45, 0.5),
        (0.42, 0.42),
        (0.47, 0.40),
        (0.5, 0.42),
    )
    hand = Hand(tuple(points))
    assert hand.middle_joint_angle(Finger.INDEX) < 130
    assert not hand.is_curled(Finger.INDEX)


def test_joint_angles_use_3d_landmarks_when_available():
    flat = open_hand()
    # In the image this finger looks straight, but it bends sharply towards the camera.
    world = [(0.0, 0.0, 0.0)] * 21
    world[5], world[6], world[7] = (0.0, 0.0, 0.0), (0.0, 0.03, 0.0), (0.0, 0.03, -0.03)
    hand = Hand(flat.landmarks, world=tuple(world))
    assert flat.middle_joint_angle(Finger.INDEX) > 170
    assert hand.middle_joint_angle(Finger.INDEX) == pytest.approx(90)


def test_fist_ends_when_two_fingers_open():
    s = Sim()
    s.hold(fist_hand(), 200)
    points = list(fist_hand().landmarks)
    set_finger(points, 5, (0.45, 0.5), (0.45, 0.35))
    one_open = Hand(tuple(points))
    s.hold(one_open, 300)
    assert s.result.fist
    s.hold(make_hand(), 200)
    assert not s.result.fist


def test_fist_cancels_a_drag_and_never_counts_as_release(sim):
    sim.hold(pinch_index(), 800)
    for step in range(1, 6):
        sim.step([pinch_index(0.5 + step * 0.02)])
    assert sim.engine.operation is Operation.DRAGGING
    sim.events.clear()
    sim.hold(fist_hand(0.6), 300)
    assert sim.types() == [EventType.CANCELLED]
    assert sim.engine.operation is Operation.IDLE


def test_cursor_holds_still_during_a_fist(sim):
    sim.hold(fist_hand(), 200)
    frozen = sim.result.cursor
    for step in range(1, 8):
        sim.step([fist_hand(0.5 + step * 0.02)])
    assert sim.result.cursor == frozen


def test_fist_during_the_first_ring_sends_no_click(sim):
    arrive_at(sim)
    sim.hold(point_hand(0.45), 500)
    sim.hold(fist_hand(0.45), 400)
    sim.hold(make_hand(0.45), 300)
    leave(sim)
    assert EventType.TAP not in sim.types()


def test_nothing_starts_until_the_hand_opens_after_a_fist(sim):
    sim.hold(fist_hand(), 300)
    sim.events.clear()
    sim.hold(pinch_middle(), 200)
    sim.hold(make_hand(), 33)
    assert sim.types() == []
    sim.hold(pinch_middle(), 200)
    sim.hold(make_hand(), 33)
    assert sim.types() == [EventType.RIGHT_CLICK]


# Skeleton stability


def with_tip(hand, index, tip):
    points = list(hand.landmarks)
    points[index] = tip
    return Hand(tuple(points), aspect=hand.aspect)


def test_one_frame_misread_finger_keeps_its_last_position(sim):
    hand = make_hand()
    sim.hold(hand, 200)
    before = sim.result.pointers[Finger.RING]
    result = sim.step([with_tip(hand, 16, (0.9, 0.1))])
    assert (result.pointers[Finger.RING].x, result.pointers[Finger.RING].y) == pytest.approx(
        (before.x, before.y)
    )


def test_misread_index_does_not_move_the_cursor(sim):
    hand = make_hand()
    sim.hold(hand, 1000)
    before = sim.result.cursor
    sim.step([with_tip(hand, 8, (0.9, 0.1))])
    assert sim.result.cursor == pytest.approx(before, abs=0.01)


def test_misread_thumb_does_not_start_a_pinch(sim):
    hand = make_hand()
    sim.hold(hand, 200)
    index_tip = hand.landmarks[8]
    sim.step([with_tip(with_tip(hand, 4, (0.1, 0.9)), 4, index_tip)])
    sim.step([hand])
    assert sim.engine.operation is Operation.IDLE


def test_real_finger_movement_is_accepted_after_a_short_wait(sim):
    hand = make_hand()
    sim.hold(hand, 200)
    moved = with_tip(hand, 16, (0.9, 0.1))
    sim.hold(moved, 200)
    assert sim.result.pointers[Finger.RING].x == pytest.approx(0.9)


def test_whole_hand_turning_is_not_treated_as_a_misread(sim):
    sim.hold(fist_hand(), 200)
    result = sim.step([open_hand()])
    assert result.pointers[Finger.MIDDLE].y == pytest.approx(open_hand().tip(Finger.MIDDLE)[1])


def test_quick_thumb_index_pinch_no_longer_clicks(sim):
    sim.hold(pinch_index(), 200)
    sim.hold(make_hand(), 33)
    assert sim.types() == []


# Right click


def test_quick_thumb_middle_pinch_is_right_click(sim):
    sim.hold(pinch_middle(), 200)
    sim.hold(make_hand(), 33)
    assert sim.types() == [EventType.RIGHT_CLICK]


# Drag


def test_drag_needs_hold_then_move_then_release(sim):
    sim.hold(pinch_index(), 800)
    assert sim.types() == [EventType.DRAG_READY]
    for step in range(1, 6):
        sim.step([pinch_index(0.5 + step * 0.02)])
    assert sim.engine.operation is Operation.DRAGGING
    sim.hold(make_hand(0.6), 33)
    assert sim.types() == [EventType.DRAG_READY, EventType.DRAG_START, EventType.DRAG_END]


def test_cursor_follows_during_drag_but_not_during_other_pinches(sim):
    sim.hold(pinch_index(), 200)
    frozen = sim.result.cursor
    for step in range(1, 8):
        sim.step([pinch_index(0.5, 0.5 + step * 0.02)])
    assert sim.engine.operation is Operation.SCROLLING
    assert sim.result.cursor == frozen

    drag = Sim()
    drag.activate()
    drag.hold(pinch_index(), 800)
    before = drag.result.cursor
    for step in range(1, 8):
        drag.step([pinch_index(0.5 + step * 0.02)])
    assert drag.engine.operation is Operation.DRAGGING
    assert drag.result.cursor[0] > before[0] + 0.1


def test_releasing_a_held_pinch_without_moving_does_nothing(sim):
    sim.hold(pinch_index(), 800)
    sim.hold(make_hand(), 33)
    assert sim.types() == [EventType.DRAG_READY]


# Scroll and swipe


def test_vertical_thumb_index_motion_scrolls_with_up_positive(sim):
    sim.hold(pinch_index(), 200)
    for step in range(1, 8):
        sim.step([pinch_index(0.5, 0.5 - step * 0.02)])
    scrolls = [e for e in sim.events if e.type is EventType.SCROLL]
    assert scrolls and all(e.amount > 0 for e in scrolls)


def test_fast_horizontal_flick_is_swipe_on_release(sim):
    sim.hold(pinch_index(), 200)
    for step in range(1, 5):
        sim.step([pinch_index(0.5 - step * 0.03)])
    assert sim.types() == []
    sim.hold(make_hand(0.38), 33)
    swipes = [e for e in sim.events if e.type is EventType.SWIPE]
    assert [e.direction for e in swipes] == ["left"]


def test_slow_horizontal_motion_is_not_swipe(sim):
    sim.hold(pinch_index(), 200)
    for step in range(1, 16):
        sim.step([pinch_index(0.5 + step * 0.002)])
    assert sim.engine.operation is Operation.SWIPING
    sim.hold(make_hand(0.53), 33)
    assert sim.types() == []


def test_direction_stays_locked_after_it_is_clear(sim):
    sim.hold(pinch_index(), 200)
    for step in range(1, 5):
        sim.step([pinch_index(0.5, 0.5 - step * 0.02)])
    assert sim.engine.operation is Operation.SCROLLING
    for step in range(1, 5):
        sim.step([pinch_index(0.5 + step * 0.03, 0.42)])
    assert sim.engine.operation is Operation.SCROLLING


# Zoom, undo and redo


def test_thumb_middle_vertical_motion_zooms_in_going_up(sim):
    sim.hold(pinch_middle(), 200)
    for step in range(1, 8):
        sim.step([pinch_middle(0.5, 0.5 - step * 0.02)])
    zooms = [e for e in sim.events if e.type is EventType.ZOOM]
    assert zooms and all(e.amount > 0 for e in zooms)


@pytest.mark.parametrize(
    "direction, expected", [(-1, EventType.UNDO), (1, EventType.REDO)]
)
def test_thumb_middle_flick_runs_one_command_on_release(sim, direction, expected):
    sim.hold(pinch_middle(), 200)
    for step in range(1, 5):
        sim.step([pinch_middle(0.5 + direction * step * 0.03)])
    assert sim.types() == []
    sim.hold(make_hand(0.5 + direction * 0.12), 33)
    assert sim.types() == [expected]


# Losing the hand


def test_losing_the_hand_cancels_and_never_counts_as_release(sim):
    sim.hold(pinch_index(), 800)
    for step in range(1, 6):
        sim.step([pinch_index(0.5 + step * 0.02)])
    sim.events.clear()
    sim.step([])
    assert sim.types() == [EventType.CANCELLED]
    assert sim.events[0].cancelled_op == "dragging"
    assert EventType.DRAG_END not in sim.types()


def test_hand_returning_still_pinched_waits_for_release(sim):
    sim.hold(pinch_index(), 200)
    sim.step([])
    sim.events.clear()
    sim.hold(pinch_index(), 400)
    assert sim.engine.operation is Operation.IDLE
    sim.hold(make_hand(), 33)
    assert sim.types() == []
    sim.hold(pinch_middle(), 200)
    sim.hold(make_hand(), 33)
    assert sim.types() == [EventType.RIGHT_CLICK]


# One hand, five pointers


def test_hand_of_similar_size_is_ignored(sim):
    first = make_hand(0.3)
    sim.hold(first, 100)
    other_pinching = pinch_index(0.8)
    for _ in range(20):
        sim.step([other_pinching, first])
    assert sim.engine.operation is Operation.IDLE
    assert sim.result.hand is first


def test_closest_hand_is_chosen_first():
    near, far = make_hand(0.7), scaled(make_hand(0.2), 0.6)
    s = Sim()
    assert s.step([far, near]).hand is near


def test_clearly_closer_hand_takes_over_after_a_moment(sim):
    current = make_hand(0.3)
    sim.hold(current, 100)
    closer = scaled(make_hand(0.8), 1.5)
    assert sim.step([current, closer]).hand is current
    sim.hold(None, 0)
    for _ in range(15):
        sim.step([current, closer])
    assert sim.result.hand is closer


def test_briefly_bigger_hand_does_not_take_over(sim):
    current = make_hand(0.3)
    sim.hold(current, 100)
    closer = scaled(make_hand(0.8), 1.5)
    for _ in range(4):
        sim.step([current, closer])
    sim.step([current])
    for _ in range(4):
        sim.step([current, closer])
    assert sim.result.hand is current


def test_closer_hand_does_not_interrupt_a_gesture(sim):
    current = pinch_index(0.3)
    sim.hold(current, 300)
    assert sim.engine.operation is Operation.PINCH_HOLD
    closer = scaled(make_hand(0.8), 1.5)
    for _ in range(20):
        sim.step([current, closer])
    assert sim.result.hand is current


def test_switching_hands_sends_no_click(sim):
    current = point_hand(0.3)
    sim.hold(current, 300)
    closer = scaled(point_hand(0.8), 1.5)
    for _ in range(20):
        sim.step([current, closer])
    assert sim.result.hand is closer
    assert EventType.TAP not in sim.types()


def test_far_away_hand_is_ignored():
    far = scaled(open_hand(), 0.3)
    s = Sim()
    assert s.step([far]).hand is None


def test_another_hand_alone_counts_as_missing_until_timeout(sim):
    far = make_hand(0.95)
    assert sim.step([far]).hand is None
    sim.hold(far, 1800)
    assert sim.result.hand is None
    sim.hold(far, 300)
    assert sim.result.hand is far


def test_preferred_hand_filters_the_other_hand():
    s = Sim(GestureConfig(preferred_hand="Right"))
    s.hold(open_hand(handedness="Left"), 1500)
    assert not s.engine.active
    s.hold(open_hand(handedness="Right"), 1100)
    assert s.engine.active


def test_each_finger_is_its_own_pointer(sim):
    sim.hold(open_hand(), 200)
    result = sim.step([open_hand()])
    assert set(result.pointers) == set(Finger)
    positions = {(p.x, p.y) for p in result.pointers.values()}
    assert len(positions) == 5
    assert all(p.extended for p in result.pointers.values())


# Cursor


def test_small_control_zone_covers_the_whole_screen(sim):
    for step in range(1, 12):
        sim.step([make_hand(0.5 + step * 0.02, 0.5 + step * 0.03)])
    sim.hold(make_hand(0.72, 0.83), 1300)
    assert sim.result.cursor[0] == pytest.approx(1.0, abs=0.02)
    assert sim.result.cursor[1] == pytest.approx(1.0, abs=0.02)


def test_one_euro_smooths_jitter_but_follows_large_moves():
    euro = OneEuroFilter(min_cutoff=1.2, beta=3.0)
    euro(0.5, 0)
    jitter = [euro(0.5 + (0.005 if i % 2 else -0.005), 33 * (i + 1)) for i in range(30)]
    assert max(jitter) - min(jitter) < 0.01
    t = 33 * 31
    for _ in range(15):
        value = euro(0.9, t)
        t += 33
    assert value == pytest.approx(0.9, abs=0.02)


def test_distance_accounts_for_frame_aspect():
    hand = make_hand(aspect=16 / 9)
    assert hand.palm_width == pytest.approx(PALM)
