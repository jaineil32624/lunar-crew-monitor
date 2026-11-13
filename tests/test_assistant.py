"""Dashboard data connector + SELENE assistant (offline brain and Claude tool loop)."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace as NS

from crew_monitor.context import DashboardContext
from crew_monitor.assistant import Assistant, ClaudeBrain, Tools

CSV = """time,Crew,HR,hrv,SpO2,sleep_hours,exercise,water,dose_msv,cabin_o2,co2,mystery
2026-11-13T08:00:00,A1,62,58,97.8,7.5,30,500,16.4,20.9,2.1,x
2026-11-13T09:00:00,A1,64,55,88.0,,45,900,16.5,20.9,2.2,y
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.csv = os.path.join(self.dir, "sim.csv")
        with open(self.csv, "w") as f:
            f.write(CSV)
        self.ctx = DashboardContext(self.csv, ":memory:")


class TestDataSource(Base):
    def test_aliases_and_latest(self):
        d = self.ctx.ds.latest("A1")
        self.assertEqual(d["heart_rate"], 64)
        self.assertEqual(d["sleep_h"], 7.5)          # empty cell keeps the last real value
        self.assertEqual(self.ctx.ds.cabin()["ppco2_mmhg"], 2.2)
        self.assertIn("mystery", self.ctx.ds.unknown_columns)

    def test_low_spo2_is_red(self):
        s = self.ctx.physical.summary("A1")
        self.assertEqual(s["status"], "RED")


class TestOffline(Base):
    def setUp(self):
        super().setUp()
        os.environ["SELENE_OFFLINE"] = "1"
        self.a = Assistant(self.ctx)

    def ask(self, t):
        return self.a.ask(t)

    def test_logging_adds_to_data(self):
        reply, _ = self.ask("I did 30 minutes of resistive exercise")
        self.assertIn("75 minutes", reply)            # 45 from the data file + 30 logged
        self.ask("I drank 2 glasses of water")
        self.assertEqual(self.ctx.physical.summary("A1")["water_ml"], 1400)

    def test_habitat_commands(self):
        self.ask("set lights to night mode")
        self.assertEqual(self.ctx.habitat.lighting, "night")
        self.ask("play ocean waves")
        self.assertEqual(self.ctx.habitat.soundscape, "ocean waves")

    def test_checkin_event_and_privacy(self):
        _, ev = self.ask("start my check-in")
        self.assertEqual(ev[0][0], "checkin")
        self.ask("pause monitoring")
        _, ev = self.ask("start my check-in")
        self.assertEqual(ev, [])

    def test_crisis_raises_red_alert(self):
        reply, ev = self.ask("I don't want to live, I want to hurt myself")
        self.assertEqual(self.ctx.habitat.alerts[0][1], "RED")
        self.assertIn("psychologist", reply)


class FakeMessages:
    """Scripted stand-in for client.beta.messages: first a tool call, then text."""

    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=lambda o: o.__dict__)))
        if len(self.calls) == 1:
            return NS(stop_reason="tool_use", content=[
                NS(type="text", text="Setting that up."),
                NS(type="tool_use", id="tu_1", name="set_lighting", input={"mode": "relax"})])
        return NS(stop_reason="end_turn", content=[NS(type="text", text="Lights are now relaxing.")])


class TestClaudeLoop(Base):
    def test_tool_loop(self):
        brain = ClaudeBrain.__new__(ClaudeBrain)
        brain.t, brain.history = Tools(self.ctx), []
        brain.tool_defs = []
        fake = FakeMessages()
        brain.client = NS(beta=NS(messages=fake))
        self.assertEqual(brain.reply("make it cozy"), "Lights are now relaxing.")
        self.assertEqual(self.ctx.habitat.lighting, "relax")
        second = fake.calls[1]["messages"]
        self.assertEqual([m["role"] for m in second], ["user", "assistant", "user"])
        self.assertEqual(second[2]["content"][0]["type"], "tool_result")
        self.assertEqual(fake.calls[0]["fallbacks"], "default")


if __name__ == "__main__":
    unittest.main()
