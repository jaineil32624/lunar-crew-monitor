"""SELENE learns from each astronaut.

Every time SELENE suggests something (lighting, music, breathing, a joke, a call home)
it records the context (e.g. mood "anxious") and the action. Reward comes from:
  * the astronaut tapping Helpful (+1) / Not helpful (0), and
  * whether their next mood log, within 3 hours, is better than before.
Actions are then chosen by Thompson sampling (a multi-armed bandit): good actions are
picked more often, but new ones still get tried. Learned data stays on the habitat computer.
"""
import random
import time

VALENCE = {"happy": 2, "calm": 1, "tired": -1, "anxious": -1.5, "sad": -2, "lonely": -2}

# Candidate responses per mood (each maps to assistant tool calls in assistant.py)
CANDIDATES = {
    "happy":   ["celebrate", "joke", "music_earthrise"],
    "calm":    ["music_deep_field", "light_relax", "none"],
    "tired":   ["light_day", "nap_window", "music_solar_wind", "joke"],
    "anxious": ["breathing", "ocean_relax", "music_lunar_drift", "talk"],
    "sad":     ["family_call", "earth_view_music", "joke", "talk", "crew_activity"],
    "lonely":  ["family_call", "crew_activity", "music_earthrise", "talk"],
}


class Learner:
    def __init__(self, store, rng=None):
        self.db = store.db
        self.rng = rng or random.Random()
        self.db.execute("""CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT, astronaut_id TEXT, ts REAL,
            context TEXT, action TEXT, reward REAL)""")
        self.db.commit()

    def record(self, aid, context, action, reward=None):
        cur = self.db.execute("INSERT INTO feedback (astronaut_id, ts, context, action, reward) VALUES (?,?,?,?,?)",
                              (aid, time.time(), context, action, reward))
        self.db.commit()
        return cur.lastrowid

    def rate(self, fid, helpful):
        self.db.execute("UPDATE feedback SET reward=? WHERE id=?", (1.0 if helpful else 0.0, fid))
        self.db.commit()

    def mood_followup(self, aid, new_mood):
        """Reward recent unrated actions by how much mood improved."""
        since = time.time() - 3 * 3600
        rows = self.db.execute("SELECT id, context FROM feedback WHERE astronaut_id=? AND ts>? AND reward IS NULL",
                               (aid, since)).fetchall()
        for fid, ctx in rows:
            if ctx in VALENCE:
                improved = VALENCE.get(new_mood, 0) - VALENCE[ctx]
                self.db.execute("UPDATE feedback SET reward=? WHERE id=?", (1.0 if improved > 0 else 0.0, fid))
        self.db.commit()

    def stats(self, aid, context):
        rows = self.db.execute("""SELECT action, COUNT(reward), COALESCE(SUM(reward),0) FROM feedback
                                  WHERE astronaut_id=? AND context=? AND reward IS NOT NULL GROUP BY action""",
                               (aid, context)).fetchall()
        return {a: (n, s) for a, n, s in rows}

    def choose(self, aid, context):
        cands = CANDIDATES.get(context, ["talk"])
        st = self.stats(aid, context)
        # Thompson sampling with a Beta(1,1) prior
        draws = {a: self.rng.betavariate(1 + st.get(a, (0, 0))[1], 1 + st.get(a, (0, 0))[0] - st.get(a, (0, 0))[1])
                 for a in cands}
        return max(draws, key=draws.get)

    def preferences(self, aid):
        """Human-readable summary of what has worked, for the Settings page and Claude."""
        out = {}
        for ctx in CANDIDATES:
            st = self.stats(aid, ctx)
            ranked = sorted(((s + 1) / (n + 2), a, n) for a, (n, s) in st.items())
            if ranked:
                out[ctx] = [{"action": a, "success_rate": round(p, 2), "tries": n} for p, a, n in reversed(ranked)]
        return out
