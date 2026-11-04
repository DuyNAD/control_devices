"""Control the real Windows mouse and shortcuts with one hand, on the primary screen.

    python windows_app.py [--camera 0] [--hand Left|Right]

Press Ctrl+Alt+Q anywhere to stop. Q or Esc also work when the preview has focus.
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import threading
import time
import winsound
from collections import deque
from ctypes import wintypes

import cv2

from gesture_core import (
    EventType,
    FrameResult,
    GestureConfig,
    GestureEvent,
    LaptopGestureEngine,
    Operation,
    Point,
)
from hand_tracking import HandTracker
from preview import describe, draw, ensure_model

WINDOW = "control_devices - Ctrl+Alt+Q to stop"
PREVIEW_DRAW_WIDTH = 640  # the preview is drawn at this size so its labels stay readable
PREVIEW_WINDOW_WIDTH = 480

# Sharper hands for the same detection speed. Measured on one laptop: 48 ms per
# frame at 720p against 37-52 ms at 480p. Some cameras are very slow in this mode,
# so open_camera checks it and falls back to the camera's default.
CAMERA_SIZE = (1280, 720)
CAMERA_MIN_FPS = 10
CAMERA_WARMUP_FRAMES = 3
CAMERA_CHECK_FRAMES = 3
CAMERA_READ_TIMEOUT_S = 2.0

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
ABSOLUTE_MAX = 65535
WHEEL_DELTA = 120
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_ESCAPE = 0x1B
VK_Y = ord("Y")
VK_Z = ord("Z")

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
STOP_KEY = ord("Q")
STOP_HOTKEY_ID = 1

# Each tone is (frequency in Hz, length in ms).
CLICK_TONES = ((880, 70),)
DOUBLE_CLICK_TONES = ((880, 70), (1175, 90))
RIGHT_CLICK_TONES = ((660, 70),)
DRAG_READY_TONES = ((660, 50), (880, 50))
DRAG_END_TONES = ((880, 50), (660, 50))
SWIPE_TONES = ((988, 60),)
UNDO_TONES = ((784, 60), (587, 80))
REDO_TONES = ((587, 60), (784, 80))
CANCEL_TONES = ((330, 150),)

# How far each gesture goes. Starting values, meant to be tuned on real use.
SCROLL_NOTCHES_PER_PALM = 4.0
ZOOM_NOTCHES_PER_PALM = 2.0
SWIPE_NOTCHES = 3


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def to_absolute(point: Point) -> tuple[int, int]:
    """Normalized cursor to SendInput's 0-65535 range, which ignores display scaling."""
    return round(point[0] * ABSOLUTE_MAX), round(point[1] * ABSOLUTE_MAX)


