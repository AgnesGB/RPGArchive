"""Mesa de jogo (aba "Jogar").

- Jogadores (papel 'player') só enxergam a Mesa: mapas compartilhados (observar e mover tokens),
  "arquivos encontrados" (páginas e arquivos que o mestre revelou) e a área dos jogadores.
- A área dos jogadores é um "mundo da mesa" (worlds.party_of = mundo principal), onde todos da mesa
  criam páginas, mapas mentais, linhas do tempo e árvores com as mesmas ferramentas do planejamento.
- Mestre = dono ou colaborador do mundo principal; ele vê e gerencia tudo isso.
"""
import json
from collections import Counter

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from .access import GM_ROLES, get_page, get_world, page_icon
from .auth import EMAIL_RE, login_required
from .blocks import file_ids_in, load_blocks
from .constants import CATEGORY_MAP
from .db import get_db
from .files import file_dict, is_image

bp = Blueprint("play", __name__)


# --------------------------------------------------------------------------- mundo da mesa

def ensure_party(main):
    """Cria (uma vez) o mundo da mesa e deixa os membros iguais aos do mundo principal."""
    db = get_db()
    party = db.execute("SELECT * FROM worlds WHERE party_of = ?", (main["id"],)).fetchone()
    if party is None:
        pid = db.execute(
            "INSERT INTO worlds (user_id, name, description, icon, party_of) VALUES (?, ?, ?, ?, ?)",
            (main["user_id"], f"{main['name']} · Mesa", "Área dos jogadores", "ri:people", main["id"])).lastrowid
        db.execute("INSERT INTO boards (world_id, name) VALUES (?, ?)", (pid, "Mapa mental do grupo"))
        party = db.execute("SELECT * FROM worlds WHERE id = ?", (pid,)).fetchone()
    sync_party(main["id"], party["id"])
    db.commit()
    return party


def sync_party(main_id, party_id=None):
    db = get_db()
    if party_id is None:
        row = db.execute("SELECT id FROM worlds WHERE party_of = ?", (main_id,)).fetchone()
        if row is None:       # ainda não existe: cria agora (ensure_party chama de volta com o id)
            main = db.execute("SELECT * FROM worlds WHERE id = ?", (main_id,)).fetchone()
            if main is not None and not main["party_of"]:
                ensure_party(main)
            return
        party_id = row["id"]
    want = {r["user_id"]: ("owner" if r["role"] == "owner" else "editor")
            for r in db.execute("SELECT user_id, role FROM world_members WHERE world_id = ?", (main_id,))}
    have = {r["user_id"]: r["role"] for r in db.execute("SELECT user_id, role FROM world_members WHERE world_id = ?", (party_id,))}
    for uid, role in want.items():
        if uid not in have:
            db.execute("INSERT INTO world_members (world_id, user_id, role) VALUES (?, ?, ?)", (party_id, uid, role))
        elif have[uid] != role:
            db.execute("UPDATE world_members SET role = ? WHERE world_id = ? AND user_id = ?", (role, party_id, uid))
    for uid in set(have) - set(want):
        db.execute("DELETE FROM world_members WHERE world_id = ? AND user_id = ?", (party_id, uid))


def _gm(world):
    if world["role"] not in GM_ROLES:
        abort(403)


def _main_world(wid):
    """Abre o mundo principal (jogadores incluídos). Se vier o id do mundo da mesa, devolve o principal."""
    world = get_world(wid, allow_player=True)
    if world["party_of"]:
        abort(redirect(url_for("play.dashboard", wid=world["party_of"])))
    row = get_db().execute("SELECT id FROM worlds WHERE party_of = ?", (wid,)).fetchone()
    g.party_id = row["id"] if row else None      # menu dos jogadores
    return world


# --------------------------------------------------------------------------- o que o jogador pode ver

def shared_map_ids(wid):
    return {r[0] for r in get_db().execute("SELECT map_id FROM play_maps WHERE world_id = ?", (wid,))}


