"""Gera o kit do editor de mapas (lore/static/mapkit) a partir dos pacotes em assets/.

Uso:  .venv\\Scripts\\pip install -r requirements-dev.txt
      .venv\\Scripts\\python scripts\\build_mapkit.py               (kit completo, uso pessoal)
      .venv\\Scripts\\python scripts\\build_mapkit.py --comercial   (só pacotes que permitem uso comercial)
      ... --out <pasta>   gera em outra pasta (ex.: para comparar sem mexer no kit do site)

Recorta tiles de terreno, separa cada objeto dos spritesheets, monta peças de parede compostas
e escreve manifest.json. Só precisa rodar de novo se mudar os assets.
"""
import argparse
import json
import re
import shutil
from collections import Counter, deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets"
OUT = ROOT / "lore" / "static" / "mapkit"

CUTE = "Cute_Fantasy_Free/Cute_Fantasy_Free"
ICONS = "Cute_Fantasy_Icons_Free/Cute_Fantasy_Icons_Free"
DP = "Dungeons and Pixels — Free Demo"
FAN = "The Fan-tasy Tileset (Free) 1.5.9/The Fan-tasy Tileset (Free)/Art"
FARM = "Farm RPG FREE 16x16 - Tiny Asset Pack/Farm RPG FREE 16x16 - Tiny Asset Pack"
X72 = "novos/0x72_DungeonTilesetII_v1.7/0x72_DungeonTilesetII_v1.7/frames"
PTD = "novos/Pixel Art Top Down - Basic v1.2.3/Texture"
FREEPACK = "novos/FreeEnvironment/FreeEnvironment/FreePack.png"
PLAT = "novos/Multi_Platformer_Tileset_Free/Multi_Platformer_Tileset_Free/GrassLand/Props"
TINY = "novos/Tiny RPG Character Asset Pack 01 v2.0 -Free Soldier&Orc/Tiny RPG Character Asset Pack 01 v2.0 -Free Soldier&Orc/Characters(100x100 split)"
CRYSTALS = "catalisadores"

# Pacotes cuja licença NÃO permite (ou ainda não confirmamos que permite) uso comercial.
# No modo --comercial tudo que vem deles fica de fora.
NON_COMMERCIAL = {
    CUTE: "Cute Fantasy Free (Kenmi): versão grátis não comercial; a premium libera",
    ICONS: "Cute Fantasy Icons Free (Kenmi): versão grátis não comercial; a premium libera",
    FAN: "The Fan-tasy Tileset (Free): licença da versão grátis não confirmada",
    FARM: "Farm RPG Tiny Asset Pack: licença da versão grátis não confirmada",
    FREEPACK: "FreeEnvironment: origem e licença desconhecidas",
    CRYSTALS: "Catalisadores (cristais): origem desconhecida",
}
COMMERCIAL = False   # ligado por --comercial
skipped = Counter()  # pacote bloqueado -> quantos recortes ficaram de fora


def blocked(path):
    if not COMMERCIAL:
        return None
    return next((pack for pack in NON_COMMERCIAL if str(path).startswith(pack)), None)