class WindowsInput:
    """Sends real mouse and keyboard input through SendInput."""

    def __init__(self) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SendInput.argtypes = (
            wintypes.UINT,
            ctypes.POINTER(INPUT),
            ctypes.c_int,
        )
        self._user32.SendInput.restype = wintypes.UINT
        self._warned = False

    def move(self, point: Point) -> None:
        self._send([self._positioned(point, MOUSEEVENTF_MOVE)])

    def click(self, point: Point) -> bool:
        return self._send_clicks(point, 1)

    def double_click(self, point: Point) -> bool:
        return self._send_clicks(point, 2)

    def _send_clicks(self, point: Point, count: int) -> bool:
        # One batch, so nothing else can slip between moving and clicking.
        press = [
            self._positioned(point, MOUSEEVENTF_LEFTDOWN),
            self._positioned(point, MOUSEEVENTF_LEFTUP),
        ]
        return self._send([self._positioned(point, MOUSEEVENTF_MOVE)] + press * count)

    def right_click(self, point: Point) -> bool:
        return self._send(
            [
                self._positioned(point, MOUSEEVENTF_MOVE),
                self._positioned(point, MOUSEEVENTF_RIGHTDOWN),
                self._positioned(point, MOUSEEVENTF_RIGHTUP),
            ]
        )

    def left_down(self, point: Point) -> bool:
        return self._send(
            [
                self._positioned(point, MOUSEEVENTF_MOVE),
                self._positioned(point, MOUSEEVENTF_LEFTDOWN),
            ]
        )

    def left_up(self, point: Point) -> bool:
        return self._send(
            [
                self._positioned(point, MOUSEEVENTF_MOVE),
                self._positioned(point, MOUSEEVENTF_LEFTUP),
            ]
        )

    def scroll(self, notches: int) -> bool:
        """Positive scrolls up."""
        return self._send([self._wheel(MOUSEEVENTF_WHEEL, notches)])

    def scroll_sideways(self, notches: int) -> bool:
        """Positive scrolls right, so the content moves left."""
        return self._send([self._wheel(MOUSEEVENTF_HWHEEL, notches)])

    def zoom(self, notches: int) -> bool:
        """Positive zooms in. Ctrl + wheel, with Ctrl released in the same batch."""
        return self._send(
            [
                self._key(VK_CONTROL),
                self._wheel(MOUSEEVENTF_WHEEL, notches),
                self._key(VK_CONTROL, up=True),
            ]
        )

    def undo(self) -> bool:
        return self._control_key(VK_Z)

    def redo(self) -> bool:
        return self._control_key(VK_Y)

    def escape(self) -> bool:
        return self._send([self._key(VK_ESCAPE), self._key(VK_ESCAPE, up=True)])

    def _control_key(self, key: int) -> bool:
        return self._send(
            [
                self._key(VK_CONTROL),
                self._key(key),
                self._key(key, up=True),
                self._key(VK_CONTROL, up=True),
            ]
        )

    @staticmethod
    def _positioned(point: Point, flags: int) -> INPUT:
        x, y = to_absolute(point)
        mouse = MOUSEINPUT(x, y, 0, flags | MOUSEEVENTF_ABSOLUTE, 0, 0)
        return INPUT(INPUT_MOUSE, _INPUTUNION(mi=mouse))

    @staticmethod
    def _wheel(flags: int, notches: int) -> INPUT:
        # The field is unsigned, and Windows reads it back as a signed amount.
        amount = (notches * WHEEL_DELTA) & 0xFFFFFFFF
        return INPUT(INPUT_MOUSE, _INPUTUNION(mi=MOUSEINPUT(0, 0, amount, flags, 0, 0)))

    @staticmethod
    def _key(key: int, up: bool = False) -> INPUT:
        flags = KEYEVENTF_KEYUP if up else 0
        return INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=KEYBDINPUT(key, 0, flags, 0, 0)))

    def _send(self, inputs: list[INPUT]) -> bool:
        batch = (INPUT * len(inputs))(*inputs)
        sent = self._user32.SendInput(len(inputs), batch, ctypes.sizeof(INPUT))
        delivered = sent == len(inputs)
        if not delivered and not self._warned:
            self._warned = True
            print("Windows blocked the input, possibly from a window running as Administrator.")
        return delivered


def play_tones(tones: tuple[tuple[int, int], ...]) -> None:
    """Plays without holding up the camera loop, since each Beep blocks until it ends."""

    def play() -> None:
        try:
            for frequency, length_ms in tones:
                winsound.Beep(frequency, length_ms)
        except RuntimeError:
            pass  # No sound device: the action itself already went through.

    threading.Thread(target=play, daemon=True).start()


