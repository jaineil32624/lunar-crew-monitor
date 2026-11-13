"""Run with:  python -m unittest discover tests   (no camera/mic needed)"""
import unittest
import numpy as np
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


class TestFusion(unittest.TestCase):
    def test_baseline_then_fatigue(self):
        import random
        from crew_monitor.fusion import assess
        from crew_monitor import config
        random.seed(0)
        base = {"face_perclos": .05, "voice_speech_rate": 4.0, "posture_neck_flexion": 40, "self_sleep_h": 7.5}
        hist = []
        for _ in range(6):
            f = {k: v + random.gauss(0, config.SCALE_FLOOR[k] * .5) for k, v in base.items()}
            hist.append({"features": f, "assessment": assess(f, hist)})
        self.assertEqual(hist[0]["assessment"]["status"], "CALIBRATING")
        tired = {"face_perclos": .25, "voice_speech_rate": 2.8, "posture_neck_flexion": 50, "self_sleep_h": 4.5}
        a = assess(tired, hist)
        self.assertEqual(a["indicators"]["fatigue"]["level"], "concern")


if __name__ == "__main__":
    unittest.main()
