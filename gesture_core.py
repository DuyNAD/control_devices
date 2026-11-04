"""Shared touchless gesture logic. See docs/gesture-rules.md for the agreed rules.

Nothing here touches a camera, MediaPipe or the operating system, so each
platform app can reuse it and only has to turn GestureEvents into real input.
Only the laptop gestures exist so far; phone gestures will sit beside them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum

Point = tuple[float, float]
Point3D = tuple[float, float, float]


class Finger(Enum):
    THUMB = "thumb"
    INDEX = "index"
    MIDDLE = "middle"
    RING = "ring"
    PINKY = "pinky"


# MediaPipe hand landmark indices.
WRIST = 0
INDEX_MCP = 5
MIDDLE_MCP = 9
PINKY_MCP = 17

# The hand skeleton: each finger's chain of joints from its base to its tip.
FINGER_CHAIN = {
    Finger.THUMB: (1, 2, 3, 4),
    Finger.INDEX: (5, 6, 7, 8),
    Finger.MIDDLE: (9, 10, 11, 12),
    Finger.RING: (13, 14, 15, 16),
    Finger.PINKY: (17, 18, 19, 20),
}
PALM_BONES = ((0, 1), (0, 5), (5, 9), (9, 13), (13, 17), (0, 17))
LONG_FINGERS = (Finger.INDEX, Finger.MIDDLE, Finger.RING, Finger.PINKY)
PINCH_FINGERS = (Finger.INDEX, Finger.MIDDLE)


@dataclass(frozen=True)
class GestureConfig:
    """Starting values from the rules, meant to be tuned during trials."""

    # Times, in milliseconds.
    activate_hold_ms: int = 1000
    deactivate_absent_ms: int = 2000
    pinch_confirm_ms: int = 150
    tap_max_ms: int = 300
    dwell_click_ms: int = 1000
    dwell_double_click_ms: int = 2000
    dwell_settle_ms: int = 400  # the cursor catching up after a pinch does not count as moving
    pointing_confirm_ms: int = 300  # the pointing pose must last this long before a click counts
    drag_hold_ms: int = 700
    fist_confirm_ms: int = 150
    hand_switch_ms: int = 300
    finger_glitch_ms: int = 100

    # Distances, in palm widths.
    pinch_on_ratio: float = 0.25
    pinch_off_ratio: float = 0.40
    still_radius: float = 0.25
    activate_still_radius: float = 0.30

    # Not fixed by the rules; chosen as starting points for the trial.
    dwell_radius: float = 0.02  # fraction of the screen
    direction_dominance: float = 1.5
    flick_speed: float = 4.0  # palm widths per second
    finger_extended_angle: float = 140.0  # degrees at the finger's middle joint
    finger_curled_angle: float = 130.0
    finger_curled_reach: float = 1.2  # fingertip to palm centre, in palm widths
    finger_max_speed: float = 15.0  # hand sizes per second, relative to the wrist
    same_hand_max_jump: float = 0.25  # fraction of frame height
    closer_hand_ratio: float = 1.25  # how much bigger a hand must look to take over
    min_hand_size: float = 0.08  # fraction of frame height; smaller hands are far away
    control_zone: tuple[float, float, float, float] = (0.3, 0.3, 0.7, 0.7)
    cursor_min_cutoff: float = 1.2
    cursor_beta: float = 3.0
    cursor_d_cutoff: float = 1.0

    # None allows either hand; "Left" or "Right" picks a dominant hand.
    preferred_hand: str | None = None


@dataclass(frozen=True)
class FingerPointer:
    """One finger as its own pointer: identity, position and state."""

    finger: Finger
    x: float
    y: float
    extended: bool


@dataclass(frozen=True)
class Hand:
    """One detected hand: 21 normalized landmarks from a mirrored frame."""

    landmarks: tuple[Point, ...]
    aspect: float = 1.0  # frame width / height, keeps distances undistorted
    handedness: str | None = None
    # 3D landmarks in metres, centred on the hand. Joint angles from these hold up
    # when fingers point at the camera, where the flat image makes them look bent.
    world: tuple[Point3D, ...] | None = None

    def distance(self, a: Point, b: Point) -> float:
        return math.hypot((a[0] - b[0]) * self.aspect, a[1] - b[1])

    @property
    def palm_width(self) -> float:
        width = self.distance(self.landmarks[INDEX_MCP], self.landmarks[PINKY_MCP])
        return max(width, 1e-6)

    @property
    def size(self) -> float:
        """How big the hand looks. Takes the longer palm axis, so turning sideways
        does not make a hand seem far away."""
        length = self.distance(self.landmarks[WRIST], self.landmarks[MIDDLE_MCP])
        return max(self.palm_width, length)

    def tip(self, finger: Finger) -> Point:
        return self.landmarks[FINGER_CHAIN[finger][-1]]

    def _joint(self, index: int) -> Point3D:
        if self.world is not None:
            return self.world[index]
        x, y = self.landmarks[index]
        return (x * self.aspect, y, 0.0)

    def middle_joint_angle(self, finger: Finger) -> float:
        """Degrees at the finger's middle joint: 180 is straight, small is bent."""
        base, middle, upper, _ = (self._joint(i) for i in FINGER_CHAIN[finger])
        to_base = [a - b for a, b in zip(base, middle)]
        to_upper = [a - b for a, b in zip(upper, middle)]
        lengths = math.hypot(*to_base) * math.hypot(*to_upper)
        if lengths == 0:
            return 0.0
        cosine = sum(a * b for a, b in zip(to_base, to_upper)) / lengths
        return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))

    def is_extended(self, finger: Finger, angle: float = 140.0) -> bool:
        if finger is Finger.THUMB:
            # The thumb folds across the palm, so measure from the pinky side.
            tip = self.tip(finger)
            joint = self.landmarks[FINGER_CHAIN[finger][2]]
            base = self.landmarks[PINKY_MCP]
            return self.distance(tip, base) > self.distance(joint, base)
        return self.middle_joint_angle(finger) >= angle

    def is_curled(self, finger: Finger, angle: float = 130.0, reach: float = 1.2) -> bool:
        """Bent and folded into the palm. Reach keeps a pinching finger, which
        bends but stays out in front of the palm, from counting as curled."""
        return self.middle_joint_angle(finger) < angle and self.reach(finger) < reach

    def reach(self, finger: Finger) -> float:
        """Fingertip to palm centre, in palm widths. Turning or moving the hand
        leaves this unchanged, so a change means the finger itself moved."""
        palm = [self._joint(i) for i in (WRIST, INDEX_MCP, PINKY_MCP)]
        centre = [sum(axis) / 3 for axis in zip(*palm)]
        tip = self._joint(FINGER_CHAIN[finger][-1])
        palm_width = max(math.dist(palm[1], palm[2]), 1e-6)
        return math.dist(tip, centre) / palm_width

    def curled_count(self, angle: float = 130.0, reach: float = 1.2) -> int:
        return sum(self.is_curled(finger, angle, reach) for finger in LONG_FINGERS)

    def pointers(self, angle: float = 140.0) -> dict[Finger, FingerPointer]:
        result = {}
        for finger in Finger:
            x, y = self.tip(finger)
            result[finger] = FingerPointer(finger, x, y, self.is_extended(finger, angle))
        return result

    def is_pointing(self, extended_angle: float = 140.0, folded_angle: float = 130.0) -> bool:
        """Index straight, with the middle, ring and pinky fingers folded. The thumb
        is free, since people hold it in many ways when pointing."""
        if not self.is_extended(Finger.INDEX, extended_angle):
            return False
        others = (Finger.MIDDLE, Finger.RING, Finger.PINKY)
        return all(self.middle_joint_angle(finger) < folded_angle for finger in others)

    def is_open(self, angle: float = 140.0) -> bool:
        return all(self.is_extended(finger, angle) for finger in Finger)

    def pinch_ratio(self, finger: Finger) -> float:
        return self.distance(self.tip(Finger.THUMB), self.tip(finger)) / self.palm_width

    def pinch_point(self, finger: Finger) -> Point:
        thumb, other = self.tip(Finger.THUMB), self.tip(finger)
        return ((thumb[0] + other[0]) / 2, (thumb[1] + other[1]) / 2)


