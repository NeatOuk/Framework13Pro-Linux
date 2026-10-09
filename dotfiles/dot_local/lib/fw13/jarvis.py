"""Jarvis' Claude settings (Settings → Jarvis): model and effort, kept in the store and passed to every `claude` run
(the panel's inline answers, Continue in terminal, fw-jarvis sessions). Empty = Claude Code's own default."""
import re

from . import store

MODELS = [("", "Default (Claude Code's choice)"), ("fable", "Fable"), ("opus", "Opus"), ("sonnet", "Sonnet"),
          ("haiku", "Haiku")]  # aliases follow the newest model; a full model name can be typed too
EFFORTS = [("", "Default"), ("low", "Low"), ("medium", "Medium"), ("high", "High"), ("xhigh", "Extra high"),
           ("max", "Max")]
_MODEL_OK = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\[\]-]*")


def check_model(text):
    """(value, error): '' is allowed (the default); anything else must look like an alias or a model id."""
    text = text.strip()
    if text and not _MODEL_OK.fullmatch(text):
        return None, "A model is an alias (opus, sonnet…) or a full name such as claude-opus-5-5"
    return text, None


def model():
    return check_model(str(store.get("jarvis_model") or ""))[0] or ""


def effort():
    e = store.get("jarvis_effort")
    return e if e in {k for k, _ in EFFORTS} else ""


def claude_args():
    """['--model', m] and ['--effort', e] for whichever are set."""
    out = []
    if model():
        out += ["--model", model()]
    if effort():
        out += ["--effort", effort()]
    return out


if __name__ == "__main__":  # fw-jarvis (bash): one argument per line
    args = claude_args()
    if args:  # nothing at all when unset: an empty line would become an empty argument
        print("\n".join(args))