def handout_page_ids(wid):
    return {r[0] for r in get_db().execute("SELECT ref_id FROM handouts WHERE world_id = ? AND kind = 'page'", (wid,))}


def _fid(value):
    """Id de arquivo em '/f/12' ou 'img:/f/12'."""
    v = (value or "").removeprefix("img:")
    return int(v[3:]) if v.startswith("/f/") and v[3:].isdigit() else None


def player_file_ids(wid):
    """Arquivos do mundo principal que um jogador pode abrir: só o que aparece na Mesa."""
    db = get_db()
    ids = set()
    maps = shared_map_ids(wid)
    if maps:
        marks = ",".join("?" * len(maps))
        ids |= {r[0] for r in db.execute(f"SELECT file_id FROM maps WHERE id IN ({marks}) AND file_id IS NOT NULL", tuple(maps))}
        ids |= {r[0] for r in db.execute(f"SELECT image_file_id FROM map_pins WHERE map_id IN ({marks}) AND image_file_id IS NOT NULL", tuple(maps))}
        for r in db.execute(f"""SELECT a.image_url FROM map_pins p JOIN articles a ON a.id = p.article_id
                                WHERE p.map_id IN ({marks}) AND p.kind = 'token'""", tuple(maps)):
            if _fid(r[0]):
                ids.add(_fid(r[0]))
        ids |= {r[0] for r in db.execute("SELECT file_id FROM map_tilesets WHERE world_id = ?", (wid,))}
    for h in db.execute("SELECT kind, ref_id FROM handouts WHERE world_id = ?", (wid,)):
        if h["kind"] == "file":
            ids.add(h["ref_id"])
            continue
        page = db.execute("SELECT * FROM articles WHERE id = ? AND world_id = ?", (h["ref_id"], wid)).fetchone()
        if page:
            ids |= {x for x in (_fid(page["image_url"]), _fid(page["icon"])) if x}
            ids |= file_ids_in(load_blocks(page))
    return ids


def _fog_cells(data):
    fog = data.get("fog") or {}
    return fog.get("cols") or 0, fog.get("rows") or 0, set(fog.get("cells") or [])


def _under_fog(pin, fog):
    cols, rows, cells = fog
    if not cols or not rows or not cells:
        return False
    c, r = min(cols - 1, int(pin["x"] * cols)), min(rows - 1, int(pin["y"] * rows))
    return f"{c},{r}" in cells


def player_pins(wid, mid, data):
    """Marcadores e tokens como o jogador vê: sem anotações, sem anexos e sem nada que esteja sob a névoa."""
    from .maps import _pin_rows, pin_dict
    fog, pages = _fog_cells(data), handout_page_ids(wid)
    out = []
    for r in _pin_rows(mid):
        d = pin_dict(r)
        if _under_fog(d, fog):
            continue
        p = {k: d[k] for k in ("id", "kind", "x", "y", "label", "color", "image")}
        p.update(note="", article_id=None, file_id=None, image_file_id=None)
        if d.get("article") and r["article_id"] in pages:
            p["article"] = {"title": d["article"]["title"], "cover": d["article"]["cover"], "icon": d["article"]["icon"],
                            "summary": "", "url": url_for("play.handout_page", wid=wid, aid=r["article_id"])}
        out.append(p)
    return out


def player_data(data):
    """Dados do mapa para o jogador: passagens secretas viram paredes comuns."""
    data = dict(data)
    data["walls"] = {k: ("stone" if v == "secret" else v) for k, v in (data.get("walls") or {}).items()}
    return data


# --------------------------------------------------------------------------- painel da Mesa

