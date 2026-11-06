"""Blocos das páginas (editor estilo Notion).

Uma página guarda `articles.blocks` = JSON com uma lista de blocos. Cada bloco tem `id` e `type`;
blocos de texto guardam HTML simples (negrito, itálico, links…), que é SEMPRE limpo aqui antes de salvar.
Contêineres: `columns` (cols[].blocks) e `toggle` (children).

`content` continua existindo: é gerado a partir dos blocos (texto + [[links]]) para a busca e o
"Mencionada em" funcionarem como antes.
"""
import json
import re
from html import escape
from html.parser import HTMLParser

from markupsafe import Markup

RICH_TYPES = {"text", "h1", "h2", "h3", "bullet", "number", "todo", "quote", "callout", "toggle"}
OTHER_TYPES = {"code", "divider", "image", "embed", "audio", "video", "file", "page", "columns", "table", "markdown"}
TYPES = RICH_TYPES | OTHER_TYPES
COLORS = ("gray", "brown", "orange", "yellow", "green", "blue", "purple", "pink", "red")
BLOCK_COLORS = {""} | set(COLORS) | {f"{c}_bg" for c in COLORS}
MAX_BLOCKS = 3000
MAX_DEPTH = 6

_PAGE_HREF = re.compile(r"^/w/\d+/p/\d+$")
_FILE_SRC = re.compile(r"^/f/(\d+)$")
_ICON_OK = re.compile(r"^(ri:[a-z0-9_-]{1,40}|img:/f/\d+|[^<>\"'&]{1,16})$")


# --------------------------------------------------------------------------- HTML inline seguro