class OneEuroFilter:
    """One Euro filter: steady when the hand is slow, responsive when it is fast."""

    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float = 1.0) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self) -> None:
        self._value: float | None = None
        self._speed = 0.0
        self._t_ms = 0.0

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, value: float, t_ms: float) -> float:
        if self._value is None or t_ms <= self._t_ms:
            if self._value is None:
                self._value = value
                self._t_ms = t_ms
            return self._value
        dt = (t_ms - self._t_ms) / 1000
        speed = (value - self._value) / dt
        self._speed += self._alpha(self.d_cutoff, dt) * (speed - self._speed)
        cutoff = self.min_cutoff + self.beta * abs(self._speed)
        self._value += self._alpha(cutoff, dt) * (value - self._value)
        self._t_ms = t_ms
        return self._value


class HandSelector:
    """Follows the hand closest to the screen and ignores any others.

    A single camera has no real depth, so the hand that looks biggest counts as
    closest. A closer hand must stay clearly bigger for a moment before it takes
    over, and it never takes over in the middle of a gesture.
    """

    def __init__(self, config: GestureConfig) -> None:
        self.config = config
        self.switched = False  # True for the frame on which the hand changed
        self._wrist: Point | None = None
        self._last_seen_ms = 0
        self._closer_since_ms: int | None = None

    def select(self, hands: list[Hand], t_ms: int, locked: bool = False) -> Hand | None:
        c = self.config
        self.switched = False
        if self._wrist is not None and t_ms - self._last_seen_ms >= c.deactivate_absent_ms:
            self._wrist = None

        hands = [h for h in hands if h.size >= c.min_hand_size]
        if c.preferred_hand is not None:
            hands = [h for h in hands if h.handedness == c.preferred_hand]
        if not hands:
            return None

        closest = max(hands, key=lambda h: h.size)
        if self._wrist is None:
            chosen = closest
            self._closer_since_ms = None
        else:
            chosen = min(hands, key=lambda h: h.distance(h.landmarks[WRIST], self._wrist))
            jump = chosen.distance(chosen.landmarks[WRIST], self._wrist)
            if jump > c.same_hand_max_jump:
                return None  # A different hand: the followed one is still missing.
            if self._closer_hand_takes_over(chosen, closest, t_ms, locked):
                chosen = closest
                self.switched = True

        self._wrist = chosen.landmarks[WRIST]
        self._last_seen_ms = t_ms
        return chosen

    def _closer_hand_takes_over(
        self, current: Hand, closest: Hand, t_ms: int, locked: bool
    ) -> bool:
        c = self.config
        if locked or closest.size < current.size * c.closer_hand_ratio:
            self._closer_since_ms = None
            return False
        if self._closer_since_ms is None:
            self._closer_since_ms = t_ms
        if t_ms - self._closer_since_ms < c.hand_switch_ms:
            return False
        self._closer_since_ms = None
        return True


