"""Local SQLite storage. Only numeric features and scores are stored -
never images or audio. Nothing leaves the habitat unless the astronaut
has consented to share summaries with ground (see `consent`)."""
import json
import sqlite3
import time
from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS astronauts (
    id TEXT PRIMARY KEY, name TEXT, role TEXT,
    share_with_ground INTEGER DEFAULT 0, created REAL);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, astronaut_id TEXT, ts REAL,
    kind TEXT, features TEXT, assessment TEXT, note TEXT);
"""


class Store:
    def __init__(self, path=None):
        path = path or config.DB_PATH
        if str(path) != ":memory:":
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        # the dashboard reads/writes from its AI worker thread too
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript(SCHEMA)

    def add_astronaut(self, aid, name, role="", share=False):
        self.db.execute("INSERT OR REPLACE INTO astronauts VALUES (?,?,?,?,?)",
                        (aid, name, role, int(share), time.time()))
        self.db.commit()

    def astronaut(self, aid):
        r = self.db.execute("SELECT id,name,role,share_with_ground FROM astronauts WHERE id=?", (aid,)).fetchone()
        return dict(zip(("id", "name", "role", "share_with_ground"), r)) if r else None

    def astronauts(self):
        return [dict(zip(("id", "name", "role", "share_with_ground"), r)) for r in
                self.db.execute("SELECT id,name,role,share_with_ground FROM astronauts ORDER BY id")]

    def set_consent(self, aid, share):
        self.db.execute("UPDATE astronauts SET share_with_ground=? WHERE id=?", (int(share), aid))
        self.db.commit()

    def add_session(self, aid, features, assessment, kind="checkin", note="", ts=None):
        cur = self.db.execute(
            "INSERT INTO sessions (astronaut_id,ts,kind,features,assessment,note) VALUES (?,?,?,?,?,?)",
            (aid, ts or time.time(), kind, json.dumps(features), json.dumps(assessment), note))
        self.db.commit()
        return cur.lastrowid

    def sessions(self, aid, limit=None):
        q = "SELECT id,ts,kind,features,assessment,note FROM sessions WHERE astronaut_id=? ORDER BY ts"
        rows = self.db.execute(q, (aid,)).fetchall()
        out = [{"id": r[0], "ts": r[1], "kind": r[2], "features": json.loads(r[3]),
                "assessment": json.loads(r[4]), "note": r[5]} for r in rows]
        return out[-limit:] if limit else out

    def delete_astronaut_data(self, aid):
        self.db.execute("DELETE FROM sessions WHERE astronaut_id=?", (aid,))
        self.db.execute("DELETE FROM astronauts WHERE id=?", (aid,))
        self.db.commit()
