"""Camera-side hand detection with MediaPipe, shared by the trial and desktop apps."""

from __future__ import annotations

import urllib.request
from pathlib import Path

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

from gesture_core import Hand

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)
MODEL_SIZE_MB = 7.8
DEFAULT_MODEL_PATH = Path(__file__).parent / "models" / "hand_landmarker.task"


def download_model(path: Path = DEFAULT_MODEL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    urllib.request.urlretrieve(MODEL_URL, partial)
    partial.replace(path)


class HandTracker:
    """Finds several hands so that the closest is among them for HandSelector to pick."""

    def __init__(self, model_path: Path = DEFAULT_MODEL_PATH, max_hands: int = 4) -> None:
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_buffer=Path(model_path).read_bytes()),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=max_hands,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._last_t_ms = -1

    def detect(self, rgb_frame, t_ms: int) -> list[Hand]:
        """rgb_frame must already be mirrored, which MediaPipe's handedness expects."""
        t_ms = max(t_ms, self._last_t_ms + 1)  # Timestamps must strictly increase.
        self._last_t_ms = t_ms
        height, width = rgb_frame.shape[:2]
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self._landmarker.detect_for_video(image, t_ms)

        hands = []
        for landmarks, world, categories in zip(
            result.hand_landmarks, result.hand_world_landmarks, result.handedness
        ):
            points = tuple((point.x, point.y) for point in landmarks)
            world_points = tuple((point.x, point.y, point.z) for point in world)
            label = categories[0].category_name if categories else None
            hands.append(
                Hand(points, aspect=width / height, handedness=label, world=world_points)
            )
        return hands

    def close(self) -> None:
        self._landmarker.close()
