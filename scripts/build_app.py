"""Build a stand-alone SELENE app (no Python needed to run it).

    pip install -r requirements.txt pyinstaller
    python scripts/build_app.py

Output: dist/SELENE/ (Windows: SELENE.exe inside; macOS: dist/SELENE.app)
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# bundle the face/pose models so the wellbeing scan works offline
from crew_monitor.models import model_path  # noqa: E402
models = [model_path(k) for k in ("face", "pose")]

import PyInstaller.__main__  # noqa: E402

sep = os.pathsep
args = [
    "selene_app.py", "--noconfirm", "--windowed", "--name", "SELENE",
    "--icon", str(ROOT / "docs" / ("selene.ico" if sys.platform != "darwin" else "selene.png")),
    "--collect-data", "customtkinter", "--collect-data", "mediapipe",
    "--hidden-import", "PIL._tkinter_finder", "--hidden-import", "PIL.ImageTk",
    "--add-data", f"{ROOT / 'examples'}{sep}examples",
    "--paths", str(ROOT),
]
for m in models:
    args += ["--add-data", f"{m}{sep}models"]
PyInstaller.__main__.run(args)
