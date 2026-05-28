#!/usr/bin/env bash
# SessionStart context injector for the token-optimized docs.
#
# Strategy: only docs needing PROACTIVE awareness are injected in full —
# COMMON_MISTAKES (can't lazy-load a warning about a mistake you're about to
# make) and DOCUMENTATION_MAINTENANCE (drives doc-update behavior). The large
# REFERENCE docs (ARCHITECTURE_MAP, QUICK_START) are injected as one-line
# pointers; Claude loads the full file on demand. The files themselves stay
# complete — only the per-session injection shrinks.
#
# A freshness banner covers ALL tracked docs (full + pointered) so a stale doc
# is obvious before it's trusted. Output is wrapped as SessionStart JSON.
set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"

# Injected in full (proactive awareness).
FULL_DOCS=(
    .claude/COMMON_MISTAKES.md
    .claude/DOCUMENTATION_MAINTENANCE.md
)

# Injected as a pointer line only (lazy-loaded on demand). Format: "path|hint".
POINTER_DOCS=(
    ".claude/ARCHITECTURE_MAP.md|file locations + full js/ & gedcom_merge/ inventory — load when you need to find where code lives"
    ".claude/QUICK_START.md|commands (dev server, tests, merge, lint) — load when you need to run something; canonical GED path is in COMMON_MISTAKES #1"
    "docs/INDEX.md|full doc map + which learnings/ deep dive to load when — keep its file list in sync when adding a learnings doc"
)

# Every doc that gets a freshness check (full + pointered).
ALL_DOCS=("${FULL_DOCS[@]}")
for entry in "${POINTER_DOCS[@]}"; do ALL_DOCS+=("${entry%%|*}"); done

doc_age_days() {
    # Echo days since the file's "Last Updated" date, or empty if none/unparseable.
    local f="$1" d then now
    d=$(grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' "$f" 2>/dev/null | tail -1) || true
    [ -n "$d" ] || return 0
    then=$(date -j -f '%Y-%m-%d' "$d" +%s 2>/dev/null) || return 0
    now=$(date +%s)
    echo $(( (now - then) / 86400 ))
}

{
    printf '===== DOC FRESHNESS (update stale docs per DOCUMENTATION_MAINTENANCE.md) =====\n'
    for f in "${ALL_DOCS[@]}"; do
        age=$(doc_age_days "$f")
        if [ -n "$age" ]; then
            flag=""
            [ "$age" -gt 30 ] && flag="  ⚠️ STALE — verify against code before trusting"
            printf '%-40s %s days old%s\n' "$f" "$age" "$flag"
        else
            printf '%-40s (no Last Updated date)\n' "$f"
        fi
    done

    for f in "${FULL_DOCS[@]}"; do
        printf '\n===== %s =====\n' "$f"
        cat "$f" 2>/dev/null || true
    done

    printf '\n===== LOAD ON DEMAND (not injected to save tokens — Read when relevant) =====\n'
    for entry in "${POINTER_DOCS[@]}"; do
        printf '  %s — %s\n' "${entry%%|*}" "${entry#*|}"
    done
    printf '  docs/learnings/*.md — deep dives; see docs/INDEX.md for which to load when\n'
} | jq -Rs '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: .}}'
