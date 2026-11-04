"""Effet Golden Warrior : cheveux dorés, aura d'énergie, éclairs et flash de transformation."""

from __future__ import annotations

import cv2
import numpy as np

GOLD_BGR = np.array([40, 205, 255], np.float32)
GLOW_BGR = np.array([40, 190, 255], np.float32)  # lueur large, or chaud
RIM_BGR = np.array([170, 245, 255], np.float32)  # liseré, presque blanc
STREAK_BGR = (110, 235, 255)
LIGHTNING_BGR = (255, 235, 190)


class GoldenState:
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


class Streaks:
    """Traits d'énergie qui naissent sur le contour et montent en s'effaçant."""

    def __init__(self, rng: np.random.Generator, max_count: int = 140):
        self._rng = rng
        self.max_count = max_count
        self.pos = np.zeros((0, 2), np.float32)
        self.speed = np.zeros(0, np.float32)
        self.length = np.zeros(0, np.float32)
        self.life = np.zeros(0, np.float32)
        self.max_life = np.zeros(0, np.float32)

    def update(self, contour: np.ndarray | None, dt: float, spawn_rate: float) -> None:
        if len(self.life):
            self.life += dt
            self.pos[:, 1] -= self.speed * dt
            self.pos[:, 0] += self._rng.normal(0, 25, len(self.life)).astype(np.float32) * dt
            keep = self.life < self.max_life
            self.pos, self.speed, self.length = self.pos[keep], self.speed[keep], self.length[keep]
            self.life, self.max_life = self.life[keep], self.max_life[keep]
        if contour is None or len(contour) == 0:
            return
        n = min(int(self._rng.poisson(spawn_rate * dt)), self.max_count - len(self.life))
        if n <= 0:
            return
        # Naissance plutôt sur le haut et les côtés : on écarte le bas du contour (coupé par le cadre).
        y_cut = np.percentile(contour[:, 1], 85)
        candidates = contour[contour[:, 1] <= y_cut]
        if len(candidates) == 0:
            return
        picks = candidates[self._rng.integers(len(candidates), size=n)].astype(np.float32)
        picks[:, 0] += self._rng.normal(0, 6, n)
        self.pos = np.vstack([self.pos, picks])
        self.speed = np.concatenate([self.speed, self._rng.uniform(260, 520, n).astype(np.float32)])
        self.length = np.concatenate([self.length, self._rng.uniform(25, 75, n).astype(np.float32)])
        self.life = np.concatenate([self.life, np.zeros(n, np.float32)])
        self.max_life = np.concatenate([self.max_life, self._rng.uniform(0.25, 0.55, n).astype(np.float32)])

    def draw(self, layer: np.ndarray) -> None:
        for (x, y), length, life, max_life in zip(self.pos, self.length, self.life, self.max_life):
            fade = 1.0 - life / max_life
            # Apparition rapide, disparition lente.
            alpha = min(1.0, life / 0.06) * fade
            if alpha <= 0.02:
                continue
            color = tuple(int(c * alpha) for c in STREAK_BGR)
            tail = (int(x), int(y + length * (0.6 + 0.4 * fade)))
            cv2.line(layer, (int(x), int(y)), tail, color, 2, cv2.LINE_AA)


