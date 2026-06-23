#!/usr/bin/env bash
# ROA statusLine entry.
#
# Optionally renders an upstream statusline first, then appends ROA's own lines.
# Set ROA_WRAP to the upstream command (e.g. another statusline renderer) to
# stack ROA below it; leave it unset for a clean ROA-only statusline.
#
# Both the upstream command and ROA get the SAME stdin (the real session JSON,
# including session_id) — captured once so neither has to guess.

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
input=$(cat)

if [ -n "$ROA_WRAP" ]; then
  printf '%s' "$input" | eval "$ROA_WRAP"
fi

printf '%s' "$input" | python3 "$here/hud"
