"""Páginas (estilo Notion), relações, linha do tempo e árvore genealógica."""
import json
import re
from pathlib import Path

import mistune
from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request,
                   url_for)
from markupsafe import Markup

from .access import get_page, get_world, page_icon, touch_world
from .blocks import Ctx, blocks_text, clean_blocks, load_blocks, page_ids_in, with_markdown_html
from .icons import glyph_text, icon_from_form
from .auth import login_required
from .constants import CATEGORY_MAP, RELATION_KINDS, relation_options
from .db import get_db
from .files import UploadError, save_upload

bp = Blueprint("pages", __name__)

_markdown = mistune.create_markdown(escape=True, plugins=["strikethrough", "table", "task_lists"])
WIKILINK_RE = re.compile(r"\[\[([^\]|\n]+)(?:\|([^\]\n]+))?\]\]")


def render_lore(world_id, content):
    """Markdown + links de wiki: [[Nome]] ou [[Nome|texto]]. Link para página inexistente vira 'criar'."""
    titles = {
        r["title"].lower(): r["id"]
        for r in get_db().execute("SELECT id, title FROM articles WHERE world_id = ?", (world_id,))
    }

    def repl(m):
        name = m.group(1).strip()
        label = (m.group(2) or name).strip()
        aid = titles.get(name.lower())
        url = (url_for("pages.view", wid=world_id, aid=aid) if aid
               else url_for("pages.new", wid=world_id, title=name))
        return f"[{label}](<{url}>)"

    return Markup(_markdown(WIKILINK_RE.sub(repl, content or "")))


def _title_taken(world_id, title, exclude_id=None):
    return get_db().execute(
        "SELECT 1 FROM articles WHERE world_id = ? AND lower(title) = lower(?) AND id IS NOT ?",
        (world_id, title, exclude_id),
    ).fetchone() is not None


def _descendant_ids(world_id, aid):
    rows = get_db().execute(
        """WITH RECURSIVE d(id) AS (SELECT ? UNION SELECT a.id FROM articles a JOIN d ON a.parent_id = d.id
           WHERE a.world_id = ?) SELECT id FROM d""", (aid, world_id)).fetchall()
    return {r["id"] for r in rows}


def _breadcrumb(world_id, page):
    db = get_db()
    trail, parent_id, seen = [], page["parent_id"], set()
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        p = db.execute("SELECT id, title, icon, category, parent_id FROM articles WHERE id = ? AND world_id = ?",
                       (parent_id, world_id)).fetchone()
        if not p:
            break
        trail.insert(0, p)
        parent_id = p["parent_id"]
    return trail


def _form_data(world, existing=None):
    """Lê o formulário de página. Pode levantar UploadError (capa)."""
    f = request.form
    category = f.get("category", "nota")
    try:
        parent_id = int(f.get("parent_id") or 0) or None
    except ValueError:
        parent_id = None
    if parent_id and not get_db().execute("SELECT 1 FROM articles WHERE id = ? AND world_id = ?",
                                          (parent_id, world["id"])).fetchone():
        parent_id = None
    if existing and parent_id and parent_id in _descendant_ids(world["id"], existing["id"]):
        parent_id = existing["parent_id"]  # evita ciclo (página dentro dela mesma)
    year_raw = f.get("year", "").strip()
    try:
        year = int(year_raw) if year_raw else None
    except ValueError:
        year = existing["year"] if existing else None
    try:
        cover_pos = max(0, min(100, int(f.get("cover_pos", 50))))
    except ValueError:
        cover_pos = 50

    cover = existing["image_url"] if existing else ""
    url_in = f.get("cover_link", "").strip()
    if url_in.startswith(("http://", "https://")):
        cover = url_in
    up = request.files.get("cover")
    if up and up.filename:
        cover = url_for("files.serve", fid=save_upload(world["id"], up, images_only=True))
    if f.get("remove_cover"):
        cover = ""

    return {
        "title": f.get("title", "").strip()[:200],
        "icon": icon_from_form(world["id"]),
        "category": category if category in CATEGORY_MAP else "nota",
        "summary": f.get("summary", "").strip()[:500],
        "image_url": cover,
        "cover_pos": cover_pos,
        "parent_id": parent_id,
        "year": year,
        "date_label": f.get("date_label", "").strip()[:120],
    }