@bp.route("/w/<int:wid>/play")
@login_required
def dashboard(wid):
    world = _main_world(wid)
    party = ensure_party(world)
    g.party_id = party["id"]
    db = get_db()
    gm = world["role"] in GM_ROLES
    shared = db.execute(
        """SELECT m.* FROM maps m JOIN play_maps pm ON pm.map_id = m.id WHERE pm.world_id = ?
           ORDER BY pm.created_at DESC""", (wid,)).fetchall()
    handouts = []
    for h in db.execute("SELECT * FROM handouts WHERE world_id = ? ORDER BY created_at DESC, id DESC", (wid,)):
        if h["kind"] == "page":
            p = db.execute("SELECT id, title, icon, category, summary, image_url, cover_pos FROM articles WHERE id = ? AND world_id = ?",
                           (h["ref_id"], wid)).fetchone()
            if p:
                handouts.append({"h": h, "page": p, "url": url_for("play.handout_page", wid=wid, aid=p["id"])})
        else:
            f = db.execute("SELECT * FROM files WHERE id = ? AND world_id = ?", (h["ref_id"], wid)).fetchone()
            if f:
                handouts.append({"h": h, "file": file_dict(f)})
    count = lambda sql: db.execute(sql, (party["id"],)).fetchone()[0]  # noqa: E731
    party_stats = {"pages": count("SELECT COUNT(*) FROM articles WHERE world_id = ?"),
                   "boards": count("SELECT COUNT(*) FROM boards WHERE world_id = ?"),
                   "timelines": count("SELECT COUNT(*) FROM timelines WHERE world_id = ?"),
                   "trees": count("SELECT COUNT(*) FROM trees WHERE world_id = ?"),
                   "files": count("SELECT COUNT(*) FROM files WHERE world_id = ?")}
    library = library_items(wid, party["id"], handouts)
    players = db.execute(
        """SELECT u.id, u.name, u.email, u.avatar_url FROM world_members m JOIN users u ON u.id = m.user_id
           WHERE m.world_id = ? AND m.role = 'player' ORDER BY u.name COLLATE NOCASE""", (wid,)).fetchall()
    ctx = {}
    if gm:
        in_maps = {m["id"] for m in shared}
        in_handouts = {(x["h"]["kind"], x["h"]["ref_id"]) for x in handouts}
        ctx = {
            "all_maps": [m for m in db.execute("SELECT id, name FROM maps WHERE world_id = ? ORDER BY name COLLATE NOCASE", (wid,))
                         if m["id"] not in in_maps],
            "all_pages": [p for p in db.execute("SELECT id, title, icon, category FROM articles WHERE world_id = ? ORDER BY title COLLATE NOCASE", (wid,))
                          if ("page", p["id"]) not in in_handouts],
            "all_files": [f for f in db.execute("SELECT id, original_name, mime FROM files WHERE world_id = ? ORDER BY original_name COLLATE NOCASE", (wid,))
                          if ("file", f["id"]) not in in_handouts],
            "pending": db.execute("SELECT email FROM world_invites WHERE world_id = ? AND role = 'player'", (wid,)).fetchall(),
            "encounters": encounters_for(wid), "enc_status": ENC_STATUS,
            "every_map": db.execute("SELECT id, name FROM maps WHERE world_id = ? ORDER BY name COLLATE NOCASE", (wid,)).fetchall(),
            "every_page": db.execute("SELECT id, title, icon, category FROM articles WHERE world_id = ? ORDER BY title COLLATE NOCASE", (wid,)).fetchall(),
            "every_file": db.execute("SELECT id, original_name FROM files WHERE world_id = ? ORDER BY original_name COLLATE NOCASE", (wid,)).fetchall(),
        }
    return render_template("play/dashboard.html", world=world, party=party, gm=gm, shared=shared, handouts=handouts,
                           party_stats=party_stats, players=players, library=library,
                           lib_counts=Counter(x["cat"] for x in library), lib_src=Counter(x["src"] for x in library), **ctx)


