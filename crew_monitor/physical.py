"""Physical health: combines your simulation / sensor data (DataSource) with
anything the astronaut logs by voice, and checks it against NASA-style targets.

Targets are inspired by NASA-STD-3001 and ISS/Artemis practice, simplified for a
student prototype - they are not medical limits.
"""
import datetime as dt
import time

TARGETS = {
    "exercise_min": 120,        # ISS crews train ~2 h/day (aerobic + resistive)
    "resistive_min": 60,        # resistive work protects bone & muscle in 1/6 g
    "water_ml": 2500,
    "sleep_h": 8.0,             # NASA schedules an 8.5 h sleep period
    "spo2_watch": 94, "spo2_alarm": 90,
    "hr_high": 100, "hr_low": 45,
    "hrv_low": 30,
    "skin_temp_high": 37.8,
    "sys_high": 140, "dia_high": 90, "sys_low": 90,
    "balance_low": 60,
}
MOODS = ["happy", "calm", "tired", "anxious", "sad", "lonely"]   # the 6-mood picker
EEG_BANDS = ["delta", "theta", "alpha", "beta", "gamma"]
LUNAR_DOSE_MSV_PER_DAY = 1.37   # measured on the lunar surface (Chang'e-4 LND, 2020)
CAREER_LIMIT_MSV = 600          # NASA career effective-dose limit (NASA-STD-3001, 2022)
ORDER = ["GREEN", "YELLOW", "ORANGE", "RED"]


