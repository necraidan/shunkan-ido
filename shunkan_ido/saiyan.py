"""Mode Super Saiyan : cheveux dorés, aura de flammes, éclairs et flash de transformation."""

from __future__ import annotations

import cv2
import numpy as np

GOLD_BGR = np.array([40, 205, 255], np.float32)
AURA_BGR = np.array([60, 215, 255], np.float32)
LIGHTNING_BGR = (255, 235, 190)


class SaiyanState:
    """Allumé / éteint, avec une montée (transformation) et une descente progressives."""

    def __init__(self, ramp_up: float = 0.8, ramp_down: float = 0.4):
        self.ramp_up, self.ramp_down = ramp_up, ramp_down
        self.active = False
        self.changed_at = -1e9

    def toggle(self, now: float) -> None:
        # On part du niveau courant pour éviter un saut si on bascule en pleine transition.
        level = self.level(now)
        self.active = not self.active
        ramp = self.ramp_up if self.active else self.ramp_down
        done = level if self.active else 1.0 - level
        self.changed_at = now - done * ramp

    def level(self, now: float) -> float:
        ramp = self.ramp_up if self.active else self.ramp_down
        t = min(1.0, (now - self.changed_at) / ramp) if ramp > 0 else 1.0
        return t if self.active else 1.0 - t

    def flash(self, now: float) -> float:
        """Flash blanc juste après la transformation."""
        if not self.active:
            return 0.0
        dt = now - self.changed_at - self.ramp_up * 0.35
        return float(max(0.0, 1.0 - abs(dt) / 0.18)) * 0.6


class SaiyanRenderer:
    WORK_SCALE = 4

    def __init__(self, width: int, height: int, seed: int = 0):
        self.width, self.height = width, height
        self.small = (width // self.WORK_SCALE, height // self.WORK_SCALE)
        self._rng = np.random.default_rng(seed)
        sw, sh = self.small
        # Texture de bruit lisse, deux fois plus haute que l'image, qui défile vers le haut.
        noise = self._rng.random((sh * 2, sw)).astype(np.float32)
        noise = cv2.GaussianBlur(noise, (0, 0), sigmaX=2.0, sigmaY=5.0)
        noise = (noise - noise.min()) / (noise.max() - noise.min() + 1e-6)
        self._noise = np.vstack([noise, noise])
        self._dil = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))

    # --- cheveux ----------------------------------------------------------------

    def _hair_mask(self, conf: np.ndarray, face: tuple | None) -> np.ndarray | None:
        """Pixels de la personne au-dessus du front : les cheveux (approximation)."""
        if face is None:
            return None
        x, y, w, h, _eyes = face
        top_line = int(y - 0.02 * h)  # le cadre BlazeFace commence vers le haut du front
        x0, x1 = int(x - 0.7 * w), int(x + 1.7 * w)
        region = np.zeros((self.height, self.width), np.float32)
        region[: max(0, top_line), max(0, x0) : min(self.width, x1)] = 1.0
        # Rampe douce sur la ligne du front pour ne pas couper net.
        ramp = int(0.10 * h)
        for i in range(ramp):
            yy = top_line + i
            if 0 <= yy < self.height:
                region[yy, max(0, x0) : min(self.width, x1)] = 1.0 - i / ramp
        hair = (conf > 0.5).astype(np.float32) * region
        return cv2.GaussianBlur(hair, (0, 0), 3)

    @staticmethod
    def _gold(frame: np.ndarray) -> np.ndarray:
        """Teinte dorée qui garde les reflets et les mèches (luminance conservée et rehaussée)."""
        lum = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        lum = 0.35 + 0.95 * lum
        return np.clip(lum[..., None] * GOLD_BGR, 0, 255).astype(np.uint8)

    # --- aura -----------------------------------------------------------------

    def _aura(self, conf: np.ndarray, now: float) -> np.ndarray:
        """Intensité (H, W) de l'aura : halo autour de la silhouette, étiré vers le haut en flammes."""
        sw, sh = self.small
        m = (cv2.resize(conf, self.small, interpolation=cv2.INTER_AREA) > 0.5).astype(np.float32)
        base = cv2.GaussianBlur(cv2.dilate(m, self._dil), (0, 0), 4.0)

        # Flammes : on traîne le halo vers le haut, plus loin là où le bruit est fort.
        offset = int(now * 60) % sh
        noise = self._noise[offset : offset + sh]
        flames = base.copy()
        steps = 16
        for k in range(1, steps + 1):
            shifted = np.zeros_like(base)
            shifted[: sh - 3 * k] = base[3 * k :]
            flames = np.maximum(flames, shifted * (1.0 - k / (steps + 1)) * (0.3 + 1.1 * noise))
        flicker = 0.85 + 0.15 * np.sin(now * 23.0)
        aura = np.clip(flames - 0.9 * m, 0.0, 1.0) * (0.55 + 0.75 * noise) * flicker
        aura += m * 0.05  # légère lueur sur le corps
        return cv2.resize(aura, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

    def _lightning(self, out: np.ndarray, conf: np.ndarray) -> None:
        """De temps en temps, un éclair bleu-blanc qui part de la silhouette."""
        if self._rng.random() > 0.22:
            return
        m = (cv2.resize(conf, self.small, interpolation=cv2.INTER_AREA) > 0.5).astype(np.uint8)
        contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            return
        pts = max(contours, key=cv2.contourArea).reshape(-1, 2) * self.WORK_SCALE
        layer = np.zeros_like(out)
        for _ in range(int(self._rng.integers(1, 3))):
            p = pts[int(self._rng.integers(len(pts)))].astype(np.float32)
            angle = self._rng.uniform(0, 2 * np.pi)
            path = [p.copy()]
            for _ in range(int(self._rng.integers(4, 8))):
                angle += self._rng.uniform(-0.9, 0.9)
                step = self._rng.uniform(12, 30)
                p = p + step * np.array([np.cos(angle), np.sin(angle)], np.float32)
                path.append(p.copy())
            poly = np.array(path, np.int32).reshape(-1, 1, 2)
            cv2.polylines(layer, [poly], False, LIGHTNING_BGR, 5, cv2.LINE_AA)
            cv2.polylines(layer, [poly], False, (255, 255, 255), 2, cv2.LINE_AA)
        glow = cv2.GaussianBlur(layer, (0, 0), 4)
        cv2.add(out, glow, dst=out)
        cv2.add(out, layer, dst=out)

    # --- rendu ----------------------------------------------------------------

    def render(self, frame: np.ndarray, conf: np.ndarray, face: tuple | None, level: float, flash: float, now: float) -> np.ndarray:
        if level <= 0.01:
            return frame
        out = frame
        hair = self._hair_mask(conf, face)
        if hair is not None:
            alpha = np.ascontiguousarray(hair * 0.85 * level, dtype=np.float32)
            out = cv2.blendLinear(out, self._gold(out), 1.0 - alpha, alpha)

        aura = self._aura(conf, now) * level
        glow = (aura[..., None] * AURA_BGR).astype(np.float32)
        out = np.clip(out.astype(np.float32) + glow, 0, 255).astype(np.uint8)

        if level > 0.6:
            self._lightning(out, conf)

        if level < 1.0:  # tremblement pendant la transformation
            amp = int(8 * np.sin(np.pi * level))
            if amp:
                out = np.roll(out, int(self._rng.integers(-amp, amp + 1)), axis=1)
        if flash > 0.01:
            out = cv2.addWeighted(out, 1.0 - flash, np.full_like(out, 255), flash, 0)
        return out
