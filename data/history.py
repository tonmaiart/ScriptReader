"""
data/history.py — persist recently opened target folders (Latest Path history)
"""

import json
import os

HISTORY_FILENAME = "history.json"
MAX_HISTORY = 15


def _history_path(app_base_dir: str) -> str:
    return os.path.join(app_base_dir, HISTORY_FILENAME)


def load_history(app_base_dir: str) -> list[str]:
    path = _history_path(app_base_dir)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, list):
        return [p for p in data if isinstance(p, str)]
    return []


def save_history(app_base_dir: str, paths: list[str]) -> None:
    path = _history_path(app_base_dir)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(paths, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def add_to_history(app_base_dir: str, folder: str) -> list[str]:
    """Move *folder* to the front of the history list (de-duplicated, capped)."""
    history = load_history(app_base_dir)
    history = [
        p for p in history
        if os.path.normcase(os.path.normpath(p)) != os.path.normcase(os.path.normpath(folder))
    ]
    history.insert(0, folder)
    history = history[:MAX_HISTORY]
    save_history(app_base_dir, history)
    return history
