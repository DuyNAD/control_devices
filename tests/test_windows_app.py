import ctypes
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gesture_core import EventType, FrameResult, GestureEvent, Operation
from windows_app import (
    CANCEL_TONES,
    CLICK_TONES,
    DOUBLE_CLICK_TONES,
    DRAG_END_TONES,
    DRAG_READY_TONES,
    INPUT,
    MOUSEEVENTF_HWHEEL,
    MOUSEEVENTF_WHEEL,
    REDO_TONES,
    RIGHT_CLICK_TONES,
    SWIPE_TONES,
    UNDO_TONES,
    WHEEL_DELTA,
    CursorController,
    LatestFrameCamera,
    WindowsInput,
    is_fast_enough,
    open_camera,
    to_absolute,
)

HAND = object()  # The controller only checks whether a hand is present.


class FakeMouse:
    def __init__(self, delivers=True):
        self.calls = []
        self.delivers = delivers

    def move(self, point):
        self.calls.append(("move", point))

    def click(self, point):
        self.calls.append(("click", point))
        return self.delivers

    def double_click(self, point):
        self.calls.append(("double_click", point))
        return self.delivers

    def right_click(self, point):
        self.calls.append(("right_click", point))
        return self.delivers

    def left_down(self, point):
        self.calls.append(("left_down", point))
        return self.delivers

    def left_up(self, point):
        self.calls.append(("left_up", point))
        return self.delivers

    def scroll(self, notches):
        self.calls.append(("scroll", notches))
        return self.delivers

    def scroll_sideways(self, notches):
        self.calls.append(("scroll_sideways", notches))
        return self.delivers

    def zoom(self, notches):
        self.calls.append(("zoom", notches))
        return self.delivers

    def undo(self):
        self.calls.append(("undo",))
        return self.delivers

    def redo(self):
        self.calls.append(("redo",))
        return self.delivers

    def escape(self):
        self.calls.append(("escape",))
        return self.delivers


def no_sound(tones):
    pass


def frame(cursor=(0.5, 0.5), active=True, hand=HAND, events=(), operation=Operation.IDLE):
    return FrameResult(
        active=active,
        operation=operation,
        pinch_finger=None,
        cursor=cursor,
        activation_progress=0.0,
        drag_progress=0.0,
        dwell_progress=0.0,
        hand=hand,
        events=list(events),
    )


def event(kind, t_ms, cursor=(0.5, 0.5), **fields):
    return GestureEvent(kind, t_ms, cursor, **fields)


def test_absolute_coordinates_cover_the_whole_screen():
    assert to_absolute((0.0, 0.0)) == (0, 0)
    assert to_absolute((1.0, 1.0)) == (65535, 65535)


def test_cursor_moves_while_active():
    mouse = FakeMouse()
    CursorController(mouse, no_sound).apply(frame(cursor=(0.2, 0.3)))
    assert mouse.calls == [("move", (0.2, 0.3))]


def test_inactive_app_leaves_the_mouse_alone():
    mouse = FakeMouse()
    CursorController(mouse, no_sound).apply(frame(active=False))
    assert mouse.calls == []


def test_missing_hand_leaves_the_physical_mouse_in_charge():
    mouse = FakeMouse()
    CursorController(mouse, no_sound).apply(frame(hand=None))
    assert mouse.calls == []


def test_unchanged_position_is_not_sent_again():
    mouse = FakeMouse()
    controller = CursorController(mouse, no_sound)
    controller.apply(frame())
    controller.apply(frame())
    assert len(mouse.calls) == 1


def test_tap_clicks_at_the_dwell_spot_then_cursor_catches_up():
    mouse = FakeMouse()
    tap = event(EventType.TAP, 1000, cursor=(0.4, 0.4))
    CursorController(mouse, no_sound).apply(frame(cursor=(0.45, 0.45), events=[tap]))
    assert mouse.calls == [("click", (0.4, 0.4)), ("move", (0.45, 0.45))]


def test_double_tap_sends_one_double_click():
    mouse = FakeMouse()
    double = event(EventType.DOUBLE_TAP, 1000, cursor=(0.4, 0.4))
    CursorController(mouse, no_sound).apply(frame(cursor=(0.4, 0.4), events=[double]))
    assert mouse.calls == [("double_click", (0.4, 0.4))]


def send(controller, *events, operation=Operation.IDLE):
    controller.apply(frame(hand=None, events=events, operation=operation))


def test_right_click_lands_where_the_pinch_held_the_cursor():
    mouse = FakeMouse()
    send(CursorController(mouse, no_sound), event(EventType.RIGHT_CLICK, 1000, (0.3, 0.4)))
    assert mouse.calls == [("right_click", (0.3, 0.4))]


