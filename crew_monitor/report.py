"""Terminal and HTML reporting."""
import datetime as dt
import html
from .fusion import LABELS

COLORS = {"GREEN": "\033[92m", "YELLOW": "\033[93m", "ORANGE": "\033[91m", "CALIBRATING": "\033[96m"}
RESET = "\033[0m"


def _day(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def print_assessment(a, color=True):
    st = a["status"]
    c, r = (COLORS.get(st, ""), RESET) if color else ("", "")
    print(f"\nStatus: {c}{st}{r}")
    if st == "CALIBRATING":
        print("  " + a["message"])
        return
    print(f"  Channels used: {', '.join(a.get('channels_used', []))}")
    for name, d in a["indicators"].items():
        chans = "  ".join(f"{k}:{v:+.1f}" for k, v in d["channels"].items())
        drivers = ", ".join(f"{f}({z:+.1f})" for f, z in d["drivers"] if z > 0.5) or "-"
        print(f"  {LABELS[name]:9s} {d['score']:+5.2f}  [{d['level']:7s}] trend {d['trend']:+.2f} | {chans}")
        print(f"            main drivers: {drivers}")
    for fl in a["flags"]:
        print(f"  ! {fl}")
    if a.get("actions"):
        print("  Suggested habitat responses:")
        for act in a["actions"]:
            print(f"    - {act}")


def print_crew(store, color=True):
    print(f"\n{'ID':4s} {'Name':16s} {'Sessions':>8s}  {'Status':12s} Fatigue  Stress  LowMood  Ground-share")
    for ast in store.astronauts():
        ss = store.sessions(ast["id"])
        last = ss[-1]["assessment"] if ss else {"status": "-", "indicators": {}}
        st = last["status"]
        c, r = (COLORS.get(st, ""), RESET) if color else ("", "")
        sc = [f"{last['indicators'][k]['score']:+6.2f}" if k in last["indicators"] else "     -"
              for k in ("fatigue", "stress", "low_mood")]
        print(f"{ast['id']:4s} {ast['name'][:16]:16s} {len(ss):8d}  {c}{st:12s}{r} {sc[0]}  {sc[1]}  {sc[2]}   "
              f"{'yes' if ast['share_with_ground'] else 'no'}")


def _svg(series, w=560, h=150):
    """series: {label: [(i, score), ...]} -> small inline SVG line chart."""
    colors = {"fatigue": "#e8a33d", "stress": "#d9534f", "low_mood": "#5b7fde"}
    n = max((len(v) for v in series.values()), default=1)
    x = lambda i: 30 + (w - 40) * i / max(n - 1, 1)
    y = lambda s: h / 2 - max(-3, min(3, s)) * (h / 2 - 10) / 3
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img">',
             f'<rect x="30" y="{y(3)}" width="{w-40}" height="{y(1.0)-y(3)}" fill="#ff000010"/>',
             f'<line x1="30" x2="{w-10}" y1="{y(0)}" y2="{y(0)}" stroke="#8888"/>',
             f'<line x1="30" x2="{w-10}" y1="{y(1)}" y2="{y(1)}" stroke="#c008" stroke-dasharray="4"/>',
             f'<text x="2" y="{y(1)+4}" font-size="10" fill="currentColor">+1</text>',
             f'<text x="2" y="{y(0)+4}" font-size="10" fill="currentColor">0</text>']
    for name, pts in series.items():
        if pts:
            path = " ".join(f"{x(i):.1f},{y(s):.1f}" for i, s in pts)
            parts.append(f'<polyline points="{path}" fill="none" stroke="{colors[name]}" stroke-width="2"/>')
    parts.append("</svg>")
    return "".join(parts)


def write_html(store, path, ground_view=False):
    rows = []
    for ast in store.astronauts():
        if ground_view and not ast["share_with_ground"]:
            rows.append(f"<section><h2>{html.escape(ast['id'])} - {html.escape(ast['name'])}</h2>"
                        "<p class=muted>Not shared: astronaut has not consented to ground reporting.</p></section>")
            continue
        ss = store.sessions(ast["id"])
        series = {k: [] for k in LABELS}
        for i, s in enumerate(ss):
            for k, d in s["assessment"].get("indicators", {}).items():
                series[k].append((i, d["score"]))
        last = ss[-1]["assessment"] if ss else {"status": "-", "flags": [], "actions": []}
        flags = "".join(f"<li>{html.escape(f)}</li>" for f in last.get("flags", []))
        acts = "".join(f"<li>{html.escape(a)}</li>" for a in last.get("actions", []))
        rows.append(f"""<section><h2>{html.escape(ast['id'])} - {html.escape(ast['name'])}
<span class="badge {last['status']}">{last['status']}</span></h2>
<p class=muted>{html.escape(ast['role'])} &middot; {len(ss)} sessions
{('&middot; last ' + _day(ss[-1]['ts'])) if ss else ''}</p>
{_svg(series)}
<p class=legend><b style="color:#e8a33d">Fatigue</b> <b style="color:#d9534f">Stress</b>
<b style="color:#5b7fde">Low mood</b> &mdash; score vs. personal baseline (z); shaded = above watch level</p>
{f'<h3>Flags</h3><ul>{flags}</ul>' if flags else ''}
{f'<h3>Suggested responses</h3><ul>{acts}</ul>' if acts else ''}</section>""")
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Crew Wellbeing Dashboard</title><style>
:root{{--bg:#f6f7f9;--card:#fff;--fg:#1d2330;--muted:#6b7280}}
@media (prefers-color-scheme: dark){{:root{{--bg:#0f1420;--card:#182032;--fg:#e6e9ef;--muted:#9aa3b2}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0;padding:16px}}
main{{max-width:980px;margin:auto;display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}}
section{{background:var(--card);border-radius:12px;padding:16px;box-shadow:0 1px 3px #0002}}
h1{{max-width:980px;margin:8px auto}} h2{{font-size:18px;margin:0}} h3{{font-size:14px;margin:12px 0 4px}}
.muted,.legend{{color:var(--muted);font-size:13px}} ul{{margin:0;padding-left:18px;font-size:13px}}
.badge{{font-size:12px;padding:2px 8px;border-radius:10px;margin-left:6px;color:#000}}
.GREEN{{background:#7bd88f}}.YELLOW{{background:#f5d76e}}.ORANGE{{background:#f39c6b}}.CALIBRATING{{background:#8fd3f4}}
</style></head><body><h1>Crew Wellbeing Dashboard {'(ground view)' if ground_view else '(habitat view)'}</h1>
<p class=muted style="max-width:980px;margin:0 auto 12px">Generated {_day(dt.datetime.now().timestamp())}.
Signals are prompts for supportive check-ins, not diagnoses. Raw video/audio is never stored.</p>
<main>{''.join(rows)}</main></body></html>"""
    with open(path, "w") as fh:
        fh.write(doc)
    return path
