"""Mapas mentais: cards (nota, página, imagem, arquivo, mapa, outro mapa mental) ligados por conexões com rótulo."""
from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from .access import get_file, get_page, get_world, page_icon
from .auth import login_required
from .constants import CARD_COLORS, CATEGORY_MAP
from .db import get_db
from .files import UploadError, is_image, save_upload

bp = Blueprint("boards", __name__)


def get_board(world, bid):
    b = get_db().execute("SELECT * FROM boards WHERE id = ? AND world_id = ?", (bid, world["id"])).fetchone()
    if b is None:
        abort(404)
    return b


def _card_rows(bid, cid=None):
    sql = """SELECT c.*, a.title AS a_title, a.category AS a_category, a.summary AS a_summary,
                    a.icon AS a_icon, a.image_url AS a_cover, a.cover_pos AS a_cover_pos,
                    f.original_name AS f_name, f.mime AS f_mime, f.size AS f_size,
                    m.name AS m_name, m.thumb AS m_thumb, m.file_id AS m_file, rb.name AS rb_name
             FROM cards c
             LEFT JOIN articles a ON a.id = c.article_id
             LEFT JOIN files f ON f.id = c.file_id
             LEFT JOIN maps m ON m.id = c.map_id
             LEFT JOIN boards rb ON rb.id = c.ref_board_id
             WHERE c.board_id = ?"""
    params = [bid]
    if cid is not None:
        sql += " AND c.id = ?"
        params.append(cid)
    return get_db().execute(sql + " ORDER BY c.id", params).fetchall()


def _items_by_card(card_ids):
    """Itens da lista "Relacionados" de cada card, já com título, ícone e link."""
    if not card_ids:
        return {}
    wid = g.world["id"]
    q = ",".join("?" * len(card_ids))
    rows = get_db().execute(
        f"""SELECT i.*, a.title AS a_title, a.icon AS a_icon, a.category AS a_cat, m.name AS m_name,
                   rb.name AS rb_name, f.original_name AS f_name, f.mime AS f_mime
            FROM card_items i
            LEFT JOIN articles a ON a.id = i.article_id LEFT JOIN maps m ON m.id = i.map_id
            LEFT JOIN boards rb ON rb.id = i.ref_board_id LEFT JOIN files f ON f.id = i.file_id
            WHERE i.card_id IN ({q}) ORDER BY i.id""", card_ids).fetchall()
    out = {}
    for r in rows:
        it = {"id": r["id"], "kind": r["kind"], "text": r["text"], "icon": "", "url": None}
        if r["kind"] == "article" and r["a_title"] is not None:
            it.update(text=r["a_title"], icon=page_icon({"icon": r["a_icon"], "category": r["a_cat"]}),
                      url=url_for("pages.view", wid=wid, aid=r["article_id"]))
        elif r["kind"] == "map" and r["m_name"] is not None:
            it.update(text=r["m_name"], icon="ri:map", url=url_for("maps.view", wid=wid, mid=r["map_id"]))
        elif r["kind"] == "board" and r["rb_name"] is not None:
            it.update(text=r["rb_name"], icon="ri:web", url=url_for("boards.view", wid=wid, bid=r["ref_board_id"]))
        elif r["kind"] == "file" and r["f_name"] is not None:
            it.update(text=r["f_name"], icon="ri:picture" if is_image(r["f_mime"]) else "ri:parchment",
                      url=url_for("files.serve", fid=r["file_id"]))
        elif r["kind"] != "note":
            continue  # o item apontava para algo que foi apagado
        out.setdefault(r["card_id"], []).append(it)
    return out


def card_dict(r, items=None):
    d = {k: r[k] for k in ("id", "kind", "title", "body", "color", "x", "y", "w", "article_id", "file_id", "map_id", "ref_board_id")}
    d["items_open"] = bool(r["items_open"])
    d["items"] = (items if items is not None else _items_by_card([r["id"]])).get(r["id"], [])
    wid = g.world["id"]
    if r["kind"] == "article" and r["a_title"] is not None:
        cat = CATEGORY_MAP.get(r["a_category"], CATEGORY_MAP["nota"])
        d["article"] = {
            "title": r["a_title"], "icon": r["a_icon"] or cat["icon"], "category": cat["single"],
            "summary": r["a_summary"], "cover": r["a_cover"], "cover_pos": r["a_cover_pos"],
            "url": url_for("pages.view", wid=wid, aid=r["article_id"]),
        }
    if r["kind"] == "map" and r["m_name"] is not None:
        thumb = r["m_thumb"] or (url_for("files.serve", fid=r["m_file"]) if r["m_file"] else "")
        d["map"] = {"name": r["m_name"], "thumb": thumb, "url": url_for("maps.view", wid=wid, mid=r["map_id"])}
    if r["kind"] == "board" and r["rb_name"] is not None:
        d["board"] = {"name": r["rb_name"], "url": url_for("boards.view", wid=wid, bid=r["ref_board_id"])}
    if r["kind"] in ("image", "file") and r["f_name"] is not None:
        d["file"] = {"name": r["f_name"], "size": r["f_size"], "is_image": is_image(r["f_mime"]),
                     "url": url_for("files.serve", fid=r["file_id"])}
    return d


