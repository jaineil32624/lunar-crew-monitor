"""SELENE AI Dashboard - CustomTkinter desktop app.

    python -m crew_monitor dashboard --data path/to/your_simulation_output.csv
"""
import datetime as dt
import math
import queue
import threading
import time
import tkinter as tk

import customtkinter as ctk
from PIL import Image

from . import logo, voice_io
from .assistant import Assistant, NAME
from .context import DashboardContext
from .habitat import LIGHTING, SOUNDSCAPES

LOGO = 96                      # header logo size (px)
BG, PANEL, PANEL2, BORDER = "#0B1020", "#121A2E", "#19233D", "#26314F"
TEXT, MUTED, ACCENT, CYAN, PINK = "#E8ECF6", "#8C97B2", "#7B61FF", "#3DDCFF", "#FF5FD2"
LEVEL = {"GREEN": "#3DDC97", "YELLOW": "#F5C04E", "ORANGE": "#FF8A4C", "RED": "#FF4D6A",
         "CALIBRATING": "#3DDCFF", "NO CHECK-IN": "#8C97B2", "NO DATA": "#8C97B2"}
LIGHT_COLOR = {"day": "#DDE8FF", "focus": "#FFF4E0", "relax": "#FFC27A", "evening": "#FFAA5C",
               "night": "#FF6A3D", "sleep": "#2A2F3F"}
QUICK = [("How am I doing?", "How am I doing today?"), ("Start check-in", "Start my check-in"),
         ("Breathing exercise", "Start a breathing exercise"), ("I can't sleep", "I can't sleep"),
         ("Log 250 ml water", "I drank 250 ml of water"), ("Relax lighting", "Set lights to relax mode"),
         ("Radiation dose", "What's my radiation dose?"), ("Crew status", "Crew status"), ("Help", "Help")]


def short_name(full):
    """'Dr. Amara Okafor' -> 'Dr. Okafor', 'Amara Okafor' -> 'Amara'."""
    parts = (full or "crew").split()
    if parts[0].endswith(".") and len(parts) > 1:
        return f"{parts[0]} {parts[-1]}"
    return parts[0]


def autowrap(label, container, pad=8):
    container.bind("<Configure>", lambda e: label.configure(wraplength=max(120, e.width - pad)), add="+")


def font(size=13, weight="normal"):
    return ctk.CTkFont(size=size, weight=weight)


class Card(ctk.CTkFrame):
    def __init__(self, master, title, **kw):
        super().__init__(master, fg_color=PANEL, corner_radius=16, border_width=1, border_color=BORDER, **kw)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 6))
        ctk.CTkLabel(head, text=title.upper(), font=font(11, "bold"), text_color=MUTED).pack(side="left")
        self.badge = ctk.CTkLabel(head, text="", font=font(11, "bold"), corner_radius=10, height=22, text_color=BG)
        self.badge.pack(side="right")
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    def set_badge(self, level, text=None):
        self.badge.configure(text=f"  {text or level}  ", fg_color=LEVEL.get(level, MUTED))


class Meter(ctk.CTkFrame):
    """Label, value text and a progress bar."""

    def __init__(self, master, label, color=ACCENT):
        super().__init__(master, fg_color="transparent")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text=label, font=font(12), text_color=MUTED).pack(side="left")
        self.value = ctk.CTkLabel(row, text="-", font=font(12, "bold"), text_color=TEXT)
        self.value.pack(side="right")
        self.bar = ctk.CTkProgressBar(self, height=8, corner_radius=4, progress_color=color, fg_color=PANEL2)
        self.bar.pack(fill="x", pady=(3, 8))
        self.bar.set(0)

    def set(self, frac, text, color=None):
        self.bar.set(max(0.0, min(1.0, frac)))
        self.value.configure(text=text)
        if color:
            self.bar.configure(progress_color=color)


class Tile(ctk.CTkFrame):
    def __init__(self, master, label, unit):
        super().__init__(master, fg_color=PANEL2, corner_radius=12)
        ctk.CTkLabel(self, text=label, font=font(11), text_color=MUTED).pack(anchor="w", padx=12, pady=(10, 0))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(anchor="w", padx=12, pady=(0, 10))
        self.value = ctk.CTkLabel(row, text="--", font=font(24, "bold"), text_color=TEXT)
        self.value.pack(side="left")
        ctk.CTkLabel(row, text=" " + unit, font=font(12), text_color=MUTED).pack(side="left", pady=(8, 0))
        self.dot = ctk.CTkLabel(self, text="", width=10, height=10, corner_radius=5, fg_color=PANEL2)
        self.dot.place(relx=1.0, x=-16, y=14)

    def set(self, value, fmt="{:.0f}", level=None):
        self.value.configure(text="--" if value is None else fmt.format(value))
        self.dot.configure(fg_color=LEVEL.get(level, PANEL2) if value is not None else PANEL2)


