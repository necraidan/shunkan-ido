"""Lecture des effets sonores avec afplay (intégré à macOS), sans bloquer la vidéo."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class SoundPlayer:
    """Joue les ``<nom>.mp3`` d'un dossier ; un son absent est simplement ignoré."""

    def __init__(self, sounds_dir: Path, enabled: bool = True, volume: float = 1.0):
        self.sounds_dir = Path(sounds_dir)
        self.enabled = enabled and shutil.which("afplay") is not None
        self.volume = volume
        self._procs: list[tuple[str, subprocess.Popen]] = []

    def play(self, name: str) -> None:
        path = self.sounds_dir / f"{name}.mp3"
        if not self.enabled or not path.exists():
            return
        self._procs = [(n, p) for n, p in self._procs if p.poll() is None]
        proc = subprocess.Popen(
            ["afplay", "-v", str(self.volume), str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._procs.append((name, proc))

    def stop(self, name: str | None = None) -> None:
        """Coupe un son en cours (ou tous si ``name`` est None)."""
        for n, p in self._procs:
            if (name is None or n == name) and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    p.kill()
        self._procs = [(n, p) for n, p in self._procs if p.poll() is None]

    def close(self) -> None:
        self.stop()
