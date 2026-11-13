"""Synthetic crew generator so the whole pipeline can be demonstrated and
tested without cameras, microphones or real astronaut data."""
import numpy as np
from . import config

TYPICAL = {
    "face_blink_rate": 17, "face_perclos": 0.05, "face_smile_mean": 0.25, "face_smile_frac": 0.2,
    "face_brow_down": 0.10, "face_gaze_down": 0.15, "face_expressivity": 0.06,
    "voice_f0_mean": 150, "voice_f0_range_st": 5.0, "voice_jitter": 0.010, "voice_energy_db": -22,
    "voice_energy_var_db": 7.0, "voice_pause_ratio": 0.15, "voice_mean_pause_s": 0.5,
    "voice_speech_rate": 4.0,
    "posture_neck_flexion": 40, "posture_trunk_lean": 5, "posture_movement": 0.02,
    "posture_fidget": 0.010, "posture_stillness": 0.3,
    "self_mood": 7, "self_stress": 3, "self_sleep_h": 7, "self_sentiment": 0.4,
}
BOUNDS = {"self_mood": (1, 10), "self_stress": (1, 10), "self_sleep_h": (0, 12), "self_sentiment": (-1, 1)}

# Effects in units of SCALE_FLOOR (approx. one personal standard deviation)
EFFECTS = {
    "fatigue": {"face_perclos": 4, "face_blink_rate": 2.5, "voice_speech_rate": -3, "voice_energy_db": -2,
                "voice_mean_pause_s": 2.5, "posture_neck_flexion": 3, "posture_movement": -3,
                "posture_stillness": 3, "self_sleep_h": -4, "self_mood": -1},
    "stress": {"face_brow_down": 3.5, "face_blink_rate": 2, "voice_f0_mean": 3, "voice_jitter": 3,
               "voice_energy_var_db": 2.5, "posture_fidget": 3.5, "self_stress": 4, "self_sentiment": -3},
    "masked_low_mood": {"face_smile_mean": -3.5, "face_smile_frac": -3, "face_expressivity": -3,
                        "face_gaze_down": 3, "voice_f0_range_st": -3.5, "voice_pause_ratio": 3,
                        "voice_energy_db": -2, "posture_trunk_lean": 3, "posture_neck_flexion": 2},
}

CREW = [
    ("A1", "Cmdr. Vega", "Commander", "steady", None),
    ("A2", "Dr. Okafor", "Flight engineer", "fatigue", (10, 21)),
    ("A3", "Dr. Lindqvist", "Scientist", "stress", (12, 16)),
    ("A4", "Sgt. Rao", "Mission specialist", "masked_low_mood", (8, 21)),
]


def simulate_day(personal, persona, day, window, rng):
    f = {}
    strength = 0.0
    if window and window[0] <= day <= window[1]:
        strength = min(1.0, (day - window[0] + 1) / 3)     # ramps up over 3 days
    for k, mu in personal.items():
        sd = config.SCALE_FLOOR[k]
        v = mu + rng.normal(0, sd * 0.8)
        v += strength * EFFECTS.get(persona, {}).get(k, 0) * sd
        if k in BOUNDS:
            v = float(np.clip(v, *BOUNDS[k]))
        f[k] = float(v)
    return f


def personal_baseline(rng):
    """Each astronaut differs from 'typical' - this is why we use personal baselines."""
    return {k: v + rng.normal(0, config.SCALE_FLOOR[k] * 3) if k not in BOUNDS else v
            for k, v in TYPICAL.items()}


def run(store, days=21, seed=7, start_ts=None, verbose=True):
    from .fusion import assess
    from .interventions import recommend
    import time
    rng = np.random.default_rng(seed)
    start_ts = start_ts or time.time() - days * 86400
    for aid, name, role, persona, window in CREW:
        store.add_astronaut(aid, name, role, share=(aid != "A4"))
        personal = personal_baseline(rng)
        for day in range(days):
            feats = simulate_day(personal, persona, day, window, rng)
            a = assess(feats, store.sessions(aid))
            a["actions"] = recommend(a, share_with_ground=(aid != "A4"))
            store.add_session(aid, feats, a, kind="simulated", ts=start_ts + day * 86400)
        if verbose:
            print(f"  simulated {days} days for {aid} {name} ({persona})")