class Sparkline(tk.Canvas):
    def __init__(self, master, height=54, color=PINK):
        super().__init__(master, height=height, bg=PANEL, highlightthickness=0)
        self.color = color

    def draw(self, values):
        self.delete("all")
        w, h = max(self.winfo_width(), 50), int(self["height"])
        if len(values) < 2:
            self.create_text(w / 2, h / 2, text="waiting for heart-rate data", fill=MUTED, font=("TkDefaultFont", 9))
            return
        lo, hi = min(values) - 2, max(values) + 2
        pts = []
        for i, v in enumerate(values):
            pts += [6 + (w - 12) * i / (len(values) - 1), h - 6 - (h - 12) * (v - lo) / (hi - lo)]
        self.create_line(*pts, fill=self.color, width=2, smooth=True)
        self.create_oval(pts[-2] - 4, pts[-1] - 4, pts[-2] + 4, pts[-1] + 4, fill=self.color, outline="")


class TrendChart(tk.Canvas):
    COLORS = {"fatigue": "#F5C04E", "stress": "#FF4D6A", "low_mood": "#3DDCFF"}

    def __init__(self, master, height=240):
        super().__init__(master, height=height, bg=PANEL, highlightthickness=0)

    def draw(self, history):
        self.delete("all")
        w, h = max(self.winfo_width(), 200), int(self["height"])
        y = lambda s: h / 2 - max(-3, min(3, s)) * (h / 2 - 16) / 3
        self.create_rectangle(36, y(3), w - 8, y(1), fill="#2A1A2A", outline="")
        for s, label in ((0, "0"), (1, "+1"), (2, "+2")):
            self.create_line(36, y(s), w - 8, y(s), fill=BORDER, dash=(2, 4) if s else ())
            self.create_text(30, y(s), text=label, anchor="e", fill=MUTED, font=("TkDefaultFont", 8))
        if len(history) < 2:
            self.create_text(w / 2, h / 2 + 30, text="Trends appear after a few wellbeing check-ins",
                             fill=MUTED, font=("TkDefaultFont", 10))
            return
        n = len(history)
        for key, col in self.COLORS.items():
            pts = []
            for i, ind in enumerate(history):
                if key in ind:
                    pts += [40 + (w - 52) * i / (n - 1), y(ind[key]["score"])]
            if len(pts) >= 4:
                self.create_line(*pts, fill=col, width=2, smooth=True)
        lx = 44
        for key, col in self.COLORS.items():
            self.create_rectangle(lx, 8, lx + 10, 18, fill=col, outline="")
            self.create_text(lx + 14, 13, text=key.replace("_", " ").title(), anchor="w", fill=TEXT, font=("TkDefaultFont", 9))
            lx += 90


