"""Simulated smart-habitat controls. In the scale model these calls could drive
Arduino/Raspberry Pi LED strips, a speaker and a fan."""
import time

LIGHTING = {
    "day":     {"cct": 6500, "brightness": 90, "label": "Day (6500 K) - alertness"},
    "focus":   {"cct": 5000, "brightness": 80, "label": "Focus (5000 K) - work and science"},
    "relax":   {"cct": 3000, "brightness": 55, "label": "Relax (3000 K) - calming"},
    "evening": {"cct": 2700, "brightness": 40, "label": "Evening (2700 K) - wind down"},
    "night":   {"cct": 1900, "brightness": 15, "label": "Night (1900 K) - protects melatonin"},
    "sleep":   {"cct": 0,    "brightness": 0,  "label": "Sleep - lights off"},
}
SOUNDSCAPES = ["earth forest", "ocean waves", "rain", "birdsong", "campfire", "white noise"]


class Habitat:
    def __init__(self, datasource=None):
        self.ds = datasource
        self.lighting = "focus"
        self.soundscape = None
        self.temperature_c = 22.0
        self.monitoring_paused = False
        self.alerts = []          # (time, severity, text)
        self.schedule = []        # (when, text)

    def set_lighting(self, mode):
        mode = mode.lower()
        if mode not in LIGHTING:
            raise ValueError(f"unknown lighting mode '{mode}'. Options: {', '.join(LIGHTING)}")
        self.lighting = mode
        return LIGHTING[mode]["label"]

    def play(self, name):
        name = name.lower()
        match = next((s for s in SOUNDSCAPES if name in s or s in name), None)
        if not match:
            raise ValueError(f"unknown soundscape '{name}'. Options: {', '.join(SOUNDSCAPES)}")
        self.soundscape = match
        return match

    def stop_sound(self):
        self.soundscape = None

    def set_temperature(self, c):
        self.temperature_c = max(18.0, min(27.0, float(c)))
        return self.temperature_c

    def alert(self, severity, text):
        self.alerts.insert(0, (time.strftime("%H:%M"), severity, text))
        self.alerts = self.alerts[:20]

    def status(self):
        return {"lighting": self.lighting, "lighting_label": LIGHTING[self.lighting]["label"],
                "soundscape": self.soundscape, "temperature_c": self.temperature_c,
                "cabin": self.ds.cabin() if self.ds else {}, "monitoring_paused": self.monitoring_paused,
                "alerts": list(self.alerts[:5]), "schedule": list(self.schedule[-5:])}
