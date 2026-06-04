#!/usr/bin/env python3
"""Compile the proofread John Dickson Carr pieces into one EPUB.

No pandoc. Mirrors ~/Projects/selectedpoe: ebooklib + Standard-Ebooks-style CSS,
a Pillow-generated cover, managed with uv.

Reads post/book.json plus every post/<group>/<issue>/{article.md, metadata.json}.
Review columns are grouped into ordered sections (order + match rules from
book.json's "sections"), sorted by date, and emitted as a two-level TOC
(column -> issue); each review is titled by its date (<toc_label>) and carries its
source citation. A standalone essay (metadata "type": "essay") is placed as its own
chapter at the front or back of the reviews ("essay_placement"). Back matter holds
an Index of Books Reviewed and a colophon.
"""

import glob
import html
import json
import os
import re
import shutil
import tempfile
import unicodedata
import zipfile

import markdown
from ebooklib import epub

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POST = os.path.join(ROOT, "post")
ASSETS = os.path.join(ROOT, "assets")
OUT = os.path.join(ROOT, "the-jury-box.epub")


# ── CSS (trimmed Standard Ebooks core + local additions) ──────────────────

CORE_CSS = """@charset "utf-8";
@namespace epub "http://www.idpf.org/2007/ops";

body { hyphens: auto; -epub-hyphens: auto; }
p { margin: 0; text-indent: 1em; }
hr { border: none; border-top: 1px solid; height: 0; margin: 1.5em auto; width: 25%; }
blockquote { margin: 1em 2.5em; }
h1, h2, h3, h4, h5, h6 {
  break-after: avoid; break-inside: avoid;
  font-variant: small-caps; hyphens: none; -epub-hyphens: none;
  margin: 2.5em 0 1em; text-align: center;
}
h2 + p, h3 + p, hr + p, p:first-child { text-indent: 0; }
b, strong { font-weight: bold; }
i, em { font-style: italic; }
i > i, em > i, i > em, em > em { font-style: normal; }
article { break-before: page; }
"""

LOCAL_CSS = """@charset "utf-8";
@namespace epub "http://www.idpf.org/2007/ops";

p.citation {
  text-align: center; text-indent: 0;
  font-style: italic; font-size: 0.85em;
  margin: -0.4em 0 2em;
}
section[epub|type~="titlepage"], section[epub|type~="halftitlepage"] { text-align: center; }
section[epub|type~="titlepage"] h1 { font-size: 1.9em; margin-bottom: 0.3em; }
section[epub|type~="titlepage"] .subtitle { font-variant: normal; font-style: italic; }
section[epub|type~="titlepage"] .author { margin-top: 2em; }
section[epub|type~="titlepage"] .version { font-size: 0.8em; font-style: italic; margin-top: 3em; }
section[epub|type~="halftitlepage"] h2 { margin-top: 28%; }
p.index-entry { text-indent: -1.5em; margin: 0 0 0 1.5em; }
"""


# ── helpers ───────────────────────────────────────────────────────────────

def esc(text: str) -> str:
    return html.escape(text, quote=True)


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def sort_key_title(title: str) -> str:
    return re.sub(r"^(the|a|an)\s+", "", title.strip(), flags=re.I).lower()


# surname particles kept with the surname when inverting "First Last" -> "Last, First"
PARTICLES = {"le", "la", "de", "du", "des", "del", "della", "van", "von", "der",
             "den", "ten", "ter", "di", "da", "dos", "das", "mac", "mc", "st", "o'"}


def invert_author(name: str) -> str:
    # Multiple authors ("A and B", "A & B"): invert only the first, keep the rest
    # as printed, so the entry still sorts under the first author's surname.
    parts = re.split(r"\s+(?:and|&)\s+", name)
    if len(parts) > 1:
        return f"{invert_author(parts[0])}, and {' and '.join(parts[1:])}"
    toks = name.split()
    if len(toks) < 2:
        return name
    j = len(toks) - 1
    while j - 1 >= 1 and toks[j - 1].lower().rstrip(".") in PARTICLES:
        j -= 1
    return f'{" ".join(toks[j:])}, {" ".join(toks[:j])}'