class CursorController:
    """Turns one frame of gesture results into mouse actions, shortcuts and sounds."""

    def __init__(self, mouse, play=play_tones) -> None:
        self._mouse = mouse
        self._play = play
        self._position: tuple[int, int] | None = None
        self._drag_start: Point | None = None
        self._unsent_notches = 0.0

    def apply(self, result: FrameResult) -> None:
        if result.operation not in (Operation.SCROLLING, Operation.ZOOMING):
            self._unsent_notches = 0.0

        for event in result.events:
            self._handle(event)

        # Without a visible hand the physical mouse stays in charge.
        if result.active and result.hand is not None:
            self._move(result.cursor)

    def _handle(self, event: GestureEvent) -> None:
        mouse = self._mouse
        kind = event.type
        if kind is EventType.TAP:
            self._press(mouse.click, event.cursor, CLICK_TONES)
        elif kind is EventType.DOUBLE_TAP:
            self._press(mouse.double_click, event.cursor, DOUBLE_CLICK_TONES)
        elif kind is EventType.RIGHT_CLICK:
            self._press(mouse.right_click, event.cursor, RIGHT_CLICK_TONES)
        elif kind is EventType.DRAG_READY:
            self._play(DRAG_READY_TONES)
        elif kind is EventType.DRAG_START:
            if mouse.left_down(event.cursor):
                self._drag_start = event.cursor
                self._position = to_absolute(event.cursor)
        elif kind is EventType.DRAG_END:
            self._press(mouse.left_up, event.cursor, DRAG_END_TONES)
            self._drag_start = None
        elif kind is EventType.SCROLL:
            self._send_notches(mouse.scroll, event.amount * SCROLL_NOTCHES_PER_PALM)
        elif kind is EventType.ZOOM:
            self._send_notches(mouse.zoom, event.amount * ZOOM_NOTCHES_PER_PALM)
        elif kind is EventType.SWIPE:
            # The content follows the hand, so a flick left scrolls the view right.
            notches = SWIPE_NOTCHES if event.direction == "left" else -SWIPE_NOTCHES
            if mouse.scroll_sideways(notches):
                self._play(SWIPE_TONES)
        elif kind is EventType.UNDO:
            if mouse.undo():
                self._play(UNDO_TONES)
        elif kind is EventType.REDO:
            if mouse.redo():
                self._play(REDO_TONES)
        elif kind is EventType.CANCELLED:
            self.cancel_drag()
            self._play(CANCEL_TONES)

    def cancel_drag(self) -> None:
        """Never leaves the button held down. Esc cancels the drag in most apps, and
        for the rest the object is dropped back where it came from."""
        if self._drag_start is None:
            return
        self._mouse.escape()
        self._mouse.left_up(self._drag_start)
        self._position = to_absolute(self._drag_start)
        self._drag_start = None

    def _send_notches(self, send, amount: float) -> None:
        # Hands move in small steps, but apps act on whole wheel notches.
        self._unsent_notches += amount
        notches = int(self._unsent_notches)
        if notches:
            send(notches)
            self._unsent_notches -= notches

    def _press(self, send, point: Point, tones) -> None:
        # Stay silent if SendInput reports a failure. It does not report every block:
        # a click into an Administrator window can still look delivered.
        if send(point):
            self._play(tones)
        self._position = to_absolute(point)

    def _move(self, point: Point) -> None:
        position = to_absolute(point)
        if position != self._position:
            self._mouse.move(point)
            self._position = position


class StopHotkey:
    """Ctrl+Alt+Q from any app, listened for on its own thread."""

    def __init__(self) -> None:
        self.pressed = threading.Event()
        self._registered = False
        self._ready = threading.Event()

    def start(self) -> bool:
        """Returns False if the hotkey could not be registered."""
        threading.Thread(target=self._listen, daemon=True).start()
        self._ready.wait()
        return self._registered

    def _listen(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        modifiers = MOD_CONTROL | MOD_ALT | MOD_NOREPEAT
        # The hotkey belongs to this thread, so it must also read the messages here.
        self._registered = bool(user32.RegisterHotKey(None, STOP_HOTKEY_ID, modifiers, STOP_KEY))
        self._ready.set()
        if not self._registered:
            return
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == WM_HOTKEY:
                self.pressed.set()
                return


def is_fast_enough(capture, clock=time.perf_counter) -> bool:
    """False if frames do not arrive, or arrive slower than the app can follow."""
    for _ in range(CAMERA_WARMUP_FRAMES):
        if not capture.read()[0]:
            return False
    started = clock()
    for _ in range(CAMERA_CHECK_FRAMES):
        if not capture.read()[0]:
            return False
    return clock() - started <= CAMERA_CHECK_FRAMES / CAMERA_MIN_FPS


def open_capture(index: int, sharp: bool):
    capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if sharp:
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_SIZE[0])
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_SIZE[1])
        capture.set(cv2.CAP_PROP_FPS, 30)
    return capture


