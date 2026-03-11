#!/usr/bin/env bash
#
# download_carr_eqmm.sh
#
# Downloads EQMM issues from Jan 1969 – Nov 1976 (the span of
# John Dickson Carr's "Best Mysteries of the Month" / "The Jury Box"
# review columns) from the Internet Archive pulp magazine scan collection.
#
# Usage:
#   chmod +x download_carr_eqmm.sh
#   ./download_carr_eqmm.sh            # dry run (list files only)
#   ./download_carr_eqmm.sh --download  # actually download
#
# Requirements: curl, grep, sed, unzip, img2pdf (for CBZ/CBR→PDF conversion)
# Downloads go into: current directory

set -euo pipefail

BASE_URL="https://archive.org/download/detective-mystery-pulp-magazine-scans/Detective-Mystery%20Pulp%20Torrent/Ellery%20Queen%27s%20Mystery%20Magazine%20-%20US"
OUTDIR="."
DOWNLOAD=false

if [[ "${1:-}" == "--download" ]]; then
    DOWNLOAD=true
fi

# Months Carr's column appeared (for filtering).
# Format: YYYY-MM. Gaps: 1971-03, 1973-07, 1976-06, 1976-07.
# We also grab Nov 1976 (his name in TOC) for completeness.
# Use a space-delimited string (bash 3.2 compat — no associative arrays).
CARR_MONTHS=" "
for y in $(seq 1969 1976); do
    for m in $(seq -w 1 12); do
        ym="${y}-${m}"
        # Skip months after Nov 1976 (strip leading zero for safe arithmetic)
        [[ "$y" -eq 1976 && "${m#0}" -gt 11 ]] && continue
        # Known gaps
        [[ "$ym" == "1971-03" ]] && continue
        [[ "$ym" == "1973-07" ]] && continue
        [[ "$ym" == "1976-06" ]] && continue
        [[ "$ym" == "1976-07" ]] && continue
        CARR_MONTHS="${CARR_MONTHS}${ym} "
    done
done

echo "=========================================="
echo " EQMM Carr Column Downloader"
echo "=========================================="
echo ""
echo "Looking for EQMM issues: Jan 1969 – Nov 1976"
echo "Expected columns: ~91 (with 4 known gaps)"
echo ""

if [[ "$DOWNLOAD" == true ]]; then
    mkdir -p "$OUTDIR"
    echo "Download mode ON — files go to $OUTDIR/"
else
    echo "DRY RUN — pass --download to actually fetch files"
fi
echo ""

# Archive structure:
#   .../Ellery Queen's Mystery Magazine - US/
#       1960-1969/
#           1969/
#               Ellery Queen's Mystery Magazine #302v53 (1969-01).cbz
#               ...
#       1970-1979/
#           1970/
#               ...
# So we iterate: decade -> year -> files in that year directory.

