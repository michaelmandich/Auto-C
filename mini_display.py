"""Compact Windows microphone and push-to-talk status display."""

import threading
import tkinter as tk

from auto_c import listen
from monitor_position import place_window
from threshold_settings import MAX_THRESHOLD, MIN_THRESHOLD, save_threshold


BG = "#141a21"
PANEL = "#24303a"
TEXT = "#f1f5f5"
MUTED = "#a5b3bd"
METER = "#63c9d0"
THRESHOLD = "#f0bf73"
TEST = "#b7a4ff"

# Title, supporting text, keycap background, keycap foreground.
STATES = {
    "starting": ("Starting microphone", "Opening the input device…", PANEL, MUTED),
    "off": ("Off", "Voice-activated C is paused.", PANEL, MUTED),
    "ready": ("Listening", "Speak to hold C for push-to-talk.", "#19353a", METER),
    "key_down": ("Talking", "C is held for push-to-talk.", "#89e6b4", "#093722"),
    "key_busy": ("Shortcut held", "Release the shortcut to resume.", "#463828", THRESHOLD),
    "test_quiet": ("Listening", "Microphone test · Keys disabled", "#312b43", TEST),
    "test_speech": ("Speech detected", "Microphone test · Keys disabled", TEST, "#231b36"),
    "error": ("Auto-C stopped", "", "#442a30", "#f4a3a6"),
}