class SeleneApp(ctk.CTk):
    def __init__(self, ctx: DashboardContext):
        super().__init__(fg_color=BG)
        self.ctx = ctx
        self.title(f"{NAME} - Lunar Habitat AI Dashboard")
        self.geometry("1440x900")
        self.minsize(1180, 760)
        self.assistant = Assistant(ctx)
        self.speaker = voice_io.Speaker()
        self.results = queue.Queue()
        self.ai_state, self.frame_i, self.busy = "idle", 0, False
        self.handsfree = False
        self.logo_frames = {"idle": [ctk.CTkImage(logo.render(LOGO, i / 24, "idle"), size=(LOGO, LOGO)) for i in range(24)]}
        self.small_logo = ctk.CTkImage(logo.render(44, 0.15), size=(44, 44))
        self.speaker.on_start = lambda: self.results.put(("state", "speaking"))
        self.speaker.on_end = lambda: self.results.put(("state", "idle"))
        threading.Thread(target=self._render_state_frames, daemon=True).start()

        self._build_sidebar()
        self.main = ctk.CTkFrame(self, fg_color=BG)
        self.main.pack(side="left", fill="both", expand=True)
        self.pages = {}
        self._build_header()
        self._build_dashboard()
        self._build_trends()
        self._build_habitat()
        self._build_crew()
        self._build_settings()
        self.show("Dashboard")
        self.greet()
        self.after(60, self._animate)
        self.after(100, self._poll)
        self.after(500, self.refresh)

    # ------------------------------------------------------------------ layout
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=230, fg_color=PANEL, corner_radius=0)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)
        brand = ctk.CTkFrame(sb, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(22, 26))
        ctk.CTkLabel(brand, image=self.small_logo, text="").pack(side="left")
        txt = ctk.CTkFrame(brand, fg_color="transparent")
        txt.pack(side="left", padx=10)
        ctk.CTkLabel(txt, text=NAME, font=font(20, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(txt, text="Lunar Habitat AI", font=font(11), text_color=MUTED).pack(anchor="w")

        self.nav = {}
        for name in ("Dashboard", "Trends", "Habitat", "Crew", "Settings"):
            b = ctk.CTkButton(sb, text=name, anchor="w", height=40, corner_radius=10, font=font(14),
                              fg_color="transparent", hover_color=PANEL2, text_color=TEXT,
                              command=lambda n=name: self.show(n))
            b.pack(fill="x", padx=12, pady=2)
            self.nav[name] = b

        ctk.CTkLabel(sb, text="ASTRONAUT", font=font(11, "bold"), text_color=MUTED).pack(anchor="w", padx=20, pady=(26, 4))
        self.crew_menu = ctk.CTkOptionMenu(sb, values=["-"], command=self._select_crew, fg_color=PANEL2,
                                           button_color=ACCENT, button_hover_color="#6A50F0", dropdown_fg_color=PANEL2)
        self.crew_menu.pack(fill="x", padx=16)

        foot = ctk.CTkFrame(sb, fg_color="transparent")
        foot.pack(side="bottom", fill="x", padx=16, pady=16)
        self.chip_ai = ctk.CTkLabel(foot, text="", font=font(11), anchor="w", text_color=TEXT)
        self.chip_ai.pack(fill="x")
        self.chip_data = ctk.CTkLabel(foot, text="", font=font(11), anchor="w", text_color=MUTED, wraplength=190, justify="left")
        self.chip_data.pack(fill="x", pady=(2, 0))
        self.chip_mon = ctk.CTkLabel(foot, text="", font=font(11), anchor="w")
        self.chip_mon.pack(fill="x", pady=(2, 0))

    def _build_header(self):
        h = ctk.CTkFrame(self.main, fg_color="transparent")
        h.pack(fill="x", padx=24, pady=(10, 4))
        h.grid_columnconfigure(0, weight=1, uniform="side")
        h.grid_columnconfigure(2, weight=1, uniform="side")
        left = ctk.CTkFrame(h, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")
        self.greeting = ctk.CTkLabel(left, text="", font=font(22, "bold"), text_color=TEXT)
        self.greeting.pack(anchor="w")
        self.subtitle = ctk.CTkLabel(left, text="", font=font(13), text_color=MUTED)
        self.subtitle.pack(anchor="w")

        center = ctk.CTkFrame(h, fg_color="transparent")          # AI logo, top middle
        center.grid(row=0, column=1)
        self.orb = ctk.CTkLabel(center, text="", image=self.logo_frames["idle"][0])
        self.orb.pack()
        ctk.CTkLabel(center, text=NAME, font=font(18, "bold"), text_color=TEXT).pack(pady=(0, 0))
        self.state_label = ctk.CTkLabel(center, text="", font=font(12), text_color=MUTED, height=16)
        self.state_label.pack()

        self.overall = ctk.CTkLabel(h, text="", font=font(13, "bold"), corner_radius=14, height=32, text_color=BG)
        self.overall.grid(row=0, column=2, sticky="e")

    def _page(self, name):
        f = ctk.CTkFrame(self.main, fg_color="transparent")
        self.pages[name] = f
        return f

    def _build_dashboard(self):
        p = self._page("Dashboard")
        p.grid_columnconfigure(0, weight=5, uniform="c")
        p.grid_columnconfigure(1, weight=4, uniform="c")
        p.grid_columnconfigure(2, weight=4, uniform="c")
        p.grid_rowconfigure(0, weight=1)

        # --- simple chatbot
        ai = ctk.CTkFrame(p, fg_color=PANEL, corner_radius=16, border_width=1, border_color=BORDER)
        ai.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ctk.CTkLabel(ai, text="CHAT WITH SELENE", font=font(11, "bold"), text_color=MUTED).pack(anchor="w", padx=16, pady=(14, 4))
        self.chat = ctk.CTkScrollableFrame(ai, fg_color=BG, corner_radius=12)
        self.chat.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        chips = ctk.CTkFrame(ai, fg_color="transparent")
        chips.pack(fill="x", padx=14)
        for i, (label, q) in enumerate(QUICK[:3]):
            ctk.CTkButton(chips, text=label, height=28, corner_radius=14, font=font(12), fg_color=PANEL2,
                          hover_color=BORDER, text_color=TEXT, command=lambda q=q: self.send(q)
                          ).grid(row=0, column=i, padx=3, sticky="ew")
            chips.grid_columnconfigure(i, weight=1)
        bar = ctk.CTkFrame(ai, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=(8, 14))
        self.entry = ctk.CTkEntry(bar, placeholder_text="Type a message...", height=42, corner_radius=21,
                                  fg_color=PANEL2, border_color=BORDER, font=font(13))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send(self.entry.get()))
        ctk.CTkButton(bar, text="Send", width=70, height=42, corner_radius=21, font=font(13, "bold"),
                      fg_color=ACCENT, hover_color="#6A50F0", command=lambda: self.send(self.entry.get())
                      ).pack(side="left", padx=(8, 0))
        self.talk_btn = ctk.CTkButton(bar, text="Mic", width=56, height=42, corner_radius=21, font=font(13, "bold"),
                                      fg_color=PANEL2, hover_color=BORDER, border_width=1, border_color=CYAN,
                                      command=self.talk)
        self.talk_btn.pack(side="left", padx=(8, 0))

        # --- physical column
        col = ctk.CTkFrame(p, fg_color="transparent")
        col.grid(row=0, column=1, sticky="nsew", padx=6)
        self.phys = Card(col, "Physical health")
        self.phys.pack(fill="both", expand=True)
        tiles = ctk.CTkFrame(self.phys.body, fg_color="transparent")
        tiles.pack(fill="x")
        self.t_hr, self.t_spo2 = Tile(tiles, "Heart rate", "bpm"), Tile(tiles, "Blood oxygen", "%")
        self.t_hrv, self.t_temp = Tile(tiles, "HRV", "ms"), Tile(tiles, "Body temp", "°C")
        for i, t in enumerate((self.t_hr, self.t_spo2, self.t_hrv, self.t_temp)):
            t.grid(row=i // 2, column=i % 2, padx=4, pady=4, sticky="ew")
        tiles.grid_columnconfigure((0, 1), weight=1)
        self.spark = Sparkline(self.phys.body)
        self.spark.pack(fill="x", pady=(6, 8))
        self.m_ex = Meter(self.phys.body, "Exercise countermeasures", ACCENT)
        self.m_res = Meter(self.phys.body, "Resistive (bone and muscle)", PINK)
        self.m_water = Meter(self.phys.body, "Hydration", CYAN)
        self.m_sleep = Meter(self.phys.body, "Sleep", "#9C8CFF")
        self.m_rad = Meter(self.phys.body, "Radiation (mission / career limit)", "#F5C04E")
        for m in (self.m_ex, self.m_res, self.m_water, self.m_sleep, self.m_rad):
            m.pack(fill="x")
        self.phys_flags = ctk.CTkLabel(self.phys.body, text="", font=font(12), text_color=LEVEL["YELLOW"],
                                       wraplength=330, justify="left", anchor="w")
        self.phys_flags.pack(fill="x")
        autowrap(self.phys_flags, self.phys.body)

        # --- mental + habitat column
        col3 = ctk.CTkFrame(p, fg_color="transparent")
        col3.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        self.mental = Card(col3, "Mental wellbeing")
        self.mental.pack(fill="x")
        self.m_fat = Meter(self.mental.body, "Fatigue", LEVEL["YELLOW"])
        self.m_str = Meter(self.mental.body, "Stress", LEVEL["RED"])
        self.m_mood = Meter(self.mental.body, "Low mood", CYAN)
        for m in (self.m_fat, self.m_str, self.m_mood):
            m.pack(fill="x")
        self.mental_note = ctk.CTkLabel(self.mental.body, text="", font=font(12), text_color=MUTED,
                                        wraplength=330, justify="left", anchor="w")
        self.mental_note.pack(fill="x", pady=(0, 8))
        autowrap(self.mental_note, self.mental.body)
        ctk.CTkButton(self.mental.body, text="Start wellbeing check-in", height=36, corner_radius=18,
                      fg_color=PANEL2, hover_color=BORDER, border_width=1, border_color=ACCENT,
                      command=lambda: self.send("Start my check-in")).pack(fill="x")

        self.hab = Card(col3, "Habitat")
        self.hab.pack(fill="x", pady=(12, 0))
        r = ctk.CTkFrame(self.hab.body, fg_color="transparent")
        r.pack(fill="x")
        self.light_swatch = ctk.CTkLabel(r, text="", width=36, height=36, corner_radius=18)
        self.light_swatch.pack(side="left")
        self.light_label = ctk.CTkLabel(r, text="", font=font(13, "bold"), text_color=TEXT, wraplength=260, justify="left")
        self.light_label.pack(side="left", padx=10)
        self.hab_info = ctk.CTkLabel(self.hab.body, text="", font=font(12), text_color=MUTED, justify="left", anchor="w")
        self.hab_info.pack(fill="x", pady=(8, 0))

        self.alerts = Card(col3, "Alerts and schedule")
        self.alerts.pack(fill="both", expand=True, pady=(12, 0))
        self.alert_text = ctk.CTkLabel(self.alerts.body, text="", font=font(12), text_color=TEXT,
                                       justify="left", anchor="nw", wraplength=330)
        self.alert_text.pack(fill="both", expand=True)
        autowrap(self.alert_text, self.alerts.body)

    def _build_trends(self):
        p = self._page("Trends")
        c = Card(p, "Mental wellbeing vs. personal baseline")
        c.pack(fill="x")
        self.trend = TrendChart(c.body)
        self.trend.pack(fill="x")
        c2 = Card(p, "Heart rate (latest readings from your data)")
        c2.pack(fill="x", pady=(12, 0))
        self.spark2 = Sparkline(c2.body, height=160)
        self.spark2.pack(fill="x")

    def _build_habitat(self):
        p = self._page("Habitat")
        c = Card(p, "Circadian lighting")
        c.pack(fill="x")
        row = ctk.CTkFrame(c.body, fg_color="transparent")
        row.pack(fill="x")
        for mode in LIGHTING:
            ctk.CTkButton(row, text=mode.title(), height=56, corner_radius=12, fg_color=PANEL2, hover_color=BORDER,
                          border_width=2, border_color=LIGHT_COLOR[mode], text_color=TEXT,
                          command=lambda m=mode: self.send(f"Set lights to {m} mode")).pack(side="left", expand=True, fill="x", padx=4)
        c = Card(p, "Soundscapes")
        c.pack(fill="x", pady=(12, 0))
        row = ctk.CTkFrame(c.body, fg_color="transparent")
        row.pack(fill="x")
        for s in SOUNDSCAPES + ["stop"]:
            ctk.CTkButton(row, text=s.title(), height=40, corner_radius=12, fg_color=PANEL2, hover_color=BORDER,
                          text_color=TEXT, command=lambda s=s: self.send("Stop sounds" if s == "stop" else f"Play {s}")
                          ).pack(side="left", expand=True, fill="x", padx=4)
        c = Card(p, "Cabin environment (from your data file)")
        c.pack(fill="x", pady=(12, 0))
        self.cabin_text = ctk.CTkLabel(c.body, text="", font=font(14), text_color=TEXT, justify="left", anchor="w")
        self.cabin_text.pack(fill="x")

    def _build_crew(self):
        p = self._page("Crew")
        self.crew_card = Card(p, "Crew overview")
        self.crew_card.pack(fill="both", expand=True)
        self.crew_rows = ctk.CTkFrame(self.crew_card.body, fg_color="transparent")
        self.crew_rows.pack(fill="both", expand=True)

    def _build_settings(self):
        p = self._page("Settings")
        c = Card(p, "Data connection")
        c.pack(fill="x")
        self.data_path_label = ctk.CTkLabel(c.body, text="", font=font(13), text_color=TEXT, anchor="w", justify="left")
        self.data_path_label.pack(fill="x")
        ctk.CTkButton(c.body, text="Choose simulation output file...", fg_color=ACCENT, command=self._choose_file
                      ).pack(anchor="w", pady=(8, 0))
        c = Card(p, "Voice and AI")
        c.pack(fill="x", pady=(12, 0))
        self.voice_switch = ctk.CTkSwitch(c.body, text="Speak replies out loud", command=self._toggle_voice, progress_color=CYAN)
        self.voice_switch.select()
        self.voice_switch.pack(anchor="w")
        self.hf_switch = ctk.CTkSwitch(c.body, text='Hands-free: listen for "Hey Selene"', command=self._toggle_handsfree,
                                       progress_color=CYAN)
        self.hf_switch.pack(anchor="w", pady=(8, 0))
        self.ai_info = ctk.CTkLabel(c.body, text="", font=font(12), text_color=MUTED, justify="left", anchor="w")
        self.ai_info.pack(fill="x", pady=(8, 0))
        c = Card(p, "Privacy")
        c.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(c.body, text="Video and audio are analyzed in memory and never saved. Only numbers are stored "
                     "locally. Ground sees results only with the astronaut's consent.", font=font(12),
                     text_color=MUTED, wraplength=900, justify="left").pack(anchor="w")
        row = ctk.CTkFrame(c.body, fg_color="transparent")
        row.pack(anchor="w", pady=(8, 0))
        ctk.CTkButton(row, text="Pause monitoring", fg_color=PANEL2, command=lambda: self.send("Pause monitoring")).pack(side="left")
        ctk.CTkButton(row, text="Resume monitoring", fg_color=PANEL2, command=lambda: self.send("Resume monitoring")).pack(side="left", padx=8)

    # ------------------------------------------------------------------ behaviour
    def show(self, name):
        for n, f in self.pages.items():
            f.pack_forget()
        self.pages[name].pack(fill="both", expand=True, padx=24, pady=(4, 24))
        for n, b in self.nav.items():
            b.configure(fg_color=PANEL2 if n == name else "transparent")
        self.after(80, lambda: self.refresh(schedule=False))   # after the page is on screen

    def greet(self):
        h = dt.datetime.now().hour
        part = "morning" if h < 12 else "afternoon" if h < 18 else "evening"
        self.greeting.configure(text=f"Good {part}, {short_name(self.ctx.name()) if self.ctx.aid else 'crew'}")
        self.add_bubble(f"Hi, I'm {NAME}, your habitat health assistant. Ask me how you're doing, "
                        "log exercise or water, or say 'start my check-in'.", "ai")

    def add_bubble(self, text, who):
        row = ctk.CTkFrame(self.chat, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ai = who == "ai"
        width = max(260, self.chat.winfo_width() - 80) if self.chat.winfo_width() > 1 else 340
        b = ctk.CTkLabel(row, text=text, font=font(13), wraplength=width, justify="left",
                         fg_color=PANEL2 if ai else ACCENT, text_color=TEXT, corner_radius=14)
        b.pack(side="left" if ai else "right", padx=6, ipadx=10, ipady=6)
        self.after(50, lambda: self.chat._parent_canvas.yview_moveto(1.0))

    def set_state(self, state, text=None):
        self.ai_state = state if state in self.logo_frames else "idle"
        labels = {"idle": "Online and ready", "listening": "Listening...",
                  "thinking": "Thinking...", "speaking": "Speaking..."}
        self.state_label.configure(text=text or labels.get(state, ""))

    def send(self, text):
        text = (text or "").strip()
        if not text or self.busy:
            return
        self.entry.delete(0, "end")
        self.focus()                    # restores the entry placeholder
        self.add_bubble(text, "user")
        self.busy = True
        self.set_state("thinking")
        threading.Thread(target=self._ask_worker, args=(text,), daemon=True).start()

    def _ask_worker(self, text):
        try:
            reply, events = self.assistant.ask(text)
        except Exception as e:
            reply, events = f"Something went wrong: {e}", []
        self.results.put(("reply", (reply, events)))

    def talk(self):
        if self.busy:
            return
        self.busy = True
        self.set_state("listening")
        threading.Thread(target=self._listen_worker, daemon=True).start()

    def _listen_worker(self, wake=False):
        try:
            heard = voice_io.listen()
            if wake:
                cmd = voice_io.strip_wake_word(heard)
                if cmd is None:
                    self.results.put(("wake_miss", None))
                    return
                heard = cmd or ""
                if not heard:
                    self.results.put(("say", "Yes?"))
                    heard = voice_io.listen()
            self.results.put(("heard", heard))
        except RuntimeError as e:
            self.results.put(("wake_miss", None) if wake else ("listen_error", str(e)))

    def _toggle_handsfree(self):
        self.handsfree = bool(self.hf_switch.get())
        if self.handsfree and not self.busy:
            self._wake_loop()

    def _wake_loop(self):
        if not self.handsfree or self.busy:
            return
        self.busy = True
        self.set_state("idle", "Waiting for \"Hey Selene\"...")
        threading.Thread(target=self._listen_worker, kwargs={"wake": True}, daemon=True).start()

    def _toggle_voice(self):
        self.speaker.enabled = bool(self.voice_switch.get())

    def _poll(self):
        try:
            while True:
                kind, data = self.results.get_nowait()
                if kind == "reply":
                    reply, events = data
                    self.busy = False
                    self.add_bubble(reply, "ai")
                    self.set_state("idle")
                    self.speaker.say(reply)
                    for ev, arg in events:
                        self._handle_event(ev, arg)
                    self.refresh(schedule=False)
                    self.after(300, self._wake_loop)
                elif kind == "heard":
                    self.busy = False
                    self.send(data)
                elif kind == "say":
                    self.speaker.say(data)
                elif kind == "listen_error":
                    self.busy = False
                    self.set_state("idle", data)
                elif kind == "wake_miss":
                    self.busy = False
                    self.after(100, self._wake_loop)
                elif kind == "state":
                    if not self.busy:
                        self.set_state(data)
                elif kind == "checkin_done":
                    self.busy = False
                    self.add_bubble(data, "ai")
                    self.speaker.say(data)
                    self.set_state("idle")
                    self.refresh(schedule=False)
                elif kind == "breath":
                    self.set_state("speaking", data)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _handle_event(self, ev, arg):
        if ev == "checkin":
            self.busy = True
            self.set_state("listening", "Check-in running: look at the camera and answer out loud")
            threading.Thread(target=self._checkin_worker, daemon=True).start()
        elif ev == "breathing":
            threading.Thread(target=self._breathing_worker, daemon=True).start()
        elif ev == "alert":
            self.overall.configure(text=f"  ALERT: {arg}  ", fg_color=LEVEL.get(arg, LEVEL["RED"]))

    def _breathing_worker(self):
        time.sleep(4)
        for rnd in range(1, 5):
            for label, secs in (("Breathe in", 4), ("Hold", 7), ("Breathe out", 8)):
                for s in range(secs, 0, -1):
                    self.results.put(("breath", f"Round {rnd}/4  -  {label}  {s}"))
                    time.sleep(1)
        self.results.put(("state", "idle"))

    def _checkin_worker(self):
        try:
            from .capture import live_session
            from .fusion import assess
            from .interventions import recommend
            from .selfreport import to_features
            aid = self.ctx.aid
            if not self.ctx.store.astronaut(aid):
                self.ctx.store.add_astronaut(aid, self.ctx.name(aid))
            feats, _ = live_session(duration=30, preview=True)
            if not feats:
                self.results.put(("checkin_done", "Check-in cancelled. Nothing was saved."))
                return
            d = self.ctx.ds.latest(aid)
            feats.update(to_features(d.get("mood"), d.get("stress"), d.get("sleep_h")))
            a = assess(feats, self.ctx.store.sessions(aid))
            a["actions"] = recommend(a, self.ctx.store.astronaut(aid)["share_with_ground"])
            self.ctx.store.add_session(aid, feats, a)
            if a["status"] == "CALIBRATING":
                msg = f"Thanks! {a['message']}"
            else:
                top = max(a["indicators"].items(), key=lambda kv: kv[1]["score"])
                msg = (f"Check-in complete. Overall {a['status'].lower()}. "
                       + (f"Your {top[0].replace('_', ' ')} is above your usual level. " if top[1]["score"] >= 1 else
                          "Everything looks close to your normal. ")
                       + (a["actions"][0] if a.get("actions") else ""))
            self.results.put(("checkin_done", msg))
        except Exception as e:
            self.results.put(("checkin_done", f"I couldn't run the camera check-in ({e}). Check that a webcam is connected."))

    def _select_crew(self, label):
        for a in self.ctx.crew():
            if label.startswith(a["id"]):
                self.ctx.aid = a["id"]
        self.assistant = Assistant(self.ctx)
        self.greet()
        self.refresh(schedule=False)

    def _choose_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(filetypes=[("Data files", "*.csv *.json *.jsonl"), ("All", "*.*")])
        if path:
            from .datasource import DataSource
            self.ctx.ds.__init__(path)
            if not self.ctx.aid and self.ctx.crew():
                self.ctx.aid = self.ctx.crew()[0]["id"]
            self.refresh(schedule=False)

    # ------------------------------------------------------------------ refresh
    def refresh(self, schedule=True):
        try:
            self._refresh()
        finally:
            if schedule:
                self.after(2000, self.refresh)

    def _refresh(self):
        ctx = self.ctx
        ctx.ds.refresh()
        crew = ctx.crew()
        labels = [f"{a['id']}  {a['name']}" if a["name"] != a["id"] else a["id"] for a in crew] or ["No crew yet"]
        self.crew_menu.configure(values=labels)
        if ctx.aid is None and crew:
            ctx.aid = crew[0]["id"]
        cur = next((l for l in labels if ctx.aid and l.startswith(ctx.aid)), labels[0])
        self.crew_menu.set(cur)

        self.chip_ai.configure(text=f"●  {self.assistant.mode}", text_color=CYAN if "Claude" in self.assistant.mode else LEVEL["GREEN"])
        if ctx.ds.connected:
            ago = int(time.time() - ctx.ds.loaded_at)
            self.chip_data.configure(text=f"Data: {ctx.ds.path.name} ({len(ctx.ds.rows)} rows, updated {ago}s ago)")
        else:
            self.chip_data.configure(text=ctx.ds.error or "No data file connected (Settings)")
        paused = ctx.habitat.monitoring_paused
        self.chip_mon.configure(text="●  Monitoring paused" if paused else "●  Monitoring on",
                                text_color=LEVEL["YELLOW"] if paused else LEVEL["RED"])
        md = ctx.ds.mission_day()
        bits = [f"{dt.datetime.now():%A %H:%M}"] + ([f"Mission day {md}"] if md else []) + ([ctx.name()] if ctx.aid else [])
        self.subtitle.configure(text="  ·  ".join(bits))

        if not ctx.aid:
            self.overall.configure(text="  NO DATA  ", fg_color=MUTED)
            return
        ps = ctx.physical.summary(ctx.aid)
        ms = ctx.mental_summary()
        T = ps["targets"]

        def lvl(v, lo=None, hi=None):
            if v is None:
                return None
            return "ORANGE" if (lo is not None and v < lo) or (hi is not None and v > hi) else "GREEN"

        self.t_hr.set(ps["heart_rate"], level=lvl(ps["heart_rate"], T["hr_low"], T["hr_high"]))
        self.t_spo2.set(ps["spo2"], level="RED" if (ps["spo2"] or 99) < 90 else lvl(ps["spo2"], T["spo2_watch"]))
        self.t_hrv.set(ps["hrv_ms"], level=lvl(ps["hrv_ms"], T["hrv_low"]))
        self.t_temp.set(ps["skin_temp_c"], "{:.1f}", level=lvl(ps["skin_temp_c"], None, T["skin_temp_high"]))
        self.spark.draw(ps["hr_trace"])

        def meter(m, val, target, unit, fmt="{:.0f}"):
            if val is None:
                m.set(0, "no data")
            else:
                m.set(val / target, f"{fmt.format(val)} / {fmt.format(target)} {unit}")
        meter(self.m_ex, ps["exercise_min"], T["exercise_min"], "min")
        meter(self.m_res, ps["resistive_min"], T["resistive_min"], "min")
        meter(self.m_water, ps["water_ml"], T["water_ml"], "ml")
        meter(self.m_sleep, ps["sleep_h"], T["sleep_h"], "h", "{:.1f}")
        if ps["radiation_mission_msv"] is None:
            self.m_rad.set(0, "no data")
        else:
            pct = ps.get("radiation_limit_pct", 0)
            self.m_rad.set(pct / 100, f"{ps['radiation_mission_msv']:.1f} mSv ({pct}%)",
                           LEVEL["ORANGE"] if pct >= 80 else "#F5C04E")
        self.phys.set_badge(ps["status"] if ps["has_data"] else "NO DATA")
        self.phys_flags.configure(text="\n".join("• " + f for f in ps["flags"][:3]))

        self.mental.set_badge(ms["status"])
        for key, m in (("fatigue", self.m_fat), ("stress", self.m_str), ("low_mood", self.m_mood)):
            ind = ms["indicators"].get(key)
            if ind:
                m.set((ind["score"] + 1) / 4, f"{ind['score']:+.1f}  {ind['level']}")
            else:
                m.set(0, "check-in needed")
        note = ms.get("message") or ("; ".join(ms["flags"][:2]) if ms["flags"] else "")
        if ms.get("last_checkin"):
            note = f"Last check-in {ms['last_checkin']}. " + note
        sr = ms.get("self_report", {})
        if sr:
            note += "  Self-report: " + ", ".join(f"{k} {v:g}" for k, v in sr.items())
        self.mental_note.configure(text=note or "Scores compare today with this astronaut's own normal.")

        hs = ctx.habitat.status()
        self.light_swatch.configure(fg_color=LIGHT_COLOR[hs["lighting"]])
        self.light_label.configure(text=hs["lighting_label"])
        c = hs["cabin"]
        air = []
        if "o2_pct" in c: air.append(f"O2 {c['o2_pct']:.1f}%")
        if "ppco2_mmhg" in c: air.append(f"CO2 {c['ppco2_mmhg']:.1f} mmHg")
        if "pressure_kpa" in c: air.append(f"{c['pressure_kpa']:.1f} kPa")
        self.hab_info.configure(text=f"Sound: {hs['soundscape'] or 'off'}   ·   Set point {hs['temperature_c']:.0f} °C\n"
                                     + ("   ·   ".join(air) if air else "Cabin air: no data"))
        self.cabin_text.configure(text="\n".join(air) if air else "Add o2_pct, ppco2_mmhg, pressure_kpa columns to show cabin air.")
        self.hab.set_badge("GREEN", hs["lighting"].upper())
        lines = [f"{t}  {sev}  {txt}" for t, sev, txt in hs["alerts"]] + [f"Scheduled: {w} - {when}" for when, w in hs["schedule"]]
        self.alert_text.configure(text="\n".join(lines) if lines else "No alerts. All systems nominal.")
        self.alerts.set_badge("RED" if any(a[1] == "RED" for a in hs["alerts"]) else "GREEN",
                              f"{len(hs['alerts'])} alerts")

        order = ["GREEN", "YELLOW", "ORANGE", "RED"]
        levels = [l for l in (ps["status"] if ps["has_data"] else None, ms["status"]) if l in order]
        overall = max(levels, key=order.index) if levels else "NO DATA"
        if not any(a[1] == "RED" for a in hs["alerts"]):
            self.overall.configure(text=f"  Overall: {overall}  ", fg_color=LEVEL.get(overall, MUTED))

        if self.pages["Trends"].winfo_ismapped():
            self.trend.draw(ctx.mental_history())
            self.spark2.draw(ctx.ds.history(ctx.aid, "heart_rate", 200))
        if self.pages["Crew"].winfo_ismapped():
            self._draw_crew()
        if self.pages["Settings"].winfo_ismapped():
            self.data_path_label.configure(text=f"File: {ctx.ds.path or 'none'}\n"
                                           + (f"Columns not recognised: {', '.join(sorted(map(str, ctx.ds.unknown_columns)))}"
                                              if ctx.ds.unknown_columns else "All columns recognised."))
            self.ai_info.configure(text=f"AI mode: {self.assistant.mode}. Set ANTHROPIC_API_KEY to enable Claude; "
                                        "offline mode always works.")

    def _draw_crew(self):
        for w in self.crew_rows.winfo_children():
            w.destroy()
        for a in self.ctx.crew():
            ps = self.ctx.physical.summary(a["id"])
            ms = self.ctx.mental_summary(a["id"])
            row = ctk.CTkFrame(self.crew_rows, fg_color=PANEL2, corner_radius=12)
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=f"{a['name']}", font=font(15, "bold"), text_color=TEXT, width=200, anchor="w").pack(side="left", padx=14, pady=12)
            info = (f"HR {ps['heart_rate']:.0f}" if ps["heart_rate"] else "HR --") + \
                   (f"   SpO2 {ps['spo2']:.0f}%" if ps["spo2"] else "") + \
                   (f"   Sleep {ps['sleep_h']:.1f} h" if ps["sleep_h"] else "")
            ctk.CTkLabel(row, text=info, font=font(13), text_color=MUTED).pack(side="left")
            for label, lv in (("Mental", ms["status"]), ("Physical", ps["status"] if ps["has_data"] else "NO DATA")):
                ctk.CTkLabel(row, text=f"  {label}: {lv}  ", font=font(11, "bold"), fg_color=LEVEL.get(lv, MUTED),
                             text_color=BG, corner_radius=10).pack(side="right", padx=6)

    # ------------------------------------------------------------------ animation
    def _render_state_frames(self):
        for st in ("listening", "thinking", "speaking"):
            pil = [logo.render(LOGO, i / 24, st) for i in range(24)]
            self.logo_frames[st] = [ctk.CTkImage(im, size=(LOGO, LOGO)) for im in pil]

    def _animate(self):
        frames = self.logo_frames.get(self.ai_state) or self.logo_frames["idle"]
        self.frame_i = (self.frame_i + 1) % len(frames)
        self.orb.configure(image=frames[self.frame_i])
        self.after(70 if self.ai_state != "idle" else 110, self._animate)


def run(data_path=None, db=None):
    ctk.set_appearance_mode("dark")
    app = SeleneApp(DashboardContext(data_path, db))
    app.mainloop()
