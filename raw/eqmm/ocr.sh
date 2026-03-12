#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

BETTERIA="$(command -v betteria)" || { echo "betteria not found in PATH" >&2; exit 1; }

for folder in "$DIR"/*/; do
    [[ -d "$folder" ]] || continue
    base="$(basename "$folder")"

    # Skip if no artifacts (enhance not done)
    [[ -d "$folder/artifacts" ]] || continue

    echo "[OCR] $base"
    if "$BETTERIA" ocr "$folder"; then
        echo "[DONE] $base"
    else
        echo "[FAIL] $base" >&2
    fi
done
