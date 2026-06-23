"""ROA tracker hook.

Fires on UserPromptSubmit / Stop / Notification / PostToolUse. For each event it:
  1) (submit/stop only) appends the trimmed event to the per-day observer log
  2) updates a per-session running-total state file
  3) brackets permission waits (Notification = a permission prompt appeared;
     the next event = it was cleared) and carves them out of H2A
  4) (Stop) reads the transcript to record this turn's token delta

Prints nothing, always exits 0 — invisible to the session.
"""
import sys
import os
import json
import datetime
import pathlib

from roa import core
from roa.paths import data_dir, state_dir, active_file, day_log


def update_active(event):
    """Maintain the global active-session pointer + today's cross-session switch
    count. Only called on UserPromptSubmit (you *acting* = a real switch)."""
    sid = event.get("session_id")
    if not sid:
        return
    day = (event.get("_observed_at") or "")[:10]   # YYYY-MM-DD
    path = active_file()
    try:
        a = json.loads(pathlib.Path(path).read_text())
    except Exception:
        a = {}
    if a.get("day") != day:                          # new day -> reset counter
        a = {"day": day, "switches_today": 0, "active_sid": None, "active_cwd": None}
    prev = a.get("active_sid")
    if prev and prev != sid:                          # you moved to a different session
        a["switches_today"] = a.get("switches_today", 0) + 1
    a["active_sid"] = sid
    a["active_cwd"] = event.get("cwd")
    pathlib.Path(path).write_text(json.dumps(a, ensure_ascii=False, indent=2))


def trim(event):
    """Shrink an event to the fields worth logging, capping giant pastes."""
    out = {k: event[k] for k in core.KEEP_FIELDS if k in event}
    for k in ("prompt", "last_assistant_message"):
        v = out.get(k)
        if isinstance(v, str) and len(v) > core.TEXT_CAP:
            out[k] = v[:core.TEXT_CAP] + "…"
    return out


def main():
    raw = sys.stdin.read()
    base = pathlib.Path(data_dir())
    sdir = pathlib.Path(state_dir())
    base.mkdir(parents=True, exist_ok=True)
    sdir.mkdir(parents=True, exist_ok=True)

    try:
        event = json.loads(raw)
    except Exception:
        return  # unparseable -> nothing to do

    event["_observed_at"] = datetime.datetime.now().isoformat()
    ev = event.get("hook_event_name")
    ts = core.epoch(event["_observed_at"])

    sid = event.get("session_id")
    state = state_file = None
    if sid:
        state_file = sdir / f"{sid}.json"
        if state_file.exists():
            state = json.loads(state_file.read_text())
        else:
            state = core.new_state(sid, event.get("cwd"))

        # Close any open permission wait: whatever event we just got is the
        # resumption (tool ran after you approved, or you denied / moved on).
        # A wait > 30min means you stepped away — treat as a break, don't count.
        if state.get("_pending_perm_ts") is not None:
            wait = ts - state["_pending_perm_ts"]
            if 0 <= wait <= core.BREAK_S:
                state["_turn_perm_s"] = state.get("_turn_perm_s", 0.0) + wait
                state["_turn_perm_n"] = state.get("_turn_perm_n", 0) + 1
            state["_pending_perm_ts"] = None

    # Notification / PostToolUse are pure timing signals: they move permission
    # state but are NOT turn boundaries and are NOT logged (keep observer lean).
    if ev in ("Notification", "PostToolUse"):
        if state is not None:
            if ev == "Notification" and core.is_perm_notification(event):
                state["_pending_perm_ts"] = ts   # a permission prompt just appeared
            state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        return

    # On Stop the turn is finalized: stash this turn's permission wait + token
    # delta onto the event so offline replay reconstructs them.
    if ev == "Stop":
        event["_perm_s"] = round(state.get("_turn_perm_s", 0.0), 1) if state else 0.0
        event["_perm_n"] = state.get("_turn_perm_n", 0) if state else 0
        # read_tokens returns the running full-transcript cumulative; store the
        # DELTA since the last Stop so tokens land on the day they happened.
        if event.get("transcript_path") and state is not None:
            toks = core.read_tokens(event["transcript_path"])
            if toks:
                out_cum, tot_cum = toks
                event["_out_tokens"] = max(0, out_cum - state.get("_out_cum", 0))
                event["_total_tokens"] = max(0, tot_cum - state.get("_tot_cum", 0))
                state["_out_cum"] = out_cum
                state["_tot_cum"] = tot_cum

    # 1) raw append to today's per-day file (submit / stop only, trimmed fields)
    with open(day_log(event["_observed_at"]), "a") as f:
        f.write(json.dumps(trim(event), ensure_ascii=False) + "\n")

    # 2) per-session state update
    if not sid:
        return

    state = core.apply_event(state, event)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    # 3) global active-session + switch tracking (only when you act)
    if ev == "UserPromptSubmit":
        update_active(event)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # a hook must never break the session
    sys.exit(0)
