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
post/book.json            # book-level metadata (title, subtitle, author, sections, essay_placement)
post/<group>/<issue>/     # article.md + metadata.json (+ structure.md) per piece
the-jury-box.epub         # output
```

## Build it
```sh
uv run python src/make_cover.py     # (re)generate the cover
uv run python src/build_epub.py     # build the EPUB
```
`uv` creates the venv and installs deps on first run.

## What `build_epub.py` does
1. Reads `post/book.json` for book metadata, the ordered `sections` list, and
   `essay_placement`.
2. Globs `post/*/*/metadata.json`. Pieces with `"type": "essay"` are set aside; the
   rest (reviews) are grouped into the `sections` **in order** — each piece joins the
   first section whose `match` fields all equal its metadata (so EQMM splits into
   "Best Mysteries of the Month" / "The Jury Box" by `title`, while the *New York
   Times* pieces group by `source`) — and sorted by `date` within each section.
3. For each piece, converts `article.md` → chapter XHTML: drops the leading
   `## <title>` and the byline line, runs the markdown body through `markdown`
   (→ `<p>`, `<h3>`, `<strong>`, `<em>`, `<blockquote>`, `<hr/>`), then prepends an
   `<h2>` and a `<p class="citation">`. The `<h2>` is the **date** (`toc_label`) for
   reviews and the **title** for the essay.
4. **Two-level TOC** via `book.toc = [(epub.Section(name, href=halftitle), (chapters…)), …]`
   — top level = column/section, nested = issues. The essay is a top-level chapter
   placed before or after the sections per `essay_placement` (`"front"` / `"back"`).
5. Front matter: cover, title page. Per-section half-title divider pages.
6. Back matter: **Index of Books Reviewed** (auto-generated from every review's
   `books_reviewed`; APA-style, author surname inverted, with publisher, sorted by
   author) and a "Note on the Texts" colophon that names each source archive.
7. Standard-Ebooks-style CSS is embedded in the script (`CORE_CSS` + `LOCAL_CSS`).
   `_fix_css_paths` rewrites ebooklib's `css/…` links to `../css/…`.

To reorder or rename sections, move the essay (`essay_placement`), or change the
title/subtitle, edit `post/book.json` — the script is otherwise data-driven and needs
no edits as pieces are added.

## Per-issue metadata schema
Produced by `/proofread` (canonical docs in `.claude/commands/proofread.md`):

| field | example |
|---|---|
| `title` | column name for EQMM/Harper's (`"The Jury Box"`); the piece's own title for NYT reviews and the essay |
| `source` | `"Ellery Queen's Mystery Magazine"` (publication; used by section `match` rules) |
| `date` | `"1969-01"` / `"1964"` / `"1948-08-01"` (sort key) |
| `toc_label` | `"January 1969"` / `"July 1964"` (a review's chapter title) |
| `pages` | `"151–152"` |
| `citation` | `"Ellery Queen's Mystery Magazine (January 1969): 151–152."` |
| `file` | `"article.md"` |
| `type` | `"essay"` — optional; marks a standalone non-review piece (placed via `essay_placement`) |
| `books_reviewed` | `[{title, author, publisher}]` (omit for essays) |

`article.md` is kept faithful to the printed page (`## <title>` and byline retained);
the build relabels the heading from the metadata.

## Status
Data-driven: each newly proofread piece is picked up automatically and slotted into
its section by date. Sections in TOC order (counts as of the last build), with the
essay at the front:
- *The Grandest Game in the World* — 1963 essay (from *The Door to Doom*); front matter.
- **The New York Times Book Review** — ⏳ proofreading in progress (4 of ~5).
- **Murder-Fancier Recommends** — Harper's, 1964–1967 (4). ✅
- **Best Mysteries of the Month** — EQMM, Jan 1969 – Apr 1970 (16). ✅
- **The Jury Box** — EQMM, May 1970 – Nov 1976 (74). ✅

Re-run the two commands above to rebuild.
