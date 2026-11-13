"""Data connector: reads the output of YOUR simulation (or real sensors).

Point the dashboard at a CSV, JSON or JSON-lines file:
    python -m crew_monitor dashboard --data path/to/your_output.csv

Each row = one reading. Columns are matched case-insensitively and common
aliases are accepted (see ALIASES), so you rarely need to change your simulation.
Only `astronaut_id` is required; every other column is optional.
The file is re-read automatically whenever it changes.
"""
import csv
import json
import os
import time
from pathlib import Path

# canonical name -> accepted column names
ALIASES = {
    "timestamp": ["timestamp", "time", "ts", "datetime", "date"],
    "astronaut_id": ["astronaut_id", "astronaut", "crew_id", "id", "crew", "name"],
    "heart_rate": ["heart_rate", "hr", "heartrate", "heart_rate_bpm", "bpm", "pulse"],
    "hrv_ms": ["hrv_ms", "hrv", "rmssd", "hrv_rmssd"],
    "spo2": ["spo2", "spo2_pct", "oxygen_saturation", "o2_sat", "blood_oxygen"],
    "skin_temp_c": ["skin_temp_c", "skin_temp", "body_temp", "temperature_c", "temp_body"],
    "resp_rate": ["resp_rate", "respiration_rate", "breathing_rate", "rr"],
    "sleep_h": ["sleep_h", "sleep_hours", "sleep"],
    "exercise_min": ["exercise_min", "exercise", "exercise_minutes", "workout_min"],
    "resistive_min": ["resistive_min", "resistive", "strength_min", "ared_min"],
    "water_ml": ["water_ml", "water", "hydration_ml", "fluid_ml"],
    "steps": ["steps", "step_count"],
    "radiation_msv": ["radiation_msv", "cumulative_dose_msv", "mission_dose_msv", "dose_msv"],
    "radiation_today_msv": ["radiation_today_msv", "daily_dose_msv", "dose_today_msv"],
    "mission_day": ["mission_day", "day", "sol"],
    "mood": ["mood", "mood_score"],
    # brainwaves (EEG headband): relative band power 0-1 or %
    "eeg_delta": ["eeg_delta", "delta"], "eeg_theta": ["eeg_theta", "theta"],
    "eeg_alpha": ["eeg_alpha", "alpha"], "eeg_beta": ["eeg_beta", "beta"],
    "eeg_gamma": ["eeg_gamma", "gamma"],
    # blood / circulation
    "systolic_bp": ["systolic_bp", "systolic", "bp_sys", "sbp"],
    "diastolic_bp": ["diastolic_bp", "diastolic", "bp_dia", "dbp"],
    "perfusion_index": ["perfusion_index", "blood_flow", "pi", "perfusion"],
    # stability: balance / postural sway (0-100, higher = steadier)
    "balance_score": ["balance_score", "balance", "stability", "postural_stability"],
    # lunar exterior environment
    "ext_temp_c": ["ext_temp_c", "exterior_temp", "surface_temp_c", "outside_temp"],
    "ext_radiation_usv_h": ["ext_radiation_usv_h", "surface_radiation", "ext_dose_rate"],
    "solar_activity": ["solar_activity", "solar_flare", "kp_index", "solar_index"],
    "dust_level": ["dust_level", "dust", "regolith_dust"],
    "sun_elevation_deg": ["sun_elevation_deg", "sun_elevation", "solar_elevation"],
    "stress": ["stress", "stress_score", "stress_index"],
    "sentiment": ["sentiment", "sentiment_score"],
    # cabin / habitat environment (may be in the same file, astronaut_id optional)
    "o2_pct": ["o2_pct", "cabin_o2", "o2"],
    "ppco2_mmhg": ["ppco2_mmhg", "co2_mmhg", "ppco2", "co2"],
    "pressure_kpa": ["pressure_kpa", "cabin_pressure", "pressure"],
    "cabin_temp_c": ["cabin_temp_c", "cabin_temp", "habitat_temp"],
    "humidity_pct": ["humidity_pct", "humidity", "rh"],
}
_LOOKUP = {alias: canon for canon, names in ALIASES.items() for alias in names}
CABIN_FIELDS = ("o2_pct", "ppco2_mmhg", "pressure_kpa", "cabin_temp_c", "humidity_pct")
EXTERIOR_FIELDS = ("ext_temp_c", "ext_radiation_usv_h", "solar_activity", "dust_level", "sun_elevation_deg")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v if v not in ("", None) else None


class DataSource:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self._mtime = None
        self.rows = []
        self.loaded_at = None
        self.error = None
        self.unknown_columns = set()
        self.refresh()

    @property
    def connected(self):
        return bool(self.path and self.path.exists() and self.rows)

    def refresh(self):
        """Reload the file if it changed. Returns True when new data was loaded."""
        if not self.path:
            return False
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            self.error = f"File not found: {self.path}"
            return False
        if mtime == self._mtime:
            return False
        try:
            raw = self._read()
        except Exception as e:      # malformed file while the simulation is writing it
            self.error = f"Could not read {self.path.name}: {e}"
            return False
        rows = []
        for r in raw:
            out = {}
            for k, v in r.items():
                canon = _LOOKUP.get(str(k).strip().lower())
                if canon:
                    out[canon] = _num(v) if canon not in ("astronaut_id", "timestamp") else (str(v).strip() if v not in (None, "") else None)
                else:
                    self.unknown_columns.add(k)
            rows.append(out)
        self.rows, self._mtime, self.error = rows, mtime, None
        self.loaded_at = time.time()
        return True

    def _read(self):
        text = self.path.read_text(encoding="utf-8-sig")
        if self.path.suffix.lower() in (".json", ".jsonl", ".ndjson"):
            text = text.strip()
            if text.startswith("["):
                return json.loads(text)
            if text.startswith("{") and "\n" not in text:
                data = json.loads(text)
                return data.get("readings", [data]) if isinstance(data, dict) else data
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        return list(csv.DictReader(text.splitlines()))

    # ---- queries -------------------------------------------------------
    def crew_ids(self):
        seen = []
        for r in self.rows:
            a = r.get("astronaut_id")
            if a and a not in seen:
                seen.append(a)
        return seen

    def latest(self, aid):
        """Most recent non-empty value of every field for one astronaut."""
        out = {}
        for r in self.rows:
            if r.get("astronaut_id") == aid:
                out.update({k: v for k, v in r.items() if v is not None})
        return out

    def history(self, aid, field, n=60):
        vals = [r[field] for r in self.rows
                if r.get("astronaut_id") == aid and isinstance(r.get(field), float)]
        return vals[-n:]

    def mission_day(self):
        """From a mission_day column if present, else days since the first timestamp."""
        days = [r["mission_day"] for r in self.rows if isinstance(r.get("mission_day"), float)]
        if days:
            return int(days[-1])
        import datetime as dt
        for r in self.rows:
            try:
                first = dt.datetime.fromisoformat(str(r.get("timestamp")))
                return (dt.datetime.now(first.tzinfo) - first).days + 1
            except (TypeError, ValueError):
                continue
        return None

    def exterior(self):
        out = {}
        for r in self.rows:
            out.update({k: r[k] for k in EXTERIOR_FIELDS if isinstance(r.get(k), float)})
        return out

    def cabin(self):
        out = {}
        for r in self.rows:
            out.update({k: r[k] for k in CABIN_FIELDS if isinstance(r.get(k), float)})
        return out
