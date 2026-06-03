Proofread and compile a magazine review article. The article directory is: `$ARGUMENTS`

This command processes extracted magazine pages containing John Dickson Carr's book review columns. Each article folder contains 2-4 page scans (PNG + OCR text) from a single issue. You will proofread the OCR text against the page images and produce a clean markdown article.

You will work through three phases. Be methodical and thorough.

---

## Phase 0: Validate prerequisites

1. Glob `$ARGUMENTS/*.png` to get all page images.
2. Glob `$ARGUMENTS/*.txt` (excluding `*.proofread.txt` and `structure.md`) to get all OCR text files.
3. Verify that every PNG has a matching `.txt` file. If any are missing, **stop and warn the user** — OCR needs to be run first.
4. Identify the **source publication** from the folder path:
   - Path contains `post/eqmm/` → *Ellery Queen's Mystery Magazine*
   - Path contains `post/harper/` → *Harper's Magazine*
5. Extract the **date** from the folder name:
   - `YYYY-MM` format → month and year (e.g. `1969-01` → January 1969)
   - `YYYY` format → year only (e.g. `1964` → 1964)

---

## Phase 1: Survey the article

Since each article is only 2-4 pages, read **every** page — but only one PNG at a time.

1. For each page, read the PNG (vision) and the OCR `.txt` side by side.
2. Determine:
   - **Column title**: e.g. "The Jury Box", "Best Mysteries of the Month", "Murder-fancier Recommends"
   - **Running headers/page numbers**: note the pattern so they can be stripped (e.g. page number at top, column title as running header)
   - **Non-Carr content to strip**: ads, other columns, copyright notices, illustrations, editorial matter that shares the page
   - **Subsection titles** within the article (if any): e.g. "Religion in the Desert", "No Place for Anyone"
   - **Books reviewed**: list each book title and author mentioned
   - **Known OCR errors**: note obvious errors spotted during the survey for fixing in Phase 2
   - **Provenance**: the printed page numbers (from the running headers) and any ProQuest/source header (publication, volume, issue, date) — recorded later as `pages` and `citation` in the metadata

Write a brief summary of your findings in `$ARGUMENTS/structure.md` before proceeding.

---

## Phase 2: Page-by-page proofreading

### Resumability

Before processing a page, check if its `.proofread.txt` file already exists (e.g. `page-1.proofread.txt` for `page-1.png`). If it does, **skip that page**. But always verify the last existing proofread file before moving on.

### Processing each page

Process **one page at a time**, sequentially. Do NOT use batch processing or subagents. For each page:

1. Read the PNG via vision and the OCR `.txt` file side by side.
2. Produce corrected text:
   - **Fix OCR errors** by comparing what you see in the PNG against the OCR text. Trust vision over OCR when they disagree.
   - **Strip running headers** (identified in Phase 1) from the top of the page.
   - **Strip page numbers** from wherever they appear.
   - **Strip non-Carr content**: ads, other columns, copyright notices, editorial matter, illustrations. Do NOT insert any placeholder — just omit silently. Keep the Carr review text only.
   - **Strip footnote anchors**: remove superscript footnote markers from the body text.
   - **Preserve paragraph structure** — maintain paragraph breaks as they appear in the original.
   - **Join lines within paragraphs**: OCR text has hard line breaks at page-width boundaries. Join these into single continuous lines per paragraph. Only paragraph breaks (double newlines) should separate paragraphs.
   - If a page contains no Carr review text at all, write `[BLANK PAGE]` as its content.

3. **Markdown formatting**:
   - `*italic*` for italic text
   - `**bold**` for bold text (e.g. first mention of a reviewed book title)
   - **Headings**: Use proper markdown heading syntax, not bold:
     - `##` for the column/article title (e.g. `## The Jury Box`)
     - `###` for subsection titles within the article
     - **NEVER use bold (`**text**`) for headings** — always use `#` syntax
   - `> ` prefix for blockquotes / indented passages
   - `---` for section breaks (instead of decorative dividers)
   - **Markdown line breaks** (`  ` — two trailing spaces) for consecutive lines that should render separately but aren't separate paragraphs (e.g. lists of book titles)
   - Paragraph breaks remain as double newlines

