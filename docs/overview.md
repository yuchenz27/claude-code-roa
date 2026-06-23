# ROA — overview

A tool that records the state of *human–AI collaboration* while you use coding
agents (Claude Code and friends). The central metric is **leverage**: the most
AI productivity moved per unit of the scarcest resource — **human attention**,
not tokens.

## What it's for

When you work with agents, the bottleneck is your attention, not compute. ROA
quantifies and tracks the attention side of the loop, for two purposes:
1. **Self-tracking** — am I conducting (1:1, leverage ≈ 1) or orchestrating
   (parallel, leverage ≫ 1)? Is my leverage trending up?
2. **Evidence** — real data for the argument that attention is the serial
   bottleneck of agentic work.

## Status

- **Data collection** — hooks on submit / stop / notification / posttooluse.
- **Live HUD** — H2A, A2H (prompt + permission), and two `Today` bands.
- **Offline report** — `bin/report` (`--today`, cwd filter, `--record`), with
  leverage, tokens, permission, and session health.
- **Daily trend** — `daily.jsonl`, one permanent line per day.
- **Token dimension** — per-turn output/total token deltas from the transcript;
  Token Leverage uses output, not total (see decisions).
- **Permission dimension** — the time the agent spends blocked on your approval
  is carved out of H2A and tracked separately.

## Roadmap (v2 ideas)

- A global attention timeline (resolves the parallel double-count in A2H and the
  "pure" Time Lev denominator at once).
- A presence signal (HID idle) to tighten the Human Time proxy.
- Log retention / cleanup automation.

See **[design.md](design.md)** for architecture and metric definitions, and
**[decisions.md](decisions.md)** for the running decision log.
