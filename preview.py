"""The camera preview shown by the Windows app, plus the model check."""

from __future__ import annotations

from collections import deque

import cv2

from gesture_core import FINGER_CHAIN, PALM_BONES, Finger, FrameResult
from hand_tracking import DEFAULT_MODEL_PATH, MODEL_SIZE_MB, MODEL_URL, download_model

FONT = cv2.FONT_HERSHEY_SIMPLEX
WHITE, GREEN, RED, YELLOW, DARK = (
    (255, 255, 255),
    (90, 220, 90),
    (80, 80, 240),
    (60, 220, 240),
    (35, 35, 35),
)
FINGER_COLORS = {
    Finger.THUMB: (80, 80, 240),
    Finger.INDEX: (90, 220, 90),
    Finger.MIDDLE: (240, 170, 60),
    Finger.RING: (220, 90, 220),
    Finger.PINKY: (60, 220, 240),
}


def label(frame, text, x, y, color=WHITE, scale=0.55, thickness=1) -> None:
    cv2.putText(frame, text, (x, y), FONT, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(frame, text, (x, y), FONT, scale, color, thickness, cv2.LINE_AA)


def progress_ring(frame, center, progress, color, radius=26) -> None:
    if progress > 0:
        end = int(360 * progress)
        cv2.ellipse(frame, center, (radius, radius), -90, 0, end, color, 3, cv2.LINE_AA)


def draw_skeleton(frame, hand) -> None:
    height, width = frame.shape[:2]
    points = [(int(x * width), int(y * height)) for x, y in hand.landmarks]
    for a, b in PALM_BONES:
        cv2.line(frame, points[a], points[b], WHITE, 2, cv2.LINE_AA)
    for finger, chain in FINGER_CHAIN.items():
        for a, b in zip(chain, chain[1:]):
            cv2.line(frame, points[a], points[b], FINGER_COLORS[finger], 2, cv2.LINE_AA)
    for point in points:
        cv2.circle(frame, point, 3, WHITE, -1, cv2.LINE_AA)


def draw(frame, result: FrameResult, zone, log: deque[str]) -> None:
    height, width = frame.shape[:2]

    if result.hand is not None:
        draw_skeleton(frame, result.hand)

    left, top, right, bottom = zone
    cv2.rectangle(
        frame,
        (int(left * width), int(top * height)),
        (int(right * width), int(bottom * height)),
        (150, 150, 150),
        1,
    )

    for finger, pointer in result.pointers.items():
        center = (int(pointer.x * width), int(pointer.y * height))
        radius = 9 if pointer.extended else 6
        cv2.circle(frame, center, radius, FINGER_COLORS[finger], -1, cv2.LINE_AA)
        label(frame, finger.value, center[0] + 10, center[1] - 8, FINGER_COLORS[finger], 0.42)

    if Finger.INDEX in result.pointers:
        index = result.pointers[Finger.INDEX]
        center = (int(index.x * width), int(index.y * height))
        progress_ring(frame, center, result.activation_progress, GREEN)
        progress_ring(frame, center, result.drag_progress, YELLOW)
        progress_ring(frame, center, min(1.0, result.dwell_progress), WHITE)
        progress_ring(frame, center, result.dwell_progress - 1, GREEN, radius=34)

    status, color = ("ON", GREEN) if result.active else ("OFF - open palm, hold 1s", RED)
    label(frame, status, 12, 28, color, 0.7, 2)
    if result.active:
        pinch = result.pinch_finger.value if result.pinch_finger else "-"
        label(frame, f"operation: {result.operation.value}", 12, 54)
        label(frame, f"pinch: thumb + {pinch}", 12, 76)
        if result.pointing:
            label(frame, "POINTING - hold still to click", 12, 98, GREEN)
    if result.hand is None:
        label(frame, "no hand", 12, 142, RED)
    if result.fist:
        label(frame, "FIST - open your hand to continue", 12, 120, YELLOW, 0.6, 2)

    # A small stand-in for the laptop screen, showing where the cursor is.
    panel_w, panel_h = 200, 125
    panel_x, panel_y = width - panel_w - 12, 12
    cv2.rectangle(frame, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), DARK, -1)
    cv2.rectangle(frame, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), WHITE, 1)
    cursor = (
        panel_x + int(result.cursor[0] * panel_w),
        panel_y + int(result.cursor[1] * panel_h),
    )
    cv2.circle(frame, cursor, 5, GREEN if result.active else (120, 120, 120), -1, cv2.LINE_AA)

    for row, line in enumerate(log):
        label(frame, line, 12, height - 14 - row * 22, YELLOW)


def describe(event) -> str:
    text = event.type.value.upper()
    if event.direction:
        text += f" {event.direction}"
    if event.cancelled_op:
        text += f" ({event.cancelled_op})"
    return text


def ensure_model() -> bool:
    if DEFAULT_MODEL_PATH.exists():
        return True
    print("The hand model is missing:")
    print(f"  file:   {DEFAULT_MODEL_PATH.name} ({MODEL_SIZE_MB} MB)")
    print(f"  source: {MODEL_URL}")
    print(f"  saved:  {DEFAULT_MODEL_PATH}")
    if input("Download it now? [y/N] ").strip().lower() != "y":
        return False
    download_model()
    return True