class _Clean(HTMLParser):
    INLINE = {"b", "strong", "i", "em", "u", "s", "strike", "code", "a", "br", "span", "mark"}
    DROP_CONTENT = {"script", "style", "iframe", "object", "embed", "template", "noscript", "svg", "math"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.DROP_CONTENT:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in ("div", "p") and self.out:      # quebras que o navegador cria ao editar
            self.out.append("<br>")
            return
        if tag not in self.INLINE:
            return
        a = dict(attrs)
        if tag == "br":
            self.out.append("<br>")
            return
        extra = ""
        if tag == "a":
            href = (a.get("href") or "").strip()
            page = (a.get("data-page") or "").strip()
            if not (href.startswith(("http://", "https://", "mailto:")) or _PAGE_HREF.match(href)):
                href = ""
            if not href:
                return                              # link inválido: fica só o texto
            extra = f' href="{escape(href)}"'
            if page.isdigit():
                extra += f' data-page="{page}"'
            else:
                extra += ' target="_blank" rel="noopener noreferrer"'
        elif tag in ("span", "mark"):
            cls = [c for c in (a.get("class") or "").split() if re.fullmatch(r"(c|bg)-(%s)" % "|".join(COLORS), c)]
            if cls:
                extra = f' class="{" ".join(cls)}"'
            elif tag == "span":
                return
        self.stack.append(tag)
        self.out.append(f"<{tag}{extra}>")

    def handle_endtag(self, tag):
        if tag in self.DROP_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in self.stack:
            return
        while self.stack:                           # fecha o que estiver aberto até a tag
            t = self.stack.pop()
            self.out.append(f"</{t}>")
            if t == tag:
                break

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and not self.skip:
            self.out.append("<br>")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(escape(data, quote=False))

    def result(self):
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")
        return "".join(self.out)


def clean_html(value, limit=20000):
    p = _Clean()
    p.feed(str(value or "")[: limit * 2])
    p.close()
    out = p.result()
    return out[:limit] if len(out) > limit else out


class _Text(HTMLParser):
    def __init__(self, titles):
        super().__init__(convert_charrefs=True)
        self.titles, self.out, self.link = titles, [], None

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.out.append("\n")
        elif tag == "a":
            page = dict(attrs).get("data-page")
            self.link = page if page and page.isdigit() else None

    def handle_endtag(self, tag):
        if tag == "a" and self.link:
            t = self.titles.get(int(self.link))
            if t:
                self.out.append(f" [[{t}]]")
            self.link = None

    def handle_data(self, data):
        self.out.append(data)


def html_to_text(value, titles):
    p = _Text(titles)
    p.feed(value or "")
    p.close()
    return "".join(p.out)


# --------------------------------------------------------------------------- validação dos blocos

def _s(v, n):
    return str(v or "")[:n]


def _num(v, default, lo, hi):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


class Ctx:
    """O que vale neste mundo: ids de páginas e de arquivos."""

    def __init__(self, page_ids, file_ids):
        self.page_ids, self.file_ids, self.count = set(page_ids), set(file_ids), 0


def clean_blocks(items, ctx, depth=0, in_columns=False):
    out = []
    if not isinstance(items, list) or depth > MAX_DEPTH:
        return out
    for b in items:
        if ctx.count >= MAX_BLOCKS:
            break
        cb = _clean_block(b, ctx, depth, in_columns)
        if isinstance(cb, list):        # colunas desfeitas: os blocos voltam para a lista
            out.extend(cb)
        elif cb:
            ctx.count += 1
            out.append(cb)
    return out


def _clean_block(b, ctx, depth, in_columns):
    if not isinstance(b, dict) or b.get("type") not in TYPES:
        return None
    t = b["type"]
    o = {"id": re.sub(r"[^A-Za-z0-9_-]", "", _s(b.get("id"), 24)) or "b", "type": t}
    color = _s(b.get("color"), 12)
    if color in BLOCK_COLORS and color:
        o["color"] = color
    if t in RICH_TYPES:
        o["html"] = clean_html(b.get("html"))
        if t == "todo":
            o["checked"] = bool(b.get("checked"))
        if t == "callout":
            icon = _s(b.get("icon"), 60)
            o["icon"] = icon if _ICON_OK.match(icon) else "ri:candle"
        if t == "toggle":
            o["open"] = bool(b.get("open", True))
            o["children"] = clean_blocks(b.get("children"), ctx, depth + 1, in_columns)
    elif t == "code":
        o["text"] = _s(b.get("text"), 20000)
    elif t == "markdown":
        o["md"] = _s(b.get("md"), 100000)
    elif t == "divider":
        style = _s(b.get("style"), 60)
        o["style"] = style if re.fullmatch(r"[a-z0-9_-]{1,40}", style) else "line"
    elif t == "image":
        src = _s(b.get("src"), 1000).strip()
        m = _FILE_SRC.match(src)
        if m and int(m.group(1)) not in ctx.file_ids:
            src = ""
        if src and not m and not src.startswith("https://"):
            src = ""
        o.update(src=src, width=_num(b.get("width"), 100, 10, 100), caption=clean_html(b.get("caption"), 2000),
                 align=b.get("align") if b.get("align") in ("left", "center", "right") else "center")
    elif t == "embed":
        url = _s(b.get("url"), 1000).strip()
        o.update(url=url if url.startswith(("https://", "http://")) else "", width=_num(b.get("width"), 100, 20, 100),
                 caption=clean_html(b.get("caption"), 2000))
    elif t in ("audio", "video", "file"):
        try:
            fid = int(b.get("file_id") or 0)
        except (TypeError, ValueError):
            fid = 0
        o.update(file_id=fid if fid in ctx.file_ids else 0, name=_s(b.get("name"), 200),
                 caption=clean_html(b.get("caption"), 2000))
        if t == "video":
            o["width"] = _num(b.get("width"), 100, 20, 100)
    elif t == "page":
        try:
            pid = int(b.get("page_id") or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid not in ctx.page_ids:
            return None
        o["page_id"] = pid
    elif t == "table":
        rows = b.get("rows") if isinstance(b.get("rows"), list) else []
        rows = [[clean_html(c, 4000) for c in (r if isinstance(r, list) else [])[:20]] for r in rows[:100]]
        width = max((len(r) for r in rows), default=0)
        o["rows"] = [r + [""] * (width - len(r)) for r in rows] or [["", ""], ["", ""]]
        o["header"] = bool(b.get("header", True))
    elif t == "columns":
        if in_columns:          # colunas dentro de colunas: achata
            inner = []
            for c in (b.get("cols") or [])[:5]:
                inner += clean_blocks((c or {}).get("blocks") if isinstance(c, dict) else [], ctx, depth + 1, True)
            return inner
        cols = []
        for c in (b.get("cols") or [])[:5]:
            if isinstance(c, dict):
                cols.append({"w": _num(c.get("w"), 50, 5, 95), "blocks": clean_blocks(c.get("blocks"), ctx, depth + 1, True)})
        cols = [c for c in cols if c["blocks"]]
        if len(cols) < 2:
            return cols[0]["blocks"] if cols else None
        total = sum(c["w"] for c in cols)
        for c in cols:
            c["w"] = round(c["w"] * 100 / total, 2)
        o["cols"] = cols
    return o


# --------------------------------------------------------------------------- texto e utilidades

def blocks_text(blocks, titles):
    """Texto puro (com [[links]] para páginas) usado na busca e em 'Mencionada em'."""
    lines = []

    def walk(items):
        for b in items:
            t = b["type"]
            if t in RICH_TYPES:
                prefix = {"h1": "# ", "h2": "## ", "h3": "### ", "bullet": "- ", "number": "1. ", "quote": "> ",
                          "todo": "- [x] " if b.get("checked") else "- [ ] "}.get(t, "")
                lines.append(prefix + html_to_text(b.get("html"), titles))
                walk(b.get("children") or [])
            elif t == "code":
                lines.append(b.get("text", ""))
            elif t == "markdown":
                lines.append(b.get("md", ""))
            elif t == "page" and titles.get(b["page_id"]):
                lines.append(f"[[{titles[b['page_id']]}]]")
            elif t == "table":
                for r in b["rows"]:
                    lines.append(" | ".join(html_to_text(c, titles) for c in r))
            elif t in ("image", "embed", "audio", "video", "file"):
                cap = html_to_text(b.get("caption"), titles)
                if cap:
                    lines.append(cap)
            elif t == "columns":
                for c in b["cols"]:
                    walk(c["blocks"])
    walk(blocks)
    return "\n\n".join(x for x in lines if x.strip())


def page_ids_in(blocks):
    ids = set()

    def walk(items):
        for b in items:
            if b["type"] == "page":
                ids.add(b["page_id"])
            walk(b.get("children") or [])
            for c in b.get("cols") or []:
                walk(c["blocks"])
    walk(blocks)
    return ids


def file_ids_in(blocks):
    ids = set()

    def walk(items):
        for b in items:
            if b.get("file_id"):
                ids.add(b["file_id"])
            m = _FILE_SRC.match(b.get("src") or "")
            if m:
                ids.add(int(m.group(1)))
            walk(b.get("children") or [])
            for c in b.get("cols") or []:
                walk(c["blocks"])
    walk(blocks)
    return ids


def load_blocks(page):
    """Blocos da página; páginas antigas (só Markdown) viram um bloco 'markdown'."""
    raw = page["blocks"] if "blocks" in page.keys() else ""
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
        except ValueError:
            pass
    if (page["content"] or "").strip():
        return [{"id": "legado", "type": "markdown", "md": page["content"]}]
    return []


def with_markdown_html(blocks, render):
    """Acrescenta `_html` (só para mostrar) nos blocos markdown, sem tocar no que é salvo."""
    out = []
    for b in blocks:
        b = dict(b)
        if b["type"] == "markdown":
            b["_html"] = str(render(b.get("md", "")))
        if b.get("children"):
            b["children"] = with_markdown_html(b["children"], render)
        if b.get("cols"):
            b["cols"] = [{**c, "blocks": with_markdown_html(c["blocks"], render)} for c in b["cols"]]
        out.append(b)
    return out


__all__ = ["clean_html", "clean_blocks", "blocks_text", "load_blocks", "with_markdown_html", "page_ids_in",
           "file_ids_in", "Ctx", "Markup"]
