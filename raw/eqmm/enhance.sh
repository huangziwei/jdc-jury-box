#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
MAX_JOBS=4  # adjust based on CPU/memory

BETTERIA="$(command -v betteria)" || { echo "betteria not found in PATH" >&2; exit 1; }
command -v pdfinfo >/dev/null || { echo "pdfinfo not found in PATH" >&2; exit 1; }
export BETTERIA DIR

is_enhance_complete() {
    local folder="$1"
    local base
    base="$(basename "$folder")"
    local original="$folder/${base}.original.pdf"
    [[ -f "$original" ]] || return 1
    local pages
    pages="$(pdfinfo "$original" 2>/dev/null | awk '/^Pages:/{print $2}')"
    [[ -n "$pages" ]] || return 1
    local npng
    npng="$(find "$folder/artifacts" -name '*.png' 2>/dev/null | wc -l | tr -d ' ')"
    [[ "$npng" -ge "$pages" ]]
}
export -f is_enhance_complete

# Restore incomplete enhances back to plain PDFs
for folder in "$DIR"/*/; do
    [[ -d "$folder" ]] || continue
    if ! is_enhance_complete "$folder"; then
        base="$(basename "$folder")"
        original="$folder/${base}.original.pdf"
        if [[ -f "$original" ]]; then
            echo "[RESTORE] $base (incomplete: pngs < pages)"
            mv "$original" "$DIR/${base}.pdf"
            rm -rf "$folder"
        fi
    else
        echo "[SKIP] $(basename "$folder") (already enhanced)"
    fi
done

enhance_pdf() {
    local pdf="$1"
    local name
    name="$(basename "$pdf" .pdf)"
    echo "[ENHANCE] $name"
    if "$BETTERIA" enhance "$pdf"; then
        echo "[DONE] $name"
    else
        echo "[FAIL] $name" >&2
        return 1
    fi
}
export -f enhance_pdf

# Process only top-level .pdf files (not yet enhanced)
find "$DIR" -maxdepth 1 -name '*.pdf' -print0 | sort -z | \
    xargs -0 -n 1 -P "$MAX_JOBS" bash -c 'enhance_pdf "$1"' _
