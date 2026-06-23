"""ROA statusline rendering.

Reads the Claude Code statusline JSON from stdin once and prints ROA's lines:
  Output Style: <style>
  H2A ｜ last · avg · total · turns [· running]        (this session)
  A2H ｜ prompt ~typical [· perm <total> · N asks]      (this session)
  Today ｜ Agent Time · Human Time · Time Lev · Switches (all sessions, today)
  Today ｜ Tokens <total> · out <output>                (footprint + real output)

Prints nothing it has no data for. Never errors.
"""
import sys
import os
import json
import time
import statistics
import datetime

from roa import core
from roa.paths import data_dir, active_file, day_log

# settings.json (for outputStyle) lives in the Claude config dir, not the data dir
CFG = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def line_style(data):
    cwd = data.get("cwd") or os.getcwd()
    merged = {}
    for path in (
        os.path.join(CFG, "settings.json"),
        os.path.join(cwd, ".claude", "settings.json"),
        os.path.join(cwd, ".claude", "settings.local.json"),
    ):
        try:
            with open(path) as f:
                merged.update(json.load(f))
        except Exception:
            pass
    style = merged.get("outputStyle") or "default"
    return f"Output Style: {style}"


def line_timing(data):
    """This session's H2A line and combined A2H (prompt + permission) line."""
    sid = data.get("session_id")
    if not sid:
        return []
    try:
        st = json.load(open(os.path.join(data_dir(), "state", f"{sid}.json")))
    except Exception:
        return []

    last_event = st.get("last_event")
    last_ts = st.get("last_ts")
    out = []

    # Human waits for Agent
    turns = st.get("turns", 0)
    if turns:
        h2a = st.get("h2a_list") or []
        last = h2a[-1] if h2a else 0
        total = st.get("h2a_total_s", 0)
        s = (f"H2A ｜ last {core.fmt(last)} · avg {core.fmt(total/turns)} "
             f"· total {core.fmt(total)} · {turns} turns")
        if last_event == "submit" and last_ts:           # agent working now
            cur = time.time() - last_ts
            if cur >= 0:
                s += f" · running {core.fmt(cur)}"
        out.append(s)

    # Agent waits for Human — one line, two reasons:
    #   prompt = turn-boundary wait (tail-heavy -> median, marked with ~)
    #   perm   = permission prompts mid-turn (short/bounded -> total + count)
    a2h = st.get("a2h_list") or []
    perm_n = st.get("perm_count", 0)
    if a2h or perm_n:
        parts = []
        if a2h:
            parts.append(f"prompt ~{core.fmt(statistics.median(a2h))}")
        if perm_n:
            parts.append(f"perm {core.fmt(st.get('perm_total_s', 0))} · {perm_n} asks")
        out.append("A2H ｜ " + " · ".join(parts))

    return out


def today_globals():
    """Today's global numbers as a dict, or None if no events.
      agent_time   = AI working time summed across all sessions (parallel adds up)
      focus_time   = your active wall-clock (elapsed minus >30m breaks)
      leverage     = agent_time / focus_time (None if focus_time is 0)
      out_tokens   = model-produced tokens summed across sessions (real work)
      total_tokens = all tokens incl. cache re-reads (footprint)
    """
    try:
        today = datetime.date.today().isoformat()
        day_path = day_log(today)
        evs = []
        try:
            lines = open(day_path)
        except FileNotFoundError:
            return None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("session_id"):
                evs.append(e)
        if not evs:
            return None
        states = {}
        for e in sorted(evs, key=lambda x: x["_observed_at"]):
            sid = e["session_id"]
            states.setdefault(sid, core.new_state(sid, e.get("cwd")))
            core.apply_event(states[sid], e)
        agent_time = sum(st["h2a_total_s"] for st in states.values())
        out_tokens = sum(st.get("out_tokens", 0) for st in states.values())
        total_tokens = sum(st.get("total_tokens", 0) for st in states.values())
        ts = sorted(core.epoch(e["_observed_at"]) for e in evs)
        focus_time = sum(b - a for a, b in zip(ts, ts[1:]) if (b - a) <= core.BREAK_S)
        return {
            "agent_time": agent_time,
            "focus_time": focus_time,
            "leverage": (agent_time / focus_time) if focus_time else None,
            "out_tokens": out_tokens,
            "total_tokens": total_tokens,
        }
    except Exception:
        return None


def line_global(data):
    """Two neon "Today ｜" bands: time/leverage, then token footprint.
    Returns a list of 0-2 lines."""
    g = today_globals()
    neon = "\033[38;2;240;90;255m"
    out = []

    parts = []
    if g:
        parts.append(f"Agent Time {core.fmt(g['agent_time'])}")
        parts.append(f"Human Time {core.fmt(g['focus_time'])}")
        if g.get("leverage") is not None:
            parts.append(f"Time Lev {g['leverage']:.2f}×")
    try:
        a = json.load(open(active_file()))
        parts.append(f"Switches {a.get('switches_today', 0)}")
    except Exception:
        pass
    if parts:
        out.append(f"{neon}Today ｜ " + " · ".join(parts) + "\033[0m")

    # second band: token footprint (total, mostly cache re-reads) + real output
    if g and g.get("total_tokens"):
        out.append(f"{neon}Today ｜ Tokens {core.ftok(g['total_tokens'])} "
                   f"· out {core.ftok(g['out_tokens'])}\033[0m")
    return out


def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        return
    lines = [line_style(data)] + line_timing(data) + line_global(data)
    for ln in lines:
        if ln:
            print(ln)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
