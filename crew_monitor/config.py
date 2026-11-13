"""Central configuration: paths, model files, thresholds, feature directions."""
from pathlib import Path
import os

DATA_DIR = Path(os.environ.get("CREW_MONITOR_HOME", Path.home() / ".lunar_crew_monitor"))
DB_PATH = DATA_DIR / "crew.db"
MODEL_DIR = Path(os.environ.get("CREW_MONITOR_MODELS", DATA_DIR / "models"))
PAUSE_FLAG = DATA_DIR / "MONITORING_PAUSED"

MODELS = {
    "face": ("face_landmarker.task",
             "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/latest/face_landmarker.task"),
    "pose": ("pose_landmarker_lite.task",
             "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
             "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"),
}

# Number of sessions used to learn each astronaut's personal baseline.
BASELINE_SESSIONS = 5
# Rolling window (sessions) for sustained-trend detection.
TREND_WINDOW = 7

# Minimum spread used when z-scoring a feature, so tiny baseline variance
# does not create huge z-scores. Units match the feature.
SCALE_FLOOR = {
    "face_blink_rate": 2.0, "face_perclos": 0.02, "face_smile_mean": 0.03,
    "face_smile_frac": 0.03, "face_brow_down": 0.03, "face_gaze_down": 0.03,
    "face_expressivity": 0.01,
    "voice_f0_mean": 5.0, "voice_f0_range_st": 0.5, "voice_jitter": 0.003,
    "voice_energy_db": 1.5, "voice_energy_var_db": 0.8, "voice_pause_ratio": 0.03,
    "voice_mean_pause_s": 0.05, "voice_speech_rate": 0.2,
    "posture_neck_flexion": 2.0, "posture_trunk_lean": 1.5,
    "posture_movement": 0.002, "posture_fidget": 0.002, "posture_stillness": 0.03,
    "self_mood": 0.7, "self_stress": 0.7, "self_sleep_h": 0.4, "self_sentiment": 0.1,
}

# Relative minimum spread (fraction of the baseline median); default 5%.
# Motion features are naturally noisy, so they get a wider floor.
REL_FLOOR = {"posture_fidget": 0.25, "posture_movement": 0.2, "posture_stillness": 0.2}

# Each wellbeing indicator is built from features with a direction:
# +1 means "higher than baseline is concerning", -1 means "lower is concerning".
INDICATORS = {
    "fatigue": {
        "face_perclos": +1, "face_blink_rate": +1,
        "voice_speech_rate": -1, "voice_energy_db": -1, "voice_mean_pause_s": +1,
        "posture_neck_flexion": +1, "posture_movement": -1, "posture_stillness": +1,
        "self_sleep_h": -1,
    },
    "stress": {
        "face_brow_down": +1, "face_blink_rate": +1,
        "voice_f0_mean": +1, "voice_jitter": +1, "voice_energy_var_db": +1,
        "posture_fidget": +1,
        "self_stress": +1,
    },
    "low_mood": {
        "face_smile_mean": -1, "face_smile_frac": -1, "face_expressivity": -1,
        "face_gaze_down": +1,
        "voice_f0_range_st": -1, "voice_pause_ratio": +1, "voice_energy_db": -1,
        "posture_trunk_lean": +1, "posture_neck_flexion": +1,
        "self_mood": -1, "self_sentiment": -1,
    },
}

# Alert thresholds on indicator scores (units: robust z-score).
WATCH_THRESHOLD = 1.0
CONCERN_THRESHOLD = 1.75
CHANNEL_ACTIVE_THRESHOLD = 1.0   # channel counts as "agreeing" above this