# ---------------------------------------------------------------- terrenos (chave, rótulo, arquivo, recorte)
TILE_TERRAINS = [
    ("grama", "Grama", f"{FAN}/Ground Tileset/Tileset_Ground.png", (0, 128, 16, 16)),
    ("grama_lisa", "Grama lisa", f"{FAN}/Ground Tileset/Tileset_Ground.png", (32, 16, 16, 16)),
    ("grama_viva", "Grama viva", f"{CUTE}/Tiles/Grass_Middle.png", None),
    ("grama_campo", "Grama do campo", f"{PTD}/TX Tileset Grass.png", (0, 0, 32, 32)),
    ("grama_pedrinhas", "Grama com pedrinhas", f"{PTD}/TX Tileset Grass.png", (160, 32, 32, 32)),
    ("terra", "Terra", f"{FAN}/Ground Tileset/Tileset_Ground.png", (176, 112, 16, 16)),
    ("caminho", "Caminho", f"{FAN}/Ground Tileset/Tileset_Road.png", (0, 128, 16, 16)),
    ("trilha", "Trilha", f"{CUTE}/Tiles/Path_Middle.png", None),
    ("areia", "Areia", f"{CUTE}/Tiles/Beach_Tile.png", (16, 16, 16, 16)),
    ("agua", "Água", f"{FAN}/Water and Sand/Tileset_Water.png", (0, 128, 16, 16)),
    ("agua_calma", "Água calma", f"{FAN}/Water and Sand/Tileset_Water.png", (32, 16, 16, 16)),
    ("lago", "Lago", f"{CUTE}/Tiles/Water_Middle.png", None),
    ("piso_pedra", "Piso de pedra", f"{DP}/Tilesets/Tileset_Dungeon.png", (32, 32, 32, 32)),
    ("piso_musgo", "Pedra com musgo", f"{DP}/Tilesets/Tileset_Dungeon.png", (64, 32, 32, 32)),
    ("lajotas", "Lajotas", f"{PTD}/TX Tileset Stone Ground.png", (32, 32, 32, 32)),
    ("masmorra_1", "Masmorra", f"{X72}/floor_1.png", None),
    ("masmorra_2", "Masmorra rachada", f"{X72}/floor_2.png", None),
    ("masmorra_3", "Masmorra antiga", f"{X72}/floor_3.png", None),
    ("masmorra_6", "Masmorra irregular", f"{X72}/floor_6.png", None),
    ("acido", "Ácido / pântano", f"{DP}/Tilesets/Tileset_Dungeon.png", (256, 128, 32, 32)),
]
# No modo comercial, terrenos de pacotes bloqueados ganham um substituto com a MESMA chave,
# para mapas já pintados e o seletor de "terreno base" continuarem funcionando.
TERRAIN_FALLBACK = {
    "grama": (f"{PTD}/TX Tileset Grass.png", (0, 0, 32, 32)),
    "grama_lisa": (f"{PTD}/TX Tileset Grass.png", (32, 0, 32, 32)),
    "grama_viva": (f"{PTD}/TX Tileset Grass.png", (64, 0, 32, 32)),
    "terra": ("#7a5a3a", "#6a4d31"),
    "caminho": ("#a88a5f", "#957a52"),
    "trilha": ("#b39668", "#a08559"),
    "areia": ("#e6d39a", "#d8c486"),
    "agua": ("#3f7fbf", "#3672ad"),
    "agua_calma": ("#5a96c9", "#4f89bb"),
    "lago": ("#2f6fa8", "#285f91"),
}
COLOR_TERRAINS = [
    ("floresta", "Floresta", "#2f5d34", "#244a29"),
    ("montanha", "Montanha", "#7b7368", "#5f5850"),
    ("neve", "Neve", "#eef2f7", "#d6dee8"),
    ("gelo", "Gelo", "#bfe3f2", "#9fd0e6"),
    ("lava", "Lava", "#d9480f", "#f59f00"),
    ("madeira", "Piso de madeira", "#9c6b3c", "#7d5430"),
    ("deserto", "Deserto", "#e3c48a", "#cfae70"),
    ("pantano", "Pântano", "#556b2f", "#3f5222"),
    ("cinzas", "Cinzas", "#4a4a4a", "#3a3a3a"),
    ("tapete", "Tapete real", "#8b1e2d", "#6e1622"),
    ("abismo", "Abismo", "#0d0c12", "#1a1822"),
    ("mar", "Mar profundo", "#1c4f8a", "#174273"),
]

# ---------------------------------------------------------------- texturas das paredes desenhadas nas arestas
WALL_TEXTURES = {
    "stone": (f"{X72}/wall_mid.png", None),
    "brick": (f"{DP}/Tilesets/Tileset_Dungeon.png", (224, 64, 32, 32)),
    "block": (f"{PTD}/TX Tileset Wall.png", (64, 192, 32, 32)),
    "door": (f"{X72}/doors_leaf_closed.png", None),
}

