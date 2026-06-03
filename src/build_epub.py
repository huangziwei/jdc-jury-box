#!/usr/bin/env python3
"""Compile the proofread John Dickson Carr review issues into one EPUB.

No pandoc. Mirrors ~/Projects/selectedpoe: ebooklib + Standard-Ebooks-style CSS,
a Pillow-generated cover, managed with uv.

Reads post/book.json plus every post/<magazine>/<issue>/{article.md, metadata.json},
groups issues by magazine (order from book.json), sorts by date, and emits a
two-level TOC (magazine -> issue). Each issue is titled "<toc_label> — <title>"
and carries its source citation. Back matter holds an Index of Books Reviewed.
"""

import glob
import html
import json
import os
import re
import shutil
import tempfile
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


def make_titlepage(title: str, subtitle: str, author: str) -> str:
    inner = (
        '<section epub:type="titlepage">\n'
        f"\t\t\t<h1>{esc(title)}</h1>\n"
        f'\t\t\t<p class="subtitle">{esc(subtitle)}</p>\n'
        f'\t\t\t<p class="author">{esc(author)}</p>\n'
        "\t\t</section>"
    )
    return wrap_xhtml(inner, title)


def make_intro(bio: str) -> str:
    inner = (
        '<section epub:type="preamble">\n'
        '\t\t\t<h2 epub:type="title">About This Collection</h2>\n'
        "\t\t\t<p>For thirteen years John Dickson Carr — a grand master of the "
        "locked-room mystery — kept up a running verdict on other people’s crime "
        "fiction, in two homes and under three running titles.</p>\n"
        "\t\t\t<p>In <i>Harper’s Magazine</i> (1964–1967) his annual column "
        "“Murder-Fancier Recommends” singled out ten novels a year. In "
        "<i>Ellery Queen’s Mystery Magazine</i> (January 1969 – November 1976) "
        "he wrote a monthly column — first “Best Mysteries of the Month,” "
        "later “The Jury Box.”</p>\n"
        "\t\t\t<p>The reviews are gathered here in two sections, each issue presented "
        "as Carr wrote it, with its original source noted.</p>\n"
        f"\t\t\t<p><i>{esc(bio)}</i></p>\n"
        "\t\t</section>"
    )
    return wrap_xhtml(inner, "About This Collection")


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
            entries.append((b["title"], b["author"], it["toc_label"]))
    entries.sort(key=lambda e: (sort_key_title(e[0]), e[1].lower()))
    rows = "\n".join(
        f'\t\t\t<p class="index-entry"><i>{esc(t)}</i>, by {esc(a)} — {esc(lbl)}</p>'
        for (t, a, lbl) in entries
    )
    inner = (
        '<section epub:type="endnotes">\n'
        '\t\t\t<h2 epub:type="title">Index of Books Reviewed</h2>\n'
        f"{rows}\n"
        "\t\t</section>"
    )
    return wrap_xhtml(inner, "Index of Books Reviewed")


def make_colophon() -> str:
    inner = (
        '<section epub:type="colophon">\n'
        '\t\t\t<h2 epub:type="title">A Note on the Texts</h2>\n'
        "\t\t\t<p>The text of each column was proofread against page scans of the "
        "original magazine issues (digitized via ProQuest), with OCR errors corrected "
        "and advertisements, running heads, and other critics’ columns removed. "
        "Each issue’s source is cited beneath its heading.</p>\n"
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


def build() -> None:
    with open(os.path.join(POST, "book.json"), encoding="utf-8") as f:
        meta = json.load(f)

    issues = load_issues()
    by_mag: dict[str, list[dict]] = {}
    for it in issues:
        by_mag.setdefault(it["source"], []).append(it)
    for mag in by_mag:
        by_mag[mag].sort(key=lambda m: str(m["date"]))

    order = [m for m in meta["magazine_order"] if m in by_mag]
    order += [m for m in sorted(by_mag) if m not in order]  # any stragglers

    book = epub.EpubBook()
    book.set_identifier("jdc-jury-box-reviews")
    book.set_title(meta["title"])
    book.set_language(meta.get("language", "en"))
    book.add_author(meta["author"])
    book.add_metadata("DC", "description",
                      f"{meta['title']}: {meta.get('subtitle', '')}".strip(": "))

    cover_path = os.path.join(ASSETS, "cover.jpg")
    if os.path.exists(cover_path):
        with open(cover_path, "rb") as f:
            book.set_cover("images/cover.jpg", f.read(), create_page=True)

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

    subtitle = meta.get("subtitle", "")
    bio = meta.get("author_bio",
                   "Mr. Carr is the author of numberless detective novels and of "
                   "“The Life of Sir Arthur Conan Doyle.” He has been president "
                   "both of the Mystery Writers of America and of the London Detection Club.")

    titlepage = page("Title Page", "text/titlepage.xhtml",
                     make_titlepage(meta["title"], subtitle, meta["author"]))
    intro = page("About This Collection", "text/about.xhtml", make_intro(bio))

    spine: list = [titlepage, "nav", intro]
    toc: list = [intro]
    flat_order: list[dict] = []

    for mag in order:
        ht_name = f"text/{slugify(mag)}-halftitle.xhtml"
        ht = page(mag, ht_name, make_halftitle(mag))
        spine.append(ht)
        chapters = []
        for it in by_mag[mag]:
            label = f'{it["toc_label"]} — {it["title"]}'
            xhtml = article_to_xhtml(it["_article"], label, it.get("citation", ""), it["_id"])
            ch = page(label, f'text/{it["_id"]}.xhtml', xhtml)
            spine.append(ch)
            chapters.append(ch)
            flat_order.append(it)
        toc.append((epub.Section(mag, href=ht_name), tuple(chapters)))

    index = page("Index of Books Reviewed", "text/index.xhtml", make_index(flat_order))
    colophon = page("A Note on the Texts", "text/colophon.xhtml", make_colophon())
    spine.extend([index, colophon])
    toc.extend([index, colophon])

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    epub.write_epub(OUT, book, {})
    _fix_css_paths(OUT)

    n_books = sum(len(it.get("books_reviewed", [])) for it in flat_order)
    print(f"Wrote {OUT}")
    print(f"  magazines: {len(order)}  issues: {len(flat_order)}  books indexed: {n_books}")
    for mag in order:
        print(f"    - {mag}: {len(by_mag[mag])} issues")


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
