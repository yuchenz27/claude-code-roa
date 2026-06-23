# ROA — design

## Questions it answers

1. While using agents, how much is **you-waiting-the-machine vs machine-waiting-you**?
2. **Leverage**: how much AI working-time does one unit of your attention buy?
   (conduct ≈ 1, orchestrate/parallel ≫ 1)
3. **Fragmentation**: how often do you switch between sessions in a day?
4. **Decomposition quality**: do sessions close same-day, or drag across days?
5. Honesty: all of this is coarse — a directional dashboard, not a precise score.

## Architecture: one brain, many faces, all-local data

```
Claude Code events
   │ (hooks: UserPromptSubmit / Stop / Notification / PostToolUse)
   ▼
tracker.py ──► observer-YYYY-MM-DD.jsonl  (per-day log; submit/stop only, with per-turn token+perm deltas)
           ├─► state/<session_id>.json    (per-session totals: H2A/A2H/perm/tokens/first_ts/last_ts)
           ├─► active.json                (active session + today's switches)
           ├─(on Stop)► read transcript_path -> cumulative tokens -> record per-turn delta
           └─(Notification[perm] / PostToolUse)► bracket the permission wait (state only, not logged)

statusline.sh ─► optional upstream wrap (ROA_WRAP)
              └─► hud.py ─► read state/active/today's log ─► print ROA's HUD lines

report.py ─► replay per-day logs (pairing) ─► Leverage / TOKENS / distributions / SESSION HEALTH
          └─► --record ─► daily.jsonl    (permanent daily trend)
```

## Components

| Path | Responsibility |
|---|---|
| `src/roa/core.py` | Pure logic: `new_state`, `apply_event`, `read_tokens`, `is_perm_notification`, formatters. Replayable offline; what the tests drive. |
| `src/roa/tracker.py` | Hook I/O. submit/stop: write the per-day log + update state. Notification/PostToolUse: bracket the permission wait (state only, not logged). On Stop: read the transcript for the token delta. |
| `src/roa/hud.py` | Render the statusline lines (this-session H2A / A2H, plus two global `Today` bands). |
| `src/roa/report.py` | Offline report (Leverage, TOKENS, permission, session health) + `--record`. |
| `src/roa/paths.py` | Resolve the data dir (`ROA_DIR` → `$CLAUDE_CONFIG_DIR/roa` → `~/.claude/roa`). |
| `bin/{track,report,hud}` | Thin entrypoints that put `src/` on the path and call the package. |
| `bin/statusline.sh` | statusLine entry; optionally wraps an upstream command via `ROA_WRAP`. |

## Data model

**Raw log** (`observer-YYYY-MM-DD.jsonl`, one event per line, per day): only
**submit / stop** are logged (Notification and PostToolUse are transient timing
signals — kept out of the log to stay lean). Fields: `_observed_at` (our own
timestamp — the sole timing source, since Claude Code payloads carry none),
`session_id`, `cwd`, `hook_event_name`, `prompt`, `last_assistant_message` (each
capped at 2000 chars). Stop events also carry `_out_tokens`/`_total_tokens` (the
turn's token delta) and `_perm_s`/`_perm_n` (the turn's permission wait / count).
These deltas let offline replay reconstruct tokens and permission.

**Per-session state** (`state/<sid>.json`): `first_ts/last_ts`, `turns`,
`h2a_list/h2a_total_s`, `a2h_list/a2h_total_s`, `perm_total_s/perm_count`,
`out_tokens/total_tokens`, `last_event`; plus live-only fields `_pending_perm_ts`
(an open permission prompt), `_turn_perm_s/_turn_perm_n` (current turn's perm),
`_out_cum/_tot_cum` (last transcript token cumulative, for delta computation).

**Global**: `active.json` (active_sid + today's switches); `daily.jsonl` (one
permanent summary line per day — leverage / tokens / perm).

## Metric definitions

- **H2A** (*you wait the agent*) = (submit → stop) **− this turn's permission
  wait** = real agent working time. Bounded per turn, no overnight tail → shown
  as last/avg/total/turns, with a live `running` while the agent works.
- **A2H** (*the agent waits you*) = two parts, one HUD line:
  - **prompt wait** = stop → next submit (turn boundary). Heavy-tailed (mixes in
    you stepping away) → shown as a **median** (marked `~`, no threshold).
  - **permission wait** = mid-turn, blocked on your approval. Bracketed by a
    permission `Notification` (start) and the next event (end; usually
    `PostToolUse` = the tool ran after you approved); waits > 30 min count as
    stepping away. Short and bounded → shown as **total + count** (`perm 1m20s ·
    2 asks`). Carved out of H2A, folded into A2H.
- **Leverage L** = Agent Time / Human Time.
  - **Agent Time** = sum of H2A across all sessions (permission excluded; parallel
    adds up, so it can exceed wall-clock).
  - **Human Time** = global event timeline, summing gaps ≤ 30 min (drops long
    breaks). A coarse proxy for attention.
  - **Time Lev (serial)** = Agent Time / (∑ prompt wait ≤30m + ∑ permission) — "AI
    work ÷ the time you were the bottleneck", closer to Amdahl. But summing
    per-session double-counts overlapping waits under parallelism, so it's shown
    in the report only as a reference; the headline keeps the parallel-safe
    Human Time version.
- **Tokens** (per Stop, a transcript delta accumulated):
  - **total** = output + input + cache_creation + cache_read (~90%+ is cache_read
    = the same context re-read every turn → a footprint; for **display**).
  - **output** = model-produced tokens (the real work).
  - **Token Lev** = output ÷ active minutes (speed-invariant output density).
    Numerator is output, not total (see decisions).
- **Switches** = session changes between consecutive submits (today).
- **Session health**: `lifespan` (first→last), `carry-over` (spans >1 calendar
  day), `drag = lifespan/active` (high = lingering, low = real autonomous work).

## HUD layout

```
Output Style: <style>
H2A ｜ last · avg · total · turns · running              (this session; permission excluded)
A2H ｜ prompt ~median · perm <total> · N asks            (this session; perm shown only if any)
Today ｜ Agent Time · Human Time · Time Lev · Switches    (global/today; neon, "Today ｜" prefix)
Today ｜ Tokens <total> · out <output>                   (global/today; footprint + real output)
```

Separators: `｜` between the label and its metrics, `·` between metrics. Note `×`
is reserved for multipliers (Leverage); counts use a word (`N asks`) to avoid
ambiguity.

## Boundaries and honesty

- Human Time is a **coarse proxy** (a 30-min threshold slices the workday, not
  real focus). Use L for trends/comparisons, not as an exact score.
- "Reading vs away" can't be told apart without a presence signal — hence A2H
  prompt wait uses a median, not a hard cutoff.
- Per-session A2H is fundamentally ambiguous under parallelism (your attention
  can't be in two places). The fix is a **global attention timeline** (v2). The
  "pure" Time Lev denominator (excluding watch time) is the same problem, so it
  ships with v2; for now we only carve permission cleanly out of the numerator.
- Permission end signal: approval flows through `PostToolUse` (accurate); a
  denial has no PostToolUse, so the wait is closed by "the next event of any
  kind", which can be slightly off.
- Token total is ~90%+ cache re-reads and has little billing meaning on a
  subscription plan (limits are cost-weighted; cache_read counts at ~0.1× input).
  Treat total as a footprint; **output** is the real work.
- `PostToolUse` fires the tracker on every tool call (cheap: read/write a small
  state file, then return; not logged), but raises the hook-invocation count.
