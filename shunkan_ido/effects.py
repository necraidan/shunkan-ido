"""Machine à états visible / caché et effet de téléportation instantanée."""

from __future__ import annotations

from enum import Enum

import cv2
import numpy as np


class Phase(Enum):
    VISIBLE = "visible"
    VANISHING = "vanishing"
    HIDDEN = "hidden"
    APPEARING = "appearing"


class VanishState:
    def __init__(self, transition: float = 0.45):
        self.transition = transition
        self.phase = Phase.VISIBLE
        self.started_at = 0.0
        self._rng_seed = 0

    @property
    def hidden_or_going(self) -> bool:
        return self.phase in (Phase.HIDDEN, Phase.VANISHING)

    def toggle(self, now: float) -> None:
        self.started_at = now
        self._rng_seed += 1
        self.phase = Phase.APPEARING if self.hidden_or_going else Phase.VANISHING

    def progress(self, now: float) -> float:
        if self.transition <= 0:
            return 1.0
        return min(1.0, (now - self.started_at) / self.transition)

    def tick(self, now: float) -> None:
        """Termine une transition arrivée à son terme."""
        if self.phase in (Phase.VANISHING, Phase.APPEARING) and self.progress(now) >= 1.0:
            self.phase = Phase.HIDDEN if self.phase is Phase.VANISHING else Phase.VISIBLE

    @property
    def seed(self) -> int:
        return self._rng_seed


def smoothstep(t: float) -> float:
    t = float(np.clip(t, 0.0, 1.0))
    return t * t * (3.0 - 2.0 * t)


def blend(a: np.ndarray, b: np.ndarray, alpha) -> np.ndarray:
    """a * (1 - alpha) + b * alpha, alpha scalaire ou masque (H, W)."""
    if np.isscalar(alpha):
        return cv2.addWeighted(a, 1.0 - float(alpha), b, float(alpha), 0)
    alpha = np.ascontiguousarray(alpha, dtype=np.float32)
    return cv2.blendLinear(a, b, 1.0 - alpha, alpha)


def erase_person(frame: np.ndarray, plate: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Remplace la personne par le fond, le reste de la scène reste en direct."""
    return blend(frame, plate, mask)


def instant_transmission(
    frame: np.ndarray,
    plate: np.ndarray,
    mask: np.ndarray,
    t: float,
    seed: int,
    band: int = 10,
    max_shift: int = 70,
) -> np.ndarray:
    """Effet Shunkan Idō : bandes qui se décalent, traînées blanches, flash, puis fondu.

    ``t`` va de 0 (visible) à 1 (disparu). Pour réapparaître on appelle avec 1 - t.
    """
    h, w = frame.shape[:2]
    rng = np.random.default_rng(seed)
    out = frame.copy()

    # 1. Découpe horizontale en bandes, décalage croissant avec t (uniquement là où il y a la personne).
    shifts = rng.uniform(-1.0, 1.0, size=(h + band - 1) // band)
    person = mask > 0.05
    for i, y in enumerate(range(0, h, band)):
        rows = person[y : y + band]
        if not rows.any():
            continue
        dx = int(shifts[i] * max_shift * t)
        if dx:
            # On ne déplace que les pixels de la silhouette, le décor reste en place.
            rolled = np.roll(frame[y : y + band], dx, axis=1)
            rolled_mask = np.roll(mask[y : y + band], dx, axis=1)
            out[y : y + band] = blend(frame[y : y + band], rolled, rolled_mask)

    # 2. Traînées blanches horizontales qui partent de la silhouette.
    ys, xs = np.nonzero(person)
    if len(ys):
        cx = int(xs.mean())
        y0, y1 = int(ys.min()), int(ys.max())
        streaks = np.zeros_like(frame)
        n = int(60 * t) + 8
        for y in rng.integers(y0, y1 + 1, size=n):
            length = int(rng.uniform(40, 260) * (0.3 + t))
            direction = 1 if rng.random() < 0.5 else -1
            x_end = int(np.clip(cx + direction * length, 0, w - 1))
            thickness = int(rng.integers(1, 3))
            cv2.line(streaks, (cx, int(y)), (x_end, int(y)), (255, 255, 255), thickness)
        streaks = cv2.GaussianBlur(streaks, (0, 0), 1.2)
        out = cv2.addWeighted(out, 1.0, streaks, 0.9 * np.sin(np.pi * t), 0)

    # 3. Fondu de la personne vers le fond.
    alpha_person = smoothstep((t - 0.25) / 0.75)
    out = blend(out, plate, mask * alpha_person)

    # 4. Flash blanc au pic de la transition.
    flash = 0.55 * np.sin(np.pi * t) ** 4
    if flash > 0.01:
        white = np.full_like(out, 255)
        out = cv2.addWeighted(out, 1.0 - flash, white, flash, 0)
    return out


def compose(
    frame: np.ndarray,
    plate: np.ndarray,
    mask: np.ndarray | None,
    state: VanishState,
    now: float,
    static_hidden: bool = False,
) -> np.ndarray:
    """Image à envoyer dans Zoom selon la phase courante."""
    if state.phase is Phase.VISIBLE:
        return frame
    if state.phase is Phase.HIDDEN:
        if static_hidden or mask is None:
            return plate
        return erase_person(frame, plate, mask)

    t = state.progress(now)
    if state.phase is Phase.APPEARING:
        t = 1.0 - t
    if mask is None:
        return blend(frame, plate, smoothstep(t))
    return instant_transmission(frame, plate, mask, t, state.seed)
