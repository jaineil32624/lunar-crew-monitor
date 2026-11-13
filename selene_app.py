"""Double-click entry point for SELENE (also used to build SELENE.exe / SELENE.app).

Finds a data file automatically:
  1. a path given on the command line
  2. the newest .csv/.json/.jsonl in the `data` folder next to the app
  3. the bundled example data
"""
import os
import sys
from pathlib import Path


def app_dir():
    # next to SELENE.exe when frozen by PyInstaller, else the project folder
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def bundle_dir():
    return Path(getattr(sys, "_MEIPASS", app_dir()))


def main():
    here = app_dir()
    for name in ("data", "music", "assets"):
        (here / name).mkdir(exist_ok=True)
    os.environ.setdefault("SELENE_MUSIC_DIR", str(here / "music"))
    os.environ.setdefault("SELENE_ASSETS_DIR", str(here / "assets"))
    if (bundle_dir() / "models").is_dir():            # models packed inside the app
        os.environ.setdefault("CREW_MONITOR_MODELS", str(bundle_dir() / "models"))

    if len(sys.argv) > 1:
        data = sys.argv[1]
    else:
        files = sorted([p for ext in ("*.csv", "*.json", "*.jsonl") for p in (here / "data").glob(ext)],
                       key=lambda p: p.stat().st_mtime)
        data = str(files[-1]) if files else str(bundle_dir() / "examples" / "data_format_example.csv")

    from crew_monitor.gui import run
    run(data)


if __name__ == "__main__":
    main()
