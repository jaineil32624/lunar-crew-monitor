"""Run with:  python -m unittest discover tests   (no camera/mic needed)"""
import unittest
import numpy as np
from crew_monitor import simulate
from crew_monitor.store import Store
from crew_monitor.voice import extract_features
from crew_monitor.selfreport import text_sentiment


def tone_speech(f0, rate, pause_every, var_st, seconds=12, sr=16000, seed=0):
    """Synthetic 'speech': harmonic syllables at `rate`/s with a 0.5 s pause
    after every `pause_every` syllables, pitch varying by `var_st` semitones."""
    rng, out, t, i = np.random.default_rng(seed), [], 0, 0
    while t < seconds:
        n = int(sr / rate)
        f = f0 * 2 ** (rng.normal(0, var_st) / 12)
        ph = 2 * np.pi * f * np.arange(n) / sr
        out.append(sum(np.sin(k * ph) / k for k in range(1, 6)) * np.hanning(n) * 0.3)
        t, i = t + 1 / rate, i + 1
        if i % pause_every == 0:
            out.append(rng.normal(0, 0.001, int(0.5 * sr)))
            t += 0.5
    return np.concatenate(out), sr


class TestVoice(unittest.TestCase):
    def test_pitch_and_monotone(self):
        normal = extract_features(*tone_speech(140, 4, 8, 2.0))
        flat = extract_features(*tone_speech(140, 2.5, 2, 0.4))
        self.assertAlmostEqual(normal["voice_f0_mean"], 140, delta=10)
        self.assertLess(flat["voice_f0_range_st"], normal["voice_f0_range_st"])
        self.assertLess(flat["voice_speech_rate"], normal["voice_speech_rate"])
        self.assertGreater(flat["voice_pause_ratio"], normal["voice_pause_ratio"])

    def test_silence_returns_nothing(self):
        self.assertEqual(extract_features(np.zeros(32000), 16000), {})


class TestText(unittest.TestCase):
    def test_sentiment(self):
        self.assertGreater(text_sentiment("feeling great and rested"), 0)
        self.assertLess(text_sentiment("tired and lonely"), 0)
        self.assertLess(text_sentiment("not happy"), 0)


class TestMission(unittest.TestCase):
    def test_simulated_crew(self):
        s = Store(":memory:")
        simulate.run(s, days=21, verbose=False)
        status = {a["id"]: [x["assessment"]["status"] for x in s.sessions(a["id"])] for a in s.astronauts()}
        self.assertNotIn("ORANGE", status["A1"])                 # steady: no false alarms
        self.assertEqual(status["A2"][-1], "ORANGE")              # fatigue detected
        self.assertIn("ORANGE", status["A3"][12:17])              # stress window detected
        self.assertNotEqual(status["A3"][-1], "ORANGE")           # ...and recovery seen
        flags = [f for x in s.sessions("A4") for f in x["assessment"]["flags"]]
        self.assertTrue(any("Self-report looks fine" in f for f in flags))  # masking caught


if __name__ == "__main__":
    unittest.main()
