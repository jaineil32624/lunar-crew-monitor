"""Locate (and optionally download) the MediaPipe model files.

On a real habitat these files are pre-installed: nothing is fetched at runtime.
"""
import urllib.request
from pathlib import Path
from . import config


def model_path(kind: str, download: bool = True) -> Path:
    fname, url = config.MODELS[kind]
    path = config.MODEL_DIR / fname
    if not path.exists():
        if not download:
            raise FileNotFoundError(f"Model {path} missing. Run: python -m crew_monitor setup-models")
        config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {fname} ...")
        urllib.request.urlretrieve(url, path)
    return path
