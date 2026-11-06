"""Mapas do mundo: imagem com marcadores (locais, arquivos) e tokens de jogadores."""
import json
import re

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from .access import get_file, get_page, get_world, page_icon
from .auth import login_required
from .db import get_db
from .files import UploadError, file_dict, is_image, save_upload

bp = Blueprint("maps", __name__)
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def get_map(world, mid):
    m = get_db().execute("SELECT * FROM maps WHERE id = ? AND world_id = ?", (mid, world["id"])).fetchone()
    if m is None:
        abort(404)
    return m


@bp.route("/w/<int:wid>/maps")
@login_required
def index(wid):
    world = get_world(wid)
    rows = get_db().execute(
        """SELECT m.*, (SELECT COUNT(*) FROM map_pins p WHERE p.map_id = m.id) AS n_pins
           FROM maps m WHERE m.world_id = ? ORDER BY m.name COLLATE NOCASE""", (wid,)).fetchall()
    return render_template("world/maps.html", world=world, maps=rows)


def _num(v, default, lo, hi):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


@bp.post("/w/<int:wid>/maps")
@login_required
def create(wid):
    """Cria um mapa a partir de uma imagem ou do zero (grade + terreno base)."""
    get_world(wid)
    name = request.form.get("name", "").strip()[:120] or "Novo mapa"
    fid = None
    grid_type = request.form.get("grid", "square")
    data = {"grid": {"type": grid_type if grid_type in GRID_TYPES else "square",
                     "size": _num(request.form.get("size"), 48, 16, 160),
                     "cols": _num(request.form.get("cols"), 30, 2, MAX_CELLS),
                     "rows": _num(request.form.get("rows"), 20, 2, MAX_CELLS),
                     "color": "#000000", "opacity": 0.25, "show": True},
            "base": request.form.get("base", "")[:40], "bg": "#1c1917",
            "terrain": {}, "walls": {}, "props": []}
    if request.form.get("mode") != "blank":
        try:
            fid = save_upload(wid, request.files.get("image"), images_only=True)
        except UploadError as e:
            flash(str(e), "error")
            return redirect(url_for("maps.index", wid=wid))
        data["grid"]["type"] = "none"   # imagem pronta: grade opcional
        data["base"] = ""
    db = get_db()
    cur = db.execute("INSERT INTO maps (world_id, name, file_id, data) VALUES (?, ?, ?, ?)",
                     (wid, name, fid, json.dumps(data)))
    db.commit()
    return redirect(url_for("maps.view", wid=wid, mid=cur.lastrowid, edit=1 if fid is None else None))


# --------------------------------------------------------------------------- dados do editor

GRID_TYPES = ("none", "square", "hex")
FOG_CELL = re.compile(r"\d{1,3},\d{1,3}")
MAX_CELLS = 150
MAX_DATA = 3 * 1024 * 1024


def _clean_data(d):
    """Valida a estrutura do mapa editável (o conteúdo só é desenhado em <canvas> no cliente)."""
    if not isinstance(d, dict):
        abort(400, "Dados inválidos.")
    gr = d.get("grid") if isinstance(d.get("grid"), dict) else {}
    color = str(gr.get("color", "#000000"))
    out = {
        "grid": {"type": gr.get("type") if gr.get("type") in GRID_TYPES else "square",
                 "size": _num(gr.get("size"), 48, 16, 160), "cols": _num(gr.get("cols"), 30, 2, MAX_CELLS),
                 "rows": _num(gr.get("rows"), 20, 2, MAX_CELLS),
                 "color": color if HEX_RE.match(color) else "#000000",
                 "opacity": max(0.0, min(1.0, float(gr.get("opacity", 0.25) or 0))), "show": bool(gr.get("show", True))},
        "base": str(d.get("base", ""))[:40],
        "bg": str(d.get("bg", "#1c1917")) if HEX_RE.match(str(d.get("bg", ""))) else "#1c1917",
        "imageOpacity": max(0.0, min(1.0, float(d.get("imageOpacity", 1) or 0))),
        "terrain": {str(k)[:16]: str(v)[:40] for k, v in (d.get("terrain") or {}).items()} if isinstance(d.get("terrain"), dict) else {},
        "walls": {str(k)[:40]: str(v)[:16] for k, v in (d.get("walls") or {}).items()} if isinstance(d.get("walls"), dict) else {},
        "props": [],
    }
    fog = d.get("fog") if isinstance(d.get("fog"), dict) else {}
    out["fog"] = {"cols": _num(fog.get("cols"), 0, 0, 400), "rows": _num(fog.get("rows"), 0, 0, 400),
                  "cells": [k for k in (fog.get("cells") or [])[:160000]
                            if isinstance(k, str) and FOG_CELL.fullmatch(k)]}
    for p in (d.get("props") or [])[:5000]:
        if not isinstance(p, dict):
            continue
        try:
            out["props"].append({"id": str(p.get("id", ""))[:20], "a": str(p.get("a", ""))[:60],
                                 "x": round(float(p.get("x", 0)), 1), "y": round(float(p.get("y", 0)), 1),
                                 "s": max(0.1, min(10.0, float(p.get("s", 1)))), "f": bool(p.get("f")),
                                 "r": round(float(p.get("r", 0) or 0) % 360, 1)})
        except (TypeError, ValueError):
            continue
    return out