def _ascii_fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def wrap_xhtml(body: str, title: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en">\n'
        "\t<head>\n"
        f"\t\t<title>{esc(title)}</title>\n"
        '\t\t<link href="../css/core.css" rel="stylesheet" type="text/css"/>\n'
        '\t\t<link href="../css/local.css" rel="stylesheet" type="text/css"/>\n'
        "\t</head>\n"
        '\t<body epub:type="bodymatter">\n'
        f"\t\t{body}\n"
        "\t</body>\n"
        "</html>\n"
    )


def article_to_xhtml(md_path: str, chapter_title: str, citation: str, file_id: str) -> str:
    """Convert an article.md to chapter XHTML.

    Drops the leading `## <column title>` heading and the byline line, converts the
    remaining markdown body, and prepends our own `<h2>` (the issue label) and a
    citation line.
    """
    with open(md_path, encoding="utf-8") as f:
        lines = f.read().split("\n")

    out: list[str] = []
    dropped_title = False
    dropped_byline = False
    for ln in lines:
        if not dropped_title and ln.lstrip().startswith("## "):
            dropped_title = True
            continue
        if dropped_title and not dropped_byline:
            if ln.strip() == "":
                continue
            if re.match(r"(?i)^(by |recommended by )", ln.strip()):
                dropped_byline = True
                continue
            dropped_byline = True  # no byline present; this line begins the body
        out.append(ln)

    body_html = markdown.markdown("\n".join(out).strip(), output_format="xhtml")
    cite = f'\t\t\t<p class="citation">{esc(citation)}</p>\n' if citation else ""
    inner = (
        f'<article id="{file_id}" epub:type="chapter">\n'
        f'\t\t\t<h2 epub:type="title">{esc(chapter_title)}</h2>\n'
        f"{cite}"
        f"{body_html}\n"
        f"\t\t</article>"
    )
    return wrap_xhtml(inner, chapter_title)


def make_titlepage(title: str, subtitle: str, author: str, version: str) -> str:
    inner = (
        '<section epub:type="titlepage">\n'
        f"\t\t\t<h1>{esc(title)}</h1>\n"
        f'\t\t\t<p class="subtitle">{esc(subtitle)}</p>\n'
        f'\t\t\t<p class="author">{esc(author)}</p>\n'
        f'\t\t\t<p class="version">Version {esc(version)}</p>\n'
        "\t\t</section>"
    )
    return wrap_xhtml(inner, title)


def make_halftitle(name: str) -> str:
    inner = (
        '<section epub:type="halftitlepage">\n'
        f'\t\t\t<h2 epub:type="title">{esc(name)}</h2>\n'
        "\t\t</section>"
    )
    return wrap_xhtml(inner, name)


def make_index(issues_in_order: list[dict]) -> str:
    entries = []
    for it in issues_in_order:
        for b in it.get("books_reviewed", []):
            entries.append((b["title"], b["author"], b.get("publisher", ""),
                            it["source"], it["toc_label"]))
    entries.sort(key=lambda e: (_ascii_fold(invert_author(e[1])), sort_key_title(e[0])))
    rows = []
    for (title, author, pub, source, label) in entries:
        inv = invert_author(author)
        dot = "" if inv.endswith(".") else "."   # avoid "Davies, L. P.." double period
        pubpart = f" ({esc(pub)})" if pub else ""
        rows.append(
            f'\t\t\t<p class="index-entry">{esc(inv)}{dot} '
            f"<i>{esc(title)}</i>{pubpart}. Reviewed in {esc(source)}, {esc(label)}.</p>"
        )
    inner = (
        '<section epub:type="endnotes">\n'
        '\t\t\t<h2 epub:type="title">Index of Books Reviewed</h2>\n'
        + "\n".join(rows) + "\n"
        "\t\t</section>"
    )
    return wrap_xhtml(inner, "Index of Books Reviewed")