def _links(bid):
    return [dict(r) for r in get_db().execute(
        "SELECT id, from_card, to_card, label FROM board_links WHERE board_id = ? ORDER BY id", (bid,))]


def _state(bid):
    rows = _card_rows(bid)
    items = _items_by_card([r["id"] for r in rows])
    return {"cards": [card_dict(r, items) for r in rows], "links": _links(bid)}


# --------------------------------------------------------------------------- páginas

@bp.post("/w/<int:wid>/boards")
@login_required
def create(wid):
    get_world(wid)
    name = request.form.get("name", "").strip()[:120] or "Novo mapa mental"
    db = get_db()
    cur = db.execute("INSERT INTO boards (world_id, name) VALUES (?, ?)", (wid, name))
    db.commit()
    return redirect(url_for("boards.view", wid=wid, bid=cur.lastrowid))


@bp.route("/w/<int:wid>/boards")
@login_required
def index(wid):
    world = get_world(wid)
    rows = get_db().execute(
        """SELECT b.*, (SELECT COUNT(*) FROM cards c WHERE c.board_id = b.id) AS n_cards
           FROM boards b WHERE b.world_id = ? ORDER BY b.name COLLATE NOCASE""", (wid,)).fetchall()
    return render_template("world/boards.html", world=world, boards=rows)


@bp.route("/w/<int:wid>/b/<int:bid>")
@login_required
def view(wid, bid):
    world = get_world(wid)
    board = get_board(world, bid)
    pages = get_db().execute(
        "SELECT id, title, icon, category, summary FROM articles WHERE world_id = ? ORDER BY title COLLATE NOCASE",
        (wid,)).fetchall()
    page_list = [{"id": p["id"], "title": p["title"], "icon": page_icon(p),
                  "cat": p["category"] if p["category"] in CATEGORY_MAP else "nota",
                  "category": CATEGORY_MAP.get(p["category"], CATEGORY_MAP["nota"])["single"]} for p in pages]
    maps = [{"id": m["id"], "name": m["name"]} for m in g.maps]
    boards = [{"id": b["id"], "name": b["name"]} for b in g.boards if b["id"] != bid]
    return render_template("world/board.html", world=world, board=board, state=_state(bid), page_list=page_list,
                           map_list=maps, board_list=boards, upload_url=url_for("files.upload", wid=wid))


@bp.post("/w/<int:wid>/b/<int:bid>/rename")
@login_required
def rename(wid, bid):
    world = get_world(wid)
    get_board(world, bid)
    name = request.form.get("name", "").strip()[:120]
    if name:
        db = get_db()
        db.execute("UPDATE boards SET name = ? WHERE id = ?", (name, bid))
        db.commit()
    return redirect(url_for("boards.view", wid=wid, bid=bid))


@bp.post("/w/<int:wid>/b/<int:bid>/delete")
@login_required
def delete(wid, bid):
    world = get_world(wid)
    b = get_board(world, bid)
    db = get_db()
    db.execute("DELETE FROM boards WHERE id = ?", (bid,))
    db.commit()
    flash(f"Mapa mental “{b['name']}” apagado.", "success")
    return redirect(url_for("boards.index", wid=wid))


# --------------------------------------------------------------------------- API JSON

@bp.route("/w/<int:wid>/b/<int:bid>/state")
@login_required
def state(wid, bid):
    world = get_world(wid)
    get_board(world, bid)
    return jsonify(_state(bid))


