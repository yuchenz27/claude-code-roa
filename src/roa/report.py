"""Offline ROA report.

Replays the raw per-day event logs and computes:
  • Leverage  L = AI working time / your active wall-clock
       AI working time  = sum of agent-working intervals across ALL sessions
                          (parallel sessions add up — that's the point)
       active wall-clock = your day minus long idle breaks (sessionized)
       L > 1  ⇒  you extracted more AI-labor-hours than clock-hours.
  • Tokens (footprint vs real output) + Token Leverage
  • Permission wait (agent blocked on you) and a serial Time Lev
  • H2A / A2H distributions, session health, per-session table

Usage:
    report [path-substring]   # all history (optionally filter by cwd substring)
    report --today            # today only
    report --record           # append/replace today's line in daily.jsonl
"""
import sys
import os
import json
import glob
import statistics
import datetime

from roa import core
from roa.paths import data_dir, state_dir, daily_file

fmt = core.fmt
epoch = core.epoch
BREAK_S = core.BREAK_S


def load_events(today_only, substr):
    base = data_dir()
    today = datetime.date.today().isoformat()
    if today_only:
        files = [os.path.join(base, f"observer-{today}.jsonl")]
    else:
        files = sorted(glob.glob(os.path.join(base, "observer-*.jsonl")))
    evs = []
    for fp in files:
        if not os.path.exists(fp):
            continue
        for line in open(fp):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if not e.get("_observed_at") or not e.get("session_id"):
                continue
            if substr and substr not in (e.get("cwd") or ""):
                continue
            evs.append(e)
    return evs


def replay(evs):
    states = {}
    for e in sorted(evs, key=lambda x: x["_observed_at"]):
        sid = e["session_id"]
        states.setdefault(sid, core.new_state(sid, e.get("cwd")))
        core.apply_event(states[sid], e)
    return states


def buckets(vals):
    n = len(vals)
    out = []
    for name, lo, hi in [("<30s", 0, 30), ("30s-2m", 30, 120), ("2-5m", 120, 300),
                         ("5-15m", 300, 900), ("15-60m", 900, 3600), (">1h", 3600, 9e9)]:
        c = sum(1 for v in vals if lo <= v < hi)
        bar = "█" * round(30 * c / n) if n else ""
        out.append(f"  {name:<8} {c:>4}  {bar} {100*c/n:.0f}%" if n else f"  {name:<8}    0")
    return out


