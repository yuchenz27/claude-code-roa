---
description: Show your Return on Attention report (leverage, tokens, permission, session health)
argument-hint: "[--today] [path-substring]"
allowed-tools: Bash(python3 *)
---

Run the ROA report and show me the result:

```
python3 "${CLAUDE_PLUGIN_ROOT}/bin/report" $ARGUMENTS
```

After printing the raw report, give me a one-sentence read of today's leverage,
token output, and permission-wait — what the numbers say about how I worked.