def library_items(wid, party_id, handouts):
    """Biblioteca do grupo: o que o mestre revelou ("encontrado") + o que o grupo criou ("do grupo"), tudo junto.

    Cada item: src ('found'|'group'), kind ('page'|'file'), cat (categoria da página ou 'arquivo'), título, capa, link.
    """
    db = get_db()
    out = []
    for x in handouts:
        if x.get("page"):
            p = x["page"]
            out.append({"src": "found", "kind": "page", "cat": p["category"], "title": p["title"], "icon": page_icon(p),
                        "cover": p["image_url"], "cover_pos": p["cover_pos"], "summary": p["summary"], "url": x["url"],
                        "date": x["h"]["created_at"], "h": x["h"]})
        else:
            f = x["file"]
            out.append({"src": "found", "kind": "file", "cat": "arquivo", "title": f["name"], "file": f, "url": f["url"],
                        "date": x["h"]["created_at"], "h": x["h"]})
    for p in db.execute("""SELECT id, title, icon, category, summary, image_url, cover_pos, updated_at FROM articles
                           WHERE world_id = ?""", (party_id,)):
        out.append({"src": "group", "kind": "page", "cat": p["category"], "title": p["title"], "icon": page_icon(p),
                    "cover": p["image_url"], "cover_pos": p["cover_pos"], "summary": p["summary"],
                    "url": url_for("pages.view", wid=party_id, aid=p["id"]), "date": p["updated_at"]})
    for r in db.execute("SELECT * FROM files WHERE world_id = ?", (party_id,)):
        f = file_dict(r)
        out.append({"src": "group", "kind": "file", "cat": "arquivo", "title": f["name"], "file": f, "url": f["url"],
                    "date": r["created_at"]})
    out.sort(key=lambda x: x["date"] or "", reverse=True)
    return out


@bp.post("/w/<int:wid>/play/maps")
@login_required
def share_map(wid):
    world = _main_world(wid)
    _gm(world)
    db = get_db()
    mid = request.form.get("map_id", type=int)
    if mid and db.execute("SELECT 1 FROM maps WHERE id = ? AND world_id = ?", (mid, wid)).fetchone():
        db.execute("INSERT OR IGNORE INTO play_maps (world_id, map_id) VALUES (?, ?)", (wid, mid))
        db.commit()
    return redirect(url_for("play.dashboard", wid=wid) + "#mapas")


@bp.post("/w/<int:wid>/play/maps/<int:mid>/remove")
@login_required
def unshare_map(wid, mid):
    world = _main_world(wid)
    _gm(world)
    db = get_db()
    db.execute("DELETE FROM play_maps WHERE world_id = ? AND map_id = ?", (wid, mid))
    db.commit()
    return redirect(url_for("play.dashboard", wid=wid) + "#mapas")


@bp.post("/w/<int:wid>/play/handouts")
@login_required
def add_handout(wid):
    world = _main_world(wid)
    _gm(world)
    db = get_db()
    kind = request.form.get("kind")
    ref = request.form.get("ref_id", type=int)
    table = {"page": "articles", "file": "files"}.get(kind)
    if table and ref and db.execute(f"SELECT 1 FROM {table} WHERE id = ? AND world_id = ?", (ref, wid)).fetchone():
        db.execute("INSERT OR IGNORE INTO handouts (world_id, kind, ref_id, note, created_by) VALUES (?, ?, ?, ?, ?)",
                   (wid, kind, ref, request.form.get("note", "").strip()[:300], g.user["id"]))
        db.commit()
        flash("Revelado para os jogadores.", "success")
    return redirect(url_for("play.dashboard", wid=wid) + "#biblioteca")


@bp.post("/w/<int:wid>/play/handouts/<int:hid>/remove")
@login_required
def remove_handout(wid, hid):
    world = _main_world(wid)
    _gm(world)
    db = get_db()
    db.execute("DELETE FROM handouts WHERE id = ? AND world_id = ?", (hid, wid))
    db.commit()
    return redirect(url_for("play.dashboard", wid=wid) + "#biblioteca")


