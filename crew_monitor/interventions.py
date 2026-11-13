"""Map assessments to habitat responses (lighting, sound, schedule, people).
In the full habitat these would be sent to the smart-building controller;
here they are returned as a list of actions."""

ACTIONS = {
    "fatigue": {
        "watch": ["Lighting: raise to 5000-6500 K, +20% brightness for 30 min (alertness).",
                  "Suggest a 10-minute movement break / treadmill session."],
        "concern": ["Lighting: daytime blue-enriched profile; schedule dim warm light 2 h before sleep.",
                    "Recommend postponing EVA or robotic-arm tasks until rested (crew decides).",
                    "Suggest a 20-minute nap window in the next schedule gap."],
    },
    "stress": {
        "watch": ["Soundscape: calm Earth nature audio in work area.",
                  "Companion: offer a 3-minute guided breathing exercise (4-7-8)."],
        "concern": ["Lighting: warm 3000 K, reduce alarm/notification volume where safe.",
                    "Companion: offer private sanctuary-alcove time and a VR relaxation scene.",
                    "Suggest reviewing today's workload with the commander."],
    },
    "low_mood": {
        "watch": ["Virtual window: show Earth view / personal photos.",
                  "Companion: open a short, friendly conversation about the day."],
        "concern": ["Suggest a shared crew activity (meal, movie, game) today.",
                    "Offer to schedule a private video call with family/friends.",
                    "Offer a private conference with the flight psychologist."],
    },
}


def recommend(assessment, share_with_ground=False):
    acts = []
    for name, d in assessment.get("indicators", {}).items():
        acts += ACTIONS[name].get(d.get("level"), [])
    if assessment.get("status") == "ORANGE":
        acts.append("Ground: summary sent to flight surgeon (consented)." if share_with_ground
                    else "Ground: NOT notified - astronaut has not consented. Astronaut sees this first.")
    return acts
