# Claude Code ROA — agent context

ROA (Return on Attention) measures how much agent work each hour of your attention
moves, from Claude Code's own hooks. **What it is / how to use it → `README.md`.**
This file is the contract for *editing* the codebase: the map, the invariants, and
where the depth lives. Keep it lean — it loads into every session.

## Map — where to look

- `src/roa/core.py` — **pure** logic: event pairing, token accounting, permission
  bracketing (`new_state`, `apply_event`, `read_tokens`). No I/O; replayable offline.
- `src/roa/tracker.py` — the hook (thin I/O around core): per-day log + state files.
- `src/roa/hud.py` — statusline rendering · `src/roa/report.py` — offline report.
- `src/roa/paths.py` — the data-dir resolver (`$ROA_DIR` → `~/.claude/roa`).
- `bin/{track,report,hud,statusline.sh}` — entrypoints hooks & statusline call.
- `hooks/` `commands/` `skills/` `.claude-plugin/` — the Claude Code plugin shell.
- `docs/design.md` — architecture, data model, metric definitions ·
  `docs/decisions.md` — decision log (the *why*, with Dn ids) ·
  `docs/overview.md` — thesis + status + roadmap.

## Invariants — violate these and it breaks

1. **A hook must never error or block.** `tracker.main` is wrapped in try/except and
   exits 0. Anything on the hook path must fail silently.
2. **Code and data are separate.** Data lives at `paths.data_dir()`, never in the
   repo. Never hardcode a data path; never write data into the repo tree.
3. **`core.py` stays pure and replayable.** Report and tests both replay raw logs
   through `apply_event`. New metric logic goes in core; per-turn values that need
   offline replay get stashed on the Stop event (like `_perm_s`, `_out_tokens`) and
   added to `KEEP_FIELDS`.
4. **The observer log is lean — submit/stop only.** Notification & PostToolUse are
   timing signals: they mutate state but are NOT logged.
5. **The repo is statusline-agnostic.** No claude-hud (or any upstream) specifics in
   the repo — composition is only via the generic `ROA_WRAP` hook in `statusline.sh`.
6. **Leverage's numerator is output tokens, not total** (total is ~98% cache
   re-reads = footprint, not work; see decisions D14).
7. **Honesty: it's a directional dashboard, not a precise score** (D6). `×` is for
   multipliers only; counts use a word (`N asks`).

## Dev loop

- Plain Python, no build step — edit and it's live on the next hook fire.
- Tests (zero deps): `python3 tests/test_core.py`.
- You dogfood against a working copy: your personal hooks point at this repo's
  `bin/track`; data stays in `~/.claude/roa`. `/plugin install` is for other people.

## When you change behavior

- Architecture/metrics changed → update `docs/design.md`.
- Made a non-obvious call → append it to `docs/decisions.md` (decision + why-not).
- HUD layout changed → refresh the README screenshot (`assets/hud.png`) + its numbers.
