#!/usr/bin/env python3
"""Regenerate the book-review tables in README.md from the issue metadata.

Reuses build_epub's section grouping, so the README tables match the EPUB's TOC
exactly (same columns, same chronological order). Rewrites only the block between
the BOOK-TABLES markers; the rest of the README is left untouched. Run this after
editing any metadata.json:

    .venv/bin/python src/gen_readme_tables.py
"""

import json
import os
import re

from build_epub import POST, assign_sections, load_issues

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")
START = "<!-- BOOK-TABLES:START -->"
END = "<!-- BOOK-TABLES:END -->"


def cell(s: str) -> str:
    # escape the column separator so titles/authors can't break the table
    return str(s).replace("|", "\\|").strip()


def year(d) -> str:
    return str(d)[:4]


def pub_dates(b: dict) -> str:
    """First-publication year, or "first/reissue" when Carr reviewed a reprint."""
    fp, ed = b.get("first_published_date"), b.get("edition_published_date")
    if fp and ed:
        return f"{fp}/{ed}"
    return str(fp) if fp else ""


def table(members: list[dict]) -> str:
    rows = ["| Issue | Title | Author | Publisher | Published |", "|---|---|---|---|---|"]
    last_label = None
    for it in members:
        label = it.get("toc_label", "")
        for b in it.get("books_reviewed", []):
            if b.get("rereview_of"):
                continue  # same work already listed at its first review
            shown = label if label != last_label else ""  # group rows by issue
            last_label = label
            rows.append(
                f"| {shown} | *{cell(b.get('title', ''))}* | {cell(b.get('author', ''))} | "
                f"{cell(b.get('publisher', ''))} | {pub_dates(b)} |"
            )
    return "\n".join(rows)


def main() -> None:
    with open(os.path.join(POST, "book.json"), encoding="utf-8") as f:
        meta = json.load(f)
    reviews = [it for it in load_issues() if it.get("type") != "essay"]
    sections = [(name, m) for name, m in assign_sections(reviews, meta) if m]

    blocks, total = [], 0
    for name, members in sections:
        nbooks = sum(1 for it in members
                     for b in it.get("books_reviewed", []) if not b.get("rereview_of"))
        total += nbooks
        yrs = sorted(year(it["date"]) for it in members)
        rng = yrs[0] if yrs[0] == yrs[-1] else f"{yrs[0]}–{yrs[-1]}"
        s = "s" if nbooks != 1 else ""
        blocks.append(f"### {name} — {nbooks} review{s} · {rng}\n\n{table(members)}")

    authors = set()
    n_issues = 0
    for _, members in sections:
        n_issues += len(members)
        for it in members:
            for b in it.get("books_reviewed", []):
                if b.get("rereview_of"):
                    continue
                for p in re.split(r"\s+(?:and|&)\s+", b.get("author", "")):
                    p = p.strip().strip(",").strip()
                    if p:
                        authors.add(p)
    summary = f"_{total} books by {len(authors)} authors across {n_issues} issues._"
    body = f"{START}\n\n{summary}\n\n" + "\n\n".join(blocks) + f"\n\n{END}"

    with open(README, encoding="utf-8") as f:
        content = f.read()
    i, j = content.find(START), content.find(END)
    if i != -1 and j != -1:
        content = content[:i] + body + content[j + len(END):]
    else:
        content = content.rstrip() + "\n\n## Book reviews\n\n" + body + "\n"
    with open(README, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Updated {README}: {total} books across {len(sections)} columns")
    for name, members in sections:
        print(f"    - {name}: {sum(len(it.get('books_reviewed', [])) for it in members)}")


if __name__ == "__main__":
    main()
