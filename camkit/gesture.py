"""Détection des gestes partagés par Shunkan Idō et Golden Warrior.

Téléportation : index et majeur serrés, posés sur le front.
Poings : les deux poings serrés face à la caméra (transformation Golden Warrior).

Pour la téléportation :

La règle est purement géométrique à partir des 21 points de la main de MediaPipe
et du cadre du visage :

* index et majeur tendus (bout plus loin du poignet que l'articulation du milieu) ;
* annulaire et auriculaire repliés ;
* bouts de l'index et du majeur proches l'un de l'autre ;
* ces deux bouts dans la zone du front (au-dessus des yeux, un peu au-dessus de la tête).

Le geste doit être tenu ``hold`` secondes, puis relâché avant de pouvoir
redéclencher : un geste = un déclenchement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

WRIST = 0
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_PIP, MIDDLE_TIP = 10, 12
RING_PIP, RING_TIP = 14, 16
PINKY_MCP, PINKY_PIP, PINKY_TIP = 17, 18, 20


@dataclass
class Zone:
    x0: float
    y0: float
    x1: float
    y1: float

    def contains(self, p: np.ndarray) -> bool:
        return self.x0 <= p[0] <= self.x1 and self.y0 <= p[1] <= self.y1


@dataclass
class GestureDebug:
    """Ce que le mode debug dessine sur l'aperçu."""

    forehead: Zone | None = None
    hands: list[np.ndarray] = field(default_factory=list)  # (21, 2) en pixels
    posed: bool = False
    progress: float = 0.0  # 0..1 pendant le maintien (téléportation)
    fists_posed: bool = False
    fists_progress: float = 0.0
    face: tuple[float, float, float, float, float] | None = None  # x, y, w, h, y des yeux (pixels)


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.hypot(*(a - b)))


def is_goku_pose(hand: np.ndarray, forehead: Zone, loose: bool = False) -> bool:
    """``hand`` : tableau (21, 2) de coordonnées pixel."""

    def extended(tip: int, pip: int) -> bool:
        return _dist(hand[tip], hand[WRIST]) > _dist(hand[pip], hand[WRIST])

    palm = _dist(hand[INDEX_MCP], hand[PINKY_MCP]) + 1e-6
    two_up = extended(INDEX_TIP, INDEX_PIP) and extended(MIDDLE_TIP, MIDDLE_PIP)
    two_down = not extended(RING_TIP, RING_PIP) and not extended(PINKY_TIP, PINKY_PIP)
    together = _dist(hand[INDEX_TIP], hand[MIDDLE_TIP]) < (0.75 if loose else 0.55) * palm
    on_forehead = forehead.contains(hand[INDEX_TIP]) and forehead.contains(hand[MIDDLE_TIP])
    if loose:
        # Mode tolérant : on ignore annulaire/auriculaire (souvent cachés par la tête).
        return two_up and together and on_forehead
    return two_up and two_down and together and on_forehead


def is_fist(hand: np.ndarray) -> bool:
    """Les quatre doigts repliés : chaque bout plus près du poignet que son articulation."""

    def folded(tip: int, pip: int) -> bool:
        return _dist(hand[tip], hand[WRIST]) < _dist(hand[pip], hand[WRIST]) * 1.05

    return all(folded(t, p) for t, p in ((INDEX_TIP, INDEX_PIP), (MIDDLE_TIP, MIDDLE_PIP), (RING_TIP, RING_PIP), (PINKY_TIP, PINKY_PIP)))


def forehead_zone(detection, width: int, height: int, loose: bool = False) -> Zone:
    """Zone du front à partir d'une détection BlazeFace (cadre + points clés)."""
    box = detection.bounding_box
    x, y, w, h = box.origin_x, box.origin_y, box.width, box.height
    # Points clés : 0 = œil droit, 1 = œil gauche (coordonnées normalisées).
    eyes_y = np.mean([detection.keypoints[0].y, detection.keypoints[1].y]) * height
    margin = 0.35 if loose else 0.2
    return Zone(
        x0=x - margin * w,
        y0=y - 0.6 * h,
        x1=x + (1 + margin) * w,
        y1=eyes_y + 0.05 * h,
    )


class HoldTrigger:
    """Déclenche une fois quand une pose est tenue ``hold`` s, puis attend qu'elle soit relâchée."""

    def __init__(self, hold: float, rearm: float = 0.4):
        self.hold, self.rearm = hold, rearm
        self._since: float | None = None
        self._released_at: float | None = None
        self._fired = False
        self.progress = 0.0

    def update(self, posed: bool, now: float) -> bool:
        if not posed:
            self._since = None
            self.progress = 0.0
            if self._fired:
                self._released_at = self._released_at if self._released_at is not None else now
                if now - self._released_at >= self.rearm:
                    self._fired = False
                    self._released_at = None
            return False
        self._released_at = None
        if self._fired:
            self.progress = 1.0
            return False
        self._since = self._since if self._since is not None else now
        held = now - self._since
        self.progress = min(1.0, held / self.hold) if self.hold > 0 else 1.0
        if held >= self.hold:
            self._fired = True
            return True
        return False


class GestureDetector:
    """Analyse chaque image et renvoie ``"teleport"``, ``"fists"`` ou ``None``."""

    def __init__(
        self,
        model_paths: dict[str, Path],
        hold: float = 0.3,
        fists_hold: float = 0.5,
        loose: bool = False,
    ):
        self.loose = loose
        self._teleport = HoldTrigger(hold)
        self._fists = HoldTrigger(fists_hold)
        self.debug = GestureDebug()

        self._hands = vision.HandLandmarker.create_from_options(
            vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(model_paths["hand_landmarker.task"])),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=2,
                min_hand_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        )
        self._face = vision.FaceDetector.create_from_options(
            vision.FaceDetectorOptions(
                base_options=BaseOptions(model_asset_path=str(model_paths["blaze_face_short_range.tflite"])),
                running_mode=vision.RunningMode.VIDEO,
                min_detection_confidence=0.5,
            )
        )

    def update(self, rgb: np.ndarray, now: float, ts_ms: int) -> str | None:
        h, w = rgb.shape[:2]
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        faces = self._face.detect_for_video(image, ts_ms).detections
        hands = self._hands.detect_for_video(image, ts_ms).hand_landmarks

        d = self.debug
        d.hands = [np.array([[lm.x * w, lm.y * h] for lm in hand]) for hand in hands]
        d.forehead = None
        d.face = None
        posed = False
        if faces:
            # Visage le plus grand = l'utilisateur.
            face = max(faces, key=lambda f: f.bounding_box.width * f.bounding_box.height)
            box = face.bounding_box
            eyes_y = float(np.mean([face.keypoints[0].y, face.keypoints[1].y]) * h)
            d.face = (box.origin_x, box.origin_y, box.width, box.height, eyes_y)
            zone = forehead_zone(face, w, h, self.loose)
            d.forehead = zone
            posed = any(is_goku_pose(hand, zone, self.loose) for hand in d.hands)
        fists = len(d.hands) == 2 and all(is_fist(hand) for hand in d.hands)

        d.posed, d.fists_posed = posed, fists
        fired_teleport = self._teleport.update(posed, now)
        fired_fists = self._fists.update(fists and not posed, now)
        d.progress, d.fists_progress = self._teleport.progress, self._fists.progress
        if fired_teleport:
            return "teleport"
        if fired_fists:
            return "fists"
        return None

    def close(self) -> None:
        self._hands.close()
        self._face.close()