class SkeletonStabilizer:
    """Stops a misread finger from being taken for a real movement.

    When fingers overlap, MediaPipe can briefly place a joint on the wrong finger.
    One or two fingers leaping faster than a finger can move, measured relative
    to the wrist, keep their last good position. A real movement persists, so it
    is accepted after a short wait.
    """

    MAX_GLITCHING_FINGERS = 2  # More than this means the whole hand really moved.

    def __init__(self, config: GestureConfig) -> None:
        self.config = config
        self.reset()

    def reset(self) -> None:
        self._offsets: dict[Finger, list[Point]] = {}
        self._suspect_since_ms: dict[Finger, int] = {}
        self._t_ms = 0

    @staticmethod
    def _measure(hand: Hand) -> dict[Finger, list[Point]]:
        wrist_x, wrist_y = hand.landmarks[WRIST]
        size = max(hand.size, 1e-6)
        return {
            finger: [
                (
                    (hand.landmarks[i][0] - wrist_x) * hand.aspect / size,
                    (hand.landmarks[i][1] - wrist_y) / size,
                )
                for i in chain
            ]
            for finger, chain in FINGER_CHAIN.items()
        }

    def update(self, hand: Hand, t_ms: int) -> Hand:
        c = self.config
        measured = self._measure(hand)
        dt = (t_ms - self._t_ms) / 1000
        if not self._offsets or dt <= 0:
            self._offsets = measured
            self._t_ms = t_ms
            return hand

        leaping = [
            finger
            for finger in Finger
            if math.dist(measured[finger][-1], self._offsets[finger][-1]) / dt > c.finger_max_speed
        ]
        if len(leaping) > self.MAX_GLITCHING_FINGERS:
            leaping = []

        held = []
        for finger in Finger:
            if finger in leaping:
                since = self._suspect_since_ms.setdefault(finger, t_ms)
                if t_ms - since < c.finger_glitch_ms:
                    held.append(finger)
                    continue
            self._suspect_since_ms.pop(finger, None)
            self._offsets[finger] = measured[finger]
        self._t_ms = t_ms
        return self._restore(hand, held) if held else hand

    def _restore(self, hand: Hand, held: list[Finger]) -> Hand:
        wrist_x, wrist_y = hand.landmarks[WRIST]
        size = max(hand.size, 1e-6)
        points = list(hand.landmarks)
        for finger in held:
            for index, (x, y) in zip(FINGER_CHAIN[finger], self._offsets[finger]):
                points[index] = (wrist_x + x * size / hand.aspect, wrist_y + y * size)
        return replace(hand, landmarks=tuple(points))