@bp.post("/w/<int:wid>/play/players")
@login_required
def add_player(wid):
    world = _main_world(wid)
    _gm(world)
    email = request.form.get("email", "").strip().lower()
    back = url_for("play.dashboard", wid=wid) + "#jogadores"
    if not EMAIL_RE.match(email):
        flash("E-mail inválido.", "error")
        return redirect(back)
    db = get_db()
    user = db.execute("SELECT id, name FROM users WHERE email = ?", (email,)).fetchone()
    if user:
        cur = db.execute("SELECT role FROM world_members WHERE world_id = ? AND user_id = ?", (wid, user["id"])).fetchone()
        if cur and cur["role"] in GM_ROLES:
            flash(f"{user['name']} já é {'dono' if cur['role'] == 'owner' else 'colaborador'} do mundo e já vê a Mesa.", "error")
            return redirect(back)
        db.execute("INSERT OR IGNORE INTO world_members (world_id, user_id, role) VALUES (?, ?, 'player')", (wid, user["id"]))
        sync_party(wid)
        flash(f"{user['name']} entrou na mesa como jogador(a).", "success")
    else:
        db.execute("""INSERT INTO world_invites (world_id, email, invited_by, role) VALUES (?, ?, ?, 'player')
                      ON CONFLICT(world_id, email) DO UPDATE SET role = 'player'""", (wid, email, g.user["id"]))
        flash(f"Convite guardado: quando {email} criar a conta (ou entrar com Google), entra na mesa como jogador(a).", "success")
    db.commit()
    return redirect(back)


@bp.post("/w/<int:wid>/play/players/<int:uid>/remove")
@login_required
def remove_player(wid, uid):
    world = _main_world(wid)
    db = get_db()
    if uid != g.user["id"]:
        _gm(world)
    db.execute("DELETE FROM world_members WHERE world_id = ? AND user_id = ? AND role = 'player'", (wid, uid))
    if request.form.get("email"):
        db.execute("DELETE FROM world_invites WHERE world_id = ? AND email = ?", (wid, request.form["email"]))
    sync_party(wid)
    db.commit()
    if uid == g.user["id"]:
        return redirect(url_for("worlds.list_worlds"))
    return redirect(url_for("play.dashboard", wid=wid) + "#jogadores")


# --------------------------------------------------------------------------- encontros (só o mestre)

ENC_STATUS = {"planned": "Planejado", "active": "Em jogo", "done": "Concluído"}
ENC_TABLES = {"map": "maps", "page": "articles", "file": "files"}


def _encounter(wid, eid):
    e = get_db().execute("SELECT * FROM encounters WHERE id = ? AND world_id = ?", (eid, wid)).fetchone()
    if e is None:
        abort(404)
    return e


def _back_to(eid):
    return redirect(url_for("play.dashboard", wid=request.view_args["wid"]) + f"#enc-{eid}")


def _reveal(wid, kind, ref):
    db = get_db()
    if kind == "map":
        db.execute("INSERT OR IGNORE INTO play_maps (world_id, map_id) VALUES (?, ?)", (wid, ref))
    else:
        db.execute("INSERT OR IGNORE INTO handouts (world_id, kind, ref_id, created_by) VALUES (?, ?, ?, ?)",
                   (wid, kind, ref, g.user["id"]))


def _hide(wid, kind, ref):
    db = get_db()
    if kind == "map":
        db.execute("DELETE FROM play_maps WHERE world_id = ? AND map_id = ?", (wid, ref))
    else:
        db.execute("DELETE FROM handouts WHERE world_id = ? AND kind = ? AND ref_id = ?", (wid, kind, ref))


