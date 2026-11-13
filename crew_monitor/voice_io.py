"""Voice chat: microphone -> text (speech recognition) and text -> speech.

Speech-to-text uses the SpeechRecognition package. By default it uses Google's
free web recognizer (needs internet). For a fully offline habitat, install
`vosk` and set SELENE_STT=vosk with a downloaded model (see README).
Text-to-speech uses pyttsx3, which is offline.
"""
import os
import queue
import threading
import numpy as np

SR = 16000


def record_utterance(max_s=8.0, silence_s=1.0, start_timeout_s=5.0):
    """Record from the mic until the speaker stops. Returns int16 numpy array or None."""
    import sounddevice as sd
    block = int(SR * 0.05)
    chunks, started, quiet, waited = [], False, 0.0, 0.0
    noise = None
    with sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=block) as stream:
        while True:
            data, _ = stream.read(block)
            x = data[:, 0].astype(np.float32)
            level = float(np.sqrt(np.mean(x ** 2)) + 1e-6)
            noise = level if noise is None else min(noise * 1.01, 0.95 * noise + 0.05 * level) if not started else noise
            loud = level > max(noise * 3.0, 300)
            if not started:
                waited += 0.05
                if loud:
                    started = True
                elif waited > start_timeout_s:
                    return None
            if started:
                chunks.append(data[:, 0].copy())
                quiet = 0.0 if loud else quiet + 0.05
                if quiet >= silence_s or len(chunks) * 0.05 >= max_s:
                    break
    return np.concatenate(chunks) if chunks else None


def transcribe(audio_int16):
    import speech_recognition as sr
    data = sr.AudioData(audio_int16.tobytes(), SR, 2)
    r = sr.Recognizer()
    if os.environ.get("SELENE_STT") == "vosk":
        return r.recognize_vosk(data)
    return r.recognize_google(data)


def listen():
    """Record and transcribe one utterance. Returns text or raises RuntimeError with a friendly message."""
    try:
        audio = record_utterance()
    except Exception as e:
        raise RuntimeError(f"Microphone unavailable ({e.__class__.__name__}). Type your message instead.")
    if audio is None:
        raise RuntimeError("I didn't hear anything.")
    try:
        return transcribe(audio)
    except Exception as e:
        name = e.__class__.__name__
        if name == "UnknownValueError":
            raise RuntimeError("Sorry, I couldn't make that out.")
        raise RuntimeError(f"Speech recognition unavailable ({name}). Check internet, or type instead.")


class Speaker:
    """Speaks replies on a background thread so the window never freezes."""

    def __init__(self):
        self.q = queue.Queue()
        self.enabled = True
        self.available = True
        self.on_start = self.on_end = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
        except Exception:
            self.available = False
            return
        while True:
            text = self.q.get()
            if self.on_start:
                self.on_start()
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass
            if self.on_end:
                self.on_end()

    def say(self, text):
        if self.enabled and self.available:
            self.q.put(text)


WAKE_WORDS = ("hey selene", "hi selene", "okay selene", "ok selene", "selene")


def strip_wake_word(text):
    """Returns the command after the wake word, '' if only the wake word, or None if absent."""
    t = text.lower().strip()
    for w in WAKE_WORDS:
        if t.startswith(w):
            return text[len(w):].lstrip(" ,.!?")
    return None
