"""Command-line interface:  python -m crew_monitor <command> ..."""
import argparse
import sys
from pathlib import Path

from . import config
from .store import Store
from .fusion import assess
from .interventions import recommend
from .report import print_assessment, print_crew, write_html
from . import selfreport


def _store(args):
    return Store(args.db) if args.db else Store()


def _require(store, aid):
    a = store.astronaut(aid)
    if not a:
        sys.exit(f"Unknown astronaut '{aid}'. Enroll first: python -m crew_monitor enroll {aid} --name ...")
    return a


def _finish(store, ast, feats, kind, note, args):
    if not feats:
        sys.exit("No usable face, voice or posture data was captured - nothing saved.")
    a = assess(feats, store.sessions(ast["id"]))
    a["actions"] = recommend(a, ast["share_with_ground"])
    store.add_session(ast["id"], feats, a, kind=kind, note="")   # free text is not stored
    if args.show_features:
        print("\nFeatures:")
        for k, v in sorted(feats.items()):
            print(f"  {k:22s} {v:10.4f}")
    print_assessment(a, color=sys.stdout.isatty())


def cmd_setup_models(args):
    from .models import model_path
    for k in config.MODELS:
        print(f"{k}: {model_path(k)}")


def cmd_enroll(args):
    s = _store(args)
    s.add_astronaut(args.id, args.name, args.role, args.share)
    print(f"Enrolled {args.id} ({args.name}). The first {config.BASELINE_SESSIONS} check-ins "
          f"build a personal baseline. Ground sharing: {'ON' if args.share else 'OFF'}")


def cmd_consent(args):
    s = _store(args)
    _require(s, args.id)
    s.set_consent(args.id, args.share == "on")
    print(f"Ground sharing for {args.id}: {args.share.upper()}")


def _paused():
    if config.PAUSE_FLAG.exists():
        sys.exit("Monitoring is PAUSED by crew request. Run 'python -m crew_monitor resume' to continue.")


def cmd_checkin(args):
    _paused()
    s = _store(args)
    ast = _require(s, args.id)
    from .capture import live_session
    cam = int(args.camera) if str(args.camera).isdigit() else args.camera
    feats, info = live_session(args.duration, cam, use_mic=not args.no_mic,
                               preview=not args.no_preview)
    if feats is None:
        print("Check-in cancelled. Nothing was saved.")
        return
    note = ""
    if not args.no_survey:
        sf, note = selfreport.ask()
        feats.update(sf)
    _finish(s, ast, feats, "checkin", note, args)


def cmd_analyze(args):
    _paused()
    s = _store(args)
    ast = _require(s, args.id)
    from .capture import file_session
    feats = file_session(args.video, args.audio, not args.no_face, not args.no_pose)
    feats.update(selfreport.to_features(args.mood, args.stress, args.sleep, args.note or ""))
    _finish(s, ast, feats, "file", args.note or "", args)


def cmd_simulate(args):
    from . import simulate
    s = _store(args)
    print(f"Simulating a {args.days}-day mission for a crew of 4...")
    simulate.run(s, days=args.days, seed=args.seed)
    print_crew(s, color=sys.stdout.isatty())
    out = write_html(s, args.html)
    print(f"\nDashboard written to {Path(out).resolve()}")


def cmd_report(args):
    s = _store(args)
    if args.id:
        _require(s, args.id)
        for sess in s.sessions(args.id, limit=args.last):
            print(f"\n=== {args.id} session {sess['id']} ({sess['kind']}) ===")
            print_assessment(sess["assessment"], color=sys.stdout.isatty())
    else:
        print_crew(s, color=sys.stdout.isatty())
    if args.html:
        print(f"\nDashboard written to {Path(write_html(s, args.html, args.ground)).resolve()}")


def cmd_pause(args):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.PAUSE_FLAG.write_text("paused")
    print("Monitoring paused. No check-ins will run until 'resume'.")


def cmd_resume(args):
    config.PAUSE_FLAG.unlink(missing_ok=True)
    print("Monitoring resumed.")


def cmd_forget(args):
    s = _store(args)
    _require(s, args.id)
    if args.yes or input(f"Permanently delete ALL data for {args.id}? [y/N] ").lower() == "y":
        s.delete_astronaut_data(args.id)
        print("Deleted.")


def main(argv=None):
    p = argparse.ArgumentParser(prog="crew_monitor",
                                description="Lunar habitat multimodal crew wellbeing monitor (prototype).")
    p.add_argument("--db", help="database file (default ~/.lunar_crew_monitor/crew.db)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup-models", help="download MediaPipe face/pose models").set_defaults(fn=cmd_setup_models)

    e = sub.add_parser("enroll", help="register an astronaut")
    e.add_argument("id"); e.add_argument("--name", required=True); e.add_argument("--role", default="")
    e.add_argument("--share", action="store_true", help="consent to share summaries with ground")
    e.set_defaults(fn=cmd_enroll)

    c = sub.add_parser("consent", help="turn ground sharing on/off")
    c.add_argument("id"); c.add_argument("share", choices=["on", "off"]); c.set_defaults(fn=cmd_consent)

    for name, fn, hlp in (("checkin", cmd_checkin, "live camera + microphone check-in"),
                          ("analyze", cmd_analyze, "analyze a recorded video and/or WAV file")):
        q = sub.add_parser(name, help=hlp)
        q.add_argument("id")
        q.add_argument("--show-features", action="store_true")
        q.set_defaults(fn=fn)
        if name == "checkin":
            q.add_argument("--duration", type=int, default=30)
            q.add_argument("--camera", default="0", help="camera index, or a video file for testing")
            q.add_argument("--no-mic", action="store_true")
            q.add_argument("--no-preview", action="store_true")
            q.add_argument("--no-survey", action="store_true")
        else:
            q.add_argument("--video"); q.add_argument("--audio")
            q.add_argument("--no-face", action="store_true"); q.add_argument("--no-pose", action="store_true")
            q.add_argument("--mood", type=float); q.add_argument("--stress", type=float)
            q.add_argument("--sleep", type=float); q.add_argument("--note")

    sm = sub.add_parser("simulate", help="run a synthetic crew mission (no hardware needed)")
    sm.add_argument("--days", type=int, default=21); sm.add_argument("--seed", type=int, default=7)
    sm.add_argument("--html", default="crew_dashboard.html"); sm.set_defaults(fn=cmd_simulate)

    r = sub.add_parser("report", help="crew summary, or one astronaut's sessions")
    r.add_argument("id", nargs="?"); r.add_argument("--last", type=int, default=3)
    r.add_argument("--html"); r.add_argument("--ground", action="store_true",
                                             help="HTML shows only astronauts who consented")
    r.set_defaults(fn=cmd_report)

    sub.add_parser("pause", help="crew privacy pause").set_defaults(fn=cmd_pause)
    sub.add_parser("resume", help="resume monitoring").set_defaults(fn=cmd_resume)
    f = sub.add_parser("forget", help="delete all of an astronaut's data")
    f.add_argument("id"); f.add_argument("--yes", action="store_true"); f.set_defaults(fn=cmd_forget)

    args = p.parse_args(argv)
    if args.db and args.db != ":memory:":
        Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    args.fn(args)


if __name__ == "__main__":
    main()
