"""Space music + soundscapes, synthesised in Python (original, offline, copyright-free).

Tracks are generated with numpy the first time they are played and then loop.
Drop your own .wav files (e.g. NASA's public-domain space sounds) into the
`music/` folder next to the project, or set SELENE_MUSIC_DIR, and they appear too.
"""
import os
import threading
import wave
from pathlib import Path

import numpy as np

SR = 22050
SPACE_TRACKS = ["lunar drift", "earthrise", "solar wind", "deep field"]
NATURE = ["earth forest", "ocean waves", "rain", "birdsong", "campfire", "white noise"]
MUSIC_DIR = Path(os.environ.get("SELENE_MUSIC_DIR", Path(__file__).resolve().parent.parent / "music"))


def _note(n):                       # MIDI note -> Hz
    return 440.0 * 2 ** ((n - 69) / 12)


def _lowpass(x, a):                 # one-pole low-pass, a in (0,1): smaller = darker
    y = np.empty_like(x)
    acc = 0.0
    for i in range(0, len(x), 2048):    # block loop keeps it fast enough
        seg = x[i:i + 2048]
        out = np.empty_like(seg)
        for j, v in enumerate(seg):
            acc += a * (v - acc)
            out[j] = acc
        y[i:i + 2048] = out
    return y


def _smooth_noise(n, rng, cutoff_hz):
    """Cheap coloured noise: interpolate random points spaced at the cutoff rate."""
    k = max(2, int(n * cutoff_hz / SR))
    pts = rng.normal(0, 1, k + 1)
    return np.interp(np.linspace(0, k, n), np.arange(k + 1), pts)


def _pad(t, notes, rng, detune=0.004, bright=3):
    out = np.zeros_like(t)
    for n in notes:
        f = _note(n)
        for d in (-detune, 0, detune):
            ph = rng.uniform(0, 2 * np.pi)
            for h in range(1, bright + 1):
                out += np.sin(2 * np.pi * f * (1 + d) * h * t + ph * h) / (h * h)
    return out


def _bells(t, scale, rng, rate=0.35, decay=2.5):
    out = np.zeros_like(t)
    n_events = int(t[-1] * rate)
    for _ in range(n_events):
        start = rng.uniform(0, t[-1] - 3)
        f = _note(rng.choice(scale))
        i0 = int(start * SR)
        seg = t[: int(4 * SR)]
        env = np.exp(-seg * decay)
        tone = (np.sin(2 * np.pi * f * seg) + 0.3 * np.sin(2 * np.pi * f * 2.76 * seg)) * env
        out[i0:i0 + len(tone)] += tone[: len(out) - i0]
    return out


def synth(name, seconds=48, seed=0):
    rng = np.random.default_rng(abs(hash(name)) % 2**32 + seed)
    n = int(SR * seconds)
    t = np.arange(n) / SR
    lfo = 0.6 + 0.4 * np.sin(2 * np.pi * t / seconds * 2)         # loops cleanly
    if name == "lunar drift":
        chords = [[45, 52, 59, 64, 71], [41, 48, 55, 60, 67], [43, 50, 57, 62, 69], [45, 52, 57, 64, 71]]
        seg = n // len(chords)
        x = np.concatenate([_pad(t[:seg], c, rng) for c in chords])
        x = x[:n] if len(x) >= n else np.pad(x, (0, n - len(x)))
        x = x * lfo * 0.08 + _bells(t, [69, 71, 72, 76, 79, 81], rng) * 0.05
    elif name == "earthrise":
        chords = [[48, 55, 64, 71], [53, 60, 69, 76], [45, 52, 60, 67], [50, 57, 65, 72]]
        seg = n // len(chords)
        x = np.concatenate([_pad(t[:seg], c, rng, bright=4) for c in chords])
        x = np.pad(x, (0, max(0, n - len(x))))[:n] * lfo * 0.07 + _bells(t, [72, 74, 76, 79, 81, 84], rng, 0.5) * 0.04
    elif name == "solar wind":
        wind = _smooth_noise(n, rng, 900) * (0.5 + 0.5 * _smooth_noise(n, rng, 0.15))
        x = wind * 0.12 + _pad(t, [38, 45], rng, bright=2) * 0.06 * lfo
    elif name == "deep field":
        drone = _pad(t, [33, 40, 45], rng, detune=0.002, bright=2) * 0.08
        shimmer = sum(np.sin(2 * np.pi * _note(m) * t) * (0.5 + 0.5 * np.sin(2 * np.pi * t / (7 + i * 3)))
                      for i, m in enumerate([88, 91, 95, 100])) * 0.012
        x = drone * lfo + shimmer
    elif name == "ocean waves":
        swell = (0.5 + 0.5 * np.sin(2 * np.pi * t / 8.0)) ** 2
        x = _smooth_noise(n, rng, 1500) * swell * 0.25
    elif name == "rain":
        x = rng.normal(0, 1, n) * 0.035
        drops = rng.integers(0, n, int(seconds * 30))
        for d in drops:
            x[d:d + 200] += np.exp(-np.arange(min(200, n - d)) / 30) * rng.uniform(0.05, 0.2)
    elif name == "white noise":
        x = rng.normal(0, 1, n) * 0.05
    elif name == "campfire":
        x = _smooth_noise(n, rng, 200) * 0.12
        for c in rng.integers(0, n, int(seconds * 6)):
            x[c:c + 80] += rng.normal(0, 0.4, min(80, n - c)) * np.exp(-np.arange(min(80, n - c)) / 12)
    elif name in ("birdsong", "earth forest"):
        x = _smooth_noise(n, rng, 300) * (0.06 if name == "earth forest" else 0.02)
        for _ in range(int(seconds * (0.8 if name == "birdsong" else 0.4))):
            s = int(rng.uniform(0, seconds - 1) * SR)
            dur = int(rng.uniform(0.08, 0.25) * SR)
            f0, f1 = rng.uniform(2500, 4500), rng.uniform(2000, 5000)
            tt = np.arange(dur) / SR
            chirp = np.sin(2 * np.pi * (f0 * tt + (f1 - f0) * tt ** 2 / (2 * tt[-1]))) * np.hanning(dur) * 0.12
            x[s:s + dur] += chirp[: n - s]
    else:
        raise ValueError(name)
    # gentle fade at the loop seam and normalise
    f = int(0.5 * SR)
    x[:f] *= np.linspace(0, 1, f)
    x[-f:] *= np.linspace(1, 0, f)
    return (x / (np.max(np.abs(x)) + 1e-9) * 0.6).astype(np.float32)