@bp.route("/w/<int:wid>/m/<int:mid>/data", methods=["GET", "PUT"])
@login_required
def data(wid, mid):
    world = get_world(wid)
    m = get_map(world, mid)
    db = get_db()
    if request.method == "GET":
        if request.args.get("v", type=int) == m["version"]:
            return "", 204
        return jsonify(data=json.loads(m["data"] or "{}"), version=m["version"])
    if request.content_length and request.content_length > MAX_DATA:
        abort(413)
    body = request.get_json(silent=True) or {}
    if body.get("version") != m["version"]:
        # alguém salvou antes: devolve o estado atual para o cliente se ajustar
        return jsonify(data=json.loads(m["data"] or "{}"), version=m["version"], conflict=True), 409
    clean = json.dumps(_clean_data(body.get("data")), separators=(",", ":"))
    thumb = str(body.get("thumb") or "")
    thumb_ok = thumb.startswith("data:image/jpeg;base64,") and len(thumb) < 400_000
    db.execute("UPDATE maps SET data = ?, version = version + 1, thumb = CASE WHEN ? THEN ? ELSE thumb END WHERE id = ?",
               (clean, thumb_ok, thumb, mid))
    db.commit()
    return jsonify(version=m["version"] + 1)


def _pin_rows(mid, pid=None):
    sql = """SELECT p.*, a.title AS a_title, a.icon AS a_icon, a.category AS a_cat, a.summary AS a_summary,
                    a.image_url AS a_cover, f.original_name AS f_name, f.mime AS f_mime, f.size AS f_size
             FROM map_pins p LEFT JOIN articles a ON a.id = p.article_id LEFT JOIN files f ON f.id = p.file_id
             WHERE p.map_id = ?"""
    params = [mid]
    if pid is not None:
        sql += " AND p.id = ?"
        params.append(pid)
    return get_db().execute(sql + " ORDER BY p.kind DESC, p.id", params).fetchall()


def pin_dict(r):
    wid = g.world["id"]
    d = {k: r[k] for k in ("id", "kind", "x", "y", "label", "note", "color", "article_id", "file_id", "image_file_id")}
    d["image"] = url_for("files.serve", fid=r["image_file_id"]) if r["image_file_id"] else None
    if r["article_id"] and r["a_title"] is not None:
        d["article"] = {"title": r["a_title"], "summary": r["a_summary"], "cover": r["a_cover"],
                        "icon": page_icon({"icon": r["a_icon"], "category": r["a_cat"]}),
                        "url": url_for("pages.view", wid=wid, aid=r["article_id"])}
        if not d["image"] and r["kind"] == "token" and r["a_cover"]:
            d["image"] = r["a_cover"]  # token sem retrato usa a capa do personagem
    if r["file_id"] and r["f_name"] is not None:
        d["file"] = {"name": r["f_name"], "size": r["f_size"], "is_image": is_image(r["f_mime"]),
                     "url": url_for("files.serve", fid=r["file_id"])}
    return d


@bp.route("/w/<int:wid>/m/<int:mid>")
@login_required
def view(wid, mid):
    world = get_world(wid)
    m = get_map(world, mid)
    db = get_db()
    pages = db.execute("SELECT id, title, icon, category FROM articles WHERE world_id = ? ORDER BY title COLLATE NOCASE",
                       (wid,)).fetchall()
    files = db.execute("SELECT * FROM files WHERE world_id = ? ORDER BY original_name COLLATE NOCASE", (wid,)).fetchall()
    return render_template(
        "world/map.html", world=world, map=m,
        image=url_for("files.serve", fid=m["file_id"]) if m["file_id"] else None,
        pins=[pin_dict(r) for r in _pin_rows(mid)],
        page_list=[{"id": p["id"], "title": p["title"], "icon": page_icon(p)} for p in pages],
        file_list=[file_dict(f) for f in files],
        mapdata=json.loads(m["data"] or "{}"), version=m["version"],
        start_edit=bool(request.args.get("edit")),
        has_thumb=bool(m["thumb"]),
        tile_sets=sets_of(wid),
        player_view=False,
    )


