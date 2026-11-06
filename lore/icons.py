"""Ícones do site.

- Pixel-art (pack Raven Fantasy, sprite em static/icons/raven.*): coisas do mundo
  (navegação, categorias, tipos de card).            ->  ri("castle"), ri("map", 32)
- Traço (static/icons/ui.svg): ações e controles
  (apagar, fechar, editar, desfazer…).                ->  ui("trash")
- Ícone guardado num campo (página, mundo): pode ser emoji escolhido pela pessoa
  ou "ri:<nome>" (padrão da categoria).               ->  {{ valor|glyph }}
"""
from flask import url_for
from markupsafe import Markup, escape

RI_PREFIX = "ri:"


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
    """Emoji/texto da pessoa, ou ícone pixel quando o valor é "ri:<nome>"."""
    value = value or ""
    if value.startswith(RI_PREFIX):
        return ri(value[len(RI_PREFIX):], size, cls)
    return Markup(f'<span class="{escape(cls)}">{escape(value)}</span>') if cls else escape(value)


def glyph_text(value) -> str:
    """Para <option> e textos simples: só o emoji da pessoa (ícones pixel não cabem em texto)."""
    value = value or ""
    return "" if value.startswith(RI_PREFIX) else value


def init_app(app):
    app.jinja_env.globals.update(ri=ri, ui=ui)
    app.jinja_env.filters["glyph"] = glyph
    app.jinja_env.filters["glyph_text"] = glyph_text
