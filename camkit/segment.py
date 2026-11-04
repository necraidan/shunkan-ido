"""Segmentation de la silhouette (MediaPipe Selfie Segmenter), une seule fois par image."""

from __future__ import annotations

from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision


class Segmenter:
    def __init__(self, model_paths: dict[str, Path]):
        self._seg = vision.ImageSegmenter.create_from_options(
            vision.ImageSegmenterOptions(
                base_options=BaseOptions(model_asset_path=str(model_paths["selfie_segmenter.tflite"])),
                running_mode=vision.RunningMode.VIDEO,
                output_confidence_masks=True,
                output_category_mask=False,
            )
        )
        self._cache: tuple[int, np.ndarray] | None = None

    def __call__(self, rgb: np.ndarray, ts_ms: int) -> np.ndarray:
        """Confiance (H, W) float32 dans [0, 1] : 1 = personne. Mise en cache par horodatage."""
        if self._cache is not None and self._cache[0] == ts_ms:
            return self._cache[1]
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        conf = np.asarray(self._seg.segment_for_video(image, ts_ms).confidence_masks[0].numpy_view())
        conf = np.ascontiguousarray(conf[..., 0] if conf.ndim == 3 else conf, dtype=np.float32)
        self._cache = (ts_ms, conf)
        return conf

    def close(self) -> None:
        self._seg.close()


class Matte:
    """Détourage fin d'une image : personne et cheveux, en flottants (H, W) dans [0, 1]."""

    __slots__ = ("person", "hair")

    def __init__(self, person: np.ndarray, hair: np.ndarray):
        self.person = person
        self.hair = hair


class PersonMatte:
    """Détourage de qualité pour les effets posés sur la personne (Golden Warrior).

    * Modèle multiclasse MediaPipe : sépare cheveux, peau, vêtements et fond, donc les
      cheveux sont les vrais cheveux et non une zone devinée au-dessus du front.
    * Exécution asynchrone (mode flux) : le modèle (~20 ms) tourne pendant qu'on traite
      l'image, le flux reste à 30 images/s. Le masque a au plus une image de retard.
    * Filtre guidé : le masque basse résolution (256 px) est recollé sur les vrais
      contours de l'image courante, mèches comprises, ce qui compense aussi ce retard.
    * Lissage temporel adaptatif : stable quand on est immobile, réactif quand on bouge.
    """

    def __init__(self, model_paths: dict[str, Path], width: int, height: int, radius: int = 8, eps: float = 1e-3):
        self.width, self.height = width, height
        self.work = (width // 2, height // 2)
        self.radius, self.eps = radius, eps
        self._latest: tuple[np.ndarray, np.ndarray] | None = None
        self._prev: Matte | None = None
        self._last_ts = -1
        self._seg = vision.ImageSegmenter.create_from_options(
            vision.ImageSegmenterOptions(
                base_options=BaseOptions(model_asset_path=str(model_paths["selfie_multiclass_256x256.tflite"])),
                running_mode=vision.RunningMode.LIVE_STREAM,
                output_confidence_masks=True,
                output_category_mask=False,
                result_callback=self._on_result,
            )
        )

    def _on_result(self, result, _image, _ts: int) -> None:
        masks = result.confidence_masks
        bg = np.asarray(masks[0].numpy_view()).squeeze()
        hair = np.asarray(masks[1].numpy_view()).squeeze()
        # Copies : les buffers MediaPipe ne survivent pas au callback.
        self._latest = (np.clip(1.0 - bg, 0.0, 1.0).astype(np.float32), hair.astype(np.float32).copy())

    def submit(self, rgb: np.ndarray, ts_ms: int) -> None:
        """Envoie l'image au modèle ; MediaPipe ignore les images s'il est encore occupé."""
        if ts_ms <= self._last_ts:
            return
        self._last_ts = ts_ms
        self._seg.segment_async(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts_ms)

    def reset(self) -> None:
        self._prev = None

    def matte(self, frame_bgr: np.ndarray) -> Matte | None:
        """Masques affinés sur l'image courante, ou None tant qu'aucun résultat n'est arrivé."""
        if self._latest is None:
            return None
        person, hair = self._latest
        guide = cv2.resize(frame_bgr, self.work, interpolation=cv2.INTER_AREA)
        # Un seul filtre guidé pour les deux masques (deux canaux) : statistiques du guide partagées.
        both = self._guided(guide, np.dstack([person, hair]))
        p, h = both[..., 0].copy(), both[..., 1] * both[..., 0]  # pas de cheveux hors de la personne
        if self._prev is not None:
            # Lissage d'autant plus faible que l'image a changé : pas de traînée en mouvement.
            change = float(np.abs(p - self._prev.person).mean())
            keep = float(np.clip(0.5 - change * 25.0, 0.0, 0.5))
            p = p * (1.0 - keep) + self._prev.person * keep
            h = h * (1.0 - keep) + self._prev.hair * keep
        self._prev = Matte(p, h)
        size = (self.width, self.height)
        return Matte(cv2.resize(p, size, interpolation=cv2.INTER_LINEAR), cv2.resize(h, size, interpolation=cv2.INTER_LINEAR))

    def _guided(self, guide: np.ndarray, prob: np.ndarray) -> np.ndarray:
        src = cv2.resize(prob, self.work, interpolation=cv2.INTER_LINEAR)
        out = cv2.ximgproc.guidedFilter(guide, src, self.radius, self.eps)
        # Contraste : le filtre guidé adoucit, on resserre la transition pour un bord net.
        return np.clip((out - 0.5) * 1.6 + 0.5, 0.0, 1.0).astype(np.float32)

    def close(self) -> None:
        self._seg.close()
