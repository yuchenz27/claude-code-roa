"""Pure ROA logic: event pairing, token accounting, permission bracketing.

Everything here is a pure function (the only file I/O is read_tokens, which reads
a transcript path it is handed). That purity is what lets report.py replay raw
logs offline and lets the test suite drive the same code the live hook runs.

Two core intervals per session:
  H2A (you wait the agent) = submit -> stop, minus any permission wait
  A2H (the agent waits you) = stop -> next submit (prompt wait) + permission wait
"""
import json
import datetime

BREAK_S = 1800   # a gap/wait > 30 min = you stepped away (not active attention)
TEXT_CAP = 2000  # truncate prompt / reply text to bound giant pastes

# Fields kept when an event is written to the per-day observer log. Stop events
# also carry the per-turn deltas (_out_tokens/_total_tokens, _perm_s/_perm_n) so
# offline replay can reconstruct token and permission numbers.
KEEP_FIELDS = ("_observed_at", "session_id", "cwd", "hook_event_name",
               "prompt", "last_assistant_message", "_out_tokens", "_total_tokens",
               "_perm_s", "_perm_n")


def epoch(iso_str):
    """ISO timestamp string -> epoch seconds (float)."""
    return datetime.datetime.fromisoformat(iso_str).timestamp()


def fmt(s):
    """Seconds -> compact human duration (e.g. 1h05m, 2m30s, 12s)."""
    s = int(s)
    if s >= 3600:
        return f"{s//3600}h{(s % 3600)//60:02d}m"
    if s >= 60:
        return f"{s//60}m{s % 60:02d}s"
    return f"{s}s"


def ftok(n):
    """Token count -> compact form (e.g. 1.2M, 340k, 87)."""
    n = int(n)
    if n >= 1_000_000:
        return f"{n/1e6:.1f}M"
    if n >= 1_000:
        return f"{n/1e3:.0f}k"
    return str(n)


def read_tokens(transcript_path):
    """Sum usage across all assistant messages in the session transcript.

    Returns (output_tokens, total_tokens) — cumulative for the whole session:
      output = model-produced tokens (the real work)
      total  = output + input + cache_creation + cache_read (footprint; ~90%+
               is cache_read = the same context re-read on every turn)
    Returns None on any failure (a hook must never break the session).
    """
    out = tot = 0
    try:
        with open(transcript_path) as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("type") != "assistant":
                    continue
                u = (o.get("message") or {}).get("usage") or {}
                if not u:
                    continue
                o_t = u.get("output_tokens", 0)
                out += o_t
                tot += (u.get("input_tokens", 0) + o_t
                        + u.get("cache_creation_input_tokens", 0)
                        + u.get("cache_read_input_tokens", 0))
    except Exception:
        return None
    return out, tot


def is_perm_notification(event):
    """A Notification hook fires both for permission requests AND for 60s-idle.
    Only the permission kind means 'the agent is blocked on you'."""
    return "permission" in (event.get("message") or "").lower()


def new_state(session_id, cwd):
    return {
        "session_id": session_id,
        "cwd": cwd,
        "first_ts": None,      # epoch of first event (session creation)
        "turns": 0,            # completed turns (= number of H2A intervals)
        "h2a_total_s": 0.0,    # total time you waited for the agent (perm excluded)
        "h2a_max_s": 0.0,
        "h2a_list": [],        # per-turn H2A seconds
        "a2h_total_s": 0.0,    # total time the agent waited for you (prompt wait)
        "a2h_count": 0,
        "a2h_max_s": 0.0,
        "a2h_list": [],        # per-gap A2H seconds (prompt wait = turn-boundary)
        "perm_total_s": 0.0,   # total permission-wait — agent blocked on you mid-turn
        "perm_count": 0,       # number of permission prompts you cleared
        "_pending_perm_ts": None,  # epoch of an open permission prompt (live only)
        "_turn_perm_s": 0.0,   # permission wait accrued in the current turn (live)
        "_turn_perm_n": 0,     # permission prompts in the current turn (live)
        "out_tokens": 0,       # output tokens accrued (sum of per-turn deltas = real work)
        "total_tokens": 0,     # all tokens accrued (incl. cache re-reads = footprint)
        "_out_cum": 0,         # last-seen full-transcript output cumulative (for delta calc)
        "_tot_cum": 0,         # last-seen full-transcript total cumulative (for delta calc)
        "last_event": None,    # "submit" | "stop"
        "last_ts": None,       # epoch seconds of last event
        "updated_at": None,
    }


def apply_event(state, event):
    """Fold one event into the running state. Pure — reusable for offline replay.

    Expects events with an `_observed_at` ISO timestamp (the only timing source;
    Claude Code payloads carry no timestamp). Stop events may carry per-turn
    deltas: `_perm_s`/`_perm_n` (permission wait) and `_out_tokens`/`_total_tokens`.
    """
    ev = event.get("hook_event_name")
    iso = event.get("_observed_at")
    if not ev or not iso:
        return state
    ts = epoch(iso)
    if state.get("first_ts") is None:
        state["first_ts"] = ts
    cwd = event.get("cwd")
    if cwd:
        state["cwd"] = cwd

    last = state.get("last_event")
    last_ts = state.get("last_ts")

    if ev == "UserPromptSubmit":
        # stop -> submit : the agent was waiting for you (A2H prompt wait)
        if last == "stop" and last_ts is not None:
            gap = ts - last_ts
            if gap >= 0:
                state["a2h_total_s"] += gap
                state["a2h_count"] += 1
                state["a2h_max_s"] = max(state["a2h_max_s"], gap)
                state.setdefault("a2h_list", []).append(round(gap, 1))
        # submit -> submit : you re-submitted before any Stop (edited / interrupted).
        # The real H2A start is the LATEST submit, so just move the marker (below).
        state["last_event"] = "submit"
        state["last_ts"] = ts
        state["_turn_perm_s"] = 0.0   # new turn — reset per-turn permission accumulator
        state["_turn_perm_n"] = 0

    elif ev == "Stop":
        # submit -> stop : you waited for the agent (H2A) — but subtract any
        # permission wait, which was the agent waiting on YOU, not working.
        perm = event.get("_perm_s", 0.0)
        if last == "submit" and last_ts is not None:
            h2a = (ts - last_ts) - perm
            if h2a >= 0:
                state["h2a_total_s"] += h2a
                state["turns"] += 1
                state["h2a_max_s"] = max(state["h2a_max_s"], h2a)
                state["h2a_list"].append(round(h2a, 1))
        # permission wait -> its own bucket (agent blocked on you mid-turn)
        state["perm_total_s"] = state.get("perm_total_s", 0.0) + perm
        state["perm_count"] = state.get("perm_count", 0) + event.get("_perm_n", 0)
        # stop -> stop : a second Stop with no submit between (e.g. stop-hook
        # continuation). No interval to count — just guard and move on.
        state["last_event"] = "stop"
        state["last_ts"] = ts

    # token counts: Stop events carry the per-turn DELTA (computed live in the
    # tracker). Accumulate so per-day / all-history replay both sum correctly,
    # and a carry-over session only contributes the day's own tokens.
    if "_out_tokens" in event:
        state["out_tokens"] = state.get("out_tokens", 0) + event["_out_tokens"]
        state["total_tokens"] = state.get("total_tokens", 0) + event.get("_total_tokens", 0)

    state["updated_at"] = datetime.datetime.fromtimestamp(ts).isoformat()
    return state
