"""Voice (prosody) features computed with numpy only - no cloud, no raw audio stored.

Features (all compared later with the astronaut's own baseline):
  voice_f0_mean       average pitch (Hz)                -> rises with stress/arousal
  voice_f0_range_st   pitch range in semitones          -> flat/monotone with low mood
  voice_jitter        frame-to-frame pitch instability  -> stress, fatigue
  voice_energy_db     loudness of speech (dBFS)         -> low with fatigue/low mood
  voice_energy_var_db loudness variability              -> agitation
  voice_pause_ratio   share of silence between speech   -> psychomotor slowing
  voice_mean_pause_s  average pause length
  voice_speech_rate   syllable-like energy peaks / s    -> slows with fatigue/low mood
"""
import threading
import wave
import numpy as np

FRAME_S, HOP_S = 0.040, 0.010
F0_MIN, F0_MAX = 60.0, 400.0
MIN_PAUSE_S = 0.25


def load_wav(path):
    with wave.open(str(path), "rb") as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[width]
    x = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    if width == 1:
        x = (x - 128) / 128.0
    else:
        x /= float(2 ** (8 * width - 1))
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


class MicRecorder:
    """Records the microphone in the background while the camera runs."""

    def __init__(self, sr=16000):
        import sounddevice as sd
        self.sd, self.sr, self.chunks = sd, sr, []
        self._stream = sd.InputStream(samplerate=sr, channels=1, callback=self._cb)

    def _cb(self, indata, frames, t, status):
        self.chunks.append(indata[:, 0].copy())

    def __enter__(self):
        self._stream.start()
        return self

    def __exit__(self, *exc):
        self._stream.stop()
        self._stream.close()

    def audio(self):
        return (np.concatenate(self.chunks) if self.chunks else np.zeros(0)), self.sr


def _frames(x, sr):
    n, h = int(FRAME_S * sr), int(HOP_S * sr)
    if len(x) < n:
        return np.zeros((0, n))
    idx = np.arange(n)[None, :] + h * np.arange((len(x) - n) // h + 1)[:, None]
    return x[idx]


def _pitch(frame, sr):
    """Autocorrelation pitch estimate; returns Hz or None if unvoiced."""
    f = (frame - frame.mean()) * np.hanning(len(frame))
    ac = np.correlate(f, f, mode="full")[len(f) - 1:]
    if ac[0] <= 0:
        return None
    ac /= ac[0]
    lo, hi = int(sr / F0_MAX), min(int(sr / F0_MIN), len(ac) - 1)
    if hi <= lo:
        return None
    lag = lo + int(np.argmax(ac[lo:hi]))
    if ac[lag] < 0.45:
        return None
    # parabolic interpolation for sub-sample accuracy
    if 0 < lag < len(ac) - 1:
        a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
        denom = a - 2 * b + c
        lag = lag + 0.5 * (a - c) / denom if denom != 0 else lag
    return sr / lag


def extract_features(x, sr):
    x = np.asarray(x, dtype=np.float64)
    if len(x) < sr:              # need at least ~1 s of audio
        return {}
    x = x - x.mean()
    fr = _frames(x, sr)
    rms = np.sqrt((fr ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-12)
    # Speech/silence threshold: above the noise floor, but never more than 25 dB
    # below the loud speech level (keeps it robust when there is little silence).
    floor, loud = np.percentile(db, 5), np.percentile(db, 95)
    speech = db > max(min(floor + 9, loud - 25), -55)
    if speech.sum() < 0.5 / HOP_S:   # less than 0.5 s of speech
        return {}

    first, last = np.argmax(speech), len(speech) - 1 - np.argmax(speech[::-1])
    span = speech[first:last + 1]
    # pauses = runs of silence inside the speaking span
    pauses, run = [], 0
    for s in span:
        if not s:
            run += 1
        else:
            if run * HOP_S >= MIN_PAUSE_S:
                pauses.append(run * HOP_S)
            run = 0
    span_s = len(span) * HOP_S
    speech_s = speech.sum() * HOP_S

    # syllable-like nuclei: local energy peaks inside speech, >=120 ms apart
    sm = np.convolve(db, np.ones(5) / 5, mode="same")
    peaks, last_peak = 0, -1e9
    min_gap = int(0.12 / HOP_S)
    for i in range(2, len(sm) - 2):
        if speech[i] and sm[i] == sm[i - 2:i + 3].max() and sm[i] - sm[max(0, i - 10):i + 10].min() > 3:
            if i - last_peak >= min_gap:
                peaks, last_peak = peaks + 1, i

    f0 = [(i, _pitch(fr[i], sr)) for i in np.where(speech)[0]]
    f0 = [(i, p) for i, p in f0 if p is not None]
    feats = {
        "voice_energy_db": float(db[speech].mean()),
        "voice_energy_var_db": float(db[speech].std()),
        "voice_pause_ratio": float(sum(pauses) / span_s) if span_s else 0.0,
        "voice_mean_pause_s": float(np.mean(pauses)) if pauses else 0.0,
        "voice_speech_rate": float(peaks / speech_s),
        "voice_speech_s": float(speech_s),
    }
    if len(f0) >= 20:
        hz = np.array([p for _, p in f0])
        # discard octave errors relative to the median
        med = np.median(hz)
        keep = (hz > med / 1.6) & (hz < med * 1.6)
        idx = np.array([i for i, _ in f0])[keep]
        hz = hz[keep]
        p10, p90 = np.percentile(hz, [10, 90])
        periods = 1.0 / hz
        adjacent = np.diff(idx) == 1
        jit = (np.abs(np.diff(periods))[adjacent].mean() / periods.mean()) if adjacent.any() else 0.0
        feats.update({
            "voice_f0_mean": float(hz.mean()),
            "voice_f0_range_st": float(12 * np.log2(p90 / p10)),
            "voice_jitter": float(jit),
        })
    return feats
