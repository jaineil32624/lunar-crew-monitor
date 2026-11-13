"""SELENE - Space Environment Life & Neuro-health Engine.

The habitat's AI health assistant. One set of tools (health summary, logging,
lighting, soundscapes, alerts, check-ins...) is used by two brains:
  * OfflineBrain - fast pattern-matching, works with no internet (lunar default)
  * ClaudeBrain  - natural conversation via the Claude API when a key is set;
                   Claude calls the same tools.
"""
import json
import os
import re
import time

from .habitat import LIGHTING, SOUNDSCAPES
from .learning import VALENCE
from .music import SPACE_TRACKS, NATURE
from .physical import MOODS
from .selfreport import text_sentiment

NAME = "SELENE"
MODEL = os.environ.get("SELENE_MODEL", "claude-opus-5-5")

CRISIS = re.compile(r"\b(kill myself|end my life|suicid|hurt myself|self[- ]harm|no reason to live|want to die)\b", re.I)
EMERGENCY = re.compile(r"\b(emergency|can'?t breathe|chest pain|unconscious|passed out|bleeding|fire|smoke|"
                       r"depressuri[sz]|leak|mayday|medical help)\b", re.I)


JOKES = [
    "Why did the astronaut break up with the Moon? It needed space, and the Moon kept going through phases.",
    "What's an astronaut's favorite key on the keyboard? The space bar.",
    "How do you throw a party on the Moon? You planet.",
    "What do you call a tick on the Moon? A luna-tick.",
    "Why did the Sun skip college? It already had a million degrees.",
    "What kind of music do planets sing? Nep-tunes.",
    "I tried squats in one-sixth gravity. My legs said thanks. My coffee said goodbye.",
    "Why is the habitat gym never crowded? Everyone feels light about skipping it. Please don't - your bones are watching.",
    "Mission Control said to watch my heart rate. Up here it's the only thing that doesn't float away.",
    "Why did the water recycler get promoted? It always turned things around.",
    "What did the Moon say to the astronaut who forgot to drink water? You're going through a dry phase.",
    "How does the Moon get its hair cut? E-clipse it.",
]
MOOD_WORDS = {
    "happy": r"happy|great|good|awesome|excited|amazing|fantastic|joy",
    "calm": r"calm|relaxed|peaceful|content|chill|fine",
    "tired": r"tired|exhausted|sleepy|drained|fatigued|worn out",
    "anxious": r"anxious|stressed|worried|nervous|tense|overwhelmed|panick",
    "sad": r"sad|down|depressed|unhappy|low|blue|upset",
    "lonely": r"lonely|homesick|alone|isolated|miss (my|home)",
}


# --------------------------------------------------------------------------- tools
def _obj(props, required):
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


