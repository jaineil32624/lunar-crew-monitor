# SELENE: Lunar Habitat AI Dashboard

**SELENE** (Space Environment Life & Neuro-health Engine) is an AI health dashboard for a
lunar habitat, built for the NASA HUNCH *Lunar Smart Adaptive Habitat* project. Astronauts
talk to it by voice or text. It watches **physical** and **mental** health, and it controls
habitat comfort systems such as lighting, soundscapes and temperature.

![SELENE dashboard](docs/dashboard.png)

It does **not** generate data itself. Point it at your simulation's output file, or at real
sensors, and it reads that file live.

> Research and education prototype. It is not a medical device and never diagnoses.

## Run it

Python 3.10-3.12 is recommended. On Linux you also need `sudo apt install python3-tk libportaudio2 espeak`.

```bash
pip install -r requirements.txt
python -m crew_monitor setup-models
python -m crew_monitor dashboard --data path/to/your_simulation_output.csv
```

`setup-models` downloads the face and pose models once (about 10 MB). You can also open
the dashboard without `--data` and pick the file under **Settings**.

## What's on the dashboard

| Area | Contents |
|---|---|
| **AI assistant** | Animated SELENE logo (idle, listening, thinking, speaking), chat, quick-prompt buttons, **Talk** push-to-talk, **Hey Selene** hands-free wake word, spoken replies |
| **Physical health** | Heart rate (with live trace), blood oxygen, HRV, body temperature; exercise countermeasures (120 min/day), resistive exercise for bone and muscle (60 min), hydration (2.5 L), sleep (8 h), radiation dose against NASA's 600 mSv career limit |
| **Mental wellbeing** | Fatigue, stress and low mood scored against the astronaut's own baseline, from the 30-second camera and microphone check-in (face, voice, posture) |
| **Habitat** | Circadian lighting (Day 6500 K to Night 1900 K), soundscapes, temperature, cabin O2, CO2 and pressure |
| **Alerts and schedule** | RED/ORANGE/YELLOW alerts, scheduled family calls |
| **Trends / Crew / Settings** | Mental trend chart and heart-rate history; whole-crew status; data file, voice and privacy controls |

## Voice commands

The wake phrase is "Hey Selene", or press **Talk**.

| Say | SELENE does |
|---|---|
| "How am I doing today?" | Physical and mental summary |
| "Start my check-in" | 30-second face, voice and posture wellbeing check |
| "Log 45 minutes of resistive exercise" / "I drank 500 ml" / "I slept 6 hours" | Adds to today's log, on top of your data file |
| "I feel stressed / tired / lonely" / "I can't sleep" | Supportive reply, plus lighting and sound changes or a family call |
| "Start a breathing exercise" | Guided 4-7-8 breathing |
| "Set lights to relax / night / focus / day" | Changes the lighting |
| "Play ocean waves" / "Stop sounds" | Soundscapes |
| "Set temperature to 23 degrees" | Cabin temperature |
| "What's my radiation dose?" / "Crew status" / "Habitat status" | Reports |
| "Schedule a family call" | Adds it to the schedule |
| "Medical emergency" / any mention of self-harm | **Immediate RED alert** to the commander and flight surgeon or psychologist (always offline, never waits for the network) |
| "Pause monitoring" / "Resume monitoring" | Privacy |

## AI modes

- **Offline AI** is the default. It understands the commands above with no internet, as a
  real lunar habitat would need with a 1.3-second, sometimes-down link to Earth.
- **Claude AI** turns on when `ANTHROPIC_API_KEY` is set. It gives natural conversation, and
  Claude calls the same habitat and health tools. If the link fails, SELENE falls back to
  offline mode automatically. Change the model with `SELENE_MODEL`.

Speech-to-text uses Google's free recognizer, which needs internet. For fully offline
speech, `pip install vosk`, download a Vosk model, and set `SELENE_STT=vosk`. Spoken replies
(pyttsx3) are always offline.

## Connecting your simulation

Your simulation writes a **CSV, JSON or JSON-lines** file with one row per reading. The
dashboard re-reads it whenever it changes. Only `astronaut_id` is required. Column names are
matched case-insensitively, and common alternatives are accepted (`hr`, `pulse`, `crew`,
`sleep_hours`, `co2`...; the full list is in `crew_monitor/datasource.py` → `ALIASES`).
Unrecognised columns are listed under Settings so you can map them.

| Column | Meaning |
|---|---|
| `timestamp`, `astronaut_id`, `mission_day` | When, who, which mission day |
| `heart_rate`, `hrv_ms`, `spo2`, `skin_temp_c`, `resp_rate` | Wearable vitals |
| `sleep_h`, `exercise_min`, `resistive_min`, `water_ml`, `steps` | Daily totals so far |
| `radiation_msv`, `radiation_today_msv` | Mission dose and today's dose |
| `mood`, `stress`, `sentiment` | Self-report / NLP scores (shown and used in check-ins) |
| `o2_pct`, `ppco2_mmhg`, `pressure_kpa`, `cabin_temp_c`, `humidity_pct` | Cabin air |

See `examples/data_format_example.csv` for the layout.

## Wellbeing check-in (face, voice, posture)

The check-in records 30 seconds of camera and microphone. MediaPipe face blendshapes give
blinks, drowsiness (PERCLOS), smiling, frowning and gaze; MediaPipe pose gives head drop,
slouching, movement and fidgeting; voice prosody gives pitch, monotone range, pauses and
speech rate. The first 5 check-ins learn each astronaut's own baseline. After that, fatigue,
stress and low mood are scored as robust z-scores against that baseline, with trend and
"says fine, but behaviour differs" flags.

## Privacy

Video and audio are processed in memory and never saved; only numbers are stored, in a
local SQLite file. There is a visible monitoring light and a pause command. Ground sees
results only with consent (`python -m crew_monitor consent A1 on`), and
`python -m crew_monitor forget A1` deletes a person's data.

## Command line (also available)

| Command | Purpose |
|---|---|
| `dashboard --data FILE` | Open the AI dashboard |
| `enroll A1 --name "Name" --role Engineer` | Register an astronaut and their display name |
| `checkin A1` / `analyze A1 --video v.mp4 --audio a.wav` | Check-in without the dashboard |
| `report [A1] [--html out.html]` | Text or HTML report |
| `consent A1 on/off`, `pause`, `resume`, `forget A1` | Privacy |

## Tests

```bash
python -m unittest discover tests
```

## Project files

| File | Purpose |
|---|---|
| `crew_monitor/gui.py` | Dashboard window (CustomTkinter) |
| `crew_monitor/assistant.py` | SELENE: tools, offline brain, Claude brain, safety rules |
| `crew_monitor/voice_io.py` | Microphone → text, text → speech, wake word |
| `crew_monitor/logo.py` | The SELENE logo, drawn in code |
| `crew_monitor/datasource.py` | Reads your simulation output |
| `crew_monitor/physical.py` | Physical health targets and flags |
| `crew_monitor/habitat.py` | Lighting, sound, temperature, alerts, schedule |
| `crew_monitor/face.py`, `posture.py`, `voice.py`, `fusion.py` | Wellbeing check-in analysis |
| `crew_monitor/context.py`, `store.py`, `capture.py`, `cli.py`, `report.py` | App state, database, camera, CLI, reports |
