"""Shunkan Idō : disparais de Zoom avec le geste de Goku, ou passe en Super Saiyan.

Boucle principale : webcam → détection du geste → compositing → caméra virtuelle OBS.
"""

from __future__ import annotations

import argparse
import sys
import time

import cv2
import numpy as np

from . import __version__
from .background import BackgroundPlate, Calibration
from .camera import FrameSource, VirtualOutput, list_cameras
from .effects import Phase, VanishState, compose
from .gesture import GestureDetector
from .models import cache_dir, ensure_models
from .saiyan import SaiyanRenderer, SaiyanState
from .sound import SoundPlayer

WINDOW = "Shunkan Ido"
HELP_KEYS = "[espace] téléportation  [s] Super Saiyan  [b] recalibrer le fond  [d] debug  [q] quitter"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="shunkan-ido",
        description="Disparais de Zoom en faisant le geste de téléportation de Goku.",
    )
    p.add_argument("--camera", default="0", help="index de la webcam, ou chemin d'une image/vidéo (défaut : 0)")
    p.add_argument("--list-cameras", action="store_true", help="liste les webcams disponibles et quitte")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--hold", type=float, default=0.3, help="durée de maintien du geste en secondes (défaut : 0.3)")
    p.add_argument("--saiyan-hold", type=float, default=0.5, help="durée de maintien des poings pour le Super Saiyan (défaut : 0.5)")
    p.add_argument("--transition", type=float, default=0.45, help="durée de l'effet en secondes (défaut : 0.45)")
    p.add_argument("--countdown", type=float, default=5.0, help="compte à rebours avant la photo du fond (défaut : 5)")
    p.add_argument("--loose", action="store_true", help="geste plus tolérant (ignore annulaire et auriculaire)")
    p.add_argument("--static", action="store_true", help="quand caché, envoie le fond figé au lieu de gommer seulement toi")
    p.add_argument("--reuse-background", action="store_true", help="réutilise le fond de la dernière session sans recalibrer")
    p.add_argument("--no-sound", action="store_true", help="coupe les effets sonores")
    p.add_argument("--volume", type=float, default=1.0, help="volume des effets sonores, de 0 à 1 (défaut : 1)")
    p.add_argument("--no-virtual", action="store_true", help="aperçu seul, sans caméra virtuelle")
    p.add_argument("--no-preview", action="store_true", help="pas de fenêtre d'aperçu (les touches sont alors inactives)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p.parse_args(argv)


def vanish_amount(state: VanishState, now: float) -> float:
    """0 = complètement visible, 1 = complètement disparu."""
    if state.phase is Phase.VISIBLE:
        return 0.0
    if state.phase is Phase.HIDDEN:
        return 1.0
    t = state.progress(now)
    return t if state.phase is Phase.VANISHING else 1.0 - t


def draw_debug(img: np.ndarray, gesture: GestureDetector) -> None:
    d = gesture.debug
    color = (0, 255, 0) if d.posed else (0, 200, 255)
    if d.forehead:
        z = d.forehead
        cv2.rectangle(img, (int(z.x0), int(z.y0)), (int(z.x1), int(z.y1)), color, 2)
    for hand in d.hands:
        for i in (8, 12):
            cv2.circle(img, (int(hand[i][0]), int(hand[i][1])), 8, color, -1)
        for i in (16, 20):
            cv2.circle(img, (int(hand[i][0]), int(hand[i][1])), 5, (255, 120, 0), -1)
    w = img.shape[1]
    if d.progress > 0:
        cv2.rectangle(img, (20, 60), (20 + int((w - 40) * d.progress), 72), color, -1)
    if d.saiyan_progress > 0:
        cv2.rectangle(img, (20, 78), (20 + int((w - 40) * d.saiyan_progress), 90), (0, 215, 255), -1)
    if d.saiyan_posed:
        for hand in d.hands:
            cv2.circle(img, (int(hand[9][0]), int(hand[9][1])), 22, (0, 215, 255), 3)


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
    gesture = GestureDetector(models, hold=args.hold, saiyan_hold=args.saiyan_hold, loose=args.loose)
    sound = SoundPlayer(enabled=not args.no_sound, volume=args.volume)
    background = BackgroundPlate(models, cache_dir() / "background.png", args.width, args.height)
    state = VanishState(transition=args.transition)
    saiyan = SaiyanState()
    saiyan_fx = SaiyanRenderer(args.width, args.height)

    def teleport(now: float) -> None:
        state.toggle(now)
        sound.play("teleport")

    def transform(now: float) -> None:
        saiyan.toggle(now)
        sound.play("saiyan" if saiyan.active else "saiyan_off")

    calibration: Calibration | None = None
    if args.reuse_background and background.load_cached():
        print("[fond] fond de la dernière session réutilisé", file=sys.stderr)
    else:
        calibration = Calibration(args.countdown, frames=30, now=time.monotonic())

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
            hud: list[str] = []

            if calibration is not None:
                plate = calibration.feed(frame, now)
                hud.append(calibration.status(now))
                if plate is not None:
                    background.set_plate(plate)
                    background.save_cache()
                    calibration = None
                    print("[fond] calibré", file=sys.stderr)
                out = frame
            else:
                event = gesture.update(rgb, now, ts_ms)
                if event == "teleport":
                    teleport(now)
                elif event == "saiyan":
                    transform(now)
                state.tick(now)

                # Super Saiyan d'abord, sur l'image en direct ; il s'efface quand on disparaît.
                level = saiyan.level(now) * (1.0 - vanish_amount(state, now))
                if level > 0.01:
                    conf = background.segment(rgb, ts_ms)
                    frame = saiyan_fx.render(frame, conf, gesture.debug.face, level, saiyan.flash(now), now)

                mask = None
                plate = None
                if state.phase is Phase.VISIBLE:
                    background.reset_mask()
                elif background.plate is not None:
                    if not (args.static and state.phase is Phase.HIDDEN):
                        mask = background.person_mask(rgb, ts_ms)
                    plate = background.match_exposure(frame, mask)
                if background.plate is None:
                    out = frame
                else:
                    out = compose(frame, plate if plate is not None else frame, mask, state, now, args.static)
                mode = "  super saiyan" if saiyan.active else ""
                hud.append(f"{state.phase.value}{mode}  {fps:.0f} fps")

            output.send(out)

            fps_count += 1
            if now - fps_clock >= 1.0:
                fps, fps_count, fps_clock = fps_count / (now - fps_clock), 0, now

            if args.no_preview:
                continue
            preview = out.copy()
            if debug:
                draw_debug(preview, gesture)
            draw_hud(preview, hud + [HELP_KEYS])
            cv2.imshow(WINDOW, preview)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                break
            if key == ord(" ") and calibration is None:
                teleport(now)
            if key == ord("s") and calibration is None:
                transform(now)
            if key == ord("b"):
                calibration = Calibration(args.countdown, frames=30, now=now)
                if state.phase is not Phase.VISIBLE:
                    state.phase = Phase.VISIBLE
            if key == ord("d"):
                debug = not debug
    except KeyboardInterrupt:
        pass
    finally:
        output.close()
        sound.close()
        source.release()
        gesture.close()
        background.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
