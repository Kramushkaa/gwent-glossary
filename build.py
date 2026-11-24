#!/usr/bin/env python3
"""Build the static GWENT glossary site from the VK wiki dump in raw/.

Usage:  python build.py
Output: index.html, data/glossary.json
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
IMG_DIR = ROOT / "assets" / "img"

# Letter ranges used by the original wiki pagination.
GROUPS = {
    1: "А",
    2: "Б",
    3: "В–Г",
    4: "Д",
    5: "Е–И",
    6: "К",
    7: "Л–М",
    8: "Н–О",
    9: "П",
    10: "Р",
    11: "С",
    12: "Т",
    13: "У–Я",
}

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "iu", "я": "ia",
}

TERM_RE = re.compile(r"^====\s*(.+?)\s*====[ \t]*$", re.M)
PHOTO_RE = re.compile(r"\[\[photo(\d+_\d+)\|([^|\]]*)(?:\|([^\]]*))?\]\]")
PHOTO_ONLY_RE = re.compile(r"\[\[photo(\d+_\d+)\|([^|\]]*)(?:\|([^\]]*))?\]\]")
ABBR_RE = re.compile(r"<gray>\s*Условные сокращения:(.*?)</gray>", re.S)
TAG_RE = re.compile(r"</?(?:center|gray|b|i|u|s|br\s*/?)>")
CAPTION_RE = re.compile(
    r"^<center>\s*(?:<gray>)?(.*?)(?:</?gray>)?\s*</center>$"
)
LIST_ORDERED_RE = re.compile(r"^\s*(\d+)[.)]\s*(.*)$")
LIST_ALPHA_RE = re.compile(r"^\s*([а-яё])\)\s*(.*)$")
LIST_BULLET_RE = re.compile(r"^\s*[*•]\s*(.*)$")

# Wiki link targets that cannot be resolved automatically.
ALIASES = {
    "афк (afk)": "АФК (АFK)",
    "винкон": "Винкондишен (винкон)",
}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def plain(line: str) -> str:
    """Strip wiki layout tags, keeping the inner text."""
    return TAG_RE.sub("", line).strip()


def norm_key(text: str) -> str:
    """Loose key: case-, punctuation- and lookalike-insensitive."""
    text = unicodedata.normalize("NFKC", text).lower()
    table = {
        "a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х",
        "y": "у", "k": "к", "m": "м", "t": "т", "h": "н", "b": "в",
    }
    text = "".join(table.get(ch, ch) for ch in text)
    return re.sub(r"[^0-9a-zа-яё]", "", text)


def slugify(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch in TRANSLIT:
            out.append(TRANSLIT[ch])
        elif ch.isalnum() and ch.isascii():
            out.append(ch)
        else:
            out.append("-")
    slug = re.sub(r"-{2,}", "-", "".join(out)).strip("-")
    return slug or "term"


def esc(text: str) -> str:
    return html.escape(text, quote=False)


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
class Context:
    def __init__(self, page: int) -> None:
        self.page = page
        self.unresolved: set[str] = set()

    def resolve(self, target: str, label: str) -> tuple[str | None, str]:
        term = ALIASES.get(target.strip().lower(), target.strip())
        slug = INDEX.resolve(term, self.page)
        if slug is None:
            self.unresolved.add(f"{term}  (page {self.page}, label {label!r})")
        return slug, term


class Index:
    def __init__(self) -> None:
        self.by_title: dict[str, str] = {}
        self.by_key: dict[str, str] = {}
        self.by_page: dict[int, dict[str, str]] = {}
        self.by_page_key: dict[int, dict[str, str]] = {}

    def add(self, page: int, title: str, slug: str) -> None:
        self.by_title.setdefault(title, slug)
        self.by_key.setdefault(norm_key(title), slug)
        self.by_page.setdefault(page, {})[title] = slug
        self.by_page_key.setdefault(page, {})[norm_key(title)] = slug

    def resolve(self, term: str, page: int) -> str | None:
        if term in self.by_page.get(page, {}):
            return self.by_page[page][term]
        if term in self.by_title:
            return self.by_title[term]
        key = norm_key(term)
        if key in self.by_page_key.get(page, {}):
            return self.by_page_key[page][key]
        if key in self.by_key:
            return self.by_key[key]
        return None


INDEX = Index()


def wikilink(target: str, label: str, ctx: Context) -> str:
    target = target.strip()
    label = label.strip()

    if target.startswith("page-") or target.startswith("@") or re.fullmatch(
        r"(?:club|public|id)\d+", target
    ):
        return f'<a class="ext" href="https://vk.com/{esc(target)}">{esc(label)}</a>'

    if target.startswith("#"):
        slug, _ = ctx.resolve(target[1:], label)
    elif "#" in target:
        _, term = target.split("#", 1)
        slug, _ = ctx.resolve(term, label)
    else:
        # link to another wiki page: point at the matching letter group
        page = page_from_name(target)
        if page is None:
            return esc(label)
        return f'<a href="#group-{page}">{esc(label)}</a>'

    if slug is None:
        return f'<span class="broken" title="Ссылка не разрешена">{esc(label)}</span>'
    return f'<a href="#{slug}">{esc(label)}</a>'


def page_from_name(name: str) -> int | None:
    match = re.search(r"Страница[\s_]*(\d+)", name, re.I)
    if match:
        return int(match.group(1))
    if name.strip().lower().startswith("глоссарий"):
        return 1
    return None


def image_html(photo_id: str, size: str, inline: bool = False) -> str:
    found = None
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"):
        candidate = IMG_DIR / f"{photo_id}{ext}"
        if candidate.exists():
            found = candidate
            break
    dims = ""
    match = re.fullmatch(r"(\d+)x(\d+)px", size.strip())
    if match:
        dims = f' width="{match.group(1)}" height="{match.group(2)}"'
    if found is None:
        if inline:
            return '<span class="img-chip">иллюстрация</span>'
        return ""
    src = f"assets/img/{found.name}"
    if inline:
        return f'<img class="img-inline" src="{src}" alt=""{dims} loading="lazy">'
    return f'<img src="{src}" alt=""{dims} loading="lazy">'


def inline(text: str, ctx: Context) -> str:
    keep: list[str] = []

    def stash(match: re.Match[str]) -> str:
        keep.append(match.group(0))
        return f"\x00{len(keep) - 1}\x00"

    text = TAG_RE.sub(stash, text)
    text = esc(text)

    text = PHOTO_RE.sub(
        lambda m: image_html(m.group(1), m.group(2), inline=True), text
    )
    text = re.sub(r"\[\[page-\d+_\d+\]\]", "", text)
    text = re.sub(
        r"\[\[([^\[\]|]+)\|([^\[\]]*)\]\]",
        lambda m: wikilink(m.group(1), clean_label(m.group(2)), ctx),
        text,
    )
    text = re.sub(
        r"\[\[([^\[\]|]+)\]\]",
        lambda m: wikilink(m.group(1), m.group(1), ctx),
        text,
    )
    text = re.sub(
        r"\[(https?://[^\]\s]+)\]",
        lambda m: f'<a class="ext" href="{esc(m.group(1))}">{esc(m.group(1))}</a>',
        text,
    )
    text = re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], text)
    return re.sub(r"\s{2,}", " ", text).strip()


def clean_label(label: str) -> str:
    label = urllib.parse.unquote(label.strip())
    label = re.sub(r"^\?f=", "", label)
    return label.strip()


def render_blocks(lines: list[str], ctx: Context) -> str:
    out: list[str] = []
    buffer: list[str] = []
    list_kind: str | None = None
    list_start = 1

    def flush_list() -> None:
        nonlocal list_kind, buffer
        if list_kind and buffer:
            tag = "ul" if list_kind == "ul" else "ol"
            attrs = ""
            if list_kind == "alpha":
                attrs = ' class="alpha"'
            elif list_kind == "ol" and list_start != 1:
                attrs = f' start="{list_start}"'
            items = "".join(f"<li>{item}</li>" for item in buffer)
            out.append(f"<{tag}{attrs}>{items}</{tag}>")
        list_kind = None
        buffer = []

    def add_item(kind: str, item: str, start: int = 1) -> None:
        nonlocal list_kind, list_start
        if list_kind != kind:
            flush_list()
            list_kind = kind
            list_start = start
        buffer.append(item)

    index = 0
    total = len(lines)
    while index < total:
        raw_line = lines[index]
        stripped = plain(raw_line)
        index += 1

        if not stripped:
            flush_list()
            continue

        if PHOTO_ONLY_RE.fullmatch(stripped):
            flush_list()
            photo = PHOTO_ONLY_RE.fullmatch(stripped)
            caption = ""
            if index < total:
                nxt = lines[index].strip()
                cap = CAPTION_RE.match(nxt)
                if cap:
                    caption = inline(cap.group(1), ctx)
                    index += 1
            body = image_html(photo.group(1), photo.group(2))
            cls = "term-figure" if body else "term-figure caption-only"
            cap_html = f"<figcaption>{caption}</figcaption>" if caption else ""
            if body or cap_html:
                out.append(f'<figure class="{cls}">{body}{cap_html}</figure>')
            continue

        cap = CAPTION_RE.match(raw_line.strip())
        if cap:
            flush_list()
            out.append(f'<p class="caption">{inline(cap.group(1), ctx)}</p>')
            continue

        ordered = LIST_ORDERED_RE.match(raw_line)
        if ordered:
            add_item("ol", inline(ordered.group(2), ctx), int(ordered.group(1)))
            continue

        alpha = LIST_ALPHA_RE.match(raw_line)
        if alpha:
            add_item("alpha", inline(alpha.group(2), ctx))
            continue

        bullet = LIST_BULLET_RE.match(raw_line)
        if bullet:
            add_item("ul", inline(bullet.group(1), ctx))
            continue

        flush_list()
        out.append(f"<p>{inline(stripped, ctx)}</p>")

    flush_list()
    return "\n".join(out)


def read_page(number: int) -> str:
    path = RAW / f"page_{number}.txt"
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def split_terms(text: str) -> list[tuple[str, list[str]]]:
    """Split one wiki page into (title, body lines) pairs."""
    matches = list(TERM_RE.finditer(text))
    terms: list[tuple[str, list[str]]] = []
    for pos, match in enumerate(matches):
        end = matches[pos + 1].start() if pos + 1 < len(matches) else len(text)
        title = match.group(1).strip()
        lines = text[match.end() : end].split("\n")

        # drop the trailing site navigation block
        lines = [ln for ln in lines if not ln.strip().startswith("[[Глоссарий")]
        while lines and not lines[-1].strip():
            lines.pop()
        while lines and not lines[0].strip():
            lines.pop(0)

        # some entries repeat their own title as the first line
        if lines and plain(lines[0]).rstrip(":").strip().lower() == title.lower():
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)

        terms.append((title, lines))
    return terms


def extract_abbreviations(text: str) -> list[str]:
    abbr = ABBR_RE.search(text)
    if not abbr:
        return []
    return [ln for ln in abbr.group(1).strip().split("\n") if ln.strip()]


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def assign_slugs(terms: list[dict]) -> None:
    seen: dict[str, int] = {}
    for term in terms:
        base = slugify(term["title"])
        count = seen.get(base, 0) + 1
        seen[base] = count
        term["slug"] = base if count == 1 else f"{base}-{count}"
        INDEX.add(term["page"], term["title"], term["slug"])


def render_toc(terms: list[dict]) -> str:
    parts = ['<nav class="toc" aria-label="Оглавление">']
    parts.append('<p class="toc-title">Оглавление</p>')
    current = None
    for term in terms:
        if term["group"] != current:
            if current is not None:
                parts.append("</ul></div>")
            current = term["group"]
            parts.append(
                f'<div class="toc-group" data-group="{esc(current)}">'
                f'<p class="toc-letter">{esc(current)}</p><ul>'
            )
        parts.append(
            f'<li><a href="#{term["slug"]}" data-slug="{term["slug"]}">'
            f'{esc(term["title"])}</a></li>'
        )
    parts.append("</ul></div>")
    parts.append("</nav>")
    return "\n".join(parts)


def render_terms(terms: list[dict]) -> str:
    parts: list[str] = []
    current = None
    for term in terms:
        if term["group"] != current:
            if current is not None:
                parts.append("</section>")
            current = term["group"]
            parts.append(
                f'<section class="group" id="group-{term["page"]}" '
                f'data-group="{esc(current)}">'
                f'<h2 class="group-title">{esc(current)}</h2>'
            )
        body = term["html"] or '<p class="empty">Определение пока не добавлено.</p>'
        parts.append(
            f'<article class="term" id="{term["slug"]}">'
            f'<h3 class="term-title">{esc(term["title"])}</h3>'
            f'<div class="term-body">{body}</div>'
            f"</article>"
        )
    parts.append("</section>")
    return "\n".join(parts)


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ru" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Глоссарий GWENT</title>
<meta name="description" content="Словарь терминов, механик и жаргона карточной игры GWENT.">
<meta name="color-scheme" content="dark light">
<link rel="stylesheet" href="assets/style.css">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚔️</text></svg>">
</head>
<body>
<a class="skip-link" href="#content">К содержанию</a>

<header class="topbar">
  <button class="toc-toggle" id="tocToggle" aria-controls="sidebar" aria-expanded="false">
    <span class="toc-toggle-bars" aria-hidden="true"></span>
    <span class="toc-toggle-label">Оглавление</span>
  </button>
  <div class="search-wrap">
    <input type="search" id="search" placeholder="Поиск по термину или определению…"
           aria-label="Поиск по глоссарию" autocomplete="off" spellcheck="false">
    <button class="search-clear" id="searchClear" aria-label="Очистить поиск" hidden>×</button>
  </div>
  <button class="theme-toggle" id="themeToggle" aria-label="Переключить тему" title="Переключить тему">◐</button>
</header>

<div class="layout">
  <aside class="sidebar" id="sidebar">
    <div class="sidebar-inner">
      <p class="sidebar-status" id="searchStatus" hidden></p>
      {toc}
    </div>
  </aside>

  <main class="content" id="content">
    <header class="page-head">
      <h1>Глоссарий GWENT</h1>
      <p class="lede">
        Термины, игровые механики, архетипы и жаргон сообщества карточной игры GWENT.
        Собрано из вики-страниц сообщества Claymore во «ВКонтакте».
      </p>
      <p class="meta">{count} терминов · {groups} разделов</p>
    </header>

    {terms}

    {abbr}

    <footer class="page-foot">
      <p>
        Источник: вики-страницы сообщества
        <a class="ext" href="https://vk.com/club154778374">Claymore</a> во «ВКонтакте».
        Материал сохранён в открытом виде, так как раздел вики-страниц ВКонтакте
        прекращает работу 4 декабря 2025 года.
      </p>
    </footer>
  </main>
</div>

<script src="assets/app.js"></script>
</body>
</html>
"""