def _clean(data):
    out = {}
    if "title" in data:
        out["title"] = str(data["title"])[:300]
    if "body" in data:
        out["body"] = str(data["body"])[:20000]
    if data.get("color") in CARD_COLORS:
        out["color"] = data["color"]
    if "items_open" in data:
        out["items_open"] = 1 if data["items_open"] else 0
    for k, lo, hi in (("x", -50000, 50000), ("y", -50000, 50000), ("w", 140, 900)):
        if k in data:
            try:
                out[k] = max(lo, min(hi, int(data[k])))
            except (TypeError, ValueError):
                pass
    return out


def _insert_card(bid, kind, fields, article_id=None, file_id=None, map_id=None, ref_board_id=None):
    f = {"title": "", "body": "", "color": "yellow", "x": 0, "y": 0, "w": 240, **fields}
    db = get_db()
    cur = db.execute(
        """INSERT INTO cards (board_id, kind, title, body, color, x, y, w, article_id, file_id, map_id, ref_board_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (bid, kind, f["title"], f["body"], f["color"], f["x"], f["y"], f["w"], article_id, file_id, map_id, ref_board_id))
    db.commit()
    return card_dict(_card_rows(bid, cur.lastrowid)[0])


@bp.post("/w/<int:wid>/b/<int:bid>/cards")
@login_required
def card_create(wid, bid):
    world = get_world(wid)
    get_board(world, bid)
    data = request.get_json(silent=True) or {}
    fields = _clean(data)
    kind = data.get("kind", "note")
    if kind == "article":
        a = get_page(world, int(data.get("article_id") or 0))
        fields.setdefault("color", "white")
        fields.setdefault("w", 260)
        return jsonify(_insert_card(bid, "article", fields, article_id=a["id"])), 201
    if kind == "map":
        m = get_db().execute("SELECT id FROM maps WHERE id = ? AND world_id = ?", (int(data.get("map_id") or 0), wid)).fetchone()
        if m is None:
            abort(404)
        fields.setdefault("color", "white")
        fields.setdefault("w", 260)
        return jsonify(_insert_card(bid, "map", fields, map_id=m["id"])), 201
    if kind == "board":
        other = get_board(world, int(data.get("ref_board_id") or 0))
        fields.setdefault("color", "white")
        return jsonify(_insert_card(bid, "board", fields, ref_board_id=other["id"])), 201
    if kind in ("image", "file"):
        f = get_file(world, int(data.get("file_id") or 0))
        kind = "image" if is_image(f["mime"]) else "file"
        fields.setdefault("color", "white")
        fields.setdefault("w", 300 if kind == "image" else 240)
        return jsonify(_insert_card(bid, kind, fields, file_id=f["id"])), 201
    return jsonify(_insert_card(bid, "note", fields)), 201


@bp.post("/w/<int:wid>/b/<int:bid>/upload")
@login_required
def upload(wid, bid):
    """Solta/cola imagens ou arquivos no mapa: salva no acervo e cria cards."""
    world = get_world(wid)
    get_board(world, bid)
    try:
        x, y = int(request.form.get("x", 0)), int(request.form.get("y", 0))
    except ValueError:
        x = y = 0
    cards, errors = [], []
    for i, fs in enumerate(request.files.getlist("files")):
        try:
            fid = save_upload(wid, fs)
        except UploadError as e:
            errors.append(str(e))
            continue
        f = get_file(world, fid)
        kind = "image" if is_image(f["mime"]) else "file"
        cards.append(_insert_card(bid, kind, {"x": x + i * 30, "y": y + i * 30, "color": "white",
                                              "w": 300 if kind == "image" else 240}, file_id=fid))
    return jsonify(cards=cards, errors=errors), (201 if cards else 400)


def _get_card(bid, cid):
    if not get_db().execute("SELECT 1 FROM cards WHERE id = ? AND board_id = ?", (cid, bid)).fetchone():
        abort(404)


@bp.route("/w/<int:wid>/b/<int:bid>/cards/<int:cid>", methods=["PATCH", "DELETE"])
@login_required
def card_update(wid, bid, cid):
    world = get_world(wid)
    get_board(world, bid)
    _get_card(bid, cid)
    db = get_db()
    if request.method == "DELETE":
        db.execute("DELETE FROM cards WHERE id = ?", (cid,))
        db.commit()
        return "", 204
    fields = _clean(request.get_json(silent=True) or {})
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)  # chaves vêm da lista fixa de _clean
        db.execute(f"UPDATE cards SET {sets} WHERE id = ?", (*fields.values(), cid))
        db.commit()
    return jsonify(card_dict(_card_rows(bid, cid)[0]))


@bp.post("/w/<int:wid>/b/<int:bid>/cards/<int:cid>/items")
@login_required
def item_create(wid, bid, cid):
    """Adiciona um assunto à lista "Relacionados" do card: texto, página, mapa, mapa mental ou arquivo."""
    world = get_world(wid)
    get_board(world, bid)
    _get_card(bid, cid)
    data = request.get_json(silent=True) or {}
    kind = data.get("kind", "note")
    db = get_db()
    vals = {"text": "", "article_id": None, "map_id": None, "ref_board_id": None, "file_id": None}
    if kind == "article":
        vals["article_id"] = get_page(world, int(data.get("article_id") or 0))["id"]
    elif kind == "map":
        m = db.execute("SELECT id FROM maps WHERE id = ? AND world_id = ?", (int(data.get("map_id") or 0), wid)).fetchone()
        if m is None:
            abort(404)
        vals["map_id"] = m["id"]
    elif kind == "board":
        vals["ref_board_id"] = get_board(world, int(data.get("ref_board_id") or 0))["id"]
    elif kind == "file":
        vals["file_id"] = get_file(world, int(data.get("file_id") or 0))["id"]
    else:
        kind = "note"
        vals["text"] = str(data.get("text", "")).strip()[:300]
        if not vals["text"]:
            abort(400, "Escreva o assunto.")
    db.execute("""INSERT INTO card_items (card_id, kind, text, article_id, map_id, ref_board_id, file_id)
                  VALUES (?,?,?,?,?,?,?)""", (cid, kind, vals["text"], vals["article_id"], vals["map_id"],
                                              vals["ref_board_id"], vals["file_id"]))
    db.execute("UPDATE cards SET items_open = 1 WHERE id = ?", (cid,))
    db.commit()
    return jsonify(card_dict(_card_rows(bid, cid)[0])), 201


@bp.delete("/w/<int:wid>/b/<int:bid>/cards/<int:cid>/items/<int:iid>")
@login_required
def item_delete(wid, bid, cid, iid):
    world = get_world(wid)
    get_board(world, bid)
    _get_card(bid, cid)
    db = get_db()
    db.execute("DELETE FROM card_items WHERE id = ? AND card_id = ?", (iid, cid))
    db.commit()
    return jsonify(card_dict(_card_rows(bid, cid)[0]))


@bp.post("/w/<int:wid>/b/<int:bid>/links")
@login_required
def link_create(wid, bid):
    world = get_world(wid)
    get_board(world, bid)
    data = request.get_json(silent=True) or {}
    try:
        a, b = int(data.get("from_card")), int(data.get("to_card"))
    except (TypeError, ValueError):
        abort(400)
    if a == b:
        abort(400)
    _get_card(bid, a)
    _get_card(bid, b)
    db = get_db()
    dup = db.execute("""SELECT id FROM board_links WHERE board_id = ? AND
                        ((from_card = ? AND to_card = ?) OR (from_card = ? AND to_card = ?))""",
                     (bid, a, b, b, a)).fetchone()
    if dup:
        return jsonify(dict(db.execute("SELECT id, from_card, to_card, label FROM board_links WHERE id = ?",
                                       (dup["id"],)).fetchone()))
    cur = db.execute("INSERT INTO board_links (board_id, from_card, to_card, label) VALUES (?,?,?,?)",
                     (bid, a, b, str(data.get("label", ""))[:200]))
    db.commit()
    return jsonify({"id": cur.lastrowid, "from_card": a, "to_card": b, "label": str(data.get("label", ""))[:200]}), 201


@bp.route("/w/<int:wid>/b/<int:bid>/links/<int:lid>", methods=["PATCH", "DELETE"])
@login_required
def link_update(wid, bid, lid):
    world = get_world(wid)
    get_board(world, bid)
    db = get_db()
    if not db.execute("SELECT 1 FROM board_links WHERE id = ? AND board_id = ?", (lid, bid)).fetchone():
        abort(404)
    if request.method == "DELETE":
        db.execute("DELETE FROM board_links WHERE id = ?", (lid,))
        db.commit()
        return "", 204
    data = request.get_json(silent=True) or {}
    if "reverse" in data:
        db.execute("UPDATE board_links SET from_card = to_card, to_card = from_card WHERE id = ?", (lid,))
    if "label" in data:
        db.execute("UPDATE board_links SET label = ? WHERE id = ?", (str(data["label"])[:200], lid))
    db.commit()
    return jsonify(dict(db.execute("SELECT id, from_card, to_card, label FROM board_links WHERE id = ?", (lid,)).fetchone()))