def test_drag_holds_the_button_from_start_to_end():
    mouse = FakeMouse()
    controller = CursorController(mouse, no_sound)
    send(controller, event(EventType.DRAG_READY, 800))
    assert mouse.calls == []
    send(controller, event(EventType.DRAG_START, 900, (0.2, 0.2)))
    controller.apply(frame(cursor=(0.6, 0.6)))
    send(controller, event(EventType.DRAG_END, 1200, (0.6, 0.6)))
    assert mouse.calls == [
        ("left_down", (0.2, 0.2)),
        ("move", (0.6, 0.6)),
        ("left_up", (0.6, 0.6)),
    ]


def test_cancelled_drag_presses_esc_and_drops_back_at_the_start():
    mouse = FakeMouse()
    controller = CursorController(mouse, no_sound)
    send(controller, event(EventType.DRAG_START, 900, (0.2, 0.2)))
    send(controller, event(EventType.CANCELLED, 1000, (0.6, 0.6), cancelled_op="dragging"))
    assert mouse.calls[1:] == [("escape",), ("left_up", (0.2, 0.2))]


def test_stopping_the_app_mid_drag_releases_the_button():
    mouse = FakeMouse()
    controller = CursorController(mouse, no_sound)
    send(controller, event(EventType.DRAG_START, 900, (0.2, 0.2)))
    controller.cancel_drag()
    assert ("left_up", (0.2, 0.2)) in mouse.calls
    mouse.calls.clear()
    controller.cancel_drag()
    assert mouse.calls == []


def test_cancelling_something_else_touches_no_button():
    mouse = FakeMouse()
    controller = CursorController(mouse, no_sound)
    send(controller, event(EventType.CANCELLED, 1000, cancelled_op="scrolling"))
    assert mouse.calls == []


def test_scroll_collects_small_steps_into_whole_notches():
    mouse = FakeMouse()
    controller = CursorController(mouse, no_sound)
    for _ in range(5):
        send(
            controller,
            event(EventType.SCROLL, 1000, amount=0.1),
            operation=Operation.SCROLLING,
        )
    assert mouse.calls == [("scroll", 1), ("scroll", 1)]


def test_scroll_down_is_negative_and_leftover_does_not_carry_to_the_next_scroll():
    mouse = FakeMouse()
    controller = CursorController(mouse, no_sound)
    send(controller, event(EventType.SCROLL, 1000, amount=-0.2), operation=Operation.SCROLLING)
    assert mouse.calls == []
    controller.apply(frame(hand=None))
    send(controller, event(EventType.SCROLL, 2000, amount=-0.2), operation=Operation.SCROLLING)
    assert mouse.calls == []
    send(controller, event(EventType.SCROLL, 2033, amount=-0.1), operation=Operation.SCROLLING)
    assert mouse.calls == [("scroll", -1)]


def test_zoom_goes_in_when_the_hand_rises():
    mouse = FakeMouse()
    controller = CursorController(mouse, no_sound)
    send(controller, event(EventType.ZOOM, 1000, amount=1.0), operation=Operation.ZOOMING)
    send(controller, event(EventType.ZOOM, 1033, amount=-1.0), operation=Operation.ZOOMING)
    assert mouse.calls == [("zoom", 2), ("zoom", -2)]


def test_swipe_moves_the_content_with_the_hand():
    mouse = FakeMouse()
    controller = CursorController(mouse, no_sound)
    send(controller, event(EventType.SWIPE, 1000, direction="left"))
    send(controller, event(EventType.SWIPE, 2000, direction="right"))
    assert mouse.calls == [("scroll_sideways", 3), ("scroll_sideways", -3)]


def test_undo_and_redo_send_one_shortcut_each():
    mouse = FakeMouse()
    controller = CursorController(mouse, no_sound)
    send(controller, event(EventType.UNDO, 1000))
    send(controller, event(EventType.REDO, 2000))
    assert mouse.calls == [("undo",), ("redo",)]


def test_gestures_with_their_own_sounds():
    played = []
    controller = CursorController(FakeMouse(), played.append)
    send(
        controller,
        event(EventType.RIGHT_CLICK, 1),
        event(EventType.DRAG_READY, 2),
        event(EventType.DRAG_END, 3),
        event(EventType.SWIPE, 4, direction="left"),
        event(EventType.UNDO, 5),
        event(EventType.REDO, 6),
        event(EventType.CANCELLED, 7, cancelled_op="zooming"),
    )
    assert played == [
        RIGHT_CLICK_TONES,
        DRAG_READY_TONES,
        DRAG_END_TONES,
        SWIPE_TONES,
        UNDO_TONES,
        REDO_TONES,
        CANCEL_TONES,
    ]