# --------------------------------------------------------------------------- lista / CRUD

@bp.route("/w/<int:wid>/pages")
@login_required
def index(wid):
    world = get_world(wid)
    cat = request.args.get("cat")
    q = request.args.get("q", "").strip()
    sql = "SELECT * FROM articles WHERE world_id = ?"
    params = [wid]
    if cat in CATEGORY_MAP:
        sql += " AND category = ?"
        params.append(cat)
    if q:
        sql += " AND (title LIKE ? OR summary LIKE ? OR content LIKE ?)"
        params += [f"%{q}%"] * 3
    rows = get_db().execute(sql + " ORDER BY title COLLATE NOCASE", params).fetchall()
    return render_template("world/pages.html", world=world, pages=rows, cat=cat, q=q)


@bp.route("/w/<int:wid>/pages/new", methods=["GET", "POST"])
@login_required
def new(wid):
    world = get_world(wid)
    if request.method == "POST":
        try:
            data = _form_data(world)
        except UploadError as e:
            flash(str(e), "error")
            data = None
        if data is not None:
            if not data["title"]:
                flash("A página precisa de um título.", "error")
            elif _title_taken(wid, data["title"]):
                flash("Já existe uma página com esse título neste mundo.", "error")
            else:
                db = get_db()
                cur = db.execute(
                    """INSERT INTO articles (world_id, parent_id, title, icon, category, summary, content,
                       image_url, cover_pos, year, date_label, created_by, updated_by)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (wid, data["parent_id"], data["title"], data["icon"], data["category"], data["summary"],
                     "", data["image_url"], data["cover_pos"], data["year"], data["date_label"],
                     g.user["id"], g.user["id"]),
                )
                _save_timelines(wid, cur.lastrowid)
                touch_world(wid)
                db.commit()
                return redirect(url_for("pages.view", wid=wid, aid=cur.lastrowid))
        page = data or {}
    else:
        cat = request.args.get("cat")
        page = {"title": request.args.get("title", ""),
                "category": cat if cat in CATEGORY_MAP else "personagem",
                "parent_id": request.args.get("parent", type=int)}
    defaults = {"icon": "", "summary": "", "image_url": "", "cover_pos": 50,
                "year": request.args.get("year", type=int), "date_label": "", "parent_id": None}
    page = {**defaults, **page}
    return _render_form(world, page, True)


@bp.post("/w/<int:wid>/pages/quick")
@login_required
def quick_new(wid):
    """Cria uma página "Sem título" e abre direto no editor de blocos (estilo Notion): o título já vem selecionado."""
    world = get_world(wid)
    cat = request.form.get("category")
    cat = cat if cat in CATEGORY_MAP else "nota"
    db = get_db()
    title, n = "Sem título", 1
    while _title_taken(wid, title):
        n += 1
        title = f"Sem título {n}"
    cur = db.execute("""INSERT INTO articles (world_id, title, icon, category, summary, content, image_url, cover_pos,
                        created_by, updated_by) VALUES (?, ?, '', ?, '', '', '', 50, ?, ?)""",
                     (world["id"], title, cat, g.user["id"], g.user["id"]))
    touch_world(wid)
    db.commit()
    return redirect(url_for("pages.view", wid=wid, aid=cur.lastrowid))


def _timelines(wid):
    return get_db().execute("SELECT id, name, color FROM timelines WHERE world_id = ? ORDER BY id", (wid,)).fetchall()


def _selected_timelines(wid, aid=None):
    if request.method == "POST":
        return {int(x) for x in request.form.getlist("timeline") if x.isdigit()}
    if aid:
        return {r["timeline_id"] for r in get_db().execute("SELECT timeline_id FROM timeline_pages WHERE article_id = ?", (aid,))}
    t = request.args.get("timeline", type=int)
    return {t} if t else set()


def _save_timelines(wid, aid):
    db = get_db()
    valid = {r["id"] for r in _timelines(wid)}
    db.execute("DELETE FROM timeline_pages WHERE article_id = ?", (aid,))
    for t in _selected_timelines(wid) & valid:
        db.execute("INSERT INTO timeline_pages (timeline_id, article_id) VALUES (?, ?)", (t, aid))


def _render_form(world, page, is_new, aid=None):
    wid = world["id"]
    parents = _parent_choices(wid) if is_new else _parent_choices(wid, _descendant_ids(wid, aid))
    return render_template("world/page_form.html", world=world, page=page, is_new=is_new, parents=parents,
                           timelines=_timelines(wid), selected_timelines=_selected_timelines(wid, aid))


def _parent_choices(wid, exclude=None):
    rows = get_db().execute("SELECT id, title, icon, category, parent_id FROM articles WHERE world_id = ?",
                            (wid,)).fetchall()
    exclude = exclude or set()
    by_parent = {}
    for r in rows:
        by_parent.setdefault(r["parent_id"], []).append(r)
    out = []

    def walk(pid, depth):
        for r in sorted(by_parent.get(pid, []), key=lambda r: r["title"].lower()):
            if r["id"] in exclude:
                continue
            out.append((r["id"], " " * depth + f"{glyph_text(page_icon(r))} {r['title']}".lstrip()))
            walk(r["id"], depth + 1)
    walk(None, 0)
    return out


@bp.route("/w/<int:wid>/p/<int:aid>")
@login_required
def view(wid, aid):
    world = get_world(wid)
    page = get_page(world, aid)
    db = get_db()
    t = page["title"].lower()
    backlinks = db.execute(
        """SELECT id, title, icon, category FROM articles
           WHERE world_id = ? AND id != ? AND (instr(lower(content), ?) > 0 OR instr(lower(content), ?) > 0)
           ORDER BY title COLLATE NOCASE""",
        (wid, aid, f"[[{t}]]", f"[[{t}|"),
    ).fetchall()
    blocks = load_blocks(page)
    in_blocks = page_ids_in(blocks)
    # subpáginas que já aparecem como bloco não se repetem na lista do fim
    children = [c for c in db.execute("SELECT * FROM articles WHERE parent_id = ? ORDER BY title COLLATE NOCASE", (aid,))
                if c["id"] not in in_blocks]
    others = db.execute("SELECT id, title, icon, category FROM articles WHERE world_id = ? AND id != ? ORDER BY title COLLATE NOCASE",
                        (wid, aid)).fetchall()
    editor = db.execute("SELECT name FROM users WHERE id = ?", (page["updated_by"],)).fetchone() if page["updated_by"] else None
    return render_template(
        "world/page.html", world=world, page=page,
        editor_data=_editor_data(world, page, blocks),
        backlinks=backlinks, children=children, breadcrumb=_breadcrumb(wid, page),
        relations=_relations_of(wid, aid), board_links=_board_links_of(wid, aid),
        others=others, relation_options=relation_options(), editor=editor,
        timelines_of=db.execute("""SELECT t.id, t.name, t.color FROM timelines t JOIN timeline_pages tp
                                   ON tp.timeline_id = t.id WHERE tp.article_id = ? ORDER BY t.id""", (aid,)).fetchall(),
    )


def _page_map(wid):
    rows = get_db().execute("SELECT id, title, icon, category FROM articles WHERE world_id = ?", (wid,)).fetchall()
    return {r["id"]: {"t": r["title"], "i": page_icon(r), "u": url_for("pages.view", wid=wid, aid=r["id"])} for r in rows}


def _dividers():
    """Divisores: qualquer .svg/.png em static/dividers (os SVG ganham a cor do tema)."""
    folder = Path(current_app.static_folder) / "dividers"
    out = []
    for f in sorted(folder.glob("*")):
        if f.suffix.lower() in (".svg", ".png", ".webp"):
            out.append({"key": re.sub(r"[^a-z0-9_-]", "-", f.stem.lower()),
                        "url": url_for("static", filename=f"dividers/{f.name}"), "mask": f.suffix.lower() == ".svg"})
    return out


def _md(wid):
    return lambda md: render_lore(wid, md)


def _editor_data(world, page, blocks):
    wid, aid = world["id"], page["id"]
    return {
        "blocks": with_markdown_html(blocks, _md(wid)),
        "version": page["blocks_version"], "title": page["title"], "aid": aid,
        "pages": _page_map(wid), "dividers": _dividers(),
        "api": {"save": url_for("pages.blocks", wid=wid, aid=aid), "subpage": url_for("pages.subpage", wid=wid, aid=aid),
                "upload": url_for("files.upload", wid=wid), "preview": url_for("pages.preview", wid=wid)},
    }


def _ctx(wid):
    db = get_db()
    return Ctx([r[0] for r in db.execute("SELECT id FROM articles WHERE world_id = ?", (wid,))],
               [r[0] for r in db.execute("SELECT id FROM files WHERE world_id = ?", (wid,))])


@bp.route("/w/<int:wid>/p/<int:aid>/blocks", methods=["GET", "PUT"])
@login_required
def blocks(wid, aid):
    """GET ?v=N: 204 se não mudou. PUT {blocks, version, title}: salva (409 se outra pessoa salvou antes)."""
    world = get_world(wid)
    page = get_page(world, aid)
    db = get_db()
    if request.method == "GET":
        if request.args.get("v", type=int) == page["blocks_version"]:
            return "", 204
        return jsonify(blocks=with_markdown_html(load_blocks(page), _md(wid)),
                       version=page["blocks_version"], title=page["title"], pages=_page_map(wid))
    if request.content_length and request.content_length > 8 * 1024 * 1024:
        abort(413)
    body = request.get_json(silent=True) or {}
    if body.get("version") != page["blocks_version"]:
        return jsonify(blocks=with_markdown_html(load_blocks(page), _md(wid)), pages=_page_map(wid),
                       version=page["blocks_version"], title=page["title"], conflict=True), 409
    clean = clean_blocks(body.get("blocks"), _ctx(wid))
    titles = {k: v["t"] for k, v in _page_map(wid).items()}
    title, title_error = page["title"], None
    new_title = str(body.get("title") or "").strip()[:200]
    if new_title and new_title != page["title"]:
        if _title_taken(wid, new_title, exclude_id=aid):
            title_error = "Já existe uma página com esse título neste mundo."
        else:
            title = new_title
    db.execute("""UPDATE articles SET blocks = ?, content = ?, title = ?, blocks_version = blocks_version + 1,
                  updated_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
               (json.dumps(clean, ensure_ascii=False, separators=(",", ":")), blocks_text(clean, titles), title,
                g.user["id"], aid))
    touch_world(wid)
    db.commit()
    return jsonify(version=page["blocks_version"] + 1, title=title, title_error=title_error)


