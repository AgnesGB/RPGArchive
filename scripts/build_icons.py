"""Gera o sprite de ícones pixel-art do site a partir do pack "Raven Fantasy Icons".

Uso:
    python scripts/build_icons.py "C:/caminho/Free - Raven Fantasy Icons"

Lê  <pack>/Full Spritesheet/16x16.png  (16 colunas, 16 px por ícone) e grava:
    lore/static/icons/raven.png   uma linha com só os ícones usados no site
    lore/static/icons/raven.css   classes .ri .ri-<nome> e tamanhos .ri-32/.ri-48/.ri-64 (múltiplos inteiros: pixel nítido)

Para trocar ou acrescentar um ícone, edite ICONS (nome -> índice no spritesheet,
contando da esquerda para a direita, de cima para baixo, a partir de 0).
"""
import sys
from pathlib import Path

from PIL import Image

ICONS = {
    # marca e navegação
    "orb": 292,        # Aquele que Observa
    "home": 15,
    "web": 904,        # mapas mentais
    "map": 307,
    "scroll": 300,     # linhas do tempo
    "tree": 31,        # árvores genealógicas
    "chest": 5,        # acervo
    "people": 990,
    "gear": 1,
    "tome": 288,       # páginas
    "world": 21,
    # categorias de página
    "hood": 2014,      # personagem
    "castle": 36,      # local
    "shield": 852,     # facção
    "beast": 1065,     # criatura
    "gem": 165,        # item
    "star": 11,        # evento
    "book": 291,       # livro / registro
    "quill": 955,      # nota
    # tipos de card e mapa
    "candle": 82,      # ideia
    "picture": 289,    # imagem
    "redbook": 96,     # pdf
    "parchment": 304,  # arquivo
    "flag": 42,        # marcador
    "coin": 130,       # token
    "sword": 671,      # jogar
    "bucket": 339,
    "brick": 202,
    "ring": 1844,      # cônjuge
    "chain": 158,      # link
    "sun": 989,
    "moon": 976,
    # extras para o seletor de ícone de mundo/página
    "tower": 37,
    "mountain": 29,
    "fire": 909,
    "wizard": 1840,
    "helmet": 1910,
    "bow": 1513,
    "staff": 1689,
    "potion": 275,
    "key": 178,
    "ruby": 162,
    "trophy": 14,
    "scales": 123,
    "anvil": 124,
    "skull": 224,
    "pirate": 672,
    "mushroom": 247,
    "rose": 262,
    "clover": 667,
    "heart": 658,
    "holy": 669,
    "fish": 352,
    "bag": 157,
}

SIZE = 16
COLS = 16
OUT = Path(__file__).resolve().parent.parent / "lore" / "static" / "icons"


def main(pack: str) -> None:
    sheet = Image.open(Path(pack) / "Full Spritesheet" / "16x16.png").convert("RGBA")
    names = list(ICONS)
    sprite = Image.new("RGBA", (SIZE * len(names), SIZE), (0, 0, 0, 0))
    for i, name in enumerate(names):
        r, c = divmod(ICONS[name], COLS)
        tile = sheet.crop((c * SIZE, r * SIZE, (c + 1) * SIZE, (r + 1) * SIZE))
        if tile.getbbox() is None:
            raise SystemExit(f"Ícone vazio: {name} ({ICONS[name]})")
        sprite.paste(tile, (i * SIZE, 0))
    OUT.mkdir(parents=True, exist_ok=True)
    sprite.save(OUT / "raven.png", optimize=True)

    n = len(names)
    css = [
        "/* gerado por scripts/build_icons.py — não edite à mão */",
        ".ri{display:inline-block;flex:none;width:16px;height:16px;vertical-align:-3px;"
        "background:url(raven.png) no-repeat;background-size:%d00%% 100%%;image-rendering:pixelated}" % n,
        ".ri-32{width:32px;height:32px;vertical-align:-8px}",
        ".ri-48{width:48px;height:48px}",
        ".ri-64{width:64px;height:64px}",
    ]
    for i, name in enumerate(names):
        css.append(f".ri-{name}{{background-position:{i * 100 / (n - 1):.4f}% 0}}")
    (OUT / "raven.css").write_text("\n".join(css) + "\n", encoding="utf-8")
    print(f"{n} ícones -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
