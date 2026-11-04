"""Fond de la pièce (plate) : calibration, correction d'exposition, masque de la personne."""

from __future__ import annotations

from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision


class Calibration:
    """Compte à rebours puis capture de N images, médiane = fond propre."""

    def __init__(self, countdown: float, frames: int, now: float):
        self.countdown = countdown
        self.frames_wanted = frames
        self.started_at = now
        self._frames: list[np.ndarray] = []

    def remaining(self, now: float) -> float:
        return max(0.0, self.countdown - (now - self.started_at))

    def capturing(self, now: float) -> bool:
        return self.remaining(now) == 0.0

    def feed(self, frame: np.ndarray, now: float) -> np.ndarray | None:
        """Ajoute une image pendant la capture ; renvoie le fond une fois terminé."""
        if not self.capturing(now):
            return None
        self._frames.append(frame.copy())
        if len(self._frames) < self.frames_wanted:
            return None
        return np.median(np.stack(self._frames), axis=0).astype(np.uint8)

    def status(self, now: float) -> str:
        if not self.capturing(now):
            return f"Sors du champ ! Photo de la pièce dans {self.remaining(now):.0f} s"
        return f"Capture du fond… {len(self._frames)}/{self.frames_wanted}"


class BackgroundPlate:
    """Fond de référence et tout ce qu'il faut pour que la zone gommée ne se voie pas.

    Trois causes rendent un contour visible quand on remplace la personne par le fond :

    1. un masque trop serré, qui laisse un liseré de cheveux, de halo ou d'ombre ;
    2. une couleur qui a dérivé depuis la calibration (balance des blancs, exposition auto,
       ombre portée par la personne sur le mur) ;
    3. un fond trop lisse : c'est une médiane de 30 images, sans le grain de la webcam.

    On corrige les trois : masque large et adouci, carte de gain de couleur locale estimée
    sur la zone visible autour de la personne, et grain calibré sur celui de l'image en direct.
    Les calculs lourds se font en quart de résolution.
    """

    WORK_SCALE = 4  # facteur de réduction pour les masques et la carte de gain

    def __init__(
        self,
        model_paths: dict[str, Path],
        cache_file: Path,
        width: int,
        height: int,
        grow: int = 32,
        feather: int = 40,
        gain_radius: int = 70,
    ):
        self.cache_file = cache_file
        self.width, self.height = width, height
        self.small = (width // self.WORK_SCALE, height // self.WORK_SCALE)
        self.plate: np.ndarray | None = None
        self._plate_f: np.ndarray | None = None
        self._plate_small: np.ndarray | None = None
        self._plate_sigma = 0.0

        # Tailles exprimées en pixels 720p, converties en pixels de travail.
        px = (height / 720.0) / self.WORK_SCALE
        g = max(3, int(grow * px * 2)) | 1
        self._grow_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (g, g))
        self._feather_sigma = max(1.0, feather * px / 2.5)
        self._gain_sigma = max(2.0, gain_radius * px)

        self._border = self._border_mask(width, height)
        sw, sh = self.small
        self._border_small = cv2.resize(self._border.astype(np.uint8), (sw, sh), interpolation=cv2.INTER_NEAREST).astype(np.float32)

        self._prev_mask: np.ndarray | None = None
        self._seg_cache: tuple[int, np.ndarray] | None = None
        self._prev_gain: np.ndarray | None = None
        self._noise_sigma = 0.0
        self._rng = np.random.default_rng()
        self._grain_bank, self._grain_unit = self._make_grain_bank(width, height)

        self._segmenter = vision.ImageSegmenter.create_from_options(
            vision.ImageSegmenterOptions(
                base_options=BaseOptions(model_asset_path=str(model_paths["selfie_segmenter.tflite"])),
                running_mode=vision.RunningMode.VIDEO,
                output_confidence_masks=True,
                output_category_mask=False,
            )
        )

    # --- fond ---------------------------------------------------------------

    @staticmethod
    def _border_mask(width: int, height: int, ratio: float = 0.08) -> np.ndarray:
        """Bande sur le pourtour de l'image, là où l'utilisateur n'est (presque) jamais."""
        m = np.zeros((height, width), dtype=bool)
        bx, by = int(width * ratio), int(height * ratio)
        m[:by, :] = m[-by:, :] = True
        m[:, :bx] = m[:, -bx:] = True
        return m

    def set_plate(self, plate: np.ndarray) -> None:
        self.plate = plate
        self._plate_f = plate.astype(np.float32)
        self._plate_small = cv2.resize(plate, self.small, interpolation=cv2.INTER_AREA).astype(np.float32)
        self._plate_sigma = self._hf_sigma(plate)
        self._prev_gain = None

    def load_cached(self) -> bool:
        if not self.cache_file.exists():
            return False
        img = cv2.imread(str(self.cache_file))
        if img is None:
            return False
        self.set_plate(cv2.resize(img, (self.width, self.height)))
        return True

    def save_cache(self) -> None:
        if self.plate is None:
            return
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(self.cache_file), self.plate)

    def match_exposure(self, frame: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
        """Fond recoloré localement et granulé pour se fondre dans l'image en direct.

        ``mask`` (personne = 1) indique où le fond n'est PAS visible en direct.
        Sans masque, la couleur est estimée sur les bords de l'image seulement.
        """
        assert self._plate_f is not None and self._plate_small is not None
        gain = self._gain_map(frame, mask)
        out = cv2.multiply(self._plate_f, gain)
        grain = self._grain(frame)
        if grain is not None:
            out = cv2.add(out, grain)
        return np.clip(out, 0, 255).astype(np.uint8)

    def _gain_map(self, frame: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
        """Carte de gain BGR basse fréquence : direct / fond, là où le fond est visible.

        Convolution normalisée : on floute (direct × poids) et (fond × poids), le poids
        valant 1 hors de la personne. Le rapport donne une correction qui suit les
        variations locales (ombre portée, lampe d'un côté) et s'étend sous la silhouette.
        """
        assert self._plate_small is not None
        live = cv2.resize(frame, self.small, interpolation=cv2.INTER_AREA).astype(np.float32)
        if mask is None:
            w = self._border_small
        else:
            w = 1.0 - cv2.resize(mask, self.small, interpolation=cv2.INTER_AREA)
            w = np.clip(w * 1.5 - 0.5, 0.0, 1.0)  # n'utiliser que le fond franchement visible
        # Ignorer ce qui a changé dans la scène (objet déplacé, quelqu'un qui passe).
        diff = np.abs(live - self._plate_small).mean(axis=2)
        w = w * (diff < 45).astype(np.float32)

        w3 = w[..., None]
        s = self._gain_sigma
        num = cv2.GaussianBlur(live * w3, (0, 0), s)
        den = cv2.GaussianBlur(self._plate_small * w3, (0, 0), s)
        wsum = cv2.GaussianBlur(w, (0, 0), s)[..., None]

        tot = float(w.sum())
        if tot > 50:
            g_global = (live * w3).sum(axis=(0, 1)) / ((self._plate_small * w3).sum(axis=(0, 1)) + 1e-3)
        else:
            g_global = np.ones(3, np.float32)
        local = num / (den + 1e-3)
        alpha = np.clip(wsum / 0.15, 0.0, 1.0)  # loin de tout fond visible → gain global
        gain = alpha * local + (1.0 - alpha) * g_global.astype(np.float32)
        gain = np.clip(gain, 0.5, 2.0).astype(np.float32)

        if self._prev_gain is not None:  # lissage temporel : pas de scintillement
            gain = 0.6 * gain + 0.4 * self._prev_gain
        self._prev_gain = gain
        return cv2.resize(gain, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

    # --- grain ----------------------------------------------------------------

    def _hf_sigma(self, img: np.ndarray) -> float:
        """Écart-type robuste des hautes fréquences sur les bords (texture + bruit)."""
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        hf = (g - cv2.GaussianBlur(g, (5, 5), 0))[::2, ::2][self._border[::2, ::2]]
        return float(1.4826 * np.median(np.abs(hf)))

    def _make_grain_bank(self, width: int, height: int, n: int = 4) -> tuple[list[np.ndarray], float]:
        """Quelques trames de grain pré-calculées (σ unitaire), et leur réponse au filtre HF."""
        bank = []
        for _ in range(n):
            mono = self._rng.standard_normal((height, width, 1), dtype=np.float32)
            chroma = self._rng.standard_normal((height, width, 3), dtype=np.float32)
            g = 0.8 * mono + 0.35 * chroma
            g = cv2.GaussianBlur(g, (0, 0), 0.6)  # léger : le bruit d'une webcam est un peu corrélé
            bank.append(g)
        # Combien de « σ HF » produit une unité de ce grain : sert à le doser.
        probe = np.clip(128 + bank[0] * 10, 0, 255).astype(np.uint8)
        unit = self._hf_sigma(probe) / 10.0
        return bank, max(unit, 1e-3)

    def _grain(self, frame: np.ndarray) -> np.ndarray | None:
        sigma_live = self._hf_sigma(frame)
        target = float(np.sqrt(max(0.0, sigma_live**2 - self._plate_sigma**2)))
        self._noise_sigma = 0.8 * self._noise_sigma + 0.2 * target
        amp = self._noise_sigma / self._grain_unit
        if amp < 0.3:
            return None
        g = self._grain_bank[int(self._rng.integers(len(self._grain_bank)))]
        if self._rng.random() < 0.5:
            g = g[::-1]
        if self._rng.random() < 0.5:
            g = g[:, ::-1]
        return np.ascontiguousarray(g) * amp

    # --- masque de la personne ------------------------------------------------

    def segment(self, rgb: np.ndarray, ts_ms: int) -> np.ndarray:
        """Confiance brute (H, W) du segmenteur, calculée une seule fois par image."""
        if self._seg_cache is not None and self._seg_cache[0] == ts_ms:
            return self._seg_cache[1]
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._segmenter.segment_for_video(image, ts_ms)
        conf = np.asarray(result.confidence_masks[0].numpy_view())
        conf = np.ascontiguousarray(conf[..., 0] if conf.ndim == 3 else conf, dtype=np.float32)
        self._seg_cache = (ts_ms, conf)
        return conf

    def person_mask(self, rgb: np.ndarray, ts_ms: int) -> np.ndarray:
        """Masque flottant (H, W) dans [0, 1] : 1 = personne, élargi pour l'effacement."""
        return self.refine_mask(self.segment(rgb, ts_ms))

    def refine_mask(self, conf: np.ndarray) -> np.ndarray:
        """Confiance brute → masque large et doux, stable dans le temps.

        Seuil bas pour attraper cheveux et bords flous, dilatation large pour couvrir
        le halo et l'ombre collée au corps, flou pour une transition invisible,
        puis maximum avec le masque précédent atténué pour ne pas laisser de traînée
        quand on bouge.
        """
        small = cv2.resize(conf.astype(np.float32), self.small, interpolation=cv2.INTER_AREA)
        mask = (small > 0.3).astype(np.uint8) * 255
        mask = cv2.dilate(mask, self._grow_kernel)
        mask = cv2.GaussianBlur(mask.astype(np.float32) / 255.0, (0, 0), self._feather_sigma)
        # La dilatation garantit 1.0 sur toute la personne ; on resserre la rampe vers l'extérieur.
        mask = np.clip(mask * 1.6, 0.0, 1.0)
        if self._prev_mask is not None:
            mask = np.maximum(mask, self._prev_mask * 0.7)
        self._prev_mask = mask
        return cv2.resize(mask, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

    def reset_mask(self) -> None:
        self._prev_mask = None
        self._prev_gain = None

    def close(self) -> None:
        self._segmenter.close()