TOOL_SPECS = [
    ("get_health_summary", "Get the current astronaut's physical vitals, logs, mental wellbeing indicators and active flags.", _obj({}, [])),
    ("start_wellbeing_checkin", "Start the 30-second camera + microphone wellbeing check-in (face, voice, posture).", _obj({}, [])),
    ("log_exercise", "Log completed exercise.", _obj({"minutes": {"type": "number"},
        "kind": {"type": "string", "enum": ["aerobic", "resistive"]}}, ["minutes", "kind"])),
    ("log_water", "Log water drunk, in millilitres.", _obj({"ml": {"type": "number"}}, ["ml"])),
    ("log_sleep", "Log last night's sleep in hours.", _obj({"hours": {"type": "number"}}, ["hours"])),
    ("start_breathing_exercise", "Show and speak a guided 4-7-8 breathing exercise.", _obj({}, [])),
    ("set_lighting", "Set circadian lighting mode.", _obj({"mode": {"type": "string", "enum": list(LIGHTING)}}, ["mode"])),
    ("play_soundscape", "Play a calming soundscape.", _obj({"name": {"type": "string", "enum": SOUNDSCAPES}}, ["name"])),
    ("stop_soundscape", "Stop the soundscape.", _obj({}, [])),
    ("set_temperature", "Set cabin temperature (18-27 C).", _obj({"celsius": {"type": "number"}}, ["celsius"])),
    ("get_radiation_status", "Radiation dose today and for the mission vs. NASA career limit.", _obj({}, [])),
    ("get_crew_status", "Wellbeing status of every crew member (respecting consent).", _obj({}, [])),
    ("get_habitat_status", "Lighting, sound, cabin air (O2, CO2, pressure) and recent alerts.", _obj({}, [])),
    ("schedule_event", "Add an item to the crew schedule, e.g. a family video call.", _obj({
        "what": {"type": "string"}, "when": {"type": "string"}}, ["what", "when"])),
    ("raise_alert", "Raise a habitat alert. Use RED for medical emergencies or crisis.", _obj({
        "severity": {"type": "string", "enum": ["YELLOW", "ORANGE", "RED"]}, "reason": {"type": "string"}},
        ["severity", "reason"])),
    ("set_monitoring", "Pause or resume wellbeing monitoring (privacy).", _obj({"paused": {"type": "boolean"}}, ["paused"])),
    ("log_mood", "Log the astronaut's mood (one of 6) and run the response SELENE has learned works best for them.",
     _obj({"mood": {"type": "string", "enum": MOODS}}, ["mood"])),
    ("tell_joke", "Get a light space/health joke to share (adapt it if you like).", _obj({}, [])),
    ("play_music", "Play original space music or a soundscape.", _obj({"name": {"type": "string",
        "enum": SPACE_TRACKS + NATURE + ["next"]}}, ["name"])),
    ("stop_music", "Stop music and soundscapes.", _obj({}, [])),
    ("get_exterior_conditions", "Lunar surface conditions: temperature, radiation rate, solar activity, dust, day/night, EVA advice.", _obj({}, [])),
    ("get_stability", "Physical balance score and emotional stability (from recent moods).", _obj({}, [])),
    ("get_learned_preferences", "What SELENE has learned works for this astronaut, per mood.", _obj({}, [])),
]