def encounters_for(wid):
    """Encontros com os itens já resolvidos (nome, ícone, link do planejamento e se já está na mesa)."""
    db = get_db()
    on_table = shared_map_ids(wid)
    revealed = {(r["kind"], r["ref_id"]) for r in db.execute("SELECT kind, ref_id FROM handouts WHERE world_id = ?", (wid,))}
    out = []
    for e in db.execute("SELECT * FROM encounters WHERE world_id = ? ORDER BY status = 'done', position, id", (wid,)):
        items = {"map": [], "page": [], "file": []}
        for it in db.execute("SELECT kind, ref_id FROM encounter_items WHERE encounter_id = ? ORDER BY position, rowid", (e["id"],)):
            k, ref = it["kind"], it["ref_id"]
            if k == "map":
                r = db.execute("SELECT id, name, thumb, file_id FROM maps WHERE id = ? AND world_id = ?", (ref, wid)).fetchone()
                if r:
                    items[k].append({"id": ref, "name": r["name"], "thumb": r["thumb"], "file_id": r["file_id"],
                                     "url": url_for("maps.view", wid=wid, mid=ref), "live": ref in on_table})
            elif k == "page":
                r = db.execute("SELECT id, title, icon, category FROM articles WHERE id = ? AND world_id = ?", (ref, wid)).fetchone()
                if r:
                    items[k].append({"id": ref, "name": r["title"], "icon": page_icon(r),
                                     "url": url_for("pages.view", wid=wid, aid=ref), "live": ("page", ref) in revealed})
            else:
                r = db.execute("SELECT * FROM files WHERE id = ? AND world_id = ?", (ref, wid)).fetchone()
                if r:
                    f = file_dict(r)
                    items[k].append({"id": ref, "name": f["name"], "is_image": f["is_image"], "url": f["url"],
                                     "live": ("file", ref) in revealed})
        n = sum(len(v) for v in items.values())
        out.append({"e": e, "parts": items, "count": n, "live": sum(i["live"] for v in items.values() for i in v),
                    "maps_off": [i["id"] for i in items["map"] if not i["live"]]})
    return out


@bp.post("/w/<int:wid>/play/encounters")
@login_required
def new_encounter(wid):
    world = _main_world(wid)
    _gm(world)
    db = get_db()
    name = request.form.get("name", "").strip()[:120] or "Novo encontro"
    pos = db.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM encounters WHERE world_id = ?", (wid,)).fetchone()[0]
    eid = db.execute("INSERT INTO encounters (world_id, name, position) VALUES (?, ?, ?)", (wid, name, pos)).lastrowid
    db.commit()
    return _back_to(eid)


@bp.post("/w/<int:wid>/play/encounters/<int:eid>")
@login_required
def edit_encounter(wid, eid):
    world = _main_world(wid)
    _gm(world)
    e = _encounter(wid, eid)
    f = request.form
    status = f.get("status") if f.get("status") in ENC_STATUS else e["status"]
    get_db().execute("UPDATE encounters SET name = ?, notes = ?, status = ? WHERE id = ?",
                     ((f.get("name", e["name"]).strip()[:120] or e["name"]), f.get("notes", e["notes"])[:20000], status, eid))
    get_db().commit()
    if request.headers.get("Accept") == "application/json":
        return jsonify(ok=True)
    return _back_to(eid)


@bp.post("/w/<int:wid>/play/encounters/<int:eid>/delete")
@login_required
def delete_encounter(wid, eid):
    world = _main_world(wid)
    _gm(world)
    _encounter(wid, eid)
    get_db().execute("DELETE FROM encounters WHERE id = ?", (eid,))
    get_db().commit()
    flash("Encontro apagado (mapas e páginas continuam no planejamento).", "success")
    return redirect(url_for("play.dashboard", wid=wid) + "#encontros")


@bp.post("/w/<int:wid>/play/encounters/<int:eid>/move")
@login_required
def move_encounter(wid, eid):
    """Sobe (-1) ou desce (+1) o encontro na lista."""
    world = _main_world(wid)
    _gm(world)
    _encounter(wid, eid)
    db = get_db()
    ids = [r[0] for r in db.execute("SELECT id FROM encounters WHERE world_id = ? ORDER BY position, id", (wid,))]
    i, d = ids.index(eid), (1 if request.form.get("dir") == "down" else -1)
    if 0 <= i + d < len(ids):
        ids[i], ids[i + d] = ids[i + d], ids[i]
        for pos, x in enumerate(ids):
            db.execute("UPDATE encounters SET position = ? WHERE id = ?", (pos, x))
        db.commit()
    return _back_to(eid)


