"""Where ROA keeps its data — deliberately separate from the code.

The code can live anywhere (a working copy, or an installed plugin cache that
gets replaced on every update). The data — your logs, per-session state, and
daily trend — must NOT live with the code, or an update would wipe your history.
So data always resolves to a stable location in your home config dir.
"""
import os


def data_dir():
    """Resolve the ROA data directory.

    Order of precedence:
      1. $ROA_DIR                       (explicit override)
      2. $CLAUDE_CONFIG_DIR/roa         (follows a custom Claude config dir)
      3. ~/.claude/roa                  (default)
    """
    override = os.environ.get("ROA_DIR")
    if override:
        return os.path.expanduser(override)
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(cfg, "roa")


def state_dir():
    return os.path.join(data_dir(), "state")


def active_file():
    return os.path.join(data_dir(), "active.json")


def daily_file():
    return os.path.join(data_dir(), "daily.jsonl")


def day_log(iso):
    """Per-day observer log path for an ISO timestamp/date string."""
    return os.path.join(data_dir(), f"observer-{iso[:10]}.jsonl")
