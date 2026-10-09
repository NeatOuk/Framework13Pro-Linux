"""fw-settings' own small preferences (~/.config/fw13/settings.json), e.g. night-light temperature."""
import json
import os
import tempfile

PATH = os.path.expanduser("~/.config/fw13/settings.json")
DEFAULTS = {"nightlight_temp": 4000, "vscode_theme": True, "terminal": "kitty"}  # vscode_theme = theme.VSCODE_ON: on unless switched off


def load():
    try:
        return {**DEFAULTS, **json.load(open(PATH))}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(data):
    """Atomic write. Each call has its own temp file: pages save on the main thread while background work
    (fw13.theme, fw13.hyprsettings) may save at the same time."""
    d = os.path.dirname(PATH)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=d)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.chmod(tmp, 0o644)
        os.replace(tmp, PATH)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def get(key):
    return load().get(key)


def set(key, value):  # noqa: A001 — module-level setter, fw13.store.set(...)
    data = load()
    data[key] = value
    save(data)
