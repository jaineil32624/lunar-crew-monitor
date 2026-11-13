"""Optional self-report + short text note. The tiny lexicon below is a stand-in:
plug your fine-tuned BERT/RoBERTa mood model into `text_sentiment`."""
import re

POS = set("good great fine happy calm rested relaxed excited proud strong energized okay ok "
          "productive fun enjoyed love grateful better".split())
NEG = set("tired exhausted sad lonely anxious stressed worried angry frustrated bored "
          "homesick drained sick hopeless overwhelmed irritable cant tense hurt bad worse".split())
NEGATORS = {"not", "no", "never", "hardly", "dont", "isnt", "wasnt"}


def text_sentiment(text: str) -> float:
    """Returns -1 (negative) .. +1 (positive)."""
    words = re.findall(r"[a-z']+", text.lower().replace("'", ""))
    score, hits = 0, 0
    for i, w in enumerate(words):
        s = 1 if w in POS else -1 if w in NEG else 0
        if s and i and words[i - 1] in NEGATORS:
            s = -s
        if s:
            score, hits = score + s, hits + 1
    return score / hits if hits else 0.0


def to_features(mood=None, stress=None, sleep_h=None, note=""):
    f = {}
    if mood is not None:
        f["self_mood"] = float(mood)
    if stress is not None:
        f["self_stress"] = float(stress)
    if sleep_h is not None:
        f["self_sleep_h"] = float(sleep_h)
    if note.strip():
        f["self_sentiment"] = text_sentiment(note)
    return f


def ask(input_fn=input):
    def num(prompt, lo, hi):
        while True:
            raw = input_fn(prompt).strip()
            if not raw:
                return None
            try:
                v = float(raw)
                if lo <= v <= hi:
                    return v
            except ValueError:
                pass
            print(f"  please enter {lo}-{hi}, or press Enter to skip")
    print("\nQuick self-report (press Enter to skip any question)")
    mood = num("  Mood today, 1 (very low) - 10 (great): ", 1, 10)
    stress = num("  Stress, 1 (none) - 10 (extreme): ", 1, 10)
    sleep = num("  Hours slept: ", 0, 16)
    note = input_fn("  Anything on your mind? (optional): ")
    return to_features(mood, stress, sleep, note), note
