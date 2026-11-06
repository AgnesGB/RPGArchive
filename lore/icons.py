"""Ícones do site.

- Pixel-art (pack Raven Fantasy, sprite em static/icons/raven.*): coisas do mundo
  (navegação, categorias, tipos de card).            ->  ri("castle"), ri("map", 32)
- Traço (static/icons/ui.svg): ações e controles
  (apagar, fechar, editar, desfazer…).                ->  ui("trash")
- Ícone guardado num campo (página, mundo):           ->  {{ valor|glyph }}
    ""                vazio: quem chama decide o padrão (ex.: ícone da categoria)
    "ri:<nome>"       ícone pixel do pack
    "img:<url>"       imagem enviada pela pessoa
    qualquer outro    emoji/texto curto escolhido pela pessoa
"""
import re

from flask import request, url_for
from markupsafe import Markup, escape

RI_PREFIX = "ri:"
IMG_PREFIX = "img:"

# Ícones oferecidos no seletor de ícone de mundo/página (nomes do sprite raven.css)
PRESETS = [
    "world", "castle", "tower", "mountain", "tree", "fire", "hood", "wizard", "helmet", "shield",
    "sword", "bow", "staff", "potion", "orb", "book", "tome", "scroll", "map", "quill",
    "key", "chest", "coin", "bag", "gem", "ruby", "ring", "trophy", "scales", "anvil",
    "skull", "pirate", "beast", "mushroom", "rose", "clover", "heart", "star", "moon", "sun",
    "holy", "candle", "fish", "flag",
]
_IMG_URL = re.compile(r"^/f/(\d+)$")


def ri(name: str, size: int = 16, cls: str = "") -> Markup:
    size_cls = f" ri-{size}" if size != 16 else ""
    return Markup(f'<span class="ri ri-{escape(name)}{size_cls} {escape(cls)}" aria-hidden="true"></span>')


def ui(name: str, cls: str = "size-4") -> Markup:
    href = url_for("static", filename="icons/ui.svg") + "#" + name
    return Markup(
        f'<svg class="ui {escape(cls)}" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round"><use href="{escape(href)}"/></svg>'
    )


def glyph(value, size: int = 16, cls: str = "") -> Markup:
    """Renderiza um valor de ícone (veja o topo do arquivo)."""
    value = value or ""
    if value.startswith(RI_PREFIX):
        return ri(value[len(RI_PREFIX):], size, cls)
    if value.startswith(IMG_PREFIX):
        return Markup(f'<img src="{escape(value[len(IMG_PREFIX):])}" alt="" loading="lazy" '
                      f'class="inline-block shrink-0 rounded-[22%] object-cover align-middle {escape(cls)}" '
                      f'style="width:{int(size)}px;height:{int(size)}px">')
    return Markup(f'<span class="{escape(cls)}">{escape(value)}</span>') if cls else escape(value)


def glyph_text(value) -> str:
    """Para <option> e textos simples: só o emoji da pessoa (ícones e imagens não cabem em texto)."""
    value = value or ""
    return "" if value.startswith((RI_PREFIX, IMG_PREFIX)) else value


def clean_icon(value: str, world_id: int) -> str:
    """Valida o valor vindo do seletor: preset conhecido, imagem do acervo do mundo ou emoji curto."""
    value = (value or "").strip()
    if value.startswith(RI_PREFIX):
        return value if value[len(RI_PREFIX):] in PRESETS else ""
    if value.startswith(IMG_PREFIX):
        m = _IMG_URL.match(value[len(IMG_PREFIX):])
        if not m:
            return ""
        from .db import get_db
        ok = get_db().execute("SELECT 1 FROM files WHERE id = ? AND world_id = ? AND mime LIKE 'image/%'",
                              (int(m.group(1)), world_id)).fetchone()
        return value if ok else ""
    return value[:8]


def icon_from_form(world_id: int) -> str:
    """Lê o seletor de ícone de um formulário (campos icon + icon_file). Pode lançar UploadError."""
    fs = request.files.get("icon_file")
    if fs and fs.filename:
        from .files import save_upload
        return IMG_PREFIX + url_for("files.serve", fid=save_upload(world_id, fs, images_only=True))
    return clean_icon(request.form.get("icon", ""), world_id)


def init_app(app):
    app.jinja_env.globals.update(ri=ri, ui=ui, ICON_PRESETS=PRESETS)
    app.jinja_env.filters["glyph"] = glyph
    app.jinja_env.filters["glyph_text"] = glyph_text
