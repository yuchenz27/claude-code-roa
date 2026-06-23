---
name: setup
description: One-time ROA setup — wire the statusLine HUD into Claude Code, optionally stacking ROA below an existing statusline (e.g. claude-hud). Trigger when the user installs ROA, runs /setup, or asks to enable/turn on the ROA statusline or HUD.
---

# ROA setup

ROA's hooks load automatically with the plugin — data collection starts on its
own. The **only** thing that needs wiring by hand is the statusLine HUD, because
Claude Code has a single `statusLine` slot and plugins cannot set it. This skill
wires it, and — if you already run another statusline like **claude-hud** — stacks
ROA's lines *below* it instead of replacing it.

Keep the repo claude-hud-agnostic: ROA ships only a generic `ROA_WRAP` hook. Any
upstream-specific path is resolved **here, on this machine, at setup time** and
written into the user's settings — never baked into the repo.

## Steps

1. **Resolve ROA's renderer** to an absolute path:
   `${CLAUDE_PLUGIN_ROOT}/bin/statusline.sh`. If `${CLAUDE_PLUGIN_ROOT}` isn't
   available (e.g. running from a clone), ask where ROA lives and use
   `<that path>/bin/statusline.sh`. Call this `ROA_SL`.

2. **Decide whether to stack an upstream statusline.** Read the user settings
   (`~/.claude/settings.json`, or `$CLAUDE_CONFIG_DIR/settings.json`). Determine
   the upstream command, if any, in this order:
   - If a `statusLine` already exists and points at **claude-hud** (or at a
     wrapper that runs it), the user clearly wants claude-hud — plan to wrap it.
   - Else, probe for claude-hud being installed:
     ```bash
     ls -d "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/plugins/cache/claude-hud/claude-hud/*/dist/index.js 2>/dev/null
     ```
     If that matches, ask the user: "claude-hud is installed — stack ROA below it?"
   - Else, no upstream: ROA-only.
   - If a `statusLine` exists pointing at some **other** tool (not claude-hud, not
     ROA), do NOT silently replace it — ask whether to wrap it (set `ROA_WRAP` to
     that command) or leave things alone.

3. **Build the upstream command** (`ROA_WRAP`), only if stacking claude-hud.
   Resolve node and use a **version-proof glob** so claude-hud updates don't break
   it (no hard-coded version). Find node (`command -v node`; fall back to common
   paths like `/opt/homebrew/bin/node`, `/usr/local/bin/node`, `/usr/bin/node`)
   and build:
   ```
   ROA_WRAP = <node> "$(ls -d "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/cache/claude-hud/claude-hud/"*/ 2>/dev/null | sort -V | tail -1)dist/index.js"
   ```
   The `$(...)` resolves the newest installed claude-hud at each statusline render,
   so it survives version bumps. (`ROA_WRAP` is run with the session JSON on stdin,
   so claude-hud gets the real input.)

4. **Compose the `statusLine` command** and write it to settings (idempotent):
   - ROA-only:
     ```json
     "statusLine": { "type": "command", "command": "bash \"<ROA_SL>\"" }
     ```
   - ROA stacked below an upstream (note the single-quoted `ROA_WRAP=...` prefix so
     the inner `$(...)` is evaluated later, by statusline.sh, not now):
     ```json
     "statusLine": { "type": "command", "command": "ROA_WRAP='<ROA_WRAP>' bash \"<ROA_SL>\"" }
     ```
   Create the settings file with `{}` if missing. Preserve every other field.

5. **Confirm and finish.** Tell the user exactly what `statusLine` you wrote,
   whether claude-hud is stacked above, and that they must **restart Claude Code**
   (or start a new session) for the statusLine and freshly-loaded hooks to take
   effect. Mention data lands in `~/.claude/roa/` (override with `ROA_DIR`), and
   that if claude-hud ever stops showing up after an update, re-running `/setup`
   re-resolves it.

## Notes

- Touch only `statusLine`. Hooks come from the plugin automatically; do not add
  hooks or change `permissions` or any other field.
- The repo carries no claude-hud paths — everything claude-hud-specific lives in
  the user's settings, resolved on their machine.
