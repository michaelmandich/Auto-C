"""Use microphone speech to hold League Team Voice's C binding."""

import argparse
import math
import queue
import signal
import sys
import time
from contextlib import nullcontext

import sounddevice as sd
import webrtcvad

from threshold_settings import DEFAULT_THRESHOLD, MAX_THRESHOLD, MIN_THRESHOLD, load_threshold
from win_ptt import LeagueKey, live_session


FRAME_MS = 20


def frame_power(frame):
    samples = memoryview(frame).cast("h")
    return sum(s * s for s in samples) / len(samples)


def decibels(power):
    return max(-96.0, 10 * math.log10(max(power, 0.001) / 32768**2))


class VoiceGate:
    def __init__(self, threshold_db=DEFAULT_THRESHOLD, release_ms=300):
        self.release_ms = release_ms
        self.reset()
        self.set_threshold(threshold_db)

    def set_threshold(self, threshold_db):
        self.threshold_db = threshold_db
        self.min_power = (32768 * 10 ** (threshold_db / 20)) ** 2
        self.speech_frames = 0

    def reset(self):
        self.vad = webrtcvad.Vad(2)
        self.active = False
        self.speech_frames = 0
        self.quiet_ms = 0
        self.power = 0.0

    def update(self, frame: bytes, rate: int) -> bool:
        self.power = frame_power(frame)
        speech = self.vad.is_speech(frame, rate) and self.power >= self.min_power
        if speech:
            self.speech_frames += 1
            self.quiet_ms = 0
            if self.speech_frames >= 2:
                self.active = True
        else:
            self.speech_frames = 0
            self.quiet_ms += FRAME_MS
            if self.quiet_ms >= self.release_ms:
                self.active = False
        return self.active


def capture_rate(device):
    for rate in (16000, 48000, 32000, 8000):
        try:
            sd.check_input_settings(device=device, channels=1, dtype="int16", samplerate=rate)
            return rate
        except sd.PortAudioError:
            continue
    raise ValueError("Microphone needs mono PCM at 8, 16, 32, or 48 kHz. Try --list-devices.")


def listen(args, stopping, on_status=None, get_threshold=None):
    mic = sd.query_devices(args.device, "input")
    rate = capture_rate(mic["index"])
    key = None if args.dry_run else LeagueKey()
    gate = VoiceGate(args.threshold)
    frames = queue.Queue(maxsize=8)
    sequence = 0

    def on_audio(data, count, timing, status):
        nonlocal sequence
        sequence += 1
        try:
            frames.put_nowait((sequence, time.monotonic(), bytes(data), bool(status)))
        except queue.Full:
            pass  # A gap in sequence resets the gate before fresh audio is used.

    mode = "Mic test (no keys sent)" if args.dry_run else "Live (C enabled in the League match window)"
    if on_status is None:
        print(f"{mode}\nMicrophone: {mic['name']} | Threshold: {args.threshold:g} dBFS | Ctrl+C to stop.",
              flush=True)
    active = False
    previous = 0
    last_audio = time.monotonic()
    next_meter = last_audio + 1
    peak_power = 0.0
    session = nullcontext() if args.dry_run else live_session()
    with session, sd.RawInputStream(device=mic["index"], samplerate=rate, channels=1, dtype="int16",
                           blocksize=rate * FRAME_MS // 1000, latency="low", callback=on_audio) as stream:
        try:
            while not stopping():
                try:
                    number, timestamp, frame, bad = frames.get(timeout=0.05)
                except queue.Empty:
                    age = time.monotonic() - last_audio
                    if age > 2 or not stream.active:
                        raise RuntimeError("Microphone stopped delivering audio. Check the device and restart Auto-C.")
                    if age < 0.25 and (key is None or not key.held or key.eligible()):
                        continue
                    frame = None
                else:
                    last_audio = timestamp
                    if number != previous + 1 or bad or time.monotonic() - timestamp > 0.2:
                        frame = None
                    previous = number

                eligible = key is None or key.eligible()
                if frame is None or not eligible:
                    if gate.active or gate.speech_frames:
                        gate.reset()
                    talking = False
                    power = frame_power(frame) if on_status and frame is not None else 0.0
                else:
                    if get_threshold is not None:
                        threshold_db = get_threshold()
                        if threshold_db != gate.threshold_db:
                            gate.set_threshold(threshold_db)
                    talking = gate.update(frame, rate)
                    power = gate.power

                if key is not None:
                    key.set_down(talking)
                    state = "key_down" if key.held else ("ready" if eligible else "waiting")
                else:
                    state = "test_speech" if talking else "test_quiet"
                if on_status is not None:
                    on_status(state, decibels(power))
                elif args.dry_run and talking != active:
                    print("Speaking -> C down" if talking else "Quiet -> C up", flush=True)
                active = talking

                if args.dry_run and on_status is None:
                    peak_power = max(peak_power, power)
                    if time.monotonic() >= next_meter:
                        db = decibels(peak_power)
                        print(f"Mic level (peak of last second): {db:.0f} dBFS", flush=True)
                        peak_power = 0.0
                        next_meter = time.monotonic() + 1
        finally:
            if key is not None:
                key.set_down(False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--display", action="store_true", help="open the mini microphone display")
    parser.add_argument("--dry-run", action="store_true", help="show mic levels and C transitions without sending keys")
    parser.add_argument("--threshold", type=float, metavar="DBFS",
                        help="initial speech threshold from -96 to 0 dBFS (default: saved setting or -45)")
    parser.add_argument("--list-devices", action="store_true", help="show microphone IDs and exit")
    parser.add_argument("--device", type=int, metavar="ID", help="microphone ID (default: Windows default input)")
    args = parser.parse_args()
    if args.threshold is None:
        args.threshold = load_threshold()
    elif not MIN_THRESHOLD <= args.threshold <= MAX_THRESHOLD:
        parser.error("--threshold must be between -96 and 0 dBFS")

    # Handle Ctrl+C between frames so it can't interrupt ownership of a key-down.
    stop = False

    def stop_requested(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, stop_requested)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, stop_requested)
    try:
        if args.list_devices:
            for mic in sd.query_devices():
                if mic["max_input_channels"]:
                    host = sd.query_hostapis(mic["hostapi"])["name"]
                    print(f"{mic['index']:3}  {mic['name']} ({host})")
        elif args.display:
            from mini_display import run_display
            return run_display(args)
        else:
            listen(args, lambda: stop)
    except (sd.PortAudioError, OSError, ValueError, RuntimeError) as error:
        print(f"Auto-C: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