class FistTracker:
    """A fist is all four long fingers curled, and it ends once two have opened."""

    def __init__(self, config: GestureConfig) -> None:
        self.config = config
        self.reset()

    def reset(self) -> None:
        self.closed = False
        self._changing_since_ms: int | None = None

    def update(self, hand: Hand, t_ms: int) -> bool:
        c = self.config
        curled = hand.curled_count(c.finger_curled_angle, c.finger_curled_reach)
        changing = curled <= 2 if self.closed else curled == len(LONG_FINGERS)
        if not changing:
            self._changing_since_ms = None
            return self.closed
        if self._changing_since_ms is None:
            self._changing_since_ms = t_ms
        if t_ms - self._changing_since_ms >= c.fist_confirm_ms:
            self.closed = not self.closed
            self._changing_since_ms = None
        return self.closed


class PinchChange(Enum):
    NONE = "none"
    STARTED = "started"
    SWITCHED = "switched"  # still unconfirmed, but now closer to the other finger
    CONFIRMED = "confirmed"
    REJECTED = "rejected"  # opened again before it was confirmed
    RELEASED = "released"


class PinchTracker:
    """Thumb + index / thumb + middle pinches with hysteresis and confirmation."""

    def __init__(self, config: GestureConfig) -> None:
        self.config = config
        self.reset()

    def reset(self) -> None:
        self.finger: Finger | None = None
        self.confirmed = False
        self.started_ms = 0
        self._finger_since_ms = 0

    def update(self, hand: Hand, t_ms: int) -> PinchChange:
        ratios = {finger: hand.pinch_ratio(finger) for finger in PINCH_FINGERS}
        closest = min(ratios, key=ratios.get)

        if self.finger is None:
            if ratios[closest] < self.config.pinch_on_ratio:
                self.finger = closest
                self.started_ms = t_ms
                self._finger_since_ms = t_ms
                return PinchChange.STARTED
            return PinchChange.NONE

        if self.confirmed:
            if ratios[self.finger] > self.config.pinch_off_ratio:
                self.reset()
                return PinchChange.RELEASED
            return PinchChange.NONE

        if ratios[closest] > self.config.pinch_off_ratio:
            self.reset()
            return PinchChange.REJECTED
        if closest is not self.finger:
            self.finger = closest
            self._finger_since_ms = t_ms
            return PinchChange.SWITCHED
        if t_ms - self._finger_since_ms >= self.config.pinch_confirm_ms:
            self.confirmed = True
            return PinchChange.CONFIRMED
        return PinchChange.NONE


