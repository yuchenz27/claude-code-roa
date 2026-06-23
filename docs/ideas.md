# ROA — ideas & backlog

Loose and unprioritized — a place to park forward-looking ideas and deferred work
so they aren't lost. **Not** a committed roadmap; promote an item into a branch when
it's worth building. Settled choices live in [decisions.md](decisions.md); this is
the "maybe / later".

## Metrics & signals

- **Global attention timeline (v2).** The keystone: it resolves the parallel
  double-count in A2H and unlocks the "pure" Time Lev denominator (AI work ÷ the time
  you're the bottleneck, excluding watch time) — one fix for both.
- **Per-session leverage as a health signal.** The ideal "is this session a good
  attention investment?" measure, but it needs the v2 attention denominator before
  it's trustworthy per-session (parallel overlap inflates a single session's A2H).
- **"Loops closed today" (global).** Reward closing sessions = freeing attention.
  Count same-day closed sessions that did real work; weight by agent-work delivered so
  a trivial session ≠ a big one. Pairs with Switches (close loops vs. over-fragment).
  Deferred to the offline report until a reliable live "is it closed" signal exists.
- **Presence signal (HID idle).** Tighten the Human Time proxy — tell "reading" from
  "away" instead of the coarse 30-min break cutoff.

## Tuning

- **Session-health drag thresholds** (aging >5× or carried over a day, draining >15×)
  are a first pass from real data — recalibrate as more accrues.

## Ops

- **Log retention / cleanup** for the per-day observer files.
- **Verify `${CLAUDE_PLUGIN_ROOT}`** resolves on a real `/plugin install` — the one
  piece never tested outside the working copy. Fall back to `bin/` on `PATH` if not.