LABELS = {
    "Tree_Emerald": "Árvore", "Oak_Tree": "Carvalho", "Bush_Emerald": "Arbusto", "Chopped_Tree": "Toco",
    "Plant": "Planta", "Barrel_Small_Empty": "Barril", "Crate_Large_Empty": "Caixote grande",
    "Crate_Medium_Closed": "Caixote", "Crate_Water": "Caixote com água", "Sack": "Saco", "Basket_Empty": "Cesto",
    "HayStack": "Feno", "Sign": "Placa", "Bench": "Banco", "Table_Medium": "Mesa", "Fireplace": "Fogueira",
    "LampPost": "Poste", "BulletinBoard": "Mural de avisos", "Banner_Stick": "Estandarte",
    "Front_Door_Closed": "Porta fechada", "Front_Door_Open": "Porta aberta", "Side_Door_Closed": "Porta lateral fechada",
    "Side_Door_Open": "Porta lateral aberta", "bones": "Ossos", "bronze_chest_closed": "Baú de bronze",
    "bronze_chest_open": "Baú de bronze aberto",
}
X72_NAMES = {
    "angel": "Anjo", "big_demon": "Demônio grande", "big_zombie": "Zumbi grande", "chort": "Chort", "doc": "Doutor da peste",
    "dwarf_f": "Anã", "dwarf_m": "Anão", "elf_f": "Elfa", "elf_m": "Elfo", "goblin": "Goblin", "ice_zombie": "Zumbi de gelo",
    "imp": "Diabrete", "knight_f": "Cavaleira", "knight_m": "Cavaleiro", "lizard_f": "Lagarta guerreira", "lizard_m": "Lagarto guerreiro",
    "masked_orc": "Orc mascarado", "muddy": "Lodo", "necromancer": "Necromante", "ogre": "Ogro", "orc_shaman": "Xamã orc",
    "orc_warrior": "Guerreiro orc", "pumpkin_dude": "Cabeça de abóbora", "skelet": "Esqueleto", "slug": "Lesma",
    "swampy": "Criatura do pântano", "tiny_slug": "Lesminha", "tiny_zombie": "Zumbizinho", "wizzard_f": "Maga",
    "wizzard_m": "Mago", "wogol": "Wogol", "zombie": "Zumbi",
}
HEROES = {"angel", "dwarf_f", "dwarf_m", "elf_f", "elf_m", "knight_f", "knight_m", "lizard_f", "lizard_m", "wizzard_f", "wizzard_m"}


def slug(s):
    return re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower() or "x"


def label_for(path):
    stem = Path(path).stem
    for k, v in LABELS.items():
        if stem.startswith(k):
            num = re.findall(r"_(\d+)$", stem)
            return f"{v} {num[0]}" if num else v
    return stem.replace("_", " ")


def load(path, box=None):
    """Abre um recorte de assets/. No modo --comercial devolve None se o pacote for bloqueado."""
    pack = blocked(path)
    if pack:
        skipped[pack] += 1
        return None
    im = Image.open(SRC / path).convert("RGBA")
    if box:
        x, y, w, h = box
        im = im.crop((x, y, x + w, y + h))
    return im


def stack(*parts):
    """Empilha imagens de cima para baixo; um item (img, 'over') é desenhado por cima da peça anterior."""
    base = [p for p in parts if not isinstance(p, tuple)]
    out = Image.new("RGBA", (max(p.width for p in base), sum(p.height for p in base)))
    y = last_y = 0
    for p in parts:
        if isinstance(p, tuple):
            out.alpha_composite(p[0], (0, last_y))
            continue
        out.alpha_composite(p, (0, y))
        last_y, y = y, y + p.height
    return out