class EventType(Enum):
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    PINCH_REJECTED = "pinch_rejected"
    TAP = "tap"
    DOUBLE_TAP = "double_tap"  # a full double click, sent later than the dwell's TAP
    RIGHT_CLICK = "right_click"
    DRAG_READY = "drag_ready"
    DRAG_START = "drag_start"
    DRAG_END = "drag_end"
    SCROLL = "scroll"
    SWIPE = "swipe"
    ZOOM = "zoom"
    UNDO = "undo"
    REDO = "redo"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class GestureEvent:
    type: EventType
    t_ms: int
    cursor: Point
    amount: float = 0.0  # SCROLL, ZOOM: palm widths moved, positive means up
    direction: str = ""  # SWIPE: "left" or "right"
    cancelled_op: str = ""  # CANCELLED: the operation that was interrupted


class Operation(Enum):
    IDLE = "idle"
    PINCH_PENDING = "pinch_pending"
    PINCH_HOLD = "pinch_hold"
    DRAG_READY = "drag_ready"
    DRAGGING = "dragging"
    SCROLLING = "scrolling"
    SWIPING = "swiping"
    ZOOMING = "zooming"
    UNDO_REDO = "undo_redo"


@dataclass
class FrameResult:
    active: bool
    operation: Operation
    pinch_finger: Finger | None
    cursor: Point
    activation_progress: float
    drag_progress: float
    dwell_progress: float  # rings completed, from 0 to 2
    hand: Hand | None
    pointers: dict[Finger, FingerPointer] = field(default_factory=dict)
    events: list[GestureEvent] = field(default_factory=list)
    fist: bool = False
    pointing: bool = False  # steady in the pointing pose, the only pose that can click