def make_colophon(version: str, n_reviews: int, n_essays: int) -> str:
    plural = "s" if n_reviews != 1 else ""
    essay_note = ""
    if n_essays:
        e_pl = "s" if n_essays != 1 else ""
        essay_note = f", plus {n_essays} essay{e_pl}"
    provenance = (
        "\t\t\t<p>The scans were drawn from several archives: the <i>Harper’s "
        "Magazine</i> columns from ProQuest; the <i>Ellery Queen’s Mystery Magazine</i> "
        "columns from the Internet Archive; and the <i>New York Times</i> reviews from "
        "the Times’ TimesMachine."
    )
    if n_essays:
        provenance += (
            " “The Grandest Game in the World” is taken from <i>The Door to Doom and "
            "Other Detections</i>, edited by Douglas G. Greene (New York: Harper &amp; "
            "Row, 1980)."
        )
    provenance += "</p>\n"
    inner = (
        '<section epub:type="colophon">\n'
        '\t\t\t<h2 epub:type="title">A Note on the Texts</h2>\n'
        "\t\t\t<p>Each piece was transcribed from its original appearance and proofread "
        "against page scans, with OCR errors corrected and advertisements, running heads, "
        "and adjacent matter removed. Each piece’s source is cited beneath its heading.</p>\n"
        + provenance +
        f"\t\t\t<p>This is <b>version {esc(version)}</b> of an ongoing transcription; "
        f"it currently gathers {n_reviews} review issue{plural}{essay_note}. The version "
        "is raised as more pieces are proofread.</p>\n"
        "\t\t\t<p>The CSS styling is adapted from the open-source "
        "<a href=\"https://standardebooks.org/\">Standard Ebooks</a> framework.</p>\n"
        "\t\t</section>"
    )
    return wrap_xhtml(inner, "A Note on the Texts")


# ── assembly ──────────────────────────────────────────────────────────────

def load_issues() -> list[dict]:
    issues = []
    for meta_path in glob.glob(os.path.join(POST, "*", "*", "metadata.json")):
        with open(meta_path, encoding="utf-8") as f:
            m = json.load(f)
        d = os.path.dirname(meta_path)
        m["_dir"] = d
        m["_article"] = os.path.join(d, m.get("file", "article.md"))
        m["_id"] = slugify(os.path.relpath(d, POST))
        issues.append(m)
    return issues


def assign_sections(reviews: list[dict], meta: dict) -> list[tuple[str, list[dict]]]:
    """Group review issues into ordered, named sections (the TOC's top level).

    Driven by book.json "sections": an ordered list of {name?, match: {field: value}}.
    A piece joins the first section whose every match field equals the piece's
    metadata — so EQMM splits into "Best Mysteries of the Month" / "The Jury Box" by
    `title`, while the New York Times pieces (per-book titles) group by `source`.
    Falls back to grouping by source (order from "magazine_order") when no sections
    are configured. Anything unmatched is appended under its source, with a warning,
    so nothing is silently dropped.
    """
    out: list[tuple[str, list[dict]]] = []
    sections_cfg = meta.get("sections")
    if sections_cfg:
        used = [False] * len(reviews)
        for sec in sections_cfg:
            crit = sec.get("match", {})
            name = sec.get("name") or crit.get("title") or crit.get("source") or "Reviews"
            members = []
            for i, it in enumerate(reviews):
                if not used[i] and all(it.get(k) == v for k, v in crit.items()):
                    members.append(it)
                    used[i] = True
            members.sort(key=lambda m: str(m["date"]))
            out.append((name, members))
        leftovers = [it for i, it in enumerate(reviews) if not used[i]]
    else:
        by: dict[str, list[dict]] = {}
        for it in reviews:
            by.setdefault(it["source"], []).append(it)
        order = [m for m in meta.get("magazine_order", []) if m in by]
        order += [m for m in sorted(by) if m not in order]
        out = [(m, sorted(by[m], key=lambda x: str(x["date"]))) for m in order]
        leftovers = []

    if leftovers:
        by = {}
        for it in leftovers:
            by.setdefault(it.get("source", "(unsorted)"), []).append(it)
        for src in sorted(by):
            out.append((src, sorted(by[src], key=lambda x: str(x["date"]))))
        print(f"  WARNING: {len(leftovers)} piece(s) matched no section in book.json "
              f'"sections"; appended under: {", ".join(sorted(by))}')
    return out