# --------------------------------------------------------------------------- aba "Meus": conjuntos e imagens

SET_KINDS = ("props", "terrain")
DEFAULT_SET = "Meus"
MAX_TILES = 4096


def tileset_dict(r):
    return {"id": r["id"], "set_id": r["set_id"], "name": r["name"], "tile": r["tile"],
            "tiles": json.loads(r["tiles"] or "[]"), "url": url_for("files.serve", fid=r["file_id"])}


def sets_of(wid):
    """Conjuntos do mundo com as imagens de cada um (o padrão "Meus" primeiro)."""
    db = get_db()
    sets = [{"id": r["id"], "name": r["name"], "kind": r["kind"], "tilesets": []} for r in db.execute(
        "SELECT * FROM map_sets WHERE world_id = ? ORDER BY name != ?, name COLLATE NOCASE, id", (wid, DEFAULT_SET))]
    by_id = {x["id"]: x for x in sets}
    for r in db.execute("SELECT * FROM map_tilesets WHERE world_id = ? ORDER BY id", (wid,)):
        if r["set_id"] in by_id:
            by_id[r["set_id"]]["tilesets"].append(tileset_dict(r))
    return sets


def _set_for_upload(wid):
    """Conjunto escolhido no envio: um existente, um novo, ou o padrão "Meus" (criado se preciso)."""
    db = get_db()
    sid = request.form.get("set_id", type=int)
    if sid:
        row = db.execute("SELECT * FROM map_sets WHERE id = ? AND world_id = ?", (sid, wid)).fetchone()
        if row is None:
            abort(404)
        return row
    name = request.form.get("new_set_name", "").strip()[:60] or DEFAULT_SET
    kind = request.form.get("new_set_kind") if request.form.get("new_set_kind") in SET_KINDS else "props"
    row = db.execute("SELECT * FROM map_sets WHERE world_id = ? AND name = ? AND kind = ?", (wid, name, kind)).fetchone()
    if row is None:
        new_id = db.execute("INSERT INTO map_sets (world_id, name, kind) VALUES (?, ?, ?)", (wid, name, kind)).lastrowid
        row = db.execute("SELECT * FROM map_sets WHERE id = ?", (new_id,)).fetchone()
    return row


@bp.post("/w/<int:wid>/tilesets")
@login_required
def tileset_create(wid):
    """Recebe a imagem + como recortar (o recorte em si é feito no navegador, com <canvas>)."""
    get_world(wid)
    tile = _num(request.form.get("tile"), 0, 0, 512)
    if tile and tile < 4:
        abort(400, "Tamanho de tile muito pequeno.")
    tiles = []
    if tile:
        try:
            raw = json.loads(request.form.get("tiles") or "[]")
            tiles = [[int(c), int(r)] for c, r in raw[:MAX_TILES] if 0 <= int(c) < 1024 and 0 <= int(r) < 1024]
        except (TypeError, ValueError):
            abort(400, "Lista de tiles inválida.")
        if not tiles:
            abort(400, "Nenhum tile com conteúdo nessa imagem.")
    try:
        fid = save_upload(wid, request.files.get("image"), images_only=True)
    except UploadError as e:
        return jsonify(error=str(e)), 400
    st = _set_for_upload(wid)
    name = request.form.get("name", "").strip()[:60] or "Imagem"
    db = get_db()
    cur = db.execute(
        "INSERT INTO map_tilesets (world_id, set_id, file_id, name, kind, tile, tiles, created_by) VALUES (?,?,?,?,?,?,?,?)",
        (wid, st["id"], fid, name, st["kind"], tile, json.dumps(tiles), g.user["id"]))
    db.commit()
    return jsonify(sets=sets_of(wid), id=cur.lastrowid), 201


@bp.delete("/w/<int:wid>/tilesets/<int:tid>")
@login_required
def tileset_delete(wid, tid):
    """Tira a imagem do conjunto (ela continua no Acervo). Objetos já colocados somem do desenho."""
    get_world(wid)
    db = get_db()
    db.execute("DELETE FROM map_tilesets WHERE id = ? AND world_id = ?", (tid, wid))
    db.commit()
    return jsonify(sets=sets_of(wid))


