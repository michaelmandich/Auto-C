"""Store Auto-C's microphone threshold for the current Windows user."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


DEFAULT_THRESHOLD = -45.0
MIN_THRESHOLD = -96.0
MAX_THRESHOLD = 0.0


def _settings_path():
    local = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    return Path(local) / "Auto-C" / "threshold.json"


def _validated(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Threshold must be a number in dBFS.")
    if not MIN_THRESHOLD <= value <= MAX_THRESHOLD:
        raise ValueError(f"Threshold must be between {MIN_THRESHOLD:g} and {MAX_THRESHOLD:g} dBFS.")
    return float(value)


def load_threshold() -> float:
    try:
        with _settings_path().open(encoding="utf-8") as file:
            return _validated(json.load(file)["threshold"])
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return DEFAULT_THRESHOLD


def save_threshold(value) -> None:
    threshold = _validated(value)
    target = _settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as file:
            temporary = Path(file.name)
            json.dump({"threshold": threshold}, file)
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