def build() -> None:
    with open(os.path.join(POST, "book.json"), encoding="utf-8") as f:
        meta = json.load(f)

    issues = load_issues()
    essays = sorted((it for it in issues if it.get("type") == "essay"),
                    key=lambda m: str(m["date"]))
    reviews = [it for it in issues if it.get("type") != "essay"]
    review_sections = assign_sections(reviews, meta)

    # Subtitle date range spans the earliest to the latest piece (fills "{years}").
    years = sorted(int(str(it["date"])[:4]) for it in issues if it.get("date"))
    year_range = (f"{years[0]}–{years[-1]}" if years and years[0] != years[-1]
                  else str(years[0]) if years else "")
    subtitle = meta.get("subtitle", "").replace("{years}", year_range)

    book = epub.EpubBook()
    book.set_identifier("jdc-jury-box-reviews")
    book.set_title(meta["title"])
    book.set_language(meta.get("language", "en"))
    book.add_author(meta["author"])
    book.add_metadata("DC", "description",
                      f"{meta['title']}: {subtitle}".strip(": "))
    version = meta.get("version", "0.0.1")
    book.add_metadata(None, "meta", version, {"property": "schema:version"})

    cover_path = os.path.join(ASSETS, "cover.jpg")
    cover_page = None
    if os.path.exists(cover_path):
        with open(cover_path, "rb") as f:
            book.set_cover("images/cover.jpg", f.read(), create_page=True)
        cover_page = book.get_item_with_id("cover")  # the auto-made cover.xhtml

    core = epub.EpubItem(uid="core_css", file_name="css/core.css",
                         media_type="text/css", content=CORE_CSS.encode("utf-8"))
    local = epub.EpubItem(uid="local_css", file_name="css/local.css",
                          media_type="text/css", content=LOCAL_CSS.encode("utf-8"))
    book.add_item(core)
    book.add_item(local)
    css = (core, local)

    def page(title: str, file_name: str, xhtml: str) -> epub.EpubHtml:
        ch = epub.EpubHtml(title=title, file_name=file_name, lang="en")
        ch.content = xhtml.encode("utf-8")
        for c in css:
            ch.add_item(c)
        book.add_item(ch)
        return ch

    def chapter(it: dict, display_title: str) -> epub.EpubHtml:
        xhtml = article_to_xhtml(it["_article"], display_title,
                                 it.get("citation", ""), it["_id"])
        return page(display_title, f'text/{it["_id"]}.xhtml', xhtml)

    titlepage = page("Title Page", "text/titlepage.xhtml",
                     make_titlepage(meta["title"], subtitle, meta["author"], version))

    spine: list = ([cover_page] if cover_page else []) + [titlepage, "nav"]
    toc: list = [cover_page] if cover_page else []
    flat_reviews: list[dict] = []

    # Standalone essay(s) — their own top-level chapter, titled by their real title.
    essay_pages = [chapter(it, it["title"]) for it in essays]
    placement = meta.get("essay_placement", "front")
    if essay_pages and placement == "front":
        spine += essay_pages
        toc += essay_pages

    # Review columns — one section (half-title + nested TOC) each, titled by date.
    for name, members in review_sections:
        if not members:
            continue
        ht_name = f"text/{slugify(name)}-halftitle.xhtml"
        ht = page(name, ht_name, make_halftitle(name))
        spine.append(ht)
        chapters = []
        for it in members:
            ch = chapter(it, it["toc_label"])
            spine.append(ch)
            chapters.append(ch)
            flat_reviews.append(it)
        toc.append((epub.Section(name, href=ht_name), tuple(chapters)))

    if essay_pages and placement == "back":
        spine += essay_pages
        toc += essay_pages

    index = page("Index of Books Reviewed", "text/index.xhtml", make_index(flat_reviews))
    colophon = page("A Note on the Texts", "text/colophon.xhtml",
                    make_colophon(version, len(flat_reviews), len(essay_pages)))
    spine.extend([index, colophon])
    toc.extend([index, colophon])

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    epub.write_epub(OUT, book, {})
    _fix_css_paths(OUT)

    n_books = sum(len(it.get("books_reviewed", [])) for it in flat_reviews)
    n_sections = sum(1 for _, members in review_sections if members)
    print(f"Wrote {OUT}")
    print(f"  {meta['title']} — {subtitle}")
    print(f"  sections: {n_sections}  review issues: {len(flat_reviews)}  "
          f"essays: {len(essay_pages)}  books indexed: {n_books}")
    for name, members in review_sections:
        if members:
            print(f"    - {name}: {len(members)}")
    for it in essays:
        print(f"    - essay ({placement}): {it['title']}")


def _fix_css_paths(epub_path: str) -> None:
    """ebooklib emits href="css/..." but XHTML lives in text/; rewrite to ../css/."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".epub")
    tmp.close()
    with zipfile.ZipFile(epub_path, "r") as zin, \
         zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("EPUB/text/") and item.filename.endswith(".xhtml"):
                data = data.decode("utf-8").replace('href="css/', 'href="../css/').encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp.name, epub_path)


if __name__ == "__main__":
    build()