@bp.post("/w/<int:wid>/p/<int:aid>/subpage")
@login_required
def subpage(wid, aid):
    """Cria uma subpágina vazia (bloco 'Página' do editor)."""
    world = get_world(wid)
    page = get_page(world, aid)
    base = str((request.get_json(silent=True) or {}).get("title") or "Sem título").strip()[:180] or "Sem título"
    title, n = base, 1
    while _title_taken(wid, title):
        n += 1
        title = f"{base} {n}"
    db = get_db()
    cur = db.execute(
        """INSERT INTO articles (world_id, parent_id, title, category, content, created_by, updated_by)
           VALUES (?, ?, ?, ?, '', ?, ?)""", (wid, aid, title, page["category"], g.user["id"], g.user["id"]))
    touch_world(wid)
    db.commit()
    row = db.execute("SELECT id, title, icon, category FROM articles WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(id=row["id"], t=row["title"], i=page_icon(row), u=url_for("pages.view", wid=wid, aid=row["id"])), 201


@bp.post("/w/<int:wid>/p/<int:aid>/favorite")
@login_required
def favorite(wid, aid):
    """Favorita / desfavorita a página (para a pessoa logada)."""
    world = get_world(wid)
    get_page(world, aid)
    db = get_db()
    if aid in g.favorite_ids:
        db.execute("DELETE FROM page_favorites WHERE user_id = ? AND article_id = ?", (g.user["id"], aid))
    else:
        db.execute("INSERT OR IGNORE INTO page_favorites (user_id, article_id) VALUES (?, ?)", (g.user["id"], aid))
    db.commit()
    return redirect(url_for("pages.view", wid=wid, aid=aid))


@bp.route("/w/<int:wid>/p/<int:aid>/edit", methods=["GET", "POST"])
@login_required
def edit(wid, aid):
    world = get_world(wid)
    page = get_page(world, aid)
    if request.method == "POST":
        try:
            data = _form_data(world, existing=page)
        except UploadError as e:
            flash(str(e), "error")
            return redirect(url_for("pages.edit", wid=wid, aid=aid))
        if not data["title"]:
            flash("A página precisa de um título.", "error")
        elif _title_taken(wid, data["title"], exclude_id=aid):
            flash("Já existe uma página com esse título neste mundo.", "error")
        else:
            db = get_db()
            db.execute(
                """UPDATE articles SET parent_id=?, title=?, icon=?, category=?, summary=?, image_url=?,
                   cover_pos=?, year=?, date_label=?, updated_by=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (data["parent_id"], data["title"], data["icon"], data["category"], data["summary"],
                 data["image_url"], data["cover_pos"], data["year"], data["date_label"], g.user["id"], aid),
            )
            _save_timelines(wid, aid)
            touch_world(wid)
            db.commit()
            flash("Página salva.", "success")
            return redirect(url_for("pages.view", wid=wid, aid=aid))
        return _render_form(world, {**data, "id": aid}, False, aid)
    return _render_form(world, page, False, aid)


@bp.post("/w/<int:wid>/p/<int:aid>/delete")
@login_required
def delete(wid, aid):
    world = get_world(wid)
    page = get_page(world, aid)
    db = get_db()
    # subpáginas sobem um nível
    db.execute("UPDATE articles SET parent_id = ? WHERE parent_id = ?", (page["parent_id"], aid))
    db.execute("DELETE FROM articles WHERE id = ?", (aid,))
    db.commit()
    flash(f"“{page['title']}” foi apagada.", "success")
    if page["parent_id"]:
        return redirect(url_for("pages.view", wid=wid, aid=page["parent_id"]))
    return redirect(url_for("pages.index", wid=wid))


@bp.post("/w/<int:wid>/preview")
@login_required
def preview(wid):
    get_world(wid)
    return jsonify(html=str(render_lore(wid, (request.get_json(silent=True) or {}).get("content", ""))))


# --------------------------------------------------------------------------- relações

def _relations_of(wid, aid):
    rows = get_db().execute(
        """SELECT r.*, a.title AS a_title, a.icon AS a_icon, a.category AS a_cat,
                  b.title AS b_title, b.icon AS b_icon, b.category AS b_cat
           FROM relations r JOIN articles a ON a.id = r.a_id JOIN articles b ON b.id = r.b_id
           WHERE r.world_id = ? AND (r.a_id = ? OR r.b_id = ?) ORDER BY r.kind, r.id""",
        (wid, aid, aid)).fetchall()
    out = []
    for r in rows:
        mine_is_a = r["a_id"] == aid
        fwd, back = RELATION_KINDS.get(r["kind"], ("", ""))
        phrase = (fwd if mine_is_a else back) if r["kind"] != "other" else r["label"]
        other = {"id": r["b_id"] if mine_is_a else r["a_id"],
                 "title": r["b_title"] if mine_is_a else r["a_title"],
                 "icon": (r["b_icon"] or CATEGORY_MAP.get(r["b_cat"], CATEGORY_MAP["nota"])["icon"]) if mine_is_a
                 else (r["a_icon"] or CATEGORY_MAP.get(r["a_cat"], CATEGORY_MAP["nota"])["icon"])}
        out.append({"id": r["id"], "phrase": phrase, "other": other})
    return out


def _board_links_of(wid, aid):
    """Ligações feitas nos mapas mentais entre esta página e outras."""
    rows = get_db().execute(
        """SELECT l.label, b.id AS board_id, b.name AS board_name,
                  ca.article_id AS a_id, cb.article_id AS b_id,
                  pa.title AS a_title, pb.title AS b_title, pa.icon AS a_icon, pb.icon AS b_icon,
                  pa.category AS a_cat, pb.category AS b_cat
           FROM board_links l JOIN boards b ON b.id = l.board_id
           JOIN cards ca ON ca.id = l.from_card JOIN cards cb ON cb.id = l.to_card
           JOIN articles pa ON pa.id = ca.article_id JOIN articles pb ON pb.id = cb.article_id
           WHERE b.world_id = ? AND (ca.article_id = ? OR cb.article_id = ?)""", (wid, aid, aid)).fetchall()
    out = []
    for r in rows:
        if r["a_id"] == r["b_id"]:
            continue
        mine_is_a = r["a_id"] == aid
        p = "b" if mine_is_a else "a"
        out.append({"board_id": r["board_id"], "board_name": r["board_name"], "label": r["label"],
                    "direction": "→" if mine_is_a else "←",
                    "other": {"id": r[f"{p}_id"], "title": r[f"{p}_title"],
                              "icon": r[f"{p}_icon"] or CATEGORY_MAP.get(r[f"{p}_cat"], CATEGORY_MAP["nota"])["icon"]}})
    return out


@bp.post("/w/<int:wid>/p/<int:aid>/relations")
@login_required
def add_relation(wid, aid):
    world = get_world(wid)
    get_page(world, aid)
    kind_dir = request.form.get("kind", "")  # ex.: "parent>" ou "parent<"
    kind, direction = (kind_dir[:-1], kind_dir[-1]) if kind_dir[-1:] in ("<", ">") else ("", "")
    try:
        other_id = int(request.form.get("other_id", 0))
    except ValueError:
        other_id = 0
    if kind not in RELATION_KINDS or other_id == aid:
        flash("Escolha o tipo de relação e outra página.", "error")
        return redirect(url_for("pages.view", wid=wid, aid=aid))
    get_page(world, other_id)
    label = request.form.get("label", "").strip()[:120]
    if kind == "other" and not label:
        flash("Escreva qual é a relação.", "error")
        return redirect(url_for("pages.view", wid=wid, aid=aid))
    a, b = (aid, other_id) if direction == ">" else (other_id, aid)
    db = get_db()
    exists = db.execute("SELECT 1 FROM relations WHERE world_id=? AND a_id=? AND b_id=? AND kind=? AND label=?",
                        (wid, a, b, kind, label)).fetchone()
    if not exists:
        db.execute("INSERT INTO relations (world_id, a_id, b_id, kind, label) VALUES (?,?,?,?,?)",
                   (wid, a, b, kind, label if kind == "other" else ""))
        db.commit()
    return redirect(url_for("pages.view", wid=wid, aid=aid) + "#relacoes")


@bp.post("/w/<int:wid>/p/<int:aid>/relations/<int:rid>/delete")
@login_required
def delete_relation(wid, aid, rid):
    get_world(wid)
    db = get_db()
    db.execute("DELETE FROM relations WHERE id = ? AND world_id = ?", (rid, wid))
    db.commit()
    return redirect(url_for("pages.view", wid=wid, aid=aid) + "#relacoes")