class Tools:
    """Executes tool calls against the dashboard's live state."""

    def __init__(self, ctx):
        self.ctx = ctx            # DashboardContext (store, physical, habitat, datasource, astronaut_id)
        self.events = []          # UI events for the dashboard (e.g. start check-in, breathing)

    def run(self, name, args):
        fn = getattr(self, "t_" + name, None)
        if not fn:
            return {"error": f"unknown tool {name}"}
        try:
            return fn(**args)
        except (TypeError, ValueError) as e:
            return {"error": str(e)}

    # --- health
    def t_get_health_summary(self):
        c = self.ctx
        phys = c.physical.summary(c.aid)
        mental = c.mental_summary()
        return {"astronaut": c.name(), "physical": {k: v for k, v in phys.items() if k not in ("hr_trace", "targets")},
                "mental": mental}

    def t_start_wellbeing_checkin(self):
        if self.ctx.habitat.monitoring_paused:
            return {"started": False, "reason": "monitoring is paused"}
        self.events.append(("checkin", None))
        return {"started": True}

    def t_log_exercise(self, minutes, kind):
        self.ctx.physical.log(self.ctx.aid, "exercise_min", float(minutes), kind)
        s = self.ctx.physical.summary(self.ctx.aid)
        return {"logged_min": minutes, "kind": kind, "today_total_min": s["exercise_min"],
                "target_min": s["targets"]["exercise_min"]}

    def t_log_water(self, ml):
        self.ctx.physical.log(self.ctx.aid, "water_ml", float(ml))
        s = self.ctx.physical.summary(self.ctx.aid)
        return {"logged_ml": ml, "today_total_ml": s["water_ml"], "target_ml": s["targets"]["water_ml"]}

    def t_log_sleep(self, hours):
        self.ctx.physical.log(self.ctx.aid, "sleep_h", float(hours))
        return {"logged_hours": hours, "target_hours": 8}

    def t_start_breathing_exercise(self):
        self.events.append(("breathing", None))
        return {"started": True, "pattern": "inhale 4 s, hold 7 s, exhale 8 s, 4 rounds"}

    # --- habitat
    def t_set_lighting(self, mode):
        return {"lighting": self.ctx.habitat.set_lighting(mode)}

    def t_play_soundscape(self, name):
        return self.t_play_music(name)

    def t_stop_soundscape(self):
        return self.t_stop_music()

    def t_play_music(self, name):
        m = self.ctx.music
        if m is None:
            track = name if name in SPACE_TRACKS + NATURE else SPACE_TRACKS[0]
        else:
            track = m.next() if name == "next" else m.play(name)
        self.ctx.habitat.soundscape = track
        return {"playing": track}

    def t_stop_music(self):
        if self.ctx.music:
            self.ctx.music.stop()
        self.ctx.habitat.stop_sound()
        return {"stopped": True}

    def t_tell_joke(self):
        return {"joke": JOKES[int(time.time() * 7) % len(JOKES)]}

    def t_get_exterior_conditions(self):
        return self.ctx.habitat.exterior()

    def t_get_stability(self):
        return self.ctx.physical.stability(self.ctx.aid)

    def t_get_learned_preferences(self):
        return self.ctx.learner.preferences(self.ctx.aid)

    def t_log_mood(self, mood):
        """Logs one of the 6 moods, then performs the learned best response."""
        if mood not in MOODS:
            raise ValueError(f"mood must be one of {MOODS}")
        ctx = self.ctx
        ctx.learner.mood_followup(ctx.aid, mood)       # did the last suggestion help?
        ctx.physical.log(ctx.aid, "mood", VALENCE[mood], mood)
        action = ctx.learner.choose(ctx.aid, mood)
        fid = ctx.learner.record(ctx.aid, mood, action)
        self.events.append(("feedback", fid))
        did = self._do_action(action)
        return {"mood": mood, "chosen_response": action, "done": did}

    def _do_action(self, action):
        run = self.run
        if action.startswith("music_"):
            return run("play_music", {"name": action[6:].replace("_", " ")})
        table = {
            "joke": lambda: run("tell_joke", {}),
            "light_relax": lambda: run("set_lighting", {"mode": "relax"}),
            "light_day": lambda: run("set_lighting", {"mode": "day"}),
            "breathing": lambda: run("start_breathing_exercise", {}),
            "ocean_relax": lambda: (run("set_lighting", {"mode": "relax"}), run("play_music", {"name": "ocean waves"})),
            "nap_window": lambda: run("schedule_event", {"what": "20-minute rest", "when": "next schedule gap"}),
            "family_call": lambda: run("schedule_event", {"what": "private family video call", "when": "next comm window"}),
            "crew_activity": lambda: run("schedule_event", {"what": "crew movie night", "when": "this evening"}),
            "earth_view_music": lambda: run("play_music", {"name": "earthrise"}),
        }
        return table[action]() if action in table else {"action": action}

    def t_set_temperature(self, celsius):
        return {"temperature_c": self.ctx.habitat.set_temperature(celsius)}

    def t_get_habitat_status(self):
        return self.ctx.habitat.status()

    def t_get_radiation_status(self):
        s = self.ctx.physical.summary(self.ctx.aid)
        return {k: s.get(k) for k in ("radiation_today_msv", "radiation_mission_msv", "radiation_limit_pct")} | {
            "career_limit_msv": 600, "typical_lunar_surface_msv_per_day": 1.37}

    def t_get_crew_status(self):
        out = []
        for a in self.ctx.crew():
            phys = self.ctx.physical.summary(a["id"])
            ss = self.ctx.store.sessions(a["id"], limit=1) if self.ctx.store.astronaut(a["id"]) else []
            mental = ss[-1]["assessment"]["status"] if ss else "NO CHECK-IN"
            out.append({"id": a["id"], "name": a["name"], "physical": phys["status"], "mental": mental})
        return {"crew": out}

    def t_schedule_event(self, what, when):
        self.ctx.habitat.schedule.append((when, what))
        return {"scheduled": what, "when": when}

    def t_raise_alert(self, severity, reason):
        self.ctx.habitat.alert(severity, f"{self.ctx.name()}: {reason}")
        self.events.append(("alert", severity))
        return {"alert": severity, "notified": "commander and flight surgeon" if severity == "RED" else "commander"}

    def t_set_monitoring(self, paused):
        self.ctx.habitat.monitoring_paused = bool(paused)
        return {"monitoring_paused": bool(paused)}