class PhysicalHealth:
    def __init__(self, store, datasource):
        self.store, self.ds = store, datasource
        store.db.execute("""CREATE TABLE IF NOT EXISTS logs (
            astronaut_id TEXT, day TEXT, ts REAL, kind TEXT, value REAL, detail TEXT)""")
        store.db.commit()

    def log(self, aid, kind, value, detail=""):
        """Voice/manual log, e.g. log(aid, 'exercise_min', 45, 'resistive')."""
        day = dt.date.today().isoformat()
        if kind == "sleep_h":
            self.store.db.execute("DELETE FROM logs WHERE astronaut_id=? AND day=? AND kind=?", (aid, day, kind))
        self.store.db.execute("INSERT INTO logs VALUES (?,?,?,?,?,?)", (aid, day, time.time(), kind, value, detail))
        self.store.db.commit()

    def _logged(self, aid, kind, detail=None):
        q = "SELECT SUM(value) FROM logs WHERE astronaut_id=? AND day=? AND kind=?"
        args = [aid, dt.date.today().isoformat(), kind]
        if detail:
            q += " AND detail=?"
            args.append(detail)
        return self.store.db.execute(q, args).fetchone()[0]

    def summary(self, aid):
        d = self.ds.latest(aid) if self.ds else {}

        def total(field, kind, detail=None):
            a, b = d.get(field), self._logged(aid, kind, detail)
            return None if a is None and b is None else (a or 0) + (b or 0)

        sleep_log = self._logged(aid, "sleep_h")
        mood_row = self.store.db.execute(
            "SELECT detail, ts FROM logs WHERE astronaut_id=? AND kind='mood' ORDER BY ts DESC LIMIT 1", (aid,)).fetchone()
        s = {
            "has_data": bool(d),
            "heart_rate": d.get("heart_rate"), "hrv_ms": d.get("hrv_ms"), "spo2": d.get("spo2"),
            "skin_temp_c": d.get("skin_temp_c"), "resp_rate": d.get("resp_rate"),
            "sleep_h": sleep_log if sleep_log is not None else d.get("sleep_h"),
            "exercise_min": total("exercise_min", "exercise_min"),
            "resistive_min": total("resistive_min", "exercise_min", "resistive"),
            "water_ml": total("water_ml", "water_ml"),
            "radiation_today_msv": d.get("radiation_today_msv"),
            "radiation_mission_msv": d.get("radiation_msv"),
            "hr_trace": self.ds.history(aid, "heart_rate") if self.ds else [],
            "systolic_bp": d.get("systolic_bp"), "diastolic_bp": d.get("diastolic_bp"),
            "perfusion_index": d.get("perfusion_index"), "balance_score": d.get("balance_score"),
            "brainwaves": self.brainwaves(d),
            "mood": mood_row[0] if mood_row else None,
            "targets": TARGETS,
        }
        if s["radiation_mission_msv"] is not None:
            s["radiation_limit_pct"] = round(100 * s["radiation_mission_msv"] / CAREER_LIMIT_MSV, 1)
        s["status"], s["flags"] = self._evaluate(s)
        return s

    @staticmethod
    def brainwaves(d):
        """Relative EEG band power -> normalised shares + a plain-language state."""
        bands = {b: d.get("eeg_" + b) for b in EEG_BANDS}
        if not any(isinstance(v, float) for v in bands.values()):
            return None
        tot = sum(v for v in bands.values() if isinstance(v, float)) or 1.0
        share = {b: (v / tot if isinstance(v, float) else 0.0) for b, v in bands.items()}
        slow = share["delta"] + share["theta"]
        if slow > 0.5 or share["theta"] > share["alpha"] + 0.05:
            state = "drowsy"                     # theta/delta dominate while awake
        elif share["beta"] + share["gamma"] > 0.5:
            state = "high alert / possibly stressed"
        elif share["alpha"] >= max(share["beta"], share["theta"]):
            state = "relaxed and calm"
        else:
            state = "focused"
        return {"share": share, "state": state}

    def stability(self, aid, mental=None):
        """Physical balance (from data) + emotional stability (spread of recent mood logs)."""
        d = self.ds.latest(aid) if self.ds else {}
        rows = self.store.db.execute(
            "SELECT detail FROM logs WHERE astronaut_id=? AND kind='mood' ORDER BY ts DESC LIMIT 7", (aid,)).fetchall()
        valence = {"happy": 2, "calm": 1, "tired": -1, "anxious": -1.5, "sad": -2, "lonely": -2}
        vals = [valence.get(r[0], 0) for r in rows]
        emo = None
        if len(vals) >= 3:
            spread = max(vals) - min(vals)
            emo = max(0, round(100 - spread * 18 - max(0, -sum(vals) / len(vals)) * 10))
        return {"balance_score": d.get("balance_score"), "emotional_stability": emo, "mood_samples": len(vals)}

    def _evaluate(self, s):
        flags, level = [], "GREEN"

        def flag(lvl, text):
            nonlocal level
            flags.append(text)
            level = max(level, lvl, key=ORDER.index)

        T, hour = TARGETS, dt.datetime.now().hour
        if s["spo2"] is not None:
            if s["spo2"] < T["spo2_alarm"]:
                flag("RED", f"Blood oxygen {s['spo2']:.0f}% is below 90%. Check cabin/suit O2 now.")
            elif s["spo2"] < T["spo2_watch"]:
                flag("YELLOW", f"Blood oxygen {s['spo2']:.0f}% is slightly low.")
        if s["heart_rate"] is not None:
            if s["heart_rate"] > T["hr_high"]:
                flag("ORANGE", f"Heart rate high at rest ({s['heart_rate']:.0f} bpm).")
            elif s["heart_rate"] < T["hr_low"]:
                flag("ORANGE", f"Heart rate low ({s['heart_rate']:.0f} bpm).")
        if s["hrv_ms"] is not None and s["hrv_ms"] < T["hrv_low"]:
            flag("YELLOW", f"Heart-rate variability low ({s['hrv_ms']:.0f} ms): poor recovery or high stress.")
        if s["skin_temp_c"] is not None and s["skin_temp_c"] > T["skin_temp_high"]:
            flag("ORANGE", f"Body temperature elevated ({s['skin_temp_c']:.1f} C).")
        if s["systolic_bp"] is not None and s["diastolic_bp"] is not None:
            if s["systolic_bp"] >= T["sys_high"] or s["diastolic_bp"] >= T["dia_high"]:
                flag("ORANGE", f"Blood pressure high ({s['systolic_bp']:.0f}/{s['diastolic_bp']:.0f} mmHg).")
            elif s["systolic_bp"] < T["sys_low"]:
                flag("YELLOW", f"Blood pressure low ({s['systolic_bp']:.0f}/{s['diastolic_bp']:.0f}): watch for dizziness.")
        if s["balance_score"] is not None and s["balance_score"] < T["balance_low"]:
            flag("YELLOW", f"Balance score {s['balance_score']:.0f}/100: take care moving in 1/6 g.")
        if s["brainwaves"] and s["brainwaves"]["state"] == "drowsy":
            flag("YELLOW", "Brainwaves show drowsiness (theta/delta high).")
        if s["sleep_h"] is not None and s["sleep_h"] < 6:
            flag("ORANGE", f"Only {s['sleep_h']:.1f} h sleep: fatigue risk for EVA and robotics.")
        if hour >= 15 and s["exercise_min"] is not None and s["exercise_min"] < T["exercise_min"] * 0.5:
            flag("YELLOW", "Exercise is well below today's countermeasure target.")
        if hour >= 14 and s["water_ml"] is not None and s["water_ml"] < 1200:
            flag("YELLOW", "Hydration is behind schedule.")
        if s.get("radiation_limit_pct", 0) >= 80:
            flag("ORANGE", f"Mission radiation dose at {s['radiation_limit_pct']}% of career limit.")
        return level, flags
