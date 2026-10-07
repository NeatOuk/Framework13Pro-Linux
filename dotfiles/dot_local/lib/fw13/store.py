"""fw-settings' own small preferences (~/.config/fw13/settings.json), e.g. night-light temperature."""
import json
import os

PATH = os.path.expanduser("~/.config/fw13/settings.json")
DEFAULTS = {"nightlight_temp": 4000}


def load():
    try:
        return {**DEFAULTS, **json.load(open(PATH))}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(data):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    json.dump(data, open(tmp, "w"), indent=2)
    os.replace(tmp, PATH)


def get(key):
    return load().get(key)


def set(key, value):  # noqa: A001 — module-level setter, fw13.store.set(...)
    data = load()
    data[key] = value
    save(data)
