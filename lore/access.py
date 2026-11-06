"""Acesso aos mundos e dados da barra lateral.

Papéis em world_members: 'owner' (dono), 'editor' (colaborador) e 'player' (jogador).
Jogadores NÃO entram no planejamento: todo get_world() os manda para a Mesa, a não ser que a rota
diga allow_player=True (só as rotas da Mesa fazem isso). Assim nada novo vaza por esquecimento.
"""
from flask import abort, g, redirect, url_for

from .constants import CATEGORY_MAP
from .db import get_db

GM_ROLES = ("owner", "editor")


def get_world(wid, owner_only=False, allow_player=False):
    db = get_db()
    world = db.execute(
        """SELECT w.*, m.role FROM worlds w
           JOIN world_members m ON m.world_id = w.id AND m.user_id = ?
           WHERE w.id = ?""",
        (g.user["id"], wid),
    ).fetchone()
    if world is None:
        abort(404)
    g.world = world
    g.is_owner = world["role"] == "owner"
    g.is_gm = world["role"] in GM_ROLES
    g.is_player = world["role"] == "player"
    if g.is_player:
        if not allow_player:
            abort(redirect(url_for("play.dashboard", wid=wid)))
        return world          # a Mesa não usa a barra lateral do planejamento
    if owner_only and world["role"] != "owner":
        abort(403)
    g.party_main = None
    if world["party_of"]:     # mundo da mesa: guarda o mundo principal para a navegação
        g.party_main = db.execute("SELECT id, name, icon FROM worlds WHERE id = ?", (world["party_of"],)).fetchone()
    pages = db.execute(
        "SELECT id, title, icon, category, parent_id FROM articles WHERE world_id = ? ORDER BY title COLLATE NOCASE",
        (wid,),
    ).fetchall()
    g.page_tree = build_tree(pages)
    # uma árvore por categoria: subpágina de outra categoria vira raiz na sua própria categoria
    g.category_trees = {}
    g.category_counts = {}
    for p in pages:
        g.category_counts[p["category"]] = g.category_counts.get(p["category"], 0) + 1
    for key in CATEGORY_MAP:
        g.category_trees[key] = build_tree([p for p in pages if p["category"] == key])
    g.favorites = db.execute(
        """SELECT a.id, a.title, a.icon, a.category FROM page_favorites f JOIN articles a ON a.id = f.article_id
           WHERE f.user_id = ? AND a.world_id = ? ORDER BY a.title COLLATE NOCASE""", (g.user["id"], wid)).fetchall()
    g.favorite_ids = {f["id"] for f in g.favorites}
    g.page_count = len(pages)
    g.boards = db.execute("SELECT id, name FROM boards WHERE world_id = ? ORDER BY name COLLATE NOCASE", (wid,)).fetchall()
    g.maps = db.execute("SELECT id, name FROM maps WHERE world_id = ? ORDER BY name COLLATE NOCASE", (wid,)).fetchall()
    g.member_count = db.execute("SELECT COUNT(*) FROM world_members WHERE world_id = ?", (wid,)).fetchone()[0]
    return world


def build_tree(pages):
    """Lista plana -> árvore [{page, children}] (ordem alfabética)."""
    nodes = {p["id"]: {"page": p, "children": []} for p in pages}
    roots = []
    for p in pages:
        parent = nodes.get(p["parent_id"])
        (parent["children"] if parent else roots).append(nodes[p["id"]])
    return roots


def page_icon(p):
    return p["icon"] or CATEGORY_MAP.get(p["category"], CATEGORY_MAP["nota"])["icon"]


def get_page(world, aid):
    a = get_db().execute("SELECT * FROM articles WHERE id = ? AND world_id = ?", (aid, world["id"])).fetchone()
    if a is None:
        abort(404)
    return a


def get_file(world, fid):
    f = get_db().execute("SELECT * FROM files WHERE id = ? AND world_id = ?", (fid, world["id"])).fetchone()
    if f is None:
        abort(404)
    return f


def file_url(fid):
    return url_for("files.serve", fid=fid) if fid else None


def touch_world(wid):
    get_db().execute("UPDATE worlds SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (wid,))