def run_display(args):
    """Run the display until closed. The capture thread owns the microphone and key."""
    root = tk.Tk()
    root.title("Auto-C · Microphone test" if args.dry_run else "Auto-C · Voice activation")
    root.configure(bg=BG)
    root.resizable(False, False)
    root.attributes("-topmost", True)

    body = tk.Frame(root, bg=BG, padx=18, pady=15)
    body.pack(fill="both", expand=True)
    hero = tk.Frame(body, bg=BG)
    hero.pack(fill="x")
    cap = tk.Frame(hero, width=48, height=48, bg=PANEL)
    cap.pack(side="left", padx=(0, 12))
    cap.pack_propagate(False)
    cap_label = tk.Label(cap, text="MIC" if args.dry_run else "C", bg=PANEL, fg=MUTED,
                         font=("Segoe UI", 12 if args.dry_run else 20, "bold"))
    cap_label.pack(fill="both", expand=True)
    copy = tk.Frame(hero, bg=BG)
    copy.pack(side="left", fill="x", expand=True)
    title = tk.Label(copy, bg=BG, fg=TEXT, font=("Segoe UI", 16, "bold"), anchor="w")
    title.pack(fill="x")
    detail = tk.Label(copy, bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w")
    detail.pack(fill="x")
    tk.Frame(body, height=1, bg=PANEL).pack(fill="x", pady=(13, 9))

    meter_head = tk.Frame(body, bg=BG)
    meter_head.pack(fill="x")
    tk.Label(meter_head, text="Microphone level", bg=BG, fg=TEXT,
             font=("Segoe UI", 9)).pack(side="left")
    reading = tk.Label(meter_head, text="— dBFS", bg=BG, fg=TEXT, font=("Consolas", 10))
    reading.pack(side="right")
    meter = tk.Canvas(body, bg=BG, width=294, height=13, highlightthickness=0)
    meter.pack(fill="x", pady=(2, 1))
    track = meter.create_rectangle(0, 4, 1, 10, fill=PANEL, outline="")
    bar = meter.create_rectangle(0, 4, 0, 10, fill=METER, outline="")
    marker = meter.create_line(0, 1, 0, 13, width=2, fill=THRESHOLD)
    controls = tk.Frame(body, bg=BG)
    controls.pack(fill="x")
    threshold_label = tk.Label(controls, bg=BG, fg=THRESHOLD, font=("Segoe UI", 9), anchor="w")
    threshold_label.pack(side="left", fill="x", expand=True)
    save_error = tk.Label(body, bg=BG, fg=THRESHOLD, font=("Segoe UI", 9), anchor="w",
                          text="Change applied. Couldn’t save the setting.")

    threshold = args.threshold
    threshold_lock = threading.Lock()

    def get_threshold():
        with threshold_lock:
            return threshold

    def draw_marker():
        width = max(1, meter.winfo_width() - 1)
        fraction = (threshold - MIN_THRESHOLD) / (MAX_THRESHOLD - MIN_THRESHOLD)
        threshold_x = min(width - 1, max(1, width * fraction))
        meter.coords(marker, threshold_x, 1, threshold_x, 13)

    def show_threshold():
        threshold_label.configure(text=f"Threshold  {threshold:g} dBFS")
        lower.configure(state="normal" if threshold > MIN_THRESHOLD else "disabled")
        raise_button.configure(state="normal" if threshold < MAX_THRESHOLD else "disabled")
        draw_marker()

    def adjust_threshold(step):
        nonlocal threshold
        with threshold_lock:
            threshold = max(MIN_THRESHOLD, min(MAX_THRESHOLD, threshold + step))
        show_threshold()
        try:
            save_threshold(threshold)
        except OSError:
            save_error.pack(fill="x", pady=(4, 0))
        else:
            save_error.pack_forget()

    button_style = dict(bg=PANEL, fg=TEXT, activebackground="#344451", activeforeground=TEXT,
                        disabledforeground="#72818a", highlightcolor=THRESHOLD,
                        highlightbackground=BG, highlightthickness=1, relief="flat", borderwidth=0,
                        takefocus=True, width=3, font=("Segoe UI", 10, "bold"))
    lower = tk.Button(controls, text="−", command=lambda: adjust_threshold(-1), **button_style)
    lower.pack(side="left", padx=(0, 3))
    raise_button = tk.Button(controls, text="+", command=lambda: adjust_threshold(1), **button_style)
    raise_button.pack(side="left")

    enabled = threading.Event()
    toggle = None
    if not args.dry_run:
        def toggle_live():
            if enabled.is_set():
                enabled.clear()
                toggle.configure(text="Turn on")
            else:
                enabled.set()
                toggle.configure(text="Turn off")

        live_controls = tk.Frame(body, bg=BG)
        live_controls.pack(fill="x", pady=(9, 0))
        tk.Label(live_controls, text="When on, C goes to the active window.", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9), anchor="w", justify="left", wraplength=197).pack(side="left")
        toggle = tk.Button(live_controls, text="Turn on", command=toggle_live, **button_style)
        toggle.configure(width=8, bg="#19353a", fg=METER)
        toggle.pack(side="right")

    def show_state(state):
        headline, subtitle, background, ink = STATES[state]
        title.configure(text=headline)
        detail.configure(text=subtitle)
        cap_label.configure(bg=background, fg=ink)
        bar_color = TEST if args.dry_run else "#89e6b4" if state == "key_down" else METER
        meter.itemconfigure(bar, fill=bar_color)

    def draw_level(level):
        width = max(1, meter.winfo_width() - 1)
        # Map the full configurable -96..0 dBFS scale to the meter.
        fill = 0 if level is None else width * min(1, max(0, (level + 96) / 96))
        meter.coords(track, 0, 4, width, 10)
        meter.coords(bar, 0, 4, fill, 10)
        reading.configure(text="— dBFS" if level is None else f"{max(-96, level):.0f} dBFS")

    show_threshold()
    meter.bind("<Configure>", lambda event: draw_marker())
    show_state("starting")
    root.update_idletasks()
    root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())
    draw_level(None)
    place_window(root)

    stop = threading.Event()
    status_lock = threading.Lock()
    latest = ("starting", None)
    failure = None

    def on_status(state, level_db):
        nonlocal latest
        with status_lock:
            latest = state, level_db

    def capture():
        nonlocal failure
        try:
            listen(args, stop.is_set, on_status=on_status, get_threshold=get_threshold,
                   is_enabled=enabled.is_set)
        except Exception as error:
            failure = str(error) or type(error).__name__

    worker = threading.Thread(target=capture, name="Auto-C microphone")
    worker.start()
    displayed = "starting"

    def refresh():
        nonlocal displayed
        if not worker.is_alive():
            if stop.is_set() or failure is None:
                root.destroy()
            else:
                show_state("error")
                enabled.clear()
                if toggle is not None:
                    toggle.configure(text="Turn on", state="disabled")
                lower.configure(state="disabled")
                raise_button.configure(state="disabled")
                detail.configure(text=failure, wraplength=max(160, copy.winfo_width()), justify="left")
                draw_level(None)
                root.protocol("WM_DELETE_WINDOW", root.destroy)
            return
        with status_lock:
            state, level = latest
        if state != displayed:
            show_state(state)
            displayed = state
        draw_level(level)
        root.after(40, refresh)

    def request_stop():
        stop.set()
        enabled.clear()
        if toggle is not None:
            toggle.configure(text="Turn on", state="disabled")

    root.protocol("WM_DELETE_WINDOW", request_stop)
    root.after(0, refresh)
    try:
        root.mainloop()
    finally:
        stop.set()
        enabled.clear()
        worker.join()
    return 1 if failure is not None else 0
