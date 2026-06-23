# ROA — key decisions

Appended in reverse-chronological order. Each entry: **decision + reasoning**
(especially "why not the other way"). This is the project's memory.

## Permission dimension

**D18 · Carve permission wait out of H2A; fold it into A2H.**
The old H2A = submit→stop, which swallowed the time the agent sat blocked on a
permission prompt waiting for you to approve — that's the agent waiting on *you*,
and it falsely inflated the leverage numerator. Fix: a permission `Notification`
(the prompt appeared) plus the next event (usually `PostToolUse` = the tool ran
after approval) bracket the wait; subtract it from H2A and record it as
`perm_total_s/perm_count`. Notification also fires on 60s-idle → filter by
`"permission"` in the message. A denial has no PostToolUse → close on the next
event.

**D17 · Keep the Time Lev denominator as global wall-clock for now (not
Perm+Prompt).** The proposal `Time Lev = AI work / (permission + prompt wait)` is
more Amdahl-pure (denominator = the time you're the bottleneck, excluding "watching
the agent"). But ∑per-session waits double-count overlapping waits under
parallelism, and prompt wait carries the away-time tail (D7). Both are the same
v2 "global attention timeline" problem. So: fix the numerator now (carve out
permission), keep the parallel-safe wall-clock denominator for the headline, and
show the serial approximation in the report only.

**D16 · Notification/PostToolUse mutate state but are not logged; counts use a
word, not `×`.** They're transient timing signals (PostToolUse fires on every
tool call); logging them would bloat the per-day file and break D4's "stay lean".
So they only update state; the per-turn perm delta is stashed on the Stop event
for offline replay. The HUD merges A2H into one line (prompt + perm) and writes
the count as `2 asks`, reserving `×` for multipliers (Leverage).

## Token dimension

**D15 · Tokens only add a dimension; they don't replace time. The denominator
(attention) is the moat.** Leverage = output ÷ attention. The denominator (human
attention) is what sets this tool apart — everything else measures tokens/cost;
nobody measures attention. Making tokens the headline would just measure the same
thing every other tool does. So time-leverage stays primary; tokens are a parallel
complement. The genuinely novel signal is the *divergence* of the two leverages
(burning time on hard problems vs efficiently driving fast models).

**D14 · Leverage's numerator uses output tokens, not total.** Total is ~98%
`cache_read` (the whole context re-read every API call = footprint, not work).
Putting it in leverage would make "bigger context" look like more leverage. Only
output represents production. So: **Token Usage displays total** (answers "how
much did I use"); **Token Leverage uses output**. Note: on a subscription plan
total has little billing meaning — limits are cost-weighted (cache_read ≈ 0.1×
input); what's limited is output + call frequency.

**D13 · Record tokens as a per-turn delta, not a full-transcript cumulative.**
`read_tokens` returns the session's running cumulative; using that directly as
"today's usage" makes a carry-over session dump several days of tokens into today
(observed: a 293M phantom vs a real ~48M). Fix: on Stop record "this turn's
delta", accumulate in `apply_event`, and persist `_out_cum` in state across days
so each day counts only its own. `transcript_path` is read live only, never
logged (per D4); the log stores the delta.

## Foundations

**D12 · Docs as a project under a personal-lab space.** Originally the docs lived
in a notes vault; the code lived in `~/.claude`. (Superseded by the standalone
repo: code + docs now live together in `claude-code-roa`, data stays in
`~/.claude/roa`.)

**D11 · Session health uses a drag ratio to distinguish two kinds of "long".**
A long session is ambiguous: running autonomously for a long time (good, high
leverage) vs dragging across days without closing (bad). `drag = lifespan/active`
separates them — drag 2× is real work, drag 15× is dragging. Metrics: lifespan +
carry-over (spans >1 day) + drag.

**D10 · Drop the journaling step from the daily ritual.** With fleeting notes
captured elsewhere, the sunset ritual no longer scans logs for follow-ups; it
just records the day (`report --record`) and reconstructs "what I worked on" per
project from the agent log.

**D9 · Removed the "you are here" marker.** The statusline doesn't refresh while
idle, so a background session would freeze showing "you are here" — false on
almost every session. Dropped it; kept only the global `Switches` count (a
slightly stale number doesn't mislead).

**D8 · No real-time "agent waits you" stopwatch.** The statusline only refreshes
on activity, so a live `waiting` counter freezes exactly when it matters (your
turn = idle). A separate always-on window would work but is too intrusive. So A2H
keeps a median (computed after the fact, accurate); `running` (while the agent
works) stays, because there's activity to refresh it then.

**D7 · A2H uses a median, not a threshold.** The real stop→submit distribution has
no natural cutoff (a smooth long tail), so any threshold (e.g. 15 min) is an
arbitrary hard cut. The median dodges the overnight tail with no parameter. The
mean is wrecked by the tail (40 min vs a 2.5 min median) — discarded.

**D6 · L is a directional dashboard, not a precise score.** The denominator
(Human Time) is a coarse proxy (a 30-min threshold slices the workday; it can't
see real focus). So L is for comparison/trends (today vs history, conduct vs
orchestrate), not an exact value. Tightening it requires a presence signal (HID
idle) — and even that is only a tighter estimate.

**D5 · Core metric = Leverage L = AI working time / human attention.** From first
principles: the goal is to move the most AI output with the least attention.
Amdahl — attention is the only serial station. Agent Time sums across parallel
sessions (numerator); Human Time is a single global timeline (denominator).

**D4 · Per-day files; keep prompt & reply, drop noise.** Per-day logs
(`observer-YYYY-MM-DD.jsonl`) mean the HUD only scans today → always fast, and
cleanup is just deleting old day-files. Keep `prompt` + `last_assistant_message`
(the reply = each turn's output, a gold signal for task tracking); drop
`transcript_path` and other noise; cap prompt/reply at 2000 chars.

**D3 · The HUD appends below an optional upstream statusline; no fork.** Originally
this wrapped a specific statusline tool; now an upstream command is optional via
`ROA_WRAP`, and ROA's lines are appended below. The wrapper feeds the same stdin
to both, so ROA's renderer gets the real `session_id` (no cwd guessing). Rejected:
forking the upstream tool (maintenance burden); using its tiny extra-cmd slot
(can't produce independent lines or control placement).

**D2 · Pair events per session_id.** In the global log, events from parallel
sessions interleave, so submit/stop must be paired within a session_id or they
mismatch. Handles back-to-back submits (take the latest = the real start).

**D1 · Collect via hooks, stamp our own timestamps.** Hook the
`UserPromptSubmit` + `Stop` (later + `Notification` + `PostToolUse`) lifecycle
events. Claude Code payloads carry no timestamp, so use the script's own
`_observed_at`. Hooks over pure log-parsing: real-time, self-contained.