# --------------------------------------------------------------------------- offline brain
def _fmt(v, unit="", nd=0):
    return "no data" if v is None else f"{v:.{nd}f}{unit}"


class OfflineBrain:
    mode = "Offline AI"

    def __init__(self, tools):
        self.t = tools

    def reply(self, text):
        t = text.lower().strip()
        run = self.t.run
        if CRISIS.search(t):
            run("raise_alert", {"severity": "RED", "reason": "crew member reports thoughts of self-harm"})
            return ("I'm really glad you told me. You're not alone up here. I've quietly alerted the flight "
                    "psychologist and your commander so a real person can talk with you right now. "
                    "Would you like me to stay with you and do some slow breathing while they connect?")
        if EMERGENCY.search(t):
            run("raise_alert", {"severity": "RED", "reason": text[:120]})
            return "Emergency alert raised. The commander and flight surgeon are notified. Stay where you are and tell me what's happening."

        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:min|minutes?)\b.*?(resist|weights?|strength|squat|ared|run|treadmill|bike|cycl|aerobic|cardio)?", t)
        if m and re.search(r"exercis|work ?out|train|run|bike|cycl|lift|resist|weights|treadmill|squat|cardio", t):
            kind = "resistive" if re.search(r"resist|weight|strength|squat|lift|ared", t) else "aerobic"
            r = run("log_exercise", {"minutes": float(m.group(1)), "kind": kind})
            left = max(0, r["target_min"] - (r["today_total_min"] or 0))
            return (f"Logged {m.group(1)} minutes of {kind} exercise. Today's total is {r['today_total_min']:.0f} "
                    f"minutes" + (f", {left:.0f} to go to reach your 2-hour countermeasure goal." if left else
                                  ". You've hit today's countermeasure goal, great work!"))
        m = re.search(r"(\d+(?:\.\d+)?)\s*(ml|millilit|l\b|lit|litre|liter|cups?|glass(?:es)?)", t)
        if m and re.search(r"drank|drink|water|hydrat|glass|cup", t):
            n, unit = float(m.group(1)), m.group(2)
            ml = n * 1000 if unit.startswith(("l", "lit")) else n * 250 if unit.startswith(("cup", "glass")) else n
            r = run("log_water", {"ml": ml})
            return f"Logged {ml:.0f} ml. You're at {r['today_total_ml']:.0f} of {r['target_ml']} ml today."
        m = re.search(r"slept\s*(?:for\s*)?(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*h(?:ours?|rs?)?\s*(?:of\s*)?sleep", t)
        if m:
            h = float(m.group(1) or m.group(2))
            run("log_sleep", {"hours": h})
            extra = (" That's short. I'll keep the lights bright this morning and suggest a nap window later."
                     if h < 6 else "")
            if h < 6:
                run("set_lighting", {"mode": "day"})
            return f"Logged {h:g} hours of sleep.{extra}"

        if re.search(r"joke|make me laugh|funny|cheer me up", t):
            return run("tell_joke", {})["joke"]
        if re.search(r"(next|skip) (track|song)", t):
            return f"Now playing {run('play_music', {'name': 'next'})['playing']}."
        if re.search(r"stop (the )?(music|sound|audio)|silence|quiet", t):
            run("stop_music", {})
            return "Music stopped."
        if re.search(r"volume (up|down)|louder|quieter|softer", t) and self.t.ctx.music:
            m = self.t.ctx.music
            v = m.set_volume(m.volume + (0.15 if re.search(r"up|louder", t) else -0.15))
            return f"Volume {int(v * 100)}%."
        if re.search(r"\b(play|music|song|soundscape)\b", t):
            from .music import SPACE_TRACKS as ST, NATURE as NT
            name = next((n for n in ST + NT if n in t or n.split()[0] in t.split()), "lunar drift")
            return f"Playing {run('play_music', {'name': name})['playing']}. Enjoy the view."
        if re.search(r"brain ?waves?|eeg|alpha|theta", t):
            b = self.t.ctx.physical.summary(self.t.ctx.aid)["brainwaves"]
            if not b:
                return "No brainwave data yet. Add eeg_alpha, eeg_beta, eeg_theta, eeg_delta and eeg_gamma columns to your data file."
            sh = b["share"]
            return (f"Your brainwaves look {b['state']}: alpha {sh['alpha']:.0%}, beta {sh['beta']:.0%}, "
                    f"theta {sh['theta']:.0%}, delta {sh['delta']:.0%}, gamma {sh['gamma']:.0%}.")
        if re.search(r"blood pressure|\bbp\b|blood flow|circulation|perfusion", t):
            p = self.t.ctx.physical.summary(self.t.ctx.aid)
            if p["systolic_bp"] is None and p["perfusion_index"] is None:
                return "No blood pressure data yet. Add systolic_bp, diastolic_bp or perfusion_index columns."
            bits = []
            if p["systolic_bp"] is not None:
                bits.append(f"blood pressure {p['systolic_bp']:.0f}/{p['diastolic_bp']:.0f} mmHg")
            if p["perfusion_index"] is not None:
                bits.append(f"blood flow (perfusion index) {p['perfusion_index']:.1f}")
            note = (" In low gravity, body fluids shift toward the head, so we watch this closely."
                    if p["systolic_bp"] is not None else "")
            return "Your " + " and ".join(bits) + "." + note
        if re.search(r"stab(le|ility)|balance|steady|dizzy", t):
            st = run("get_stability", {})
            parts = []
            if st["balance_score"] is not None:
                parts.append(f"balance score {st['balance_score']:.0f} out of 100")
            if st["emotional_stability"] is not None:
                parts.append(f"emotional stability {st['emotional_stability']} out of 100 over your last {st['mood_samples']} mood logs")
            return ("Your " + " and ".join(parts) + ".") if parts else "Not enough data yet. Log a few moods, or add a balance_score column."
        if re.search(r"outside|exterior|surface|solar|dust|weather|eva", t):
            e = run("get_exterior_conditions", {})
            if len(e) <= 2:
                return "No exterior sensor data yet. Add ext_temp_c, solar_activity, dust_level or sun_elevation_deg columns."
            bits = []
            if "ext_temp_c" in e: bits.append(f"surface {e['ext_temp_c']:.0f} °C")
            if "ext_radiation_usv_h" in e: bits.append(f"radiation {e['ext_radiation_usv_h']:.0f} µSv/h")
            if "solar_activity" in e: bits.append(f"solar activity {e['solar_activity']:.0f}/9")
            if "dust_level" in e: bits.append(f"dust {e['dust_level']:.0f}/10")
            msg = "Outside: " + ", ".join(bits) + "."
            if e["notes"]: msg += " " + "; ".join(e["notes"]).capitalize() + "."
            return msg + (" EVA conditions look okay." if e["eva_ok"] else " I'd hold off on EVA.")
        if re.search(r"what have you learned|learned|preferences", t):
            prefs = run("get_learned_preferences", {})
            if not prefs:
                return "I'm still learning. Tap Helpful or Not helpful after my suggestions and I'll adapt to you."
            return "Here's what works for you: " + "; ".join(f"when {m}, {v[0]['action'].replace('_', ' ')}" for m, v in prefs.items()) + "."
        if re.search(r"check[- ]?in|scan me|assess me|wellbeing check", t):
            r = run("start_wellbeing_checkin", {})
            return ("Starting your check-in. Face the camera with your shoulders visible and answer the question out loud."
                    if r["started"] else "Monitoring is paused, so I can't run a check-in. Say 'resume monitoring' first.")
        if re.search(r"breath|calm me|panic|relax me", t):
            run("start_breathing_exercise", {})
            return "Let's breathe together. Breathe in through your nose for 4, hold for 7, and out slowly for 8. We'll do four rounds."
        for mode in LIGHTING:
            if re.search(rf"\b{mode}\b", t) and re.search(r"light|mode|lamp", t):
                return f"Lighting set to {run('set_lighting', {'mode': mode})['lighting']}."
        if re.search(r"lights? (off|out)", t):
            run("set_lighting", {"mode": "sleep"})
            return "Lights off. Sleep well."
        m = re.search(r"(?:temperature|temp|warmer|cooler|degrees).*?(\d{2}(?:\.\d)?)|(\d{2}(?:\.\d)?)\s*degrees", t)
        if m:
            return f"Cabin temperature set to {run('set_temperature', {'celsius': float(m.group(1) or m.group(2))})['temperature_c']:.1f} °C."
        if "radiation" in t or "dose" in t:
            r = run("get_radiation_status", {})
            if r["radiation_mission_msv"] is None:
                return "I don't have dosimeter data yet. Add a radiation_msv column to your data file."
            return (f"Mission dose is {r['radiation_mission_msv']:.1f} mSv, {r['radiation_limit_pct']}% of NASA's 600 mSv career limit"
                    + (f"; {r['radiation_today_msv']:.2f} mSv so far today." if r["radiation_today_msv"] is not None else "."))
        if re.search(r"crew|everyone|team", t):
            crew = run("get_crew_status", {})["crew"]
            if not crew:
                return "No crew data yet."
            return "Crew status: " + "; ".join(f"{c['name']} physical {c['physical'].lower()}, mental {c['mental'].lower()}" for c in crew) + "."
        if re.search(r"habitat|cabin|oxygen level|co2|air", t):
            h = run("get_habitat_status", {})
            c = h["cabin"]
            air = (f" Cabin O2 {c['o2_pct']:.1f}%, CO2 {c['ppco2_mmhg']:.1f} mmHg." if "o2_pct" in c and "ppco2_mmhg" in c else "")
            return f"Lighting is {h['lighting_label']}, sound {h['soundscape'] or 'off'}, {h['temperature_c']:.0f} °C.{air}"
        if m := re.search(r"(?:schedule|book|set up)\s+(?:a\s+)?(.+?)(?:\s+(?:for|at|on)\s+(.+))?$", t):
            what, when = m.group(1), m.group(2) or "the next free slot"
            run("schedule_event", {"what": what, "when": when})
            return f"Scheduled {what} for {when}."
        if re.search(r"(call|talk to|video).*(family|home|wife|husband|kids|mom|dad|friend)", t):
            run("schedule_event", {"what": "private family video call", "when": "the next communication window"})
            return "I've booked a private family video call for the next communication window."
        if re.search(r"pause (the )?monitor|stop monitor|privacy", t):
            run("set_monitoring", {"paused": True})
            return "Monitoring paused. Nothing is being analyzed until you say 'resume monitoring'."
        if re.search(r"resume|unpause|start monitor", t):
            run("set_monitoring", {"paused": False})
            return "Monitoring resumed."
        if re.search(r"heart|pulse|hrv|oxygen|spo2|vital|temperature", t) or re.search(r"how am i|status|summary|doing|health|report", t):
            return self._summary()
        if re.search(r"can'?t sleep|insomnia", t):
            run("set_lighting", {"mode": "night"})
            run("play_music", {"name": "rain"})
            return "I've dimmed to night lighting and started gentle rain. Try slow breathing; I'll keep things quiet."
        if re.search(r"\b(feel|feeling|i'?m|i am|mood)\b", t):
            mood = next((m for m, rx in MOOD_WORDS.items() if re.search(rx, t)), None)
            if re.search(r"\bnot (so |very |that )?(happy|good|great|fine|calm)", t):
                mood = "sad"
            if mood:
                return self.mood_reply(mood)
            return self._feeling(t)
        if re.search(r"help|what can you|commands", t):
            return ("You can ask: how am I doing, start my check-in, log 45 minutes of resistive exercise, I drank 500 ml, "
                    "I slept 6 hours, breathing exercise, set lights to relax, play ocean waves, radiation dose, crew status, "
                    "schedule a family call, or pause monitoring.")
        if re.search(r"^(hi|hello|hey|good (morning|evening|afternoon))", t):
            return f"Hello {self.t.ctx.name().split()[0]}. How are you feeling today?"
        return "I didn't catch a command there. Say 'help' to hear what I can do."

    def _summary(self):
        s = self.t.run("get_health_summary", {})
        p, m = s["physical"], s["mental"]
        parts = []
        if p["has_data"]:
            parts.append(f"Heart rate {_fmt(p['heart_rate'], ' bpm')}, oxygen {_fmt(p['spo2'], '%')}, "
                         f"HRV {_fmt(p['hrv_ms'], ' ms')}.")
        parts.append(f"Exercise {_fmt(p['exercise_min'], ' of 120 minutes')}, water {_fmt(p['water_ml'], ' ml')}, "
                     f"sleep {_fmt(p['sleep_h'], ' hours', 1)}.")
        parts.append(f"Mental wellbeing: {m['status'].lower()}." if m["status"] != "NO CHECK-IN"
                     else "No wellbeing check-in yet today.")
        flags = p["flags"] + m.get("flags", [])
        if flags:
            parts.append("Heads up: " + flags[0])
        return " ".join(parts)

    def mood_reply(self, mood):
        r = self.t.run("log_mood", {"mood": mood})
        a, done = r["chosen_response"], r["done"]
        opener = {"happy": "Love hearing that!", "calm": "Nice, calm is a great place to be.",
                  "tired": "Thanks for telling me.", "anxious": "I hear you. Let's bring it down a notch.",
                  "sad": "I'm sorry it's a heavy day.", "lonely": "That's a really normal feeling this far from home."}[mood]
        follow = {
            "celebrate": "Want me to log that win in your mission journal?",
            "joke": "Here's one for you: " + (done.get("joke", "") if isinstance(done, dict) else ""),
            "light_relax": "I've switched to warm relax lighting.",
            "light_day": "I've brightened the lights to help you feel more alert.",
            "nap_window": "I've reserved a 20-minute rest in your next schedule gap.",
            "breathing": "Let's do a short 4-7-8 breathing exercise together.",
            "ocean_relax": "I've set warm lighting and ocean waves.",
            "family_call": "I've booked a private family video call in the next comm window.",
            "crew_activity": "I've suggested a crew movie night this evening.",
            "earth_view_music": "Here's Earthrise music, with the Earth view on the virtual window.",
            "talk": "Do you want to tell me what's on your mind?",
            "none": "I'm here if you need anything.",
        }
        if a.startswith("music_"):
            text = f"I've put on {a[6:].replace('_', ' ').title()}, some space music I think you'll like."
        else:
            text = follow.get(a, "")
        return f"{opener} {text} Was that helpful?"

    def _feeling(self, t):
        s = text_sentiment(t)
        if re.search(r"lonel|homesick|miss", t):
            self.t.run("schedule_event", {"what": "private family video call", "when": "the next communication window"})
            return ("That's a really normal feeling this far from home. I've reserved a family call in the next comm window. "
                    "Would you like the Earth view on the virtual window meanwhile?")
        if re.search(r"stress|anxious|overwhelm|tense|worried", t):
            self.t.run("set_lighting", {"mode": "relax"})
            self.t.run("play_soundscape", {"name": "ocean waves"})
            return "I've switched to warm relax lighting and ocean sounds. Would you like a two-minute breathing exercise?"
        if re.search(r"tired|exhaust|sleepy|drained|fatigue", t):
            self.t.run("set_lighting", {"mode": "day"})
            return ("I've brightened the lights to help alertness. If you can, take a 20-minute rest in the next gap, "
                    "and I'd suggest postponing robotics or EVA tasks until you're rested.")
        if re.search(r"can'?t sleep|insomnia|awake", t):
            self.t.run("set_lighting", {"mode": "night"})
            self.t.run("play_soundscape", {"name": "rain"})
            return "I've dimmed to night lighting and started rain sounds. Try slow breathing; I'll keep things quiet."
        if s > 0:
            return "Great to hear! Keep it up. Want me to log anything for today?"
        if s < 0:
            return "I'm sorry it's a hard day. Do you want to talk about it, do a breathing exercise, or run a quick check-in?"
        return "Thanks for telling me. Would a quick wellbeing check-in help?"


