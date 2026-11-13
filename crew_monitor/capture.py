"""Run a check-in session from a live camera + microphone, or from recorded
files. Frames and audio are processed in memory and then discarded."""
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

# Quiet MediaPipe/TFLite console logging
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

from .face import FaceAnalyzer, FaceAggregator
from .posture import PoseAnalyzer, PoseAggregator
from . import voice
from .models import model_path

PROMPTS = [
    "How did you sleep, and what is on your schedule today?",
    "Tell me about the best and the hardest part of yesterday.",
    "What are you looking forward to this week?",
    "How is the crew getting along right now?",
    "Describe what you can see out of the habitat window today.",
]
MAX_FPS = 15


class VisionPipeline:
    def __init__(self, use_face=True, use_pose=True):
        self.face = FaceAnalyzer(model_path("face")) if use_face else None
        self.pose = PoseAnalyzer(model_path("pose")) if use_pose else None
        self.face_agg, self.pose_agg = FaceAggregator(), PoseAggregator()
        self.last_face = self.last_pose = None

    def process(self, frame_bgr, t_s):
        import cv2
        import mediapipe as mp
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts = int(t_s * 1000)
        if self.face:
            self.last_face = self.face.process(img, ts)
            self.face_agg.add(self.last_face, t_s)
        if self.pose:
            self.last_pose = self.pose.process(img, ts)
            self.pose_agg.add(self.last_pose, t_s)

    def draw(self, frame, elapsed, duration, prompt):
        import cv2
        h, w = frame.shape[:2]
        if self.last_face:
            for x, y in self.last_face["landmarks"][::12]:
                cv2.circle(frame, (int(x * w), int(y * h)), 1, (0, 255, 255), -1)
        if self.last_pose:
            for x, y, v in self.last_pose[:25]:
                if v > 0.5:
                    cv2.circle(frame, (int(x * w), int(y * h)), 4, (0, 200, 0), -1)
        cv2.rectangle(frame, (0, 0), (w, 60), (20, 20, 20), -1)
        cv2.putText(frame, prompt[:70], (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        status = (f"REC {elapsed:4.0f}/{duration}s  face:{'Y' if self.last_face else '-'}  "
                  f"pose:{'Y' if self.last_pose else '-'}   [q] finish   [x] cancel (nothing saved)")
        cv2.putText(frame, status, (10, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 1)
        cv2.circle(frame, (w - 20, 30), 8, (0, 0, 255), -1)   # visible "monitoring on" light

    def features(self):
        f = {}
        f.update(self.face_agg.features())
        f.update(self.pose_agg.features())
        return f

    def close(self):
        for a in (self.face, self.pose):
            if a:
                a.close()


def live_session(duration=30, camera=0, use_mic=True, preview=True, prompt=None):
    """Returns (features, info) or (None, info) if cancelled."""
    import cv2
    prompt = prompt or PROMPTS[int(time.time() // 86400) % len(PROMPTS)]
    print(f"\nCheck-in prompt: \"{prompt}\"\nPlease answer out loud while facing the camera "
          f"(sit so your shoulders are visible). Recording {duration}s...")
    cap = cv2.VideoCapture(camera)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera {camera}")
    vp = VisionPipeline()
    rec = voice.MicRecorder() if use_mic else None
    cancelled = False
    try:
        if rec:
            rec.__enter__()
        is_file = isinstance(camera, str)            # video file stands in for a camera
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        t0, last, idx = time.time(), -1.0, 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            el = idx / fps if is_file else time.time() - t0
            idx += 1
            if el >= duration:
                break
            if el - last < 1 / MAX_FPS:
                continue
            last = el
            vp.process(frame, el)
            if preview:
                vp.draw(frame, el, duration, prompt)
                cv2.imshow("Lunar Crew Monitor - check-in", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("x"):
                    cancelled = True
                    break
    finally:
        if rec:
            rec.__exit__(None, None, None)
        cap.release()
        if preview:
            cv2.destroyAllWindows()
        vp.close()
    if cancelled:
        return None, {"cancelled": True}
    feats = vp.features()
    if rec:
        x, sr = rec.audio()
        feats.update(voice.extract_features(x, sr))
    return feats, {"prompt": prompt}


def _extract_audio(video):
    if not shutil.which("ffmpeg"):
        return None
    out = Path(tempfile.mkstemp(suffix=".wav")[1])
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vn",
                        "-ac", "1", "-ar", "16000", str(out)])
    return out if r.returncode == 0 and out.stat().st_size > 1000 else None


def file_session(video=None, audio=None, use_face=True, use_pose=True):
    feats, tmp = {}, None
    if video:
        import cv2
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video {video}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, round(fps / MAX_FPS))
        vp = VisionPipeline(use_face, use_pose)
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % step == 0:
                vp.process(frame, i / fps)
            i += 1
        cap.release()
        vp.close()
        feats.update(vp.features())
        if audio is None:
            audio = tmp = _extract_audio(video)
    if audio:
        x, sr = voice.load_wav(audio)
        feats.update(voice.extract_features(x, sr))
    if tmp:
        Path(tmp).unlink(missing_ok=True)   # never keep raw audio
    return feats