class GoldenRenderer:
    WORK_SCALE = 4

    def __init__(self, width: int, height: int, seed: int | None = None, lightning: bool = True):
        self.width, self.height = width, height
        self.lightning = lightning
        self.small = (width // self.WORK_SCALE, height // self.WORK_SCALE)
        self._rng = np.random.default_rng(seed)
        self._streaks = Streaks(self._rng)
        self._last_now: float | None = None

    # --- cheveux ----------------------------------------------------------------

    @staticmethod
    def _gold(roi: np.ndarray, hair: np.ndarray) -> np.ndarray:
        """Teinte dorée lumineuse qui garde les mèches, quelle que soit la couleur d'origine.

        La luminance est recentrée sur la moyenne des cheveux : des cheveux noirs deviennent
        un or vif, pas un olive terne, et le relief des mèches est conservé (et accentué).
        """
        lum = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        w = hair > 0.5
        mean = float(lum[w].mean()) if w.any() else 0.3
        shade = np.clip(0.82 + 1.6 * (lum - mean), 0.45, 1.25)
        return np.clip(shade[..., None] * GOLD_BGR, 0, 255).astype(np.uint8)

    @staticmethod
    def _bbox(mask: np.ndarray, thr: float = 0.02, pad: int = 4) -> tuple[slice, slice] | None:
        rows = np.flatnonzero(mask.max(axis=1) > thr)
        if rows.size == 0:
            return None
        cols = np.flatnonzero(mask[rows[0] : rows[-1] + 1].max(axis=0) > thr)
        h, w = mask.shape
        return (slice(max(0, rows[0] - pad), min(h, rows[-1] + 1 + pad)), slice(max(0, cols[0] - pad), min(w, cols[-1] + 1 + pad)))

    # --- aura -----------------------------------------------------------------

    def _aura(self, person: np.ndarray, now: float) -> np.ndarray:
        """Lumière additive (H, W, 3) float : liseré net + lueur large qui pulse."""
        m = cv2.resize(person, self.small, interpolation=cv2.INTER_AREA)
        pulse = 0.8 + 0.2 * np.sin(now * 9.0) + 0.06 * np.sin(now * 31.0)

        # Liseré : bord extérieur fin et lumineux.
        rim = np.clip(cv2.GaussianBlur(m, (0, 0), 1.2) - m, 0.0, 1.0) * 2.2
        # Lueur : halo large, légèrement plus haut que la silhouette (l'énergie monte).
        glow = cv2.GaussianBlur(m, (0, 0), 7.0)
        glow = np.roll(glow, -3, axis=0)
        glow = np.clip(glow - m, 0.0, 1.0) * 2.2  # uniquement autour de la silhouette, pas dessus

        light = rim[..., None] * RIM_BGR + (glow * pulse)[..., None] * GLOW_BGR
        light += (m * 0.04)[..., None] * GLOW_BGR  # légère lueur sur le corps
        return cv2.resize(light, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

    def _contour(self, person: np.ndarray) -> np.ndarray | None:
        m = (cv2.resize(person, self.small, interpolation=cv2.INTER_AREA) > 0.5).astype(np.uint8)
        contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            return None
        return max(contours, key=cv2.contourArea).reshape(-1, 2) * self.WORK_SCALE

    def _lightning(self, out: np.ndarray, contour: np.ndarray | None) -> None:
        """De temps en temps, un éclair bleu-blanc qui part de la silhouette."""
        if contour is None or self._rng.random() > 0.22:
            return
        layer = np.zeros_like(out)
        for _ in range(int(self._rng.integers(1, 3))):
            p = contour[int(self._rng.integers(len(contour)))].astype(np.float32)
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

    def render(self, frame: np.ndarray, matte, level: float, flash: float, now: float) -> np.ndarray:
        """``matte`` : détourage (camkit.segment.Matte, champs ``person`` et ``hair``) ou None."""
        dt = 0.0 if self._last_now is None else min(0.1, now - self._last_now)
        self._last_now = now
        active = level > 0.01 and matte is not None
        contour = self._contour(matte.person) if active else None
        self._streaks.update(contour, dt, spawn_rate=220.0 * level)
        if not active:
            return frame

        out = frame.copy()
        # Cheveux dorés, calculés seulement dans le cadre des cheveux.
        box = self._bbox(matte.hair)
        if box is not None:
            hair = matte.hair[box]
            alpha = np.ascontiguousarray(np.clip(hair * 1.2, 0.0, 1.0) * 0.92 * level, dtype=np.float32)
            roi = out[box]
            out[box] = cv2.blendLinear(roi, self._gold(roi, hair), 1.0 - alpha, alpha)

        # Lumière additive en 8 bits (addition saturée), bien plus rapide qu'en flottants.
        light = cv2.convertScaleAbs(self._aura(matte.person, now), alpha=level)
        streaks = np.zeros_like(frame)
        self._streaks.draw(streaks)
        # Les traits restent derrière la personne : on les coupe sur la silhouette.
        behind = np.ascontiguousarray(1.0 - np.clip(matte.person * 1.5, 0.0, 1.0), dtype=np.float32)
        streaks = cv2.blendLinear(np.zeros_like(streaks), streaks, 1.0 - behind, behind)
        half = (self.width // 2, self.height // 2)
        halo = cv2.resize(cv2.GaussianBlur(cv2.resize(streaks, half, interpolation=cv2.INTER_AREA), (0, 0), 1.6), (self.width, self.height))
        cv2.add(out, light, dst=out)
        cv2.add(out, streaks, dst=out)
        cv2.add(out, cv2.convertScaleAbs(halo, alpha=1.5), dst=out)

        if self.lightning and level > 0.6:
            self._lightning(out, contour)

        if level < 1.0:  # tremblement pendant la transformation
            amp = int(8 * np.sin(np.pi * level))
            if amp:
                out = np.roll(out, int(self._rng.integers(-amp, amp + 1)), axis=1)
        if flash > 0.01:
            out = cv2.addWeighted(out, 1.0 - flash, np.full_like(out, 255), flash, 0)
        return out