def record_today():
    """Append/replace today's summary line in daily.jsonl (permanent trend log)."""
    evs = load_events(True, None)
    if not evs:
        print("No events today — nothing to record.")
        return
    states = replay(evs)
    all_h2a = [g for st in states.values() for g in (st.get("h2a_list") or [])]
    all_a2h = [g for st in states.values() for g in (st.get("a2h_list") or [])]
    agent_time = sum(st["h2a_total_s"] for st in states.values())
    out_tokens = sum(st.get("out_tokens", 0) for st in states.values())
    total_tokens = sum(st.get("total_tokens", 0) for st in states.values())
    perm_total = sum(st.get("perm_total_s", 0) for st in states.values())
    perm_count = sum(st.get("perm_count", 0) for st in states.values())
    ts = sorted(epoch(e["_observed_at"]) for e in evs)
    human = sum(b - a for a, b in zip(ts, ts[1:]) if (b - a) <= BREAK_S)
    submits = [e for e in sorted(evs, key=lambda x: x["_observed_at"])
               if e.get("hook_event_name") == "UserPromptSubmit"]
    switches = sum(1 for a, b in zip(submits, submits[1:])
                   if a["session_id"] != b["session_id"])
    per_proj = {}
    for st in states.values():
        proj = os.path.basename((st.get("cwd") or "?").rstrip("/")) or "?"
        per_proj.setdefault(proj, {"turns": 0, "agent_s": 0})
        per_proj[proj]["turns"] += st["turns"]
        per_proj[proj]["agent_s"] += int(st["h2a_total_s"])

    today_iso = datetime.date.today().isoformat()
    carry_over = 0  # sessions touched today that were created on an earlier day
    for sid in states:
        try:
            sf = json.load(open(os.path.join(state_dir(), f"{sid}.json")))
            ft = sf.get("first_ts")
            if ft and datetime.date.fromtimestamp(ft).isoformat() < today_iso:
                carry_over += 1
        except Exception:
            pass

    rec = {
        "date": today_iso,
        "carry_over": carry_over,
        "agent_time_s": int(agent_time),
        "human_time_s": int(human),
        "leverage": round(agent_time / human, 2) if human else None,
        "out_tokens": out_tokens,
        "total_tokens": total_tokens,
        "token_leverage": round(out_tokens / (human / 60), 1) if human else None,
        "perm_total_s": int(perm_total),
        "perm_count": perm_count,
        "switches": switches,
        "turns": len(all_h2a),
        "h2a_median_s": int(statistics.median(all_h2a)) if all_h2a else None,
        "a2h_median_s": int(statistics.median(all_a2h)) if all_a2h else None,
        "per_project": per_proj,
    }
    path = daily_file()
    lines = []
    if os.path.exists(path):
        lines = [l for l in open(path) if l.strip()
                 and json.loads(l).get("date") != rec["date"]]
    lines.append(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(path, "w") as f:
        f.writelines(lines)
    print(f"Recorded {rec['date']}: leverage {rec['leverage']}×, "
          f"agent {fmt(agent_time)}, human {fmt(human)}, switches {switches}")


def main():
    args = sys.argv[1:]
    if "--record" in args:
        record_today()
        return
    today_only = "--today" in args
    substr = next((a for a in args if not a.startswith("--")), None)

    evs = load_events(today_only, substr)
    if not evs:
        print("No events.")
        return

    states = replay(evs)
    all_h2a = [g for st in states.values() for g in (st.get("h2a_list") or [])]
    all_a2h = [g for st in states.values() for g in (st.get("a2h_list") or [])]
    ai_labor = sum(st["h2a_total_s"] for st in states.values())

    # global active wall-clock + switches
    ts = sorted(epoch(e["_observed_at"]) for e in evs)
    active = sum(b - a for a, b in zip(ts, ts[1:]) if (b - a) <= BREAK_S)
    breaks = sum(1 for a, b in zip(ts, ts[1:]) if (b - a) > BREAK_S)
    submits = [e for e in sorted(evs, key=lambda x: x["_observed_at"])
               if e.get("hook_event_name") == "UserPromptSubmit"]
    switches = sum(1 for a, b in zip(submits, submits[1:])
                   if a["session_id"] != b["session_id"])

    L = ai_labor / active if active else 0
    scope = "today" if today_only else (f"cwd~'{substr}'" if substr else "all history")

    perm_total = sum(st.get("perm_total_s", 0) for st in states.values())
    perm_count = sum(st.get("perm_count", 0) for st in states.values())
    prompt_wait = sum(g for st in states.values()
                      for g in (st.get("a2h_list") or []) if g <= BREAK_S)
    bottleneck = prompt_wait + perm_total
    lev_serial = ai_labor / bottleneck if bottleneck else 0

    print(f"\n=== ROA Report ({scope}) ===\n")
    print("LEVERAGE  (AI productivity per unit of your attention)")
    print(f"  AI working time     {fmt(ai_labor)}   (summed across {len(states)} sessions, parallel adds up; permission excluded)")
    print(f"  Your active time    {fmt(active)}   (wall-clock minus {breaks} breaks >{BREAK_S//60}m)")
    print(f"  Leverage  L         {L:.2f}×   (AI-hours per attention-hour)")
    print(f"  Switches            {switches}   (attention fragmentation)")
    print(f"  Permission wait     {fmt(perm_total)}   ({perm_count}× — agent blocked on you, now out of H2A)")
    if bottleneck:
        print(f"  Time Lev (serial)   {lev_serial:.2f}×   (AI work / your blocking time = prompt≤{BREAK_S//60}m + permission)")

    out_tokens = sum(st.get("out_tokens", 0) for st in states.values())
    total_tokens = sum(st.get("total_tokens", 0) for st in states.values())
    tok_lev = out_tokens / (active / 60) if active else 0
    print("\nTOKENS  (footprint vs real output)")
    print(f"  total tokens        {total_tokens:,}   (incl. cache re-reads — footprint, not work)")
    print(f"  output tokens       {out_tokens:,}   (model-produced — the real work)")
    print(f"  Token Lev           {tok_lev:.0f} tok/min   (output per active minute, speed-invariant)")

    print("\nYOU WAIT AGENT  (H2A)")
    if all_h2a:
        print(f"  turns {len(all_h2a)} · median {fmt(statistics.median(all_h2a))} · "
              f"mean {fmt(sum(all_h2a)/len(all_h2a))} · max {fmt(max(all_h2a))}")
        for b in buckets(all_h2a):
            print(b)

    print("\nAGENT WAITS YOU  (A2H)")
    if all_a2h:
        print(f"  gaps {len(all_a2h)} · median {fmt(statistics.median(all_a2h))} · "
              f"mean {fmt(sum(all_a2h)/len(all_a2h))} (mean is tail-wrecked — use median)")
        for b in buckets(all_a2h):
            print(b)

    print("\nSESSION HEALTH  (closed loops vs lingering open ones)")
    health = []
    for st in states.values():
        ft, lt = st.get("first_ts"), st.get("last_ts")
        if not ft or not lt:
            continue
        lifespan = lt - ft
        agent = st.get("h2a_total_s", 0)
        days = (datetime.date.fromtimestamp(lt) - datetime.date.fromtimestamp(ft)).days
        health.append((st, lifespan, agent, days))
    carry = [h for h in health if h[3] >= 1]   # spans >1 calendar day = not closed same-day
    print(f"  carry-over sessions (open across >1 day): {len(carry)} / {len(health)}")
    if health:
        med_life = statistics.median([h[1] for h in health])
        print(f"  median lifespan {fmt(med_life)}")
    for st, lifespan, agent, days in sorted(health, key=lambda h: h[1], reverse=True)[:8]:
        proj = os.path.basename((st.get("cwd") or "?").rstrip("/")) or "?"
        flag = f"  ⚠ {days}d" if days >= 1 else ""
        drag = f"  drag {lifespan/agent:.0f}×" if agent else ""
        print(f"  {proj[:18]:<18} lifespan {fmt(lifespan):>7} · active {fmt(agent):>7}{drag}{flag}")

    print("\nPER SESSION")
    rows = sorted(states.values(), key=lambda s: s.get("h2a_total_s", 0), reverse=True)
    print(f"  {'project':<20} {'turns':>5} {'you-wait med':>13} {'AI labor':>10}")
    for st in rows:
        proj = os.path.basename((st.get("cwd") or "?").rstrip("/")) or "?"
        h2a = st.get("h2a_list") or []
        med = fmt(statistics.median(h2a)) if h2a else "-"
        print(f"  {proj[:20]:<20} {st['turns']:>5} {med:>13} {fmt(st['h2a_total_s']):>10}")
    print()


if __name__ == "__main__":
    main()