def test_scroll_and_zoom_are_silent():
    played = []
    controller = CursorController(FakeMouse(), played.append)
    send(controller, event(EventType.SCROLL, 1, amount=1.0), operation=Operation.SCROLLING)
    send(controller, event(EventType.ZOOM, 2, amount=1.0), operation=Operation.ZOOMING)
    assert played == []


def test_wheel_amounts_reach_windows_in_its_own_format():
    up = WindowsInput._wheel(MOUSEEVENTF_WHEEL, 2)
    down = WindowsInput._wheel(MOUSEEVENTF_HWHEEL, -1)
    assert up.u.mi.mouseData == 2 * WHEEL_DELTA
    assert ctypes.c_int32(down.u.mi.mouseData).value == -WHEEL_DELTA


def test_input_has_the_size_windows_expects():
    assert ctypes.sizeof(INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)


def test_click_and_double_click_have_different_sounds():
    played = []
    controller = CursorController(FakeMouse(), played.append)
    controller.apply(frame(hand=None, events=[event(EventType.TAP, 1000)]))
    controller.apply(frame(hand=None, events=[event(EventType.DOUBLE_TAP, 2000)]))
    assert played == [CLICK_TONES, DOUBLE_CLICK_TONES]
    assert CLICK_TONES != DOUBLE_CLICK_TONES


def test_moving_the_cursor_is_silent():
    played = []
    CursorController(FakeMouse(), played.append).apply(frame())
    assert played == []


def test_click_refused_by_windows_is_silent():
    played = []
    mouse = FakeMouse(delivers=False)
    CursorController(mouse, played.append).apply(
        frame(hand=None, events=[event(EventType.TAP, 1000)])
    )
    assert played == []


# Camera


class FakeCapture:
    def __init__(self, frames=None, opened=True, on_read=None):
        self.frames = iter(frames) if frames is not None else None
        self.opened = opened
        self.on_read = on_read
        self.released = False
        self.block = threading.Event()

    def isOpened(self):
        return self.opened

    def read(self):
        if self.on_read:
            self.on_read()
        if self.frames is None:
            return True, "frame"
        try:
            return True, next(self.frames)
        except StopIteration:
            return False, None

    def release(self):
        self.released = True


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_camera_mode_at_full_speed_is_accepted():
    clock = FakeClock()

    def tick():
        clock.now += 1 / 30

    assert is_fast_enough(FakeCapture(on_read=tick), clock)


def test_very_slow_camera_mode_is_rejected():
    clock = FakeClock()

    def tick():
        clock.now += 1.0

    assert not is_fast_enough(FakeCapture(on_read=tick), clock)


def test_camera_mode_without_frames_is_rejected():
    assert not is_fast_enough(FakeCapture(frames=[]), FakeClock())


def test_sharp_camera_mode_is_used_when_it_works():
    sharp = FakeCapture()
    opened = open_camera(0, opener=lambda index, is_sharp: sharp, check=lambda capture: True)
    assert opened is sharp
    assert not sharp.released


def test_slow_sharp_mode_falls_back_to_the_camera_default():
    sharp, plain = FakeCapture(), FakeCapture()
    opener = lambda index, is_sharp: sharp if is_sharp else plain
    assert open_camera(0, opener=opener, check=lambda capture: False) is plain
    assert sharp.released


def test_camera_that_cannot_open_gives_none():
    capture = FakeCapture(opened=False)
    assert open_camera(0, opener=lambda index, is_sharp: capture) is None
    assert capture.released


def test_latest_frame_skips_older_frames():
    release = threading.Event()
    frames = ["old", "newer", "newest"]
    produced = threading.Event()

    class Burst(FakeCapture):
        def read(self):
            if frames:
                return True, frames.pop(0)
            produced.set()
            release.wait(5)
            return False, None

    camera = LatestFrameCamera(Burst())
    assert produced.wait(5)
    assert camera.read() == "newest"
    release.set()
    assert camera.read() is None
    camera.close()


def test_same_frame_is_never_returned_twice():
    release = threading.Event()
    frames = ["only"]

    class One(FakeCapture):
        def read(self):
            if frames:
                return True, frames.pop(0)
            release.wait(5)
            return False, None

    camera = LatestFrameCamera(One())
    assert camera.read(timeout=5) == "only"
    assert camera.read(timeout=0.05) is None
    release.set()
    camera.close()


def test_camera_stopping_is_reported_and_closing_releases_it():
    capture = FakeCapture(frames=[])
    camera = LatestFrameCamera(capture)
    assert camera.read(timeout=5) is None
    camera.close()
    assert capture.released