def grid_components(im, cell, auto=True, groups=()):
    """Spritesheet em grade: cada célula é um objeto, a menos que o desenho atravesse a borda para a vizinha
    (auto) ou que a célula esteja num dos `groups` informados (objetos grandes, ex.: poste de 3 células)."""
    a = im.getchannel("A").load()
    cols, rows = im.width // cell, im.height // cell
    filled = {(c, r) for r in range(rows) for c in range(cols)
              if im.crop((c * cell, r * cell, (c + 1) * cell, (r + 1) * cell)).getbbox()}
    parent = {k: k for k in filled}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def touches(c, r, horizontal):
        n = 0
        if horizontal:   # borda vertical entre (c,r) e (c+1,r)
            x = (c + 1) * cell
            for y in range(r * cell, (r + 1) * cell):
                if a[x - 1, y] > 16 and a[x, y] > 16:
                    n += 1
        else:            # borda horizontal entre (c,r) e (c,r+1)
            y = (r + 1) * cell
            for x in range(c * cell, (c + 1) * cell):
                if a[x, y - 1] > 16 and a[x, y] > 16:
                    n += 1
        return n >= 2

    for g in groups:
        for k in g[1:]:
            if k in filled and g[0] in filled:
                parent[find(k)] = find(g[0])
    for (c, r) in (filled if auto else ()):
        if (c + 1, r) in filled and touches(c, r, True):
            parent[find((c + 1, r))] = find((c, r))
        if (c, r + 1) in filled and touches(c, r, False):
            parent[find((c, r + 1))] = find((c, r))
    groups = {}
    for k in filled:
        groups.setdefault(find(k), []).append(k)
    boxes = [(min(c for c, _ in g) * cell, min(r for _, r in g) * cell,
              (max(c for c, _ in g) + 1) * cell, (max(r for _, r in g) + 1) * cell) for g in groups.values()]
    return sorted(boxes, key=lambda b: (b[1], b[0]))