4. **Output**: Write the corrected text to `$ARGUMENTS/page-N.proofread.txt` (matching the source file's naming, e.g. `page-1.proofread.txt` or `page-066.proofread.txt`).

Do NOT summarize or paraphrase — reproduce the author's exact text with only OCR corrections and header/footer/ad removal.

**CRITICAL: Content filtering workaround.** Content (especially passages involving violence, war, religion, or other sensitive topics) may trigger content filtering. To avoid this:

1. Do NOT reproduce any of the article's content in your conversational text output.
2. **The preferred method**: Copy the OCR `.txt` file to the `.proofread.txt` path using `cp` via Bash, then use the `Edit` tool to make targeted corrections (fix OCR errors, add markdown formatting). This avoids putting the full page text in a tool parameter.
3. **Mechanical helpers** (their patterns hold no body text, so they are also safe): use `perl` for whole-line work — strip boilerplate with `perl -ni -e 'print unless /<running header|citation|copyright|ad line>/'`, squeeze blank lines with `perl -i -0pe 's/\n{3,}/\n\n/g; s/^\n+//; s/\n+$/\n/'`, and stitch with `cat page-*.proofread.txt > article.md` followed by a `perl -0pe` substitution per page boundary. **Caution:** curly quotes/apostrophes/en-dashes are multibyte, and a regex `.` matches only one byte — never put `'`, `"`, or `–` in a `perl`/`grep` pattern; match on an ASCII-only substring of the line instead.
4. **Never fall back** to using the `Write` tool with the corrected article text. (Writing `structure.md` and `metadata.json` is fine — those are your own notes/data, not the article body.)
5. Never discuss or quote the article's content in your conversational responses.

---

## Phase 2.5: Post-proofread cleanup

After all pages are proofread, scan for any stray annotations:

1. Grep all `*.proofread.txt` files for `[FIGURE:`, `[IMAGE:`, or similar placeholders.
2. For each match, read the corresponding PNG to confirm it's not actual text.
3. Remove any placeholder lines.

---

## Phase 3: Stitch into article

Since articles are only 2-4 pages, stitch them manually (no script needed).

### Step 1: Join pages

1. Read all `.proofread.txt` files in page order.
2. At each page boundary, apply these rules:
   - If the next page starts with a `#` heading → new section (keep the paragraph break).
   - If the current page ends with `word-` (hyphenation) → join the word fragments, no break.
   - If the current page ends **without** sentence-ending punctuation (`.?!"')]}`) → mid-sentence, join with a space.
   - If the current page ends **with** sentence-ending punctuation → **ambiguous**. Check the PNG of the next page to see if the first body text line (below the running header) is:
     - **Indented** → new paragraph (keep the break)
     - **Flush left** → continuation (join with a space)
3. Skip any `[BLANK PAGE]` entries.
4. Clean up triple+ newlines.
5. The article must start with a `##` heading (the column title).

### Step 2: Add byline

After the `##` heading, add the byline if it appears in the original:
- e.g. `by John Dickson Carr` (preserving the original phrasing/formatting)

### Step 3: Write output

Write the final article to `$ARGUMENTS/article.md`.

### Step 4: Verify

Check the final article:
- No `<!--PB:` markers remain
- No `[FIGURE:` or `[IMAGE:` lines
- No `[BLANK PAGE]` entries
- No trailing word-hyphens (`\w-$` at line ends)
- Starts with `## `
- Word count looks reasonable for 2-4 magazine pages (typically 1000-3000 words)

### Step 5: Write metadata

Write `$ARGUMENTS/metadata.json` with this schema:

```json
{
  "title": "<Column Title>",
  "author": "John Dickson Carr",
  "source": "<Publication Name>",
  "date": "<YYYY-MM or YYYY>",
  "toc_label": "<TOC issue label, e.g. January 1969 or July 1964>",
  "pages": "<printed page range, e.g. 151–152 or 104, 106–107>",
  "citation": "<full source citation from the ProQuest/source header>",
  "file": "article.md",
  "books_reviewed": [
    {
      "title": "<Book Title>",
      "author": "<Book Author>",
      "publisher": "<Publisher>"
    }
  ]
}
```

- `title`: the column title, normalized for display (e.g. "The Jury Box", "Best Mysteries of the Month", "Murder-Fancier Recommends"). Keep `article.md`'s heading faithful to the printed page even if it differs slightly from this.
- `source`: full publication name (e.g. "Ellery Queen's Mystery Magazine", "Harper's Magazine", "New York Times Book Review")
- `date`: from the folder name, in `YYYY-MM` or `YYYY` format
- `toc_label`: the issue label for the compiled book's table of contents — month + year for EQMM ("January 1969"); "July <year>" for Harper's (all Harper's issues are dated July 1)
- `pages`: the printed page numbers the Carr column occupies, read from the running headers (e.g. "151–152"); use commas when the column skips ad pages (e.g. "104, 106–107")
- `citation`: a full source citation built from the ProQuest/source header, e.g. "Ellery Queen's Mystery Magazine (January 1969): 151–152." or "Harper's Magazine 229, no. 1370 (July 1, 1964): 104–106."
- `books_reviewed`: list of books reviewed, in order of appearance — each `{title, author, publisher}`. The `publisher` is the one Carr prints in the review's `(Publisher, $price)` parenthetical (e.g. `Harper & Row`; keep multi-word publishers like `Dodd, Mead` intact; book publication year is not recorded — it is rarely given). Omit `books_reviewed` entirely if the article is not a standard review column (e.g. an essay or tribute).

These per-issue files compile into one EPUB — *The Jury Box: The Mystery Reviews of John Dickson Carr, 1964–1976* — with a two-level table of contents (magazine → issue, each issue labeled `{toc_label} — {title}`). The build keeps `article.md` faithful and derives the chapter headings from the metadata; see `post/book.json` and `post/BUILD.md`.

---

## Important notes

- Always prefer what you **see** in the PNG over what the OCR text says.
- Do not add any text that isn't in the original article — no summaries, commentary, or notes.
- Preserve the author's formatting choices (italics, bold, paragraph breaks, section breaks).
- If you encounter an ambiguous word, use the context of the sentence and the visual appearance to determine the correct reading.
- Work systematically through all pages — do not skip content pages.
- **Prefer thoroughness over speed.** When choosing between a faster approach and a more careful approach, always choose the more careful way.
- NEVER load more than one PNG at a time.
- NEVER use the .txt OCR files as a substitute for reading the PNG — always cross-reference both.
- The OCR is generally high quality: treat the `.proofread.txt` copy as your base text and correct it against the PNG. Override the OCR only for clear non-word garbles, high-confidence visual reads, or logical necessity. When a word is ambiguous, **re-read the PNG to confirm** — never "correct" the OCR from your memory of an earlier glance, as first-pass recollections can be wrong (they have invented review endings and mis-assigned book authors before).
- Multi-column scans often interleave **other critics' columns and advertisements** into the OCR text. Strip everything that is not Carr's column, verifying column membership against the PNG.
- For a substantive footnote (e.g. an award note), fold its text inline near the book it annotates rather than dropping it; still remove the superscript anchor from the body.
