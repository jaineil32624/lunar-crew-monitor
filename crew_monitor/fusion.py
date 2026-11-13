"""Multimodal fusion: compare today's features with the astronaut's personal
baseline, build fatigue / stress / low-mood indicators, check agreement across
channels, detect sustained trends and self-report vs. behaviour mismatch.

Outputs are wellbeing *signals* to prompt a supportive check-in, never a diagnosis.
"""
import numpy as np
from . import config

CHANNELS = ("face", "voice", "posture", "self")
_SCORED = {f for spec in config.INDICATORS.values() for f in spec}
LABELS = {"fatigue": "Fatigue", "stress": "Stress", "low_mood": "Low mood"}


def channel_of(feature):
    return feature.split("_", 1)[0]


def build_baseline(history, n=None):
    """history: earlier feature dicts (oldest first) -> {feat: (median, scale)}.
    Each feature uses the first `n` sessions in which it was measured, so a channel
    added later (e.g. a microphone plugged in on day 8) still gets its own baseline."""
    n = n or config.BASELINE_SESSIONS
    cols = {}
    for f in history:
        for k, v in f.items():
            if len(cols.setdefault(k, [])) < n:
                cols[k].append(v)
    base = {}
    for k, vals in cols.items():
        if len(vals) < n:
            continue
        a = np.array(vals, dtype=float)
        med = float(np.median(a))
        mad = float(np.median(np.abs(a - med))) * 1.4826
        # floor = fixed minimum OR 5% of the typical value, whichever is larger
        base[k] = (med, max(mad, config.SCALE_FLOOR.get(k, 1e-6), config.REL_FLOOR.get(k, 0.05) * abs(med)))
    return base


def zscores(features, baseline):
    return {k: float(np.clip((v - baseline[k][0]) / baseline[k][1], -4, 4))
            for k, v in features.items() if k in baseline}


def indicator_scores(z):
    out = {}
    for name, spec in config.INDICATORS.items():
        per_ch = {}
        contrib = []
        for feat, sign in spec.items():
            if feat in z:
                per_ch.setdefault(channel_of(feat), []).append(sign * z[feat])
                contrib.append((feat, round(sign * z[feat], 2)))
        ch_scores = {c: float(np.mean(v)) for c, v in per_ch.items()}
        score = float(np.mean(list(ch_scores.values()))) if ch_scores else 0.0
        agreeing = [c for c, s in ch_scores.items() if s >= config.CHANNEL_ACTIVE_THRESHOLD]
        out[name] = {
            "score": round(score, 2),
            "channels": {c: round(s, 2) for c, s in ch_scores.items()},
            "agreeing": agreeing,
            "drivers": sorted(contrib, key=lambda t: -t[1])[:3],
        }
    return out


def assess(features, past_sessions):
    """features: today's merged feature dict. past_sessions: earlier sessions (oldest first)."""
    past_feats = [s["features"] for s in past_sessions]
    if len(past_feats) < config.BASELINE_SESSIONS:
        return {"status": "CALIBRATING",
                "message": f"Learning personal baseline ({len(past_feats) + 1}/{config.BASELINE_SESSIONS}).",
                "indicators": {}, "flags": []}

    base = build_baseline(past_feats)
    z = zscores(features, base)
    pending = sorted({channel_of(k) for k in features if k not in base and k in _SCORED} -
                     {channel_of(k) for k in z})
    ind = indicator_scores(z)

    # Sustained trend: average indicator over the recent window (including today)
    recent = [s["assessment"].get("indicators", {}) for s in past_sessions[-(config.TREND_WINDOW - 1):]]
    flags, levels = [], {}
    for name, d in ind.items():
        hist = [r[name]["score"] for r in recent if name in r] + [d["score"]]
        d["trend"] = round(float(np.mean(hist)), 2)
        # consecutive sessions (ending today) above the watch level
        streak = 0
        for sc in reversed(hist):
            if sc < config.WATCH_THRESHOLD:
                break
            streak += 1
        d["streak"] = streak
        if d["score"] >= config.CONCERN_THRESHOLD and len(d["agreeing"]) >= 2:
            levels[name] = "concern"
        elif streak >= 3:
            levels[name] = "concern"
            flags.append(f"{LABELS[name]} above personal baseline for {streak} sessions in a row.")
        elif d["score"] >= config.WATCH_THRESHOLD:
            levels[name] = "watch"
        else:
            levels[name] = "ok"
        d["level"] = levels[name]

    # Self-report says fine, but behaviour (face/voice/posture) says otherwise
    for name in ("low_mood", "stress"):
        ch = ind[name]["channels"]
        objective = [ch[c] for c in ("face", "voice", "posture") if c in ch]
        if "self" in ch and objective:
            obj = float(np.mean(objective))
            if (ch["self"] < config.WATCH_THRESHOLD * 0.75 and obj >= config.CONCERN_THRESHOLD - 0.25
                    and obj - ch["self"] >= 1.5):
                flags.append(f"Self-report looks fine but face/voice/posture suggest "
                             f"{LABELS[name].lower()} (behaviour {obj:+.1f}). A friendly check-in is suggested.")

    status = ("ORANGE" if "concern" in levels.values() else
              "YELLOW" if "watch" in levels.values() or flags else "GREEN")
    if pending:
        flags.append(f"Still learning baseline for: {', '.join(pending)} (not scored yet).")
    return {"status": status, "indicators": ind, "flags": flags,
            "channels_used": sorted({channel_of(k) for k in z})}