def main() -> None:
    all_terms: list[dict] = []
    abbreviations: list[str] = []

    for page in sorted(GROUPS):
        text = read_page(page)
        if not abbreviations:
            abbreviations = extract_abbreviations(text)
        entries = split_terms(text)
        for title, lines in entries:
            all_terms.append(
                {
                    "title": title,
                    "slug": "",
                    "page": page,
                    "group": GROUPS[page],
                    "lines": lines,
                    "html": "",
                    "unresolved": [],
                }
            )
        print(f"page {page:>2}: {len(entries):>2} терминов")

    # pass 1 must be complete before links can be resolved
    assign_slugs(all_terms)

    unresolved: set[str] = set()
    for term in all_terms:
        ctx = Context(term["page"])
        term["html"] = render_blocks(term["lines"], ctx)
        term["unresolved"] = sorted(ctx.unresolved)
        unresolved.update(ctx.unresolved)

    if unresolved:
        print("\nНеразрешённые ссылки:")
        for item in sorted(unresolved):
            print("  -", item)

    abbr_html = ""
    if abbreviations:
        abbr_html = (
            '<section class="abbr"><h2>Условные сокращения</h2>'
            f"{render_blocks(abbreviations, Context(1))}</section>"
        )

    page = PAGE_TEMPLATE.format(
        toc=render_toc(all_terms),
        terms=render_terms(all_terms),
        abbr=abbr_html,
        count=len(all_terms),
        groups=len(GROUPS),
    )
    (ROOT / "index.html").write_text(page, encoding="utf-8")

    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    payload = [
        {
            "title": term["title"],
            "slug": term["slug"],
            "group": term["group"],
            "page": term["page"],
            "html": term["html"],
        }
        for term in all_terms
    ]
    (data_dir / "glossary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nindex.html: {len(all_terms)} терминов, {len(page):,} байт")


if __name__ == "__main__":
    main()