def user_tracks():
    if not MUSIC_DIR.is_dir():
        return {}
    return {p.stem.replace("_", " ").lower(): p for p in sorted(MUSIC_DIR.glob("*.wav"))}


def _load_wav(path):
    with wave.open(str(path), "rb") as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype={1: np.uint8, 2: np.int16, 4: np.int32}[width]).astype(np.float32)
    x = (x - 128) / 128 if width == 1 else x / float(2 ** (8 * width - 1))
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR:                                   # simple resample to the player rate
        x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * SR / sr)), np.arange(len(x)), x).astype(np.float32)
    return x


class MusicPlayer:
    def __init__(self):
        self.cache, self.buf, self.pos = {}, None, 0
        self.current, self.volume, self.error = None, 0.6, None
        self._stream, self._lock = None, threading.Lock()

    def catalog(self):
        return SPACE_TRACKS + NATURE + list(user_tracks())

    def resolve(self, name):
        name = (name or "").lower().strip()
        cat = self.catalog()
        if name in ("", "music", "space music", "space"):
            return SPACE_TRACKS[0]
        return next((c for c in cat if name in c or c in name), None)

    def play(self, name):
        track = self.resolve(name)
        if not track:
            raise ValueError(f"unknown track '{name}'. Try: {', '.join(self.catalog())}")
        threading.Thread(target=self._start, args=(track,), daemon=True).start()
        self.current = track
        return track

    def next(self):
        cat = SPACE_TRACKS + list(user_tracks())
        i = (cat.index(self.current) + 1) % len(cat) if self.current in cat else 0
        return self.play(cat[i])

    def _start(self, track):
        try:
            if track not in self.cache:
                ut = user_tracks()
                self.cache[track] = _load_wav(ut[track]) if track in ut else synth(track)
            with self._lock:
                self.buf, self.pos = self.cache[track], 0
            if self._stream is None:
                import sounddevice as sd
                self._stream = sd.OutputStream(samplerate=SR, channels=1, dtype="float32", callback=self._cb)
                self._stream.start()
            self.error = None
        except Exception as e:                       # no audio device / PortAudio missing
            self.error = f"{e.__class__.__name__}: {e}"

    def _cb(self, out, frames, t, status):
        with self._lock:
            if self.buf is None:
                out[:] = 0
                return
            idx = (self.pos + np.arange(frames)) % len(self.buf)
            out[:, 0] = self.buf[idx] * self.volume
            self.pos = (self.pos + frames) % len(self.buf)

    def stop(self):
        with self._lock:
            self.buf = None
        self.current = None

    def set_volume(self, v):
        self.volume = float(min(1.0, max(0.0, v)))
        return self.volume
