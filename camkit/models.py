"""Téléchargement et localisation des modèles MediaPipe.

Les modèles (mains, visage, deux segmentations) pèsent environ 25 Mo.
Ils sont téléchargés au premier lancement dans le dossier ``models/`` du projet
ou, si le projet n'est pas lancé depuis son dépôt, dans ``~/.cache/camkit``.
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

BASE_URL = "https://storage.googleapis.com/mediapipe-models"

MODELS = {
    "hand_landmarker.task": "hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
    "blaze_face_short_range.tflite": "face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite",
    "selfie_segmenter.tflite": "image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite",
    # Cheveux, peau du visage, peau du corps, vêtements séparés : pour le détourage du Golden Warrior.
    "selfie_multiclass_256x256.tflite": "image_segmenter/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite",
}


def models_dir() -> Path:
    """Dossier des modèles : variable d'env, dépôt du projet, sinon cache utilisateur."""
    override = os.environ.get("SHUNKAN_IDO_MODELS")
    if override:
        return Path(override).expanduser()
    repo_root = Path(__file__).resolve().parent.parent
    if (repo_root / "pyproject.toml").exists():
        return repo_root / "models"
    return Path.home() / ".cache" / "camkit" / "models"


def cache_dir() -> Path:
    """Dossier de cache utilisateur (fond calibré, etc.)."""
    return Path.home() / ".cache" / "camkit"


def ensure_models() -> dict[str, Path]:
    """Télécharge les modèles manquants et renvoie leurs chemins."""
    target = models_dir()
    target.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, remote in MODELS.items():
        path = target / name
        if not path.exists() or path.stat().st_size == 0:
            print(f"[modèles] téléchargement de {name}…", file=sys.stderr)
            tmp = path.with_suffix(path.suffix + ".part")
            urllib.request.urlretrieve(f"{BASE_URL}/{remote}", tmp)
            tmp.replace(path)
        paths[name] = path
    return paths
