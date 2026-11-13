#!/bin/bash
# SELENE launcher for macOS (double-click) and Linux (./start_selene.command)
cd "$(dirname "$0")"
PY=""
for c in python3.12 python3.11 python3.10 python3; do
  command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }
done
if [ -z "$PY" ]; then
  echo "Python is not installed. Opening the download page - install Python 3.12, then run this again."
  (open "https://www.python.org/downloads/" || xdg-open "https://www.python.org/downloads/") 2>/dev/null
  read -r -p "Press Enter to close"; exit 1
fi
[ -x .venv/bin/python ] || { echo "First start: setting things up (only once)..."; "$PY" -m venv .venv || exit 1; }
if [ ! -f .venv/setup_core.ok ]; then
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r requirements-core.txt && touch .venv/setup_core.ok || { read -r -p "Install failed. Press Enter"; exit 1; }
fi
if [ ! -f .venv/setup_full.ok ]; then
  echo "Installing camera scan and Claude features (optional)..."
  .venv/bin/python -m pip install opencv-python mediapipe anthropic && .venv/bin/python -m crew_monitor setup-models && touch .venv/setup_full.ok \
    || echo "Optional features could not be installed. The dashboard still works."
fi
DATA="examples/data_format_example.csv"
for f in data/*.csv data/*.json data/*.jsonl; do [ -f "$f" ] && DATA="$f"; done
echo "Opening SELENE with data file: $DATA"
.venv/bin/python -m crew_monitor dashboard --data "$DATA"