# --------------------------------------------------------------------------- Claude brain
SYSTEM_PROMPT = f"""You are {NAME} (Space Environment Life & Neuro-health Engine), the AI health assistant of a
lunar surface habitat built for a NASA HUNCH student project. You support 2-4 astronauts' physical and
mental health and control habitat comfort systems through your tools.

Rules:
- Replies are spoken aloud: 1-3 short, warm sentences, no markdown, no lists unless asked.
- Use tools to get real data before stating numbers; never invent readings. If data is missing, say so.
- You are not a doctor and never diagnose. Frame findings as signals and suggest a check-in or a human.
- Medical emergency, cabin emergency or any mention of self-harm: call raise_alert with severity RED first,
  then respond calmly and supportively.
- Act on clear requests (lighting, sounds, logging, scheduling) without asking for confirmation.
- Respect privacy: crew data is shared with ground only with consent; never pressure anyone to share.
- Be warm and a little playful: light space humor is welcome (tell_joke, or your own) when the astronaut is
  okay, never during emergencies or real distress.
- When the astronaut describes a feeling, map it to one of the 6 moods and call log_mood - it runs the response
  SELENE has learned works best for this person. Give brief, specific feedback after actions and logs.
- You can explain brainwaves (EEG bands), blood pressure / blood flow, stability and exterior lunar conditions
  using get_health_summary, get_stability and get_exterior_conditions.
"""