def open_camera(index: int, opener=open_capture, check=is_fast_enough):
    """The sharp mode if this camera handles it, otherwise its default. None if neither opens."""
    capture = opener(index, True)
    if capture.isOpened() and check(capture):
        return capture
    capture.release()
    capture = opener(index, False)
    if capture.isOpened():
        return capture
    capture.release()
    return None


class LatestFrameCamera:
    """Reads the camera on its own thread and keeps only the newest frame.

    Detection is slower than the camera, so reading in the main loop could work
    through frames that are already old. Here the hand is always the current one.
    """

    def __init__(self, capture) -> None:
        self._capture = capture
        self._condition = threading.Condition()
        self._frame = None
        self._running = True
        self._thread = threading.Thread(target=self._grab, daemon=True)
        self._thread.start()

    def _grab(self) -> None:
        while self._running:
            ok, frame = self._capture.read()
            with self._condition:
                if not ok:
                    self._running = False
                else:
                    self._frame = frame
                self._condition.notify_all()

    def read(self, timeout: float = CAMERA_READ_TIMEOUT_S):
        """The next frame not yet returned, or None if the camera has stopped."""
        with self._condition:
            self._condition.wait_for(
                lambda: self._frame is not None or not self._running, timeout
            )
            frame, self._frame = self._frame, None
            return frame

    def close(self) -> None:
        self._running = False
        self._thread.join(timeout=CAMERA_READ_TIMEOUT_S)
        self._capture.release()


def main() -> int:
    parser = argparse.ArgumentParser(description="Control the Windows cursor by hand.")
    parser.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    parser.add_argument("--hand", choices=["Left", "Right"], help="only follow this hand")
    args = parser.parse_args()

    if not ensure_model():
        print("The app needs the model, so it did not start.")
        return 1

    # Without a working stop key the app must not take over the mouse.
    stop = StopHotkey()
    if not stop.start():
        print("Could not register Ctrl+Alt+Q. Is another app using it?")
        return 1

    capture = open_camera(args.camera)
    if capture is None:
        print(f"Could not open camera {args.camera}. Is another app using it?")
        return 1
    camera = LatestFrameCamera(capture)

    config = GestureConfig(preferred_hand=args.hand)
    engine = LaptopGestureEngine(config)
    tracker = HandTracker()
    controller = CursorController(WindowsInput())
    log: deque[str] = deque(maxlen=8)
    started = time.monotonic()

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_TOPMOST, 1)
    window_sized = False

    print("Ready. Open your palm and hold it still for 1 second to take control.")
    print("Point with your index finger and hold still: 1s to click, 2s to double-click.")
    print("Open and closed hands do not click. Pinch for the other gestures.")
    print("Press Ctrl+Alt+Q anywhere to stop.")

    try:
        while not stop.pressed.is_set():
            frame = camera.read()
            if frame is None:
                print("The camera stopped sending frames.")
                return 1
            frame = cv2.flip(frame, 1)
            t_ms = int((time.monotonic() - started) * 1000)
            hands = tracker.detect(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), t_ms)
            result = engine.update(hands, t_ms)

            if stop.pressed.is_set():
                break  # It may have been pressed while the frame was being read.
            controller.apply(result)

            for event in result.events:
                # Scroll and zoom fire every frame and would flood the log.
                if event.type not in (EventType.SCROLL, EventType.ZOOM):
                    log.appendleft(describe(event))
                    print(f"{event.t_ms:>8} ms  {describe(event)}")

            height, width = frame.shape[:2]
            view_height = round(height * PREVIEW_DRAW_WIDTH / width)
            view = cv2.resize(frame, (PREVIEW_DRAW_WIDTH, view_height))
            draw(view, result, config.control_zone, log)
            cv2.imshow(WINDOW, view)
            if not window_sized:
                window_height = round(height * PREVIEW_WINDOW_WIDTH / width)
                cv2.resizeWindow(WINDOW, PREVIEW_WINDOW_WIDTH, window_height)
                window_sized = True
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                return 0
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                return 0  # The preview was closed.
        print("Stopped by Ctrl+Alt+Q.")
        return 0
    finally:
        controller.cancel_drag()  # However the app stops, the button must not stay down.
        tracker.close()
        camera.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    sys.exit(main())
