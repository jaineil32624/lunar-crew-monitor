# Lunar Crew Monitor

A prototype for the NASA HUNCH *Lunar Smart Adaptive Habitat* project. It combines
**face**, **voice** and **posture** analysis with a short self-report to track an
astronaut's wellbeing against their **own personal baseline**. It then suggests
supportive habitat responses: lighting, soundscapes, companion prompts and crew activities.

> Research and education prototype only. It is **not** a medical or diagnostic device.
> Its outputs are prompts for a friendly check-in.

## How it works

```
 camera ──► Face Landmarker ──► blink rate, PERCLOS (drowsiness), smile, brow-down,
        │                        gaze-down, expressivity (flat affect)
        └─► Pose Landmarker ──► head-drop angle, trunk lean, movement, stillness, fidgeting
 mic ─────► prosody (numpy) ──► pitch, pitch range (monotone), jitter, loudness,
                                 pauses, speech rate
 survey ──► mood / stress / sleep + text sentiment
                   │
                   ▼
   Personal baseline (first 5 sessions, median + MAD) ──► robust z-scores
                   ▼
   Indicators: FATIGUE · STRESS · LOW MOOD (each averaged per channel)
   + cross-channel agreement  + 3-session trend  + "says fine, but behaviour differs" flag
                   ▼
   Status GREEN / YELLOW / ORANGE  ──►  habitat responses  ──►  local dashboard
```

**Privacy by design:** frames and audio are processed in memory and then discarded.
Only numbers are saved, to a local SQLite file, and free-text notes are not stored.
A red dot shows while monitoring is on. Press `x` to cancel a session without saving
anything. The `pause` command stops all monitoring. Ground is notified only if the
astronaut opts in with `consent`, and `forget` deletes all of a person's data.

## Install (Windows, macOS or Linux, Python 3.9-3.12 recommended)

```bash
cd lunar_crew_monitor
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
python -m crew_monitor setup-models      # downloads the 2 MediaPipe models (~10 MB) once
```

Linux only: you may also need `sudo apt install libportaudio2 libegl1 libgles2`.

## Try it with no camera: a simulated 21-day mission

```bash
python -m crew_monitor simulate
```

This simulates a 4-person crew: one steady, one with developing fatigue, one with a
stress spike on days 12-16, and one with hidden low mood (says "fine" but face and voice
disagree). It then writes `crew_dashboard.html`, which you can open in a browser.

## Use it for real (webcam + microphone)

```bash
python -m crew_monitor enroll A1 --name "Your Name" --role Engineer
python -m crew_monitor checkin A1            # 30 s: answer the spoken prompt, then 4 quick questions
python -m crew_monitor report A1             # recent sessions in detail
python -m crew_monitor report --html dash.html
```

During a check-in, sit so your face **and shoulders** are visible and answer the prompt
out loud. Press `q` to finish early or `x` to cancel. The first 5 check-ins build your
baseline, and scoring starts at check-in 6. Do them at roughly the same time each day.

Other commands:

| Command | What it does |
|---|---|
| `checkin A1 --duration 45 --camera 1` | longer session, second camera |
| `checkin A1 --no-mic` / `--no-survey` / `--no-preview` | skip a channel or the window |
| `analyze A1 --video clip.mp4 --audio clip.wav --mood 6 --sleep 7` | score recorded files |
| `consent A1 on` / `off` | allow or stop sharing summaries with ground |
| `report --html ground.html --ground` | dashboard showing only consenting crew |
| `pause` / `resume` | crew privacy pause |
| `forget A1` | delete all of A1's data |

Data is stored in `~/.lunar_crew_monitor/`. Set `CREW_MONITOR_HOME` to change this.

## Run the tests

```bash
python -m unittest discover tests
```

## Project files

| File | Purpose |
|---|---|
| `crew_monitor/face.py` | MediaPipe blendshapes → facial features |
| `crew_monitor/posture.py` | MediaPipe pose → posture and movement features |
| `crew_monitor/voice.py` | microphone/WAV → prosody features (numpy only) |
| `crew_monitor/selfreport.py` | survey and text sentiment (swap in your BERT model here) |
| `crew_monitor/fusion.py` | personal baseline, z-scores, indicators, trends, flags |
| `crew_monitor/interventions.py` | indicator → habitat response mapping |
| `crew_monitor/config.py` | thresholds and which features feed which indicator |
| `crew_monitor/simulate.py` | synthetic crew for demos and testing |
| `crew_monitor/capture.py`, `cli.py`, `report.py`, `store.py` | capture, CLI, dashboard, database |

## Ideas to extend

- Replace the tiny lexicon in `selfreport.text_sentiment` with your fine-tuned BERT model,
  and transcribe the check-in audio with Whisper so the spoken answer is scored too.
- Feed the session features into your Random Forest from the proposal, then rerun the
  +0.3 sentiment sensitivity test to show that the multimodal version is more robust.
- Send `interventions.recommend()` output to Arduino/Raspberry Pi LED lighting in the scale model.
- Validate the features on DAIC-WOZ, which ships OpenFace and COVAREP features.