@bp.post("/w/<int:wid>/play/encounters/<int:eid>/items")
@login_required
def add_encounter_item(wid, eid):
    world = _main_world(wid)
    _gm(world)
    _encounter(wid, eid)
    db = get_db()
    kind, ref = request.form.get("kind"), request.form.get("ref_id", type=int)
    table = ENC_TABLES.get(kind)
    if table and ref and db.execute(f"SELECT 1 FROM {table} WHERE id = ? AND world_id = ?", (ref, wid)).fetchone():
        pos = db.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM encounter_items WHERE encounter_id = ?", (eid,)).fetchone()[0]
        db.execute("INSERT OR IGNORE INTO encounter_items (encounter_id, kind, ref_id, position) VALUES (?, ?, ?, ?)",
                   (eid, kind, ref, pos))
        db.commit()
    return _back_to(eid)


@bp.post("/w/<int:wid>/play/encounters/<int:eid>/items/remove")
@login_required
def remove_encounter_item(wid, eid):
    world = _main_world(wid)
    _gm(world)
    _encounter(wid, eid)
    get_db().execute("DELETE FROM encounter_items WHERE encounter_id = ? AND kind = ? AND ref_id = ?",
                     (eid, request.form.get("kind"), request.form.get("ref_id", type=int)))
    get_db().commit()
    return _back_to(eid)


@bp.post("/w/<int:wid>/play/encounters/<int:eid>/reveal")
@login_required
def reveal_encounter_item(wid, eid):
    """Põe um item do encontro na mesa (mapa) ou revela (página/arquivo); hide=1 esconde de novo."""
    world = _main_world(wid)
    _gm(world)
    _encounter(wid, eid)
    kind, ref = request.form.get("kind"), request.form.get("ref_id", type=int)
    if get_db().execute("SELECT 1 FROM encounter_items WHERE encounter_id = ? AND kind = ? AND ref_id = ?",
                        (eid, kind, ref)).fetchone():
        (_hide if request.form.get("hide") else _reveal)(wid, kind, ref)
        get_db().commit()
    return _back_to(eid)


@bp.post("/w/<int:wid>/play/encounters/<int:eid>/start")
@login_required
def start_encounter(wid, eid):
    """Começar: põe todos os mapas do encontro na mesa (páginas e arquivos esperam ser encontrados)."""
    world = _main_world(wid)
    _gm(world)
    _encounter(wid, eid)
    db = get_db()
    for (ref,) in db.execute("SELECT ref_id FROM encounter_items WHERE encounter_id = ? AND kind = 'map'", (eid,)).fetchall():
        _reveal(wid, "map", ref)
    db.execute("UPDATE encounters SET status = 'active' WHERE id = ?", (eid,))
    db.commit()
    flash("Encontro começou: os mapas dele estão na mesa.", "success")
    return _back_to(eid)


@bp.post("/w/<int:wid>/play/encounters/<int:eid>/finish")
@login_required
def finish_encounter(wid, eid):
    """Encerrar: tira os mapas do encontro da mesa. O que foi revelado continua com os jogadores."""
    world = _main_world(wid)
    _gm(world)
    _encounter(wid, eid)
    db = get_db()
    for (ref,) in db.execute("SELECT ref_id FROM encounter_items WHERE encounter_id = ? AND kind = 'map'", (eid,)).fetchall():
        _hide(wid, "map", ref)
    db.execute("UPDATE encounters SET status = 'done' WHERE id = ?", (eid,))
    db.commit()
    flash("Encontro concluído: os mapas dele saíram da mesa.", "success")
    return _back_to(eid)


# --------------------------------------------------------------------------- mapa da mesa (jogadores)

def _shared_map(world, mid):
    from .maps import get_map
    m = get_map(world, mid)
    if world["role"] not in GM_ROLES and mid not in shared_map_ids(world["id"]):
        abort(404)
    return m


