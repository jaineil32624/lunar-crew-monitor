"""Posture and movement features from MediaPipe Pose Landmarker.

Angles are measured in the image plane. Because lunar gravity (1/6 g) changes
how people stand and move, every feature is compared with the astronaut's OWN
baseline recorded in the habitat, never with Earth population norms.
"""
import math
import numpy as np

# MediaPipe pose landmark indices
NOSE, L_EAR, R_EAR, L_SH, R_SH, L_WR, R_WR, L_HIP, R_HIP = 0, 7, 8, 11, 12, 15, 16, 23, 24
VIS = 0.5


def _mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _angle_from_vertical(top, bottom):
    """Angle (deg) of the segment bottom->top from straight up (image y grows down)."""
    dx, dy = top[0] - bottom[0], bottom[1] - top[1]
    return abs(math.degrees(math.atan2(dx, dy)))


class PoseAnalyzer:
    def __init__(self, model_file):
        from mediapipe.tasks.python import vision, BaseOptions
        opts = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_file)),
            running_mode=vision.RunningMode.VIDEO, num_poses=1)
        self._lm = vision.PoseLandmarker.create_from_options(opts)

    def process(self, mp_image, ts_ms: int):
        res = self._lm.detect_for_video(mp_image, ts_ms)
        if not res.pose_landmarks:
            return None
        lms = res.pose_landmarks[0]
        return [(p.x, p.y, p.visibility if p.visibility is not None else 1.0) for p in lms]

    def close(self):
        self._lm.close()


class PoseAggregator:
    def __init__(self):
        self.frames = 0
        self.neck, self.trunk, self.body_speed, self.hand_speed = [], [], [], []
        self._prev = None

    def add(self, lms, t_s: float):
        self.frames += 1
        if lms is None:
            self._prev = None
            return
        ok = lambda *idx: all(lms[i][2] > VIS for i in idx)
        if ok(L_SH, R_SH, L_EAR, R_EAR):
            sh = _mid(lms[L_SH], lms[R_SH])
            ear = _mid(lms[L_EAR], lms[R_EAR])
            # Head-drop angle (front camera): the smaller the vertical gap between
            # ears and shoulders relative to shoulder width, the more the head
            # hangs forward/down. Scale-free, so distance to camera doesn't matter.
            half_width = max(abs(lms[L_SH][0] - lms[R_SH][0]) / 2, 1e-3)
            self.neck.append(90 - math.degrees(math.atan2(sh[1] - ear[1], half_width)))
        if ok(L_SH, R_SH, L_HIP, R_HIP):
            self.trunk.append(_angle_from_vertical(_mid(lms[L_SH], lms[R_SH]),
                                                   _mid(lms[L_HIP], lms[R_HIP])))
        if self._prev is not None:
            pt, prev = self._prev
            dt = max(t_s - pt, 1e-3)
            body = [i for i in (NOSE, L_SH, R_SH, L_HIP, R_HIP) if lms[i][2] > VIS and prev[i][2] > VIS]
            hands = [i for i in (L_WR, R_WR) if lms[i][2] > VIS and prev[i][2] > VIS]
            if body:
                self.body_speed.append(np.mean([math.dist(lms[i][:2], prev[i][:2]) for i in body]) / dt)
            if hands:
                self.hand_speed.append(np.mean([math.dist(lms[i][:2], prev[i][:2]) for i in hands]) / dt)
        self._prev = (t_s, lms)

    def features(self):
        f = {}
        if len(self.neck) >= 10:
            f["posture_neck_flexion"] = float(np.median(self.neck))   # higher = head dropped
        if len(self.trunk) >= 10:
            f["posture_trunk_lean"] = float(np.median(self.trunk))    # higher = slumped/leaning
        if len(self.body_speed) >= 10:
            s = np.array(self.body_speed)
            f["posture_movement"] = float(s.mean())                   # overall activity
            f["posture_stillness"] = float(np.mean(s < 0.01))         # frozen / withdrawn
        if len(self.hand_speed) >= 10:
            # Fidgeting: jittery, irregular hand motion
            f["posture_fidget"] = float(np.std(np.diff(self.hand_speed)))
        return f
