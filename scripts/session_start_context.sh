#!/usr/bin/env bash
# SessionStart context injector for the token-optimized docs.
#
# Emits a short freshness banner (how old each always-loaded doc is, from its
# "Last Updated: YYYY-MM-DD" line) followed by the doc contents, then wraps the
# whole thing as SessionStart additionalContext JSON. A visible age makes a
# stale doc obvious instead of silently trusted.
set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"

DOCS=(
    .claude/COMMON_MISTAKES.md
    .claude/QUICK_START.md
    .claude/ARCHITECTURE_MAP.md
    .claude/DOCUMENTATION_MAINTENANCE.md
)

doc_age_days() {
    # Echo days since the file's "Last Updated" date, or empty if none/unparseable.
    local f="$1" d
    d=$(grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' "$f" 2>/dev/null | tail -1) || true
    [ -n "$d" ] || return 0
    local then now
    then=$(date -j -f '%Y-%m-%d' "$d" +%s 2>/dev/null) || return 0
    now=$(date +%s)
    echo $(( (now - then) / 86400 ))
}

{
    printf '===== DOC FRESHNESS (update stale docs per DOCUMENTATION_MAINTENANCE.md) =====\n'
    for f in "${DOCS[@]}"; do
        age=$(doc_age_days "$f")
        if [ -n "$age" ]; then
            flag=""
            [ "$age" -gt 30 ] && flag="  ⚠️ STALE — verify against code before trusting"
            printf '%-40s %s days old%s\n' "$f" "$age" "$flag"
        else
            printf '%-40s (no Last Updated date)\n' "$f"
        fi
    done
    for f in "${DOCS[@]}"; do
        printf '\n===== %s =====\n' "$f"
        cat "$f" 2>/dev/null || true
    done
} | jq -Rs '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: .}}'