@bp.delete("/w/<int:wid>/sets/<int:sid>")
@login_required
def set_delete(wid, sid):
    get_world(wid)
    db = get_db()
    db.execute("DELETE FROM map_sets WHERE id = ? AND world_id = ?", (sid, wid))
    db.commit()
    return jsonify(sets=sets_of(wid))


@bp.post("/w/<int:wid>/m/<int:mid>/settings")
@login_required
def settings(wid, mid):
    world = get_world(wid)
    get_map(world, mid)
    db = get_db()
    name = request.form.get("name", "").strip()[:120]
    if name:
        db.execute("UPDATE maps SET name = ? WHERE id = ?", (name, mid))
    up = request.files.get("image")
    if up and up.filename:
        try:
            db.execute("UPDATE maps SET file_id = ? WHERE id = ?", (save_upload(wid, up, images_only=True), mid))
        except UploadError as e:
            flash(str(e), "error")
    db.commit()
    return redirect(url_for("maps.view", wid=wid, mid=mid))


@bp.post("/w/<int:wid>/m/<int:mid>/delete")
@login_required
def delete(wid, mid):
    world = get_world(wid)
    m = get_map(world, mid)
    db = get_db()
    db.execute("DELETE FROM maps WHERE id = ?", (mid,))
    db.commit()
    flash(f"Mapa “{m['name']}” apagado (a imagem continua no acervo).", "success")
    return redirect(url_for("maps.index", wid=wid))


# --------------------------------------------------------------------------- API dos marcadores

@bp.route("/w/<int:wid>/m/<int:mid>/pins")
@login_required
def pins(wid, mid):
    world = get_world(wid)
    get_map(world, mid)
    return jsonify([pin_dict(r) for r in _pin_rows(mid)])


def _clean_pin(world, data):
    out = {}
    for k, n in (("label", 120), ("note", 5000)):
        if k in data:
            out[k] = str(data[k] or "")[:n]
    for k in ("x", "y"):
        if k in data:
            try:
                out[k] = max(0.0, min(1.0, float(data[k])))
            except (TypeError, ValueError):
                pass
    if HEX_RE.match(str(data.get("color", ""))):
        out["color"] = data["color"]
    if "article_id" in data:
        out["article_id"] = get_page(world, int(data["article_id"]))["id"] if data["article_id"] else None
    for k in ("file_id", "image_file_id"):
        if k in data:
            out[k] = get_file(world, int(data[k]))["id"] if data[k] else None
    return out


@bp.post("/w/<int:wid>/m/<int:mid>/pins")
@login_required
def pin_create(wid, mid):
    world = get_world(wid)
    get_map(world, mid)
    data = request.get_json(silent=True) or {}
    kind = "token" if data.get("kind") == "token" else "pin"
    f = {"x": 0.5, "y": 0.5, "label": "", "note": "", "color": "#f59e0b", "article_id": None,
         "file_id": None, "image_file_id": None, **_clean_pin(world, data)}
    db = get_db()
    cur = db.execute(
        """INSERT INTO map_pins (map_id, kind, x, y, label, note, color, article_id, file_id, image_file_id)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (mid, kind, f["x"], f["y"], f["label"], f["note"], f["color"], f["article_id"], f["file_id"], f["image_file_id"]))
    db.commit()
    return jsonify(pin_dict(_pin_rows(mid, cur.lastrowid)[0])), 201


@bp.route("/w/<int:wid>/m/<int:mid>/pins/<int:pid>", methods=["PATCH", "DELETE"])
@login_required
def pin_update(wid, mid, pid):
    world = get_world(wid)
    get_map(world, mid)
    db = get_db()
    if not db.execute("SELECT 1 FROM map_pins WHERE id = ? AND map_id = ?", (pid, mid)).fetchone():
        abort(404)
    if request.method == "DELETE":
        db.execute("DELETE FROM map_pins WHERE id = ?", (pid,))
        db.commit()
        return "", 204
    fields = _clean_pin(world, request.get_json(silent=True) or {})
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)  # chaves vêm de lista fixa em _clean_pin
        db.execute(f"UPDATE map_pins SET {sets} WHERE id = ?", (*fields.values(), pid))
        db.commit()
    return jsonify(pin_dict(_pin_rows(mid, pid)[0]))
