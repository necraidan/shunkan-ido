"""Capture webcam (OpenCV / AVFoundation) et sortie vers la caméra virtuelle OBS."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

OBS_HELP = """
La caméra virtuelle OBS n'est pas disponible.

  1. Ouvre OBS Studio une fois et clique sur « Démarrer la caméra virtuelle »
     pour installer l'extension système.
  2. Autorise-la dans Réglages Système › Général › Ouverture et extensions
     › Extensions caméra › « OBS Virtual Camera ».
  3. Relance le programme. Si ça ne marche toujours pas, redémarre le Mac.

En attendant, tu peux tester avec --no-virtual (aperçu seul).
"""


class FrameSource:
    """Lit des images depuis une webcam (index) ou un fichier image / vidéo (chemin)."""

    def __init__(self, source: str, width: int, height: int, fps: int):
        self.width, self.height, self.fps = width, height, fps
        self._still: np.ndarray | None = None
        self._cap: cv2.VideoCapture | None = None

        path = Path(source)
        if source.isdigit():
            self._cap = cv2.VideoCapture(int(source), cv2.CAP_AVFOUNDATION)
            if not self._cap.isOpened():
                raise RuntimeError(
                    f"Impossible d'ouvrir la caméra {source}. "
                    "Vérifie l'autorisation caméra du Terminal dans Réglages Système › "
                    "Confidentialité et sécurité › Caméra, ou essaie --list-cameras."
                )
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self._cap.set(cv2.CAP_PROP_FPS, fps)
        elif path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}:
            img = cv2.imread(str(path))
            if img is None:
                raise RuntimeError(f"Image illisible : {path}")
            self._still = cv2.resize(img, (width, height))
        else:
            self._cap = cv2.VideoCapture(str(path))
            if not self._cap.isOpened():
                raise RuntimeError(f"Vidéo illisible : {path}")

    def read(self) -> np.ndarray:
        """Renvoie une image BGR à la taille demandée (boucle sur les vidéos)."""
        if self._still is not None:
            return self._still.copy()
        assert self._cap is not None
        ok, frame = self._cap.read()
        if not ok:
            # Fin de vidéo : on rembobine.
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
            if not ok:
                raise RuntimeError("Plus d'image disponible depuis la source.")
        if frame.shape[1] != self.width or frame.shape[0] != self.height:
            frame = cv2.resize(frame, (self.width, self.height))
        return frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()


def list_cameras(max_index: int = 6) -> list[int]:
    """Indices des caméras qui s'ouvrent avec AVFoundation."""
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_AVFOUNDATION)
        if cap.isOpened():
            found.append(i)
        cap.release()
    return found


class VirtualOutput:
    """Enveloppe pyvirtualcam ; ``send`` est un no-op si la sortie est désactivée."""

    def __init__(self, width: int, height: int, fps: int, enabled: bool = True):
        self._cam = None
        if not enabled:
            return
        import pyvirtualcam

        try:
            self._cam = pyvirtualcam.Camera(width=width, height=height, fps=fps, backend="obs")
        except RuntimeError as exc:
            print(OBS_HELP, file=sys.stderr)
            raise SystemExit(f"[caméra virtuelle] {exc}") from exc
        print(f"[caméra virtuelle] prête : {self._cam.device}", file=sys.stderr)

    @property
    def enabled(self) -> bool:
        return self._cam is not None

    def send(self, frame_bgr: np.ndarray) -> None:
        if self._cam is None:
            return
        self._cam.send(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))

    def close(self) -> None:
        if self._cam is not None:
            self._cam.close()
            self._cam = None