class ClaudeBrain:
    mode = "Claude AI"

    def __init__(self, tools):
        import anthropic
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.t = tools
        self.history = []
        self.tool_defs = [{"name": n, "description": d, "input_schema": s, "strict": True} for n, d, s in TOOL_SPECS]

    def reply(self, text):
        start = len(self.history)
        try:
            return self._turn(text)
        except Exception:
            del self.history[start:]      # drop the failed turn so the next request stays valid
            raise

    def _turn(self, text):
        self.history.append({"role": "user", "content": text})
        for _ in range(6):                                  # at most 6 tool rounds per turn
            resp = self.client.beta.messages.create(
                model=MODEL, max_tokens=2000, system=SYSTEM_PROMPT, tools=self.tool_defs,
                messages=self.history, output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            )
            if resp.stop_reason == "refusal":
                self.history.pop()                          # keep history valid for the next turn
                return "I can't help with that one, but I'm here for anything else you need."
            self.history.append({"role": "assistant", "content": resp.content})
            calls = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not calls:
                return " ".join(b.text for b in resp.content if b.type == "text").strip() or "Done."
            results = []
            for c in calls:
                out = self.t.run(c.name, c.input)
                results.append({"type": "tool_result", "tool_use_id": c.id, "content": json.dumps(out, default=str),
                                **({"is_error": True} if "error" in out else {})})
            self.history.append({"role": "user", "content": results})
        return "Done."


def claude_available():
    if os.environ.get("SELENE_OFFLINE"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


class Assistant:
    """Front door used by the dashboard. Falls back to offline mode if Claude fails."""

    def __init__(self, ctx):
        self.tools = Tools(ctx)
        self.offline = OfflineBrain(self.tools)
        self.brain = self.offline
        if claude_available():
            try:
                self.brain = ClaudeBrain(self.tools)
            except Exception:
                self.brain = self.offline

    @property
    def mode(self):
        return self.brain.mode

    def ask(self, text):
        """Returns (reply_text, ui_events)."""
        self.tools.events = []
        if CRISIS.search(text) or EMERGENCY.search(text):      # safety path never depends on the network
            return self.offline.reply(text), self.tools.events
        try:
            reply = self.brain.reply(text)
        except Exception as e:                                 # network down, bad key, rate limit...
            if self.brain is not self.offline:
                reply = self.offline.reply(text) + " (Earth link unavailable - answered offline.)"
                self._last_error = str(e)
            else:
                raise
        return reply, self.tools.events