@bp.route("/w/<int:wid>/play/m/<int:mid>")
@login_required
def map_view(wid, mid):
    world = _main_world(wid)
    m = _shared_map(world, mid)
    if world["role"] in GM_ROLES:          # o mestre abre o mapa completo (com edição e névoa)
        return redirect(url_for("maps.view", wid=wid, mid=mid))
    from .maps import sets_of
    data = player_data(json.loads(m["data"] or "{}"))
    return render_template(
        "world/map.html", world=world, map=m, player_view=True,
        image=url_for("files.serve", fid=m["file_id"]) if m["file_id"] else None,
        pins=player_pins(wid, mid, data), page_list=[], file_list=[],
        mapdata=data, version=m["version"], start_edit=False, has_thumb=True, tile_sets=sets_of(wid),
        data_url=url_for("play.map_data", wid=wid, mid=mid), pins_url=url_for("play.map_pins", wid=wid, mid=mid),
        back_url=url_for("play.dashboard", wid=wid))


@bp.route("/w/<int:wid>/play/m/<int:mid>/data")
@login_required
def map_data(wid, mid):
    world = _main_world(wid)
    m = _shared_map(world, mid)
    if request.args.get("v", type=int) == m["version"]:
        return "", 204
    return jsonify(data=player_data(json.loads(m["data"] or "{}")), version=m["version"])


@bp.route("/w/<int:wid>/play/m/<int:mid>/pins")
@login_required
def map_pins(wid, mid):
    world = _main_world(wid)
    m = _shared_map(world, mid)
    return jsonify(player_pins(wid, mid, json.loads(m["data"] or "{}")))


@bp.route("/w/<int:wid>/play/m/<int:mid>/pins/<int:pid>", methods=["PATCH"])
@login_required
def move_token(wid, mid, pid):
    """Jogador só move tokens (x/y); o resto do marcador não muda."""
    world = _main_world(wid)
    m = _shared_map(world, mid)
    db = get_db()
    pin = db.execute("SELECT * FROM map_pins WHERE id = ? AND map_id = ?", (pid, mid)).fetchone()
    data = json.loads(m["data"] or "{}")
    if pin is None or pin["kind"] != "token" or _under_fog(pin, _fog_cells(data)):
        abort(404)
    body = request.get_json(silent=True) or {}
    try:
        x, y = max(0.0, min(1.0, float(body["x"]))), max(0.0, min(1.0, float(body["y"])))
    except (KeyError, TypeError, ValueError):
        abort(400)
    db.execute("UPDATE map_pins SET x = ?, y = ? WHERE id = ?", (x, y, pid))
    db.commit()
    return jsonify(next((p for p in player_pins(wid, mid, data) if p["id"] == pid), {"id": pid, "x": x, "y": y}))


# --------------------------------------------------------------------------- arquivos encontrados

@bp.route("/w/<int:wid>/play/p/<int:aid>")
@login_required
def handout_page(wid, aid):
    world = _main_world(wid)
    if world["role"] not in GM_ROLES and aid not in handout_page_ids(wid):
        abort(404)
    page = get_page(world, aid)
    from .blocks import with_markdown_html
    from .pages import render_lore
    db = get_db()
    allowed = handout_page_ids(wid)
    pages = {r["id"]: {"t": r["title"], "i": page_icon(r), "u": url_for("play.handout_page", wid=wid, aid=r["id"])}
             for r in db.execute("SELECT id, title, icon, category FROM articles WHERE world_id = ?", (wid,)) if r["id"] in allowed}
    data = {"blocks": with_markdown_html(load_blocks(page), lambda md: render_lore(wid, md)), "version": 0,
            "title": page["title"], "aid": aid, "pages": pages, "dividers": [], "readonly": True,
            "api": {"save": "", "subpage": "", "upload": "", "preview": ""}}
    from .pages import _dividers
    data["dividers"] = _dividers()
    return render_template("play/handout.html", world=world, page=page, editor_data=data,
                           cat=CATEGORY_MAP.get(page["category"], CATEGORY_MAP["nota"]))


__all__ = ["ensure_party", "sync_party", "player_file_ids", "is_image"]
