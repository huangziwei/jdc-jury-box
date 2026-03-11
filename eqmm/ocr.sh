#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

BETTERIA="$(command -v betteria)" || { echo "betteria not found in PATH" >&2; exit 1; }

# Process each enhanced folder sequentially
for folder in "$DIR"/*/; do
    [[ -d "$folder" ]] || continue
    base="$(basename "$folder")"
    enhanced="$folder/${base}.pdf"

    # Skip if not enhanced yet or already OCR'd
    [[ -f "$enhanced" ]] || continue
    if [[ -f "$folder/${base}.txt" ]]; then
        echo "[SKIP] $base (already OCR'd)"
        continue
    fi

    echo "[OCR] $base"
    if "$BETTERIA" ocr "$folder"; then
        echo "[DONE] $base"
    else
        echo "[FAIL] $base" >&2
    fi
done
