"""Lecture des effets sonores avec afplay (intégré à macOS), sans bloquer la vidéo."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SOUNDS_DIR = Path(__file__).resolve().parent


class SoundPlayer:
    def __init__(self, enabled: bool = True, volume: float = 1.0):
        self.enabled = enabled and shutil.which("afplay") is not None
        self.volume = volume
        self._procs: list[subprocess.Popen] = []

    def play(self, name: str) -> None:
        """Joue ``<name>.mp3`` du paquet s'il existe ; ne fait rien sinon."""
        path = SOUNDS_DIR / f"{name}.mp3"
        if not self.enabled or not path.exists():
            return
        self._procs = [p for p in self._procs if p.poll() is None]
        self._procs.append(
            subprocess.Popen(
                ["afplay", "-v", str(self.volume), str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )

    def close(self) -> None:
        for p in self._procs:
            if p.poll() is None:
                p.terminate()