class LaptopGestureEngine:
    """Turns hand frames into laptop gesture events (rules table: Laptop)."""

    def __init__(self, config: GestureConfig | None = None) -> None:
        self.config = config or GestureConfig()
        self._selector = HandSelector(self.config)
        self._pinch = PinchTracker(self.config)
        self._stabilizer = SkeletonStabilizer(self.config)
        self._fist = FistTracker(self.config)
        self._filter_x = self._new_filter()
        self._filter_y = self._new_filter()
        self.active = False
        self.operation = Operation.IDLE
        self.cursor: Point = (0.5, 0.5)
        self._events: list[GestureEvent] = []
        self._last_seen_ms = 0
        self._open_since_ms: int | None = None
        self._open_anchor: Point = (0.0, 0.0)
        self._wait_for_release = False
        self._pinch_started_ms = 0
        self._locked_right = False
        self._dwell_anchor: Point | None = None
        self._dwell_since_ms = 0
        self._dwell_armed = False
        self._dwell_clicked = False
        self._dwell_settled_ms = 0
        self._now_ms = 0
        self._pointing_since_ms: int | None = None
        self._pointing_steady = False
        self._dwell_arm_on_pose = False
        self._pose_can_arm_after_ms = 0
        self._reset_motion((0.0, 0.0), 0)

    def _new_filter(self) -> OneEuroFilter:
        c = self.config
        return OneEuroFilter(c.cursor_min_cutoff, c.cursor_beta, c.cursor_d_cutoff)

    def _reset_motion(self, point: Point, t_ms: int) -> None:
        self._anchor = point
        self._previous = point
        self._previous_ms = t_ms
        self._peak_speed_x = 0.0
        self._last_axis_point = point

    def _emit(self, event_type: EventType, t_ms: int, cursor: Point | None = None, **fields) -> None:
        self._events.append(GestureEvent(event_type, t_ms, cursor or self.cursor, **fields))

    def update(self, hands: list[Hand], t_ms: int) -> FrameResult:
        self._events = []
        self._now_ms = t_ms
        locked = self.operation is not Operation.IDLE
        hand = self._selector.select(hands, t_ms, locked=locked)
        if hand is None:
            self._stabilizer.reset()
            self._fist.reset()
            self._update_without_hand(t_ms)
        else:
            if self._selector.switched:
                self._stabilizer.reset()
                self._fist.reset()
                self._cancel_dwell()
            hand = self._stabilizer.update(hand, t_ms)
            self._fist.update(hand, t_ms)
            self._last_seen_ms = t_ms
            if self.active:
                self._update_active(hand, t_ms)
            else:
                self._update_activation(hand, t_ms)

        pointers = hand.pointers(self.config.finger_extended_angle) if hand else {}
        return FrameResult(
            active=self.active,
            operation=self.operation,
            pinch_finger=self._pinch.finger,
            cursor=self.cursor,
            activation_progress=self._activation_progress(t_ms),
            drag_progress=self._drag_progress(t_ms),
            dwell_progress=self._dwell_progress(t_ms),
            hand=hand,
            pointers=pointers,
            events=self._events,
            fist=self._fist.closed,
            pointing=self._pointing_steady,
        )

    def _activation_progress(self, t_ms: int) -> float:
        if self.active or self._open_since_ms is None:
            return 0.0
        return min(1.0, (t_ms - self._open_since_ms) / self.config.activate_hold_ms)

    def _drag_progress(self, t_ms: int) -> float:
        if self._pinch.finger is not Finger.INDEX:
            return 0.0
        if self.operation not in (Operation.PINCH_PENDING, Operation.PINCH_HOLD):
            return 0.0
        return min(1.0, (t_ms - self._pinch.started_ms) / self.config.drag_hold_ms)

    def _dwell_progress(self, t_ms: int) -> float:
        if not self._dwell_armed or self._dwell_anchor is None:
            return 0.0
        c = self.config
        elapsed = t_ms - self._dwell_since_ms
        if elapsed < c.dwell_click_ms:
            return elapsed / c.dwell_click_ms
        second_ring = c.dwell_double_click_ms - c.dwell_click_ms
        return min(2.0, 1.0 + (elapsed - c.dwell_click_ms) / second_ring)

    def _cancel_dwell(self) -> None:
        """The cursor must leave its current spot before another dwell can start."""
        self._stop_dwell()
        self._dwell_arm_on_pose = False
        self._pointing_since_ms = None
        self._pointing_steady = False
        # Fingers still opening after a pinch or fist are not a choice to point again.
        self._pose_can_arm_after_ms = self._now_ms + self.config.dwell_settle_ms

    def _stop_dwell(self) -> None:
        self._dwell_anchor = None
        self._dwell_armed = False
        self._dwell_clicked = False

    def _update_idle_pose(self, hand: Hand, t_ms: int) -> None:
        """Only a steady pointing pose can click. Open hands and everything in
        between do nothing, however long they rest."""
        c = self.config
        if not hand.is_pointing(c.finger_extended_angle, c.finger_curled_angle):
            self._pointing_since_ms = None
            self._pointing_steady = False
            self._stop_dwell()
            # Choosing to point from another pose starts a ring without moving first.
            if t_ms >= self._pose_can_arm_after_ms:
                self._dwell_arm_on_pose = True
            return

        if self._pointing_since_ms is None:
            self._pointing_since_ms = t_ms
        self._pointing_steady = t_ms - self._pointing_since_ms >= c.pointing_confirm_ms
        if self._pointing_steady:
            self._update_dwell(t_ms)

    def _update_dwell(self, t_ms: int) -> None:
        if self._dwell_anchor is None:
            self._dwell_anchor = self.cursor
            self._dwell_since_ms = t_ms
            self._dwell_settled_ms = t_ms + self.config.dwell_settle_ms
            self._dwell_armed = self._dwell_arm_on_pose
            self._dwell_arm_on_pose = False
            return

        c = self.config
        elapsed = t_ms - self._dwell_since_ms
        left = math.dist(self.cursor, self._dwell_anchor) > c.dwell_radius
        if left:
            self._dwell_anchor = self.cursor
            self._dwell_since_ms = t_ms
            # After a scroll the cursor jumps to the hand. Pausing to read then must not click.
            self._dwell_armed = self._dwell_armed or t_ms >= self._dwell_settled_ms
            self._dwell_clicked = False
        elif self._dwell_armed and not self._dwell_clicked and elapsed >= c.dwell_click_ms:
            self._emit(EventType.TAP, t_ms, cursor=self._dwell_anchor)
            self._dwell_clicked = True
        elif self._dwell_armed and elapsed >= c.dwell_double_click_ms:
            self._emit(EventType.DOUBLE_TAP, t_ms, cursor=self._dwell_anchor)
            self._dwell_armed = False

    def _update_without_hand(self, t_ms: int) -> None:
        self._open_since_ms = None
        self._cancel_dwell()
        if self.operation is not Operation.IDLE:
            # Losing the hand mid-gesture cancels it; it never counts as a release.
            if self.operation is not Operation.PINCH_PENDING:
                self._emit(EventType.CANCELLED, t_ms, cancelled_op=self.operation.value)
            self.operation = Operation.IDLE
            self._pinch.reset()
            self._wait_for_release = True
        if self.active and t_ms - self._last_seen_ms >= self.config.deactivate_absent_ms:
            self.active = False
            self._wait_for_release = False
            self._filter_x.reset()
            self._filter_y.reset()
            self._emit(EventType.DEACTIVATED, t_ms)

    def _update_activation(self, hand: Hand, t_ms: int) -> None:
        c = self.config
        wrist = hand.landmarks[WRIST]
        if not hand.is_open(c.finger_extended_angle):
            self._open_since_ms = None
            return
        moved = hand.distance(wrist, self._open_anchor) / hand.palm_width
        if self._open_since_ms is None or moved > c.activate_still_radius:
            self._open_since_ms = t_ms
            self._open_anchor = wrist
            return
        if t_ms - self._open_since_ms >= c.activate_hold_ms:
            self.active = True
            self._open_since_ms = None
            self._move_cursor(hand, t_ms, frozen=False)
            self._emit(EventType.ACTIVATED, t_ms)

    def _move_cursor(self, hand: Hand, t_ms: int, frozen: bool) -> None:
        left, top, right, bottom = self.config.control_zone
        x, y = hand.tip(Finger.INDEX)
        x = min(1.0, max(0.0, (x - left) / (right - left)))
        y = min(1.0, max(0.0, (y - top) / (bottom - top)))
        # The filter keeps running while frozen so it has no stale lag afterwards.
        smooth = (self._filter_x(x, t_ms), self._filter_y(y, t_ms))
        if not frozen:
            self.cursor = smooth

    def _update_fist(self, hand: Hand, t_ms: int) -> None:
        """A fist cancels whatever is under way, and the cursor holds still."""
        if self.operation is not Operation.IDLE:
            if self.operation is not Operation.PINCH_PENDING:
                self._emit(EventType.CANCELLED, t_ms, cancelled_op=self.operation.value)
            self.operation = Operation.IDLE
        self._pinch.reset()
        self._cancel_dwell()
        self._wait_for_release = True
        self._move_cursor(hand, t_ms, frozen=True)

    def _update_active(self, hand: Hand, t_ms: int) -> None:
        if self._fist.closed:
            self._update_fist(hand, t_ms)
            return

        c = self.config
        closing = hand.curled_count(c.finger_curled_angle, c.finger_curled_reach) == len(LONG_FINGERS)
        if closing and self.operation is not Operation.IDLE:
            # Fingers parting on the way to a fist look like a release, so wait
            # for the fist to be confirmed, which cancels the operation instead.
            self._move_cursor(hand, t_ms, frozen=True)
            return

        if self._wait_for_release:
            ratios = [hand.pinch_ratio(finger) for finger in PINCH_FINGERS]
            if min(ratios) > self.config.pinch_off_ratio:
                self._wait_for_release = False
            self._move_cursor(hand, t_ms, frozen=False)
            self._cancel_dwell()
            return

        finger_before = self._pinch.finger
        change = self._pinch.update(hand, t_ms)
        finger = self._pinch.finger

        if change is PinchChange.STARTED:
            self.operation = Operation.PINCH_PENDING
            self._pinch_started_ms = t_ms  # The tracker clears its copy on release.
            self._reset_motion(hand.pinch_point(finger), t_ms)
        elif change is PinchChange.SWITCHED:
            self._reset_motion(hand.pinch_point(finger), t_ms)
        elif change is PinchChange.REJECTED:
            self.operation = Operation.IDLE
            self._emit(EventType.PINCH_REJECTED, t_ms)
        elif change is PinchChange.RELEASED:
            self._finish_pinch(finger_before, hand, t_ms)
        elif change is PinchChange.CONFIRMED:
            self.operation = Operation.PINCH_HOLD

        if finger is not None:
            self._track_motion(hand, finger, t_ms)
        if self._pinch.confirmed:
            self._advance_operation(hand, finger, t_ms)

        # The cursor holds still through a pinch so it cannot drift off target.
        self._move_cursor(
            hand,
            t_ms,
            frozen=self.operation not in (Operation.IDLE, Operation.DRAGGING),
        )

        if self.operation is Operation.IDLE and not closing:
            self._update_idle_pose(hand, t_ms)
        else:
            self._cancel_dwell()

    def _delta(self, hand: Hand, a: Point, b: Point) -> Point:
        palm = hand.palm_width
        return ((b[0] - a[0]) * hand.aspect / palm, (b[1] - a[1]) / palm)

    def _track_motion(self, hand: Hand, finger: Finger, t_ms: int) -> None:
        point = hand.pinch_point(finger)
        dt = (t_ms - self._previous_ms) / 1000
        if dt > 0:
            step_x, _ = self._delta(hand, self._previous, point)
            self._peak_speed_x = max(self._peak_speed_x, abs(step_x) / dt)
        self._previous = point
        self._previous_ms = t_ms

    def _advance_operation(self, hand: Hand, finger: Finger, t_ms: int) -> None:
        c = self.config
        point = hand.pinch_point(finger)
        dx, dy = self._delta(hand, self._anchor, point)
        moved = math.hypot(dx, dy) > c.still_radius

        if self.operation is Operation.PINCH_HOLD:
            if moved:
                self._lock_direction(dx, dy, finger, point)
            elif finger is Finger.INDEX and t_ms - self._pinch.started_ms >= c.drag_hold_ms:
                self.operation = Operation.DRAG_READY
                self._emit(EventType.DRAG_READY, t_ms)
        elif self.operation is Operation.DRAG_READY:
            if moved:
                self.operation = Operation.DRAGGING
                self._emit(EventType.DRAG_START, t_ms)
        elif self.operation in (Operation.SCROLLING, Operation.ZOOMING):
            _, step_y = self._delta(hand, self._last_axis_point, point)
            self._last_axis_point = point
            if step_y:
                kind = EventType.SCROLL if self.operation is Operation.SCROLLING else EventType.ZOOM
                self._emit(kind, t_ms, amount=-step_y)

    def _lock_direction(self, dx: float, dy: float, finger: Finger, point: Point) -> None:
        dominance = self.config.direction_dominance
        if abs(dy) >= abs(dx) * dominance:
            vertical = True
        elif abs(dx) >= abs(dy) * dominance:
            vertical = False
        else:
            return  # Still diagonal: wait until one direction is clear.
        self._locked_right = dx > 0
        self._last_axis_point = point
        if finger is Finger.INDEX:
            self.operation = Operation.SCROLLING if vertical else Operation.SWIPING
        else:
            self.operation = Operation.ZOOMING if vertical else Operation.UNDO_REDO

    def _finish_pinch(self, finger: Finger, hand: Hand, t_ms: int) -> None:
        c = self.config
        operation = self.operation
        self.operation = Operation.IDLE
        held_ms = t_ms - self._pinch_started_ms
        flicked = self._peak_speed_x >= c.flick_speed

        if operation is Operation.PINCH_HOLD and held_ms < c.tap_max_ms:
            dx, dy = self._delta(hand, self._anchor, self._previous)
            if finger is Finger.MIDDLE and math.hypot(dx, dy) <= c.still_radius:
                self._emit(EventType.RIGHT_CLICK, t_ms)
        elif operation is Operation.DRAGGING:
            self._emit(EventType.DRAG_END, t_ms)
        elif operation is Operation.SWIPING and flicked:
            direction = "right" if self._locked_right else "left"
            self._emit(EventType.SWIPE, t_ms, direction=direction)
        elif operation is Operation.UNDO_REDO and flicked:
            self._emit(EventType.REDO if self._locked_right else EventType.UNDO, t_ms)
