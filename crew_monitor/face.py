"""Facial expression features from MediaPipe Face Landmarker blendshapes.

Blendshapes are Action-Unit-like muscle activations (0..1), e.g.
mouthSmileLeft ~ AU12, browDownLeft ~ AU4, eyeBlinkLeft ~ AU45.
Only these numbers are kept; video frames are never stored.
"""
import numpy as np

BLINK_ON, BLINK_OFF = 0.5, 0.35      # hysteresis for blink detection
CLOSED = 0.6                          # eye "mostly closed" for PERCLOS
SMILE_ON = 0.35


class FaceAnalyzer:
    def __init__(self, model_file):
        from mediapipe.tasks.python import vision, BaseOptions
        opts = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_file)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1, output_face_blendshapes=True)
        self._lm = vision.FaceLandmarker.create_from_options(opts)

    def process(self, mp_image, ts_ms: int):
        """Return a dict of blendshape scores for the first face, or None."""
        res = self._lm.detect_for_video(mp_image, ts_ms)
        if not res.face_blendshapes:
            return None
        bs = {c.category_name: c.score for c in res.face_blendshapes[0]}
        pts = res.face_landmarks[0]
        return {"bs": bs, "landmarks": [(p.x, p.y) for p in pts]}

    def close(self):
        self._lm.close()


class FaceAggregator:
    """Accumulates per-frame face results into session-level features."""

    def __init__(self):
        self.frames = 0
        self.t, self.eye, self.smile, self.brow, self.gaze_down, self.expr = [], [], [], [], [], []

    def add(self, result, t_s: float):
        self.frames += 1
        if result is None:
            return
        b = result["bs"]
        self.t.append(t_s)
        self.eye.append((b.get("eyeBlinkLeft", 0) + b.get("eyeBlinkRight", 0)) / 2)
        self.smile.append((b.get("mouthSmileLeft", 0) + b.get("mouthSmileRight", 0)) / 2)
        self.brow.append((b.get("browDownLeft", 0) + b.get("browDownRight", 0)) / 2)
        self.gaze_down.append((b.get("eyeLookDownLeft", 0) + b.get("eyeLookDownRight", 0)) / 2)
        # Expressivity: overall facial muscle activity, excluding eye blinks/gaze.
        keys = [k for k in b if not k.startswith(("eyeBlink", "eyeLook", "_neutral"))]
        self.expr.append([b[k] for k in sorted(keys)])

    def features(self):
        n = len(self.t)
        if n < 10:
            return {}
        eye = np.array(self.eye)
        duration_min = max((self.t[-1] - self.t[0]) / 60.0, 1e-6)
        blinks, closed = 0, False
        for v in eye:
            if not closed and v > BLINK_ON:
                blinks, closed = blinks + 1, True
            elif closed and v < BLINK_OFF:
                closed = False
        smile = np.array(self.smile)
        expr = np.array(self.expr)
        return {
            "face_present_frac": n / max(self.frames, 1),
            "face_blink_rate": blinks / duration_min,           # blinks per minute
            "face_perclos": float(np.mean(eye > CLOSED)),       # drowsiness
            "face_smile_mean": float(smile.mean()),
            "face_smile_frac": float(np.mean(smile > SMILE_ON)),
            "face_brow_down": float(np.mean(self.brow)),        # tension / frowning
            "face_gaze_down": float(np.mean(self.gaze_down)),
            "face_expressivity": float(expr.std(axis=0).mean()),  # flat affect -> low
        }
