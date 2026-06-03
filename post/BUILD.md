# Compilation plan — *The Jury Box* (EPUB)

Compile every proofread issue into one EPUB. **No pandoc** — the build is a small
Python program using [`ebooklib`](https://github.com/aerkalov/ebooklib), modeled on
`~/Projects/selectedpoe` (ebooklib + Standard-Ebooks-style CSS + a Pillow cover,
managed with `uv`).

## Layout
```
pyproject.toml            # deps: ebooklib, markdown, pillow (uv-managed)
.python-version
src/make_cover.py         # generates assets/cover.jpg (typographic cover)
src/build_epub.py         # scans post/, builds the-jury-box.epub
assets/cover.jpg          # generated
post/book.json            # book-level metadata (title, subtitle, author, bio, magazine order)
post/<magazine>/<issue>/  # article.md + metadata.json (+ structure.md) per issue
the-jury-box.epub         # output
```

## Build it
```sh
uv run python src/make_cover.py     # (re)generate the cover
uv run python src/build_epub.py     # build the EPUB
```
`uv` creates the venv and installs deps on first run.

## What `build_epub.py` does
1. Reads `post/book.json` for book metadata + `magazine_order`.
2. Globs `post/*/*/metadata.json`, groups issues by `source` (magazine), sorts each
   group by `date`.
3. For each issue, converts `article.md` → chapter XHTML: drops the leading
   `## <column title>` and the byline line, runs the markdown body through
   `markdown` (→ `<p>`, `<h3>`, `<strong>`, `<em>`, `<blockquote>`, `<hr/>`), then
   prepends `<h2>` = `"{toc_label} — {title}"` and a `<p class="citation">`.
4. **Two-level TOC** via `book.toc = [(epub.Section(magazine, href=halftitle), (chapters…)), …]`
   — top level = magazine, nested = issues. (`--toc-depth` equivalent: `###`
   subsections are not added to the nav.)
5. Front matter: cover, title page, "About This Collection" (intro + author bio).
   Per-magazine half-title divider pages.
6. Back matter: **Index of Books Reviewed** (auto-generated from every issue's
   `books_reviewed`, alphabetized by title) and a "Note on the Texts" colophon.
7. Standard-Ebooks-style CSS is embedded in the script (`CORE_CSS` + `LOCAL_CSS`).
   `_fix_css_paths` rewrites ebooklib's `css/…` links to `../css/…`.

To change the book title, subtitle, author bio, or magazine order, edit
`post/book.json` — the script is otherwise data-driven and needs no edits as issues
are added.

## Per-issue metadata schema
Produced by `/proofread` (canonical docs in `.claude/commands/proofread.md`):

| field | example |
|---|---|
| `title` | `"The Jury Box"` (normalized column name) |
| `source` | `"Ellery Queen's Mystery Magazine"` (magazine = TOC group) |
| `date` | `"1969-01"` / `"1964"` (sort key) |
| `toc_label` | `"January 1969"` / `"July 1964"` |
| `pages` | `"151–152"` |
| `citation` | `"Ellery Queen's Mystery Magazine (January 1969): 151–152."` |
| `file` | `"article.md"` |
| `books_reviewed` | `[{title, author}]` |

`article.md` is kept faithful to the printed page (`## <column title>` and byline
retained); the build relabels the heading from the metadata.

## Status
- Harper's 1964–1967 — ✅ proofread; **build verified** (4 issues, nested TOC, 38 books indexed).
- EQMM 1969–1976 — ⏳ in progress. As each issue is proofread it is picked up
  automatically and appears under an "Ellery Queen's Mystery Magazine" section,
  sorted by date. Re-run the two commands above to rebuild.
