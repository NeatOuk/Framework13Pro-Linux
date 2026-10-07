"""Audio outputs/inputs and volume through PipeWire's wpctl."""
import re

from .hypr import sh

_ROW = re.compile(r"^\s*│?\s*(\*)?\s*(\d+)\.\s+(.+?)\s+\[vol:\s*([\d.]+)(\s+MUTED)?\]")


def devices():
    """{"sinks": [...], "sources": [...]}, each {id, name, default, volume (0–1.5), muted}."""
    out = {"sinks": [], "sources": []}
    section = None
    in_audio = False
    for line in sh("wpctl", "status").splitlines():
        if not line.startswith((" ", "│", "├", "└")):
            in_audio = line.strip() == "Audio"
            continue
        if not in_audio:
            continue
        head = re.search(r"[├└]─ (\w+):", line)
        if head:
            section = {"Sinks": "sinks", "Sources": "sources"}.get(head.group(1))
            continue
        m = _ROW.match(line)
        if section and m:
            out[section].append({"id": int(m.group(2)), "name": m.group(3).strip(), "default": bool(m.group(1)),
                                 "volume": float(m.group(4)), "muted": bool(m.group(5))})
    return out


def set_default(node_id):
    sh("wpctl", "set-default", str(node_id))


def set_volume(node_id, frac):
    sh("wpctl", "set-volume", "-l", "1.0", str(node_id), f"{max(0.0, min(frac, 1.0)):.2f}")


def set_mute(node_id, muted):
    sh("wpctl", "set-mute", str(node_id), "1" if muted else "0")
