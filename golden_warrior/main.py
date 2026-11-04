"""Golden Warrior : serre les deux poings et deviens un guerrier doré sur Zoom.

Boucle principale : webcam → détection des poings → effet doré → caméra virtuelle OBS.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from camkit.camera import FrameSource, VirtualOutput, list_cameras
from camkit.gesture import GestureDetector
from camkit.models import ensure_models
from camkit.segment import PersonMatte
from camkit.sound import SoundPlayer

from . import __version__
from .effect import GoldenRenderer, GoldenState

WINDOW = "Golden Warrior"
SOUNDS = Path(__file__).resolve().parent
HELP_KEYS = "[g] transformation  [d] debug  [q] quitter"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="golden-warrior",
        description="Serre les deux poings face à la caméra et deviens un guerrier doré.",
    )
    p.add_argument("--camera", default="0", help="index de la webcam, ou chemin d'une image/vidéo (défaut : 0)")
    p.add_argument("--list-cameras", action="store_true", help="liste les webcams disponibles et quitte")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--hold", type=float, default=0.5, help="durée de maintien des poings en secondes (défaut : 0.5)")
    p.add_argument("--no-lightning", action="store_true", help="désactive les éclairs")
    p.add_argument("--no-sound", action="store_true", help="coupe les effets sonores")
    p.add_argument("--volume", type=float, default=1.0, help="volume des effets sonores, de 0 à 1 (défaut : 1)")
    p.add_argument("--no-virtual", action="store_true", help="aperçu seul, sans caméra virtuelle")
    p.add_argument("--no-preview", action="store_true", help="pas de fenêtre d'aperçu (les touches sont alors inactives)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p.parse_args(argv)


def draw_debug(img: np.ndarray, gesture: GestureDetector) -> None:
    d = gesture.debug
    color = (0, 215, 255) if d.fists_posed else (200, 200, 200)
    for hand in d.hands:
        cv2.circle(img, (int(hand[9][0]), int(hand[9][1])), 22, color, 3)
    if d.face:
        x, y, w, h, _ = d.face
        cv2.rectangle(img, (int(x), int(y)), (int(x + w), int(y + h)), (255, 255, 255), 1)
    if d.fists_progress > 0:
        width = img.shape[1]
        cv2.rectangle(img, (20, 60), (20 + int((width - 40) * d.fists_progress), 72), (0, 215, 255), -1)


def draw_hud(img: np.ndarray, lines: list[str]) -> None:
    y = 30
    for line in lines:
        cv2.putText(img, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)
        y += 28


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list_cameras:
        cams = list_cameras()
        print("Caméras disponibles :", ", ".join(map(str, cams)) if cams else "aucune")
        return 0

    models = ensure_models()
    source = FrameSource(args.camera, args.width, args.height, args.fps)
    output = VirtualOutput(args.width, args.height, args.fps, enabled=not args.no_virtual)
    gesture = GestureDetector(models, fists_hold=args.hold)
    matte = PersonMatte(models, args.width, args.height)
    sound = SoundPlayer(SOUNDS, enabled=not args.no_sound, volume=args.volume)
    state = GoldenState()
    fx = GoldenRenderer(args.width, args.height, lightning=not args.no_lightning)

    def transform(now: float) -> None:
        state.toggle(now)
        # Musique à la transformation seulement (fondu intégré au fichier) ; silence à l'arrêt.
        if state.active:
            sound.play("golden")
        else:
            sound.stop("golden")

    debug = False
    t0 = time.monotonic()
    fps_clock, fps_count, fps = time.monotonic(), 0, 0.0
    print(HELP_KEYS, file=sys.stderr)

    try:
        while True:
            frame = source.read()
            now = time.monotonic()
            ts_ms = int((now - t0) * 1000)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if gesture.update(rgb, now, ts_ms) == "fists":
                transform(now)

            level = state.level(now)
            if level > 0.01:
                matte.submit(rgb, ts_ms)
                m = matte.matte(frame)
            else:
                matte.reset()
                m = None
            out = fx.render(frame, m, level, state.flash(now), now)
            output.send(out)

            fps_count += 1
            if now - fps_clock >= 1.0:
                fps, fps_count, fps_clock = fps_count / (now - fps_clock), 0, now

            if args.no_preview:
                continue
            preview = out.copy()
            if debug:
                draw_debug(preview, gesture)
            mode = "golden warrior" if state.active else "normal"
            draw_hud(preview, [f"{mode}  {fps:.0f} fps", HELP_KEYS])
            cv2.imshow(WINDOW, preview)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                break
            if key == ord("g"):
                transform(now)
            if key == ord("d"):
                debug = not debug
    except KeyboardInterrupt:
        pass
    finally:
        output.close()
        sound.close()
        source.release()
        gesture.close()
        matte.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
