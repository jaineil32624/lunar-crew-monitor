"""Shared live state for the dashboard and the assistant."""
import datetime as dt
from .datasource import DataSource
from .habitat import Habitat
from .physical import PhysicalHealth
from .store import Store
from .learning import Learner


class DashboardContext:
    def __init__(self, data_path=None, db=None):
        self.store = Store(db) if db else Store()
        self.ds = DataSource(data_path)
        self.physical = PhysicalHealth(self.store, self.ds)
        self.habitat = Habitat(self.ds)
        self.learner = Learner(self.store)
        self.music = None            # MusicPlayer, attached by the dashboard
        crew = self.crew()
        self.aid = crew[0]["id"] if crew else None

    def crew(self):
        """Astronauts enrolled in the monitor plus any IDs found in the data file."""
        out = {a["id"]: a for a in self.store.astronauts()}
        for aid in self.ds.crew_ids():
            out.setdefault(aid, {"id": aid, "name": aid, "role": "", "share_with_ground": 0})
        return list(out.values())

    def name(self, aid=None):
        aid = aid or self.aid
        a = self.store.astronaut(aid) if aid else None
        return a["name"] if a else (aid or "Astronaut")

    def mental_summary(self, aid=None):
        aid = aid or self.aid
        ss = self.store.sessions(aid, limit=1) if aid and self.store.astronaut(aid) else []
        d = self.ds.latest(aid) if aid else {}
        if not ss:
            return {"status": "NO CHECK-IN", "indicators": {}, "flags": [],
                    "self_report": {k: d[k] for k in ("mood", "stress") if k in d}}
        a = ss[-1]["assessment"]
        return {"status": a["status"], "last_checkin": dt.datetime.fromtimestamp(ss[-1]["ts"]).strftime("%b %d %H:%M"),
                "indicators": {k: {"score": v["score"], "level": v.get("level", "")} for k, v in a.get("indicators", {}).items()},
                "flags": a.get("flags", []), "message": a.get("message", ""),
                "self_report": {k: d[k] for k in ("mood", "stress") if k in d}}

    def mental_history(self, aid=None, n=21):
        aid = aid or self.aid
        if not aid or not self.store.astronaut(aid):
            return []
        return [s["assessment"].get("indicators", {}) for s in self.store.sessions(aid)][-n:]
