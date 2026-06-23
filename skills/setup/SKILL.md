---
name: setup
description: One-time ROA setup — wire the statusLine HUD into Claude Code. Trigger when the user installs ROA, runs /roa setup, or asks to enable/turn on the ROA statusline or HUD.
---

# ROA setup

ROA's hooks load automatically with the plugin — data collection starts on its
own. The **only** thing that needs wiring by hand is the statusLine HUD, because
plugins cannot set `statusLine`. This skill does that wiring.

## Steps

1. **Find the renderer.** It ships with this plugin at
   `${CLAUDE_PLUGIN_ROOT}/bin/statusline.sh`. Resolve that to an absolute path
   (the user's settings file needs a concrete path, not the variable). If
   `${CLAUDE_PLUGIN_ROOT}` is unavailable in this context, ask the user where
   they cloned/installed ROA and use `<that path>/bin/statusline.sh`.

2. **Read the user settings** at `~/.claude/settings.json` (or
   `$CLAUDE_CONFIG_DIR/settings.json` if that env var is set). Create the file
   with `{}` if it does not exist.

3. **Wire the statusLine, idempotently.** Set:
   ```json
   "statusLine": {
     "type": "command",
     "command": "bash \"<absolute path>/bin/statusline.sh\""
   }
   ```
   - If a `statusLine` already exists and is some OTHER command (e.g. another
     statusline tool the user already runs), DO NOT clobber it. Tell the user
     they can stack ROA below it by setting the `ROA_WRAP` env var to their
     existing command, then pointing `statusLine` at ROA's `statusline.sh`.
     Ask before overwriting.
   - If `statusLine` is missing or already points at ROA, just write it.

4. **Confirm** what you changed and tell the user to restart Claude Code (or
   start a new session) for the statusLine and the freshly-loaded hooks to take
   effect. Mention that data lands in `~/.claude/roa/` (override with `ROA_DIR`).

## Notes

- Do not touch `permissions`, `hooks`, or any other settings field — hooks come
  from the plugin automatically; only `statusLine` is yours to set here.
- ROA never edits files outside the user's settings during setup.