# Convert a CBZ/CBR file to PDF.
# CBZ = zip of images, CBR = rar of images.
# Extracts images, sorts them, and combines into a single PDF via img2pdf.
cbz_to_pdf() {
    local infile="$1"
    local outpdf="$2"
    local tmpdir
    tmpdir=$(mktemp -d)

    local ext_lower
    ext_lower=$(echo "${infile##*.}" | tr '[:upper:]' '[:lower:]')

    # Extract images (try multiple tools as fallback).
    # Note: 7z may exit non-zero for partially corrupt archives but still
    # extract usable files, so we don't rely on exit codes alone.
    if [[ "$ext_lower" == "cbz" ]]; then
        unzip -q -j "$infile" -d "$tmpdir" 2>/dev/null \
            || 7z x -o"$tmpdir" "$infile" >/dev/null 2>&1 \
            || true
    elif [[ "$ext_lower" == "cbr" ]]; then
        if command -v unrar >/dev/null 2>&1; then
            unrar x -inul "$infile" "$tmpdir/" 2>/dev/null || true
        fi
        # Try 7z as fallback (or primary if unrar not installed)
        if [[ -z "$(find "$tmpdir" -type f -size +0 2>/dev/null | head -1)" ]]; then
            7z x -o"$tmpdir" "$infile" >/dev/null 2>&1 || true
        fi
    fi

    # Collect non-empty image files sorted by name (find images in subdirs too)
    local images
    images=$(find "$tmpdir" -type f -size +0 \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.gif' -o -iname '*.webp' -o -iname '*.tif' -o -iname '*.tiff' \) | sort)

    if [[ -z "$images" ]]; then
        echo "         ERROR: no images found in archive"
        rm -rf "$tmpdir"
        return 1
    fi

    # Build PDF with img2pdf (lossless — no re-encoding)
    echo "$images" | tr '\n' '\0' | xargs -0 img2pdf -o "$outpdf" 2>/dev/null || {
        echo "         ERROR: img2pdf failed"
        rm -rf "$tmpdir"
        return 1
    }

    rm -rf "$tmpdir"
    return 0
}

# Map each year to its decade directory
decade_for_year() {
    local y=$1
    if [[ "$y" -le 1969 ]]; then
        echo "1960-1969"
    else
        echo "1970-1979"
    fi
}

found=0
converted=0
skipped=0
errors=0

for year in $(seq 1969 1976); do
    decade=$(decade_for_year "$year")
    year_url="${BASE_URL}/${decade}/${year}/"

    echo "--- Scanning ${decade}/${year}/ ---"

    # Fetch directory listing for this year
    listing=$(curl -sL "$year_url" 2>/dev/null || true)

    if [[ -z "$listing" ]]; then
        echo "  WARNING: Could not fetch listing for ${decade}/${year}"
        ((errors++)) || true
        echo ""
        continue
    fi

    # Extract href values from HTML, filter for scan file extensions
    # Use grep -oE + sed (macOS BSD grep has no -P flag)
    files=$(echo "$listing" | grep -oE 'href="[^"]+"' | sed 's/^href="//;s/"$//' \
        | grep -iE '\.(pdf|cbr|cbz|djvu)$' || true)

    if [[ -z "$files" ]]; then
        echo "  WARNING: No files found in ${decade}/${year}"
        echo ""
        continue
    fi

    while IFS= read -r href_value; do
        [[ -z "$href_value" ]] && continue

        # Decode percent-encoding for display and matching
        decoded=$(printf '%b' "${href_value//%/\\x}" 2>/dev/null || echo "$href_value")

        # Try to extract YYYY-MM from the filename
        # The IA filenames consistently use (YYYY-MM) in parentheses
        matched_month=""
        if echo "$decoded" | grep -qE "\(${year}-[0-9]{2}\)"; then
            matched_month=$(echo "$decoded" | sed -n "s/.*(\(${year}-\([0-9][0-9]\)\)).*/\2/p")
        fi

        # Fallback: try YYYY-MM without parens
        if [[ -z "$matched_month" ]]; then
            if echo "$decoded" | grep -qE "${year}-[0-9]{2}"; then
                matched_month=$(echo "$decoded" | sed -n "s/.*${year}-\([0-9][0-9]\).*/\1/p")
            fi
        fi

        if [[ -z "$matched_month" ]]; then
            echo "  [UNKNOWN MONTH] <- $decoded"
            continue
        fi

        ym="${year}-${matched_month}"
        if [[ "$CARR_MONTHS" == *" ${ym} "* ]]; then
            ((found++)) || true
            echo "  [MATCH] $ym  <- $decoded"
            if [[ "$DOWNLOAD" == true ]]; then
                file_url="${year_url}${href_value}"
                # Build a clean output filename
                ext="${decoded##*.}"
                outfile="${OUTDIR}/EQMM_${year}-${matched_month}.${ext}"
                pdffile="${OUTDIR}/EQMM_${year}-${matched_month}.pdf"
                if [[ -f "$pdffile" ]]; then
                    echo "         (PDF already exists, skipping)"
                elif [[ -f "$outfile" ]]; then
                    echo "         (already downloaded, skipping download)"
                else
                    echo "         Downloading..."
                    curl -sL -o "$outfile" "$file_url" || {
                        echo "         ERROR: download failed"
                        ((errors++)) || true
                    }
                fi
                # Convert CBZ/CBR to PDF if needed
                ext_lower=$(echo "$ext" | tr '[:upper:]' '[:lower:]')
                if [[ "$ext_lower" == "cbz" || "$ext_lower" == "cbr" ]] \
                    && [[ -f "$outfile" ]] && [[ ! -f "$pdffile" ]]; then
                    echo "         Converting $ext -> PDF..."
                    if cbz_to_pdf "$outfile" "$pdffile"; then
                        ((converted++)) || true
                        echo "         OK: $pdffile"
                        rm -f "$outfile"
                    else
                        ((errors++)) || true
                    fi
                fi
            fi
        else
            ((skipped++)) || true
        fi

    done <<< "$files"

    echo ""
done

echo "=========================================="
echo " Summary"
echo "=========================================="
echo "  Matched (in Carr range):  $found"
echo "  Converted to PDF:         $converted"
echo "  Outside range (skipped):  $skipped"
echo "  Errors:                   $errors"
echo ""

if [[ "$DOWNLOAD" == false ]]; then
    echo "This was a dry run. To download, run:"
    echo "  ./download_carr_eqmm.sh --download"
fi
echo ""
echo "Expected: ~91 issues (Jan 1969 – Nov 1976 minus 4 gaps)"
echo "If fewer matched, the scan collection may be incomplete"
echo "or filenames may use an unexpected format."
echo ""
echo "After downloading, look for the review column near the back"
echo "of each issue (typically the last 2-3 pages before ads)."
echo "Column title: 'Best Mysteries of the Month' (1969-Apr 1970)"
echo "              'The Jury Box' (May 1970-Oct 1976)"