def free_components(im, min_area=40, gap=2):
    """Sprites soltos (sem grade): áreas conectadas, juntando pedaços a até `gap` px."""
    a = im.getchannel("A").load()
    w, h = im.size
    seen = bytearray(w * h)
    boxes = []
    for y in range(h):
        for x in range(w):
            if seen[y * w + x] or a[x, y] < 16:
                continue
            q = deque([(x, y)])
            seen[y * w + x] = 1
            x0 = x1 = x
            y0 = y1 = y
            n = 0
            while q:
                cx, cy = q.popleft()
                n += 1
                x0, y0, x1, y1 = min(x0, cx), min(y0, cy), max(x1, cx), max(y1, cy)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx] and a[nx, ny] >= 16:
                            seen[ny * w + nx] = 1
                            q.append((nx, ny))
            boxes.append([x0, y0, x1 + 1, y1 + 1, n])
    changed = True
    while changed:
        changed = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                A, B = boxes[i], boxes[j]
                if A[0] - gap < B[2] and B[0] - gap < A[2] and A[1] - gap < B[3] and B[1] - gap < A[3]:
                    boxes[i] = [min(A[0], B[0]), min(A[1], B[1]), max(A[2], B[2]), max(A[3], B[3]), A[4] + B[4]]
                    boxes.pop(j)
                    changed = True
                    break
            if changed:
                break
    return sorted([b[:4] for b in boxes if b[4] >= min_area], key=lambda b: (b[1] // 16, b[0]))


def first_frame(name):
    folder = SRC / X72
    for pat in (f"{name}_idle_anim_f0.png", f"{name}_anim_f0.png", f"{name}_anim_f1.png", f"{name}.png"):
        if (folder / pat).exists():
            return f"{X72}/{pat}"
    return None


def main():
    global COMMERCIAL, OUT
    ap = argparse.ArgumentParser(description="Gera o kit do editor de mapas.")
    ap.add_argument("--comercial", action="store_true", help="usa só pacotes que permitem uso comercial")
    ap.add_argument("--out", type=Path, help="pasta de saída (padrão: lore/static/mapkit)")
    args = ap.parse_args()
    COMMERCIAL = args.comercial
    if args.out:
        OUT = args.out.resolve()
    if OUT.exists():
        shutil.rmtree(OUT)
    for d in ("terrain", "props", "walls"):
        (OUT / d).mkdir(parents=True)
    manifest = {"terrains": [], "props": [], "walls": {}}

    for key, label, path, box in TILE_TERRAINS:
        im = load(path, box)
        if im is None:
            fb = TERRAIN_FALLBACK.get(key)
            if fb and fb[0].startswith("#"):
                manifest["terrains"].append({"key": key, "label": label, "file": None, "color": fb[0], "color2": fb[1]})
                continue
            im = load(*fb) if fb else None
            if im is None:
                continue
        im.save(OUT / "terrain" / f"{key}.png")
        avg = im.convert("RGB").resize((1, 1), Image.BOX).getpixel((0, 0))
        manifest["terrains"].append({"key": key, "label": label, "file": f"terrain/{key}.png",
                                     "color": "#%02x%02x%02x" % avg, "px": im.width})
    for key, label, c1, c2 in COLOR_TERRAINS:
        manifest["terrains"].append({"key": key, "label": label, "file": None, "color": c1, "color2": c2})
    for key, (path, box) in WALL_TEXTURES.items():
        im = load(path, box)
        if im is None:
            continue
        im.save(OUT / "walls" / f"{key}.png")
        manifest["walls"][key] = {"file": f"walls/{key}.png", "px": im.width}

    used = set()

    def add(cat, im, name, label, unit=16):
        if im is None:
            return
        bbox = im.getbbox()
        if not bbox:
            return
        im = im.crop(bbox)
        key = slug(f"{cat}_{name}")
        while key in used:
            key += "_b"
        used.add(key)
        im.save(OUT / "props" / f"{key}.png")
        manifest["props"].append({"key": key, "label": label, "category": cat, "file": f"props/{key}.png",
                                  "w": im.width, "h": im.height, "u": unit})

    def add_sheet(cat, path, prefix, label, unit, cell=None, min_area=40, gap=2, auto=True, groups=()):
        im = load(path)
        if im is None:
            return
        boxes = grid_components(im, cell, auto, groups) if cell else free_components(im, min_area, gap)
        for i, b in enumerate(boxes, 1):
            add(cat, im.crop(b), f"{prefix}_{i}", f"{label} {i}", unit)

    def W(n):
        return load(f"{X72}/{n}.png")

    # ---- Paredes: peças que ocupam o quadrado (encaixam no grid)
    add("Paredes", stack(W("wall_top_mid"), W("wall_mid")), "parede", "Parede de masmorra")
    add("Paredes", stack(W("wall_top_left"), W("wall_left")), "parede_esq", "Parede (ponta esquerda)")
    add("Paredes", stack(W("wall_top_right"), W("wall_right")), "parede_dir", "Parede (ponta direita)")
    add("Paredes", W("wall_top_mid"), "topo", "Topo de parede")
    for cor, nome in (("blue", "azul"), ("green", "verde"), ("red", "vermelho"), ("yellow", "amarelo")):
        add("Paredes", stack(W("wall_top_mid"), W("wall_mid"), (W(f"wall_banner_{cor}"), "over")), f"estandarte_{cor}",
            f"Parede com estandarte {nome}")
    for cor, nome in (("blue", "azul"), ("red", "vermelha")):
        add("Paredes", stack(W("wall_fountain_top_1"), W(f"wall_fountain_mid_{cor}_anim_f0"),
                             W(f"wall_fountain_basin_{cor}_anim_f0")), f"fonte_{cor}", f"Fonte {nome}")
    add("Paredes", stack(W("wall_top_mid"), W("wall_mid"), (W("wall_goo"), "over"), W("wall_goo_base")), "limo", "Parede com limo")
    add("Paredes", stack(W("wall_top_mid"), W("wall_hole_1")), "buraco1", "Parede com buraco")
    add("Paredes", stack(W("wall_top_mid"), W("wall_hole_2")), "buraco2", "Parede rachada")
    add("Paredes", W("column"), "coluna", "Coluna")
    add("Paredes", W("column_wall"), "coluna_parede", "Coluna na parede")
    door = Image.new("RGBA", (64, 48))
    door.alpha_composite(W("doors_frame_left"), (0, 16))
    door.alpha_composite(W("doors_frame_right"), (48, 16))
    door.alpha_composite(W("doors_frame_top"), (16, 0))
    door_open = door.copy()
    door.alpha_composite(W("doors_leaf_closed"), (16, 16))
    door_open.alpha_composite(W("doors_leaf_open"), (16, 16))
    add("Paredes", door, "porta_fechada", "Porta de masmorra")
    add("Paredes", door_open, "porta_aberta", "Porta de masmorra aberta")
    for x, y, w, h, nome in ((32, 0, 32, 32, "Muro de tijolos"), (64, 0, 32, 32, "Muro com musgo"),
                             (128, 0, 32, 32, "Muro com grade"), (224, 64, 32, 32, "Tijolos"), (192, 64, 32, 32, "Tijolos 2")):
        add("Paredes", load(f"{DP}/Tilesets/Tileset_Dungeon.png", (x, y, w, h)), slug(nome), nome, 32)
    add_sheet("Paredes", f"{PTD}/TX Tileset Wall.png", "bloco", "Bloco de pedra", 32)
    add_sheet("Paredes", f"{PTD}/TX Struct.png", "estrutura", "Estrutura de pedra", 32)
    for n in ("wall_left", "wall_right", "wall_mid", "wall_edge_left", "wall_edge_right", "wall_edge_top_left",
              "wall_edge_top_right", "wall_edge_bottom_left", "wall_edge_bottom_right", "wall_edge_mid_left",
              "wall_edge_mid_right", "wall_outer_top_left", "wall_outer_top_right", "wall_outer_mid_left",
              "wall_outer_mid_right", "wall_outer_front_left", "wall_outer_front_right"):
        add("Paredes · peças", W(n), n, n.replace("wall_", "").replace("_", " "))

    # ---- Masmorra
    add("Masmorra", load(f"{DP}/Tilesets/Tileset_Dungeon.png", (192, 96, 32, 64)), "escada", "Escada", 32)
    for n, nome in (("floor_stairs", "Escada para baixo"), ("floor_ladder", "Alçapão"), ("hole", "Buraco"),
                    ("edge_down", "Beirada"), ("floor_spikes_anim_f3", "Espinhos"), ("chest_full_open_anim_f0", "Baú"),
                    ("chest_full_open_anim_f2", "Baú aberto"), ("chest_mimic_open_anim_f2", "Mímico"), ("crate", "Caixote"),
                    ("skull", "Caveira"), ("bomb_f0", "Bomba"), ("lever_left", "Alavanca"), ("button_red_up", "Botão"),
                    ("coin_anim_f0", "Moeda")):
        add("Masmorra", W(n), n, nome)
    for p in ("Front_Door_Closed", "Front_Door_Open", "Side_Door_Closed", "Side_Door_Open", "bones1", "bones2",
              "bronze_chest_closed", "bronze_chest_open"):
        add("Masmorra", load(f"{DP}/Props/Static/{p}.png"), p, label_for(p), 32)
    add("Masmorra", load(f"{DP}/Items/health_potion.png"), "pocao_vida", "Poção de vida", 32)
    add("Masmorra", load(f"{DP}/Items/mana_potion.png"), "pocao_mana", "Poção de mana", 32)

    # ---- Personagens e criaturas
    for base, nome in X72_NAMES.items():
        f = first_frame(base)
        if f:
            add("Personagens" if base in HEROES else "Criaturas", load(f), base, nome)
    add("Personagens", load(f"{TINY}/Soldier/Soldier/Soldier_Idle.png", (0, 0, 100, 100)), "soldado", "Soldado")
    add("Criaturas", load(f"{TINY}/Orc/Orc/Orc_Idle.png", (0, 0, 100, 100)), "orc", "Orc")
    add("Personagens", load(f"{DP}/Characters/Hero_Warrior/Strips/Idle/down_strip.png", (0, 0, 32, 48)), "guerreiro", "Guerreiro", 32)
    add("Personagens", load(f"{CUTE}/Player/Player.png", (0, 0, 32, 32)), "aventureiro", "Aventureiro")
    add("Criaturas", load(f"{CUTE}/Enemies/Skeleton.png", (0, 0, 32, 32)), "esqueleto_fofo", "Esqueleto (fofo)")
    add("Criaturas", load(f"{CUTE}/Enemies/Slime_Green.png", (0, 0, 64, 64)), "slime", "Slime")
    for bicho, nome in (("Chicken", "Galinha"), ("Cow", "Vaca"), ("Pig", "Porco"), ("Sheep", "Ovelha")):
        add("Animais", load(f"{CUTE}/Animals/{bicho}/{bicho}.png", (0, 0, 32, 32)), bicho, nome)

    # ---- Catalisadores (cristais)
    for f in sorted((SRC / CRYSTALS).glob("*.png")):
        if blocked(CRYSTALS):
            skipped[CRYSTALS] += 1
            continue
        nome = re.sub(r"^\d+_", "", f.stem).replace("_", " ").capitalize()
        nome = nome.replace("Agua", "Água").replace("Ambar", "Âmbar")
        add("Catalisadores", Image.open(f).convert("RGBA"), f.stem, nome, 32)

    # ---- Natureza
    for p in [f"{FAN}/Trees and Bushes/Tree_Emerald_{i}.png" for i in (1, 2, 3, 4)] + [f"{CUTE}/Outdoor decoration/Oak_Tree.png"] \
            + [f"{FAN}/Trees and Bushes/Bush_Emerald_{i}.png" for i in (1, 2, 3, 4, 5)] \
            + [f"{FAN}/Props/Chopped_Tree_1.png", f"{FAN}/Props/Plant_2.png"]:
        add("Árvores e plantas", load(p), Path(p).stem, label_for(p))
    add_sheet("Árvores e plantas", f"{CUTE}/Outdoor decoration/Oak_Tree_Small.png", "arvore_pequena", "Árvore pequena", 16, cell=16)
    add_sheet("Árvores e plantas", f"{PTD}/TX Plant.png", "planta", "Planta do campo", 32)
    add_sheet("Natureza selvagem", FREEPACK, "natureza", "Natureza", 32, gap=1)
    for n, nome in (("Tree", "Árvore"), ("Bush", "Moita"), ("ChoppedTree", "Tronco cortado"), ("LoneTrunk", "Tronco"),
                    ("Stone_1", "Pedra 1"), ("Stone_2", "Pedra 2"), ("Stone_3", "Pedra 3"), ("Flower_1", "Flor 1"),
                    ("Flower_2", "Flor 2"), ("Flower_3", "Flor 3"), ("TallGrass_1", "Capim 1"), ("TallGrass_2", "Capim 2")):
        add("Natureza selvagem", load(f"{PLAT}/GrassLand_{n}.png"), f"plat_{n}", nome, 16)
    for p in (1, 2, 4, 6, 9):
        add("Pedras", load(f"{FAN}/Rocks/Rock_Brown_{p}.png"), f"rock{p}", f"Pedra {p}")
    # neste sheet as sombras encostam na célula vizinha: só o poste e o tronco ocupam mais de uma célula
    add_sheet("Decoração", f"{CUTE}/Outdoor decoration/Outdoor_Decor_Free.png", "decor", "Decoração", 16, cell=16,
              auto=False, groups=[[(4, 4), (4, 5), (4, 6)], [(0, 7), (1, 7)]])

    # ---- Vila e construções
    for n in ("1", "2", "3", "4_Purple"):
        add("Construções", load(f"{FAN}/Buildings/House_Hay_{n}.png"), f"house{n}", f"Casa de palha {n[0]}")
    add("Construções", load(f"{CUTE}/Outdoor decoration/House_1_Wood_Base_Blue.png"), "casa_madeira", "Casa de madeira")
    add("Construções", load(f"{FAN}/Buildings/CityWall_Gate_1.png"), "portao", "Portão da muralha")
    add("Construções", load(f"{FAN}/Buildings/Well_Hay_1.png"), "poco", "Poço")
    for n in ("Barrel_Small_Empty", "Crate_Large_Empty", "Crate_Medium_Closed", "Crate_Water_1", "Sack_3", "Basket_Empty",
              "HayStack_2", "Sign_1", "Sign_2", "Bench_1", "Bench_3", "Table_Medium_1", "Fireplace_1", "LampPost_3",
              "BulletinBoard_1", "Banner_Stick_1_Purple"):
        add("Vila", load(f"{FAN}/Props/{n}.png"), n, label_for(n))
    add("Vila", load(f"{CUTE}/Outdoor decoration/Chest.png"), "bau", "Baú")
    add_sheet("Vila", f"{PTD}/TX Props.png", "objeto", "Objeto", 32)
    add_sheet("Interior", f"{FARM}/Objects/Interior.png", "interior", "Móvel", 16, cell=16)

    # ---- Itens
    for n in sorted(p.stem for p in (SRC / X72).glob("flask_*.png")) + sorted(p.stem for p in (SRC / X72).glob("weapon_*.png")):
        add("Itens", W(n), n, n.replace("flask_", "frasco ").replace("weapon_", "").replace("_", " "))
    sheet = load(f"{ICONS}/32x32/Free_Icons_all_32x32.png")
    n = 0
    for y in range(0, sheet.height if sheet else 0, 32):
        for x in range(0, sheet.width, 32):
            tile = sheet.crop((x, y, x + 32, y + 32))
            if tile.getbbox():
                n += 1
                add("Itens", tile, f"icone_{n}", f"Item {n}", 32)

    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    packs = [
        (CUTE, "Cute Fantasy (Free) e Cute Fantasy Icons — Kenmi"),
        (DP, "Dungeons and Pixels — Free Demo — Vladimir Ivanov"),
        (FAN, "The Fan-tasy Tileset (Free)"),
        (FARM, "Farm RPG FREE 16x16 - Tiny Asset Pack"),
        (X72, "0x72 Dungeon Tileset II — 0x72 (CC0)"),
        (PTD, "Pixel Art Top Down - Basic — Cainos"),
        (FREEPACK, "FreeEnvironment"),
        (PLAT, "Multi Platformer Tileset — Shackhal (CC0)"),
        (TINY, "Tiny RPG Character Asset Pack — Zerie"),
    ]
    if not COMMERCIAL:
        packs.append((CRYSTALS, "Catalisadores (cristais)"))
    (OUT / "CREDITS.md").write_text(
        "# Créditos dos assets do editor de mapas\n\n"
        + ("Kit gerado em **modo comercial** (`--comercial`): só pacotes cuja licença permite uso comercial.\n\n"
           if COMMERCIAL else
           "Recortados de pacotes gratuitos por `scripts/build_mapkit.py`, para uso pessoal (não comercial).\n"
           "Kit para uso comercial: `python scripts/build_mapkit.py --comercial`.\n\n")
        + "".join(f"- {name}\n" for pack, name in packs if not blocked(pack))
        + "\nOs pacotes não permitem redistribuir os arquivos: não publique esta pasta em repositório público.\n",
        encoding="utf-8")
    print(f"{len(manifest['terrains'])} terrenos, {len(manifest['props'])} objetos:",
          dict(Counter(p["category"] for p in manifest["props"])))
    if COMMERCIAL:
        print("\nModo comercial: ficaram de fora")
        for pack, why in NON_COMMERCIAL.items():
            print(f"  - {why}  ({skipped[pack]} recortes)")
        print("Terrenos trocados por substitutos (mesma chave): "
              + ", ".join(k for k, _, path, _ in TILE_TERRAINS if blocked(path) and k in TERRAIN_FALLBACK))


if __name__ == "__main__":
    main()
