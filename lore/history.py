"""Várias linhas do tempo e várias árvores genealógicas por mundo."""
import re

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from .access import get_page, get_world, page_icon, touch_world
from .auth import login_required
from .db import get_db

bp = Blueprint("history", __name__)
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
TIMELINE_COLORS = ["#f59e0b", "#ef4444", "#3b82f6", "#ec4899", "#8b5cf6", "#10b981", "#06b6d4", "#78716c"]


def _get(table, wid, oid):
    row = get_db().execute(f"SELECT * FROM {table} WHERE id = ? AND world_id = ?", (oid, wid)).fetchone()
    if row is None:
        abort(404)
    return row


def _int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# =========================================================================== linhas do tempo

@bp.route("/w/<int:wid>/timelines")
@login_required
def timelines(wid):
    world = get_world(wid)
    db = get_db()
    lines = db.execute(
        """SELECT t.*, (SELECT COUNT(*) FROM timeline_pages tp JOIN articles a ON a.id = tp.article_id
                        WHERE tp.timeline_id = t.id AND a.year IS NOT NULL) AS n
           FROM timelines t WHERE t.world_id = ? ORDER BY t.id""", (wid,)).fetchall()
    current = None
    tid = request.args.get("t", type=int)
    if tid:
        current = next((t for t in lines if t["id"] == tid), None)
        if current is None:
            abort(404)
    if current:
        events = db.execute(
            """SELECT a.* FROM articles a JOIN timeline_pages tp ON tp.article_id = a.id
               WHERE tp.timeline_id = ? AND a.year IS NOT NULL ORDER BY a.year, a.date_label, a.title COLLATE NOCASE""",
            (current["id"],)).fetchall()
    else:
        events = db.execute(
            "SELECT * FROM articles WHERE world_id = ? AND year IS NOT NULL ORDER BY year, date_label, title COLLATE NOCASE",
            (wid,)).fetchall()
    # em quais linhas cada evento está (bolinhas coloridas)
    membership = {}
    for r in db.execute("""SELECT tp.article_id, t.id, t.name, t.color FROM timeline_pages tp
                           JOIN timelines t ON t.id = tp.timeline_id WHERE t.world_id = ?""", (wid,)):
        membership.setdefault(r["article_id"], []).append(r)
    pages = db.execute("SELECT id, title, icon, category, year FROM articles WHERE world_id = ? ORDER BY title COLLATE NOCASE",
                       (wid,)).fetchall()
    return render_template("world/timeline.html", world=world, lines=lines, current=current, events=events,
                           membership=membership, pages=pages, colors=TIMELINE_COLORS)


@bp.post("/w/<int:wid>/timelines")
@login_required
def timeline_create(wid):
    get_world(wid)
    name = request.form.get("name", "").strip()[:120] or "Nova linha do tempo"
    color = request.form.get("color", "")
    db = get_db()
    n = db.execute("SELECT COUNT(*) FROM timelines WHERE world_id = ?", (wid,)).fetchone()[0]
    cur = db.execute("INSERT INTO timelines (world_id, name, color) VALUES (?, ?, ?)",
                     (wid, name, color if HEX_RE.match(color) else TIMELINE_COLORS[n % len(TIMELINE_COLORS)]))
    db.commit()
    return redirect(url_for("history.timelines", wid=wid, t=cur.lastrowid))


@bp.post("/w/<int:wid>/timelines/<int:tid>")
@login_required
def timeline_update(wid, tid):
    get_world(wid)
    t = _get("timelines", wid, tid)
    db = get_db()
    if request.form.get("delete"):
        db.execute("DELETE FROM timelines WHERE id = ?", (tid,))
        db.commit()
        flash(f"Linha “{t['name']}” apagada (as páginas continuam existindo).", "success")
        return redirect(url_for("history.timelines", wid=wid))
    name = request.form.get("name", "").strip()[:120] or t["name"]
    color = request.form.get("color", "")
    db.execute("UPDATE timelines SET name = ?, color = ? WHERE id = ?",
               (name, color if HEX_RE.match(color) else t["color"], tid))
    db.commit()
    return redirect(url_for("history.timelines", wid=wid, t=tid))


@bp.post("/w/<int:wid>/timelines/events")
@login_required
def timeline_add_event(wid):
    """Cria um evento novo ou coloca uma página existente em uma ou mais linhas."""
    world = get_world(wid)
    db = get_db()
    year = _int(request.form.get("year"))
    line_ids = [i for i in (_int(x) for x in request.form.getlist("timeline")) if i]
    valid = {r["id"] for r in db.execute("SELECT id FROM timelines WHERE world_id = ?", (wid,))}
    line_ids = [i for i in line_ids if i in valid]
    back = url_for("history.timelines", wid=wid, t=_int(request.form.get("back")))

    page_id = _int(request.form.get("page_id"))
    if page_id:
        page = get_page(world, page_id)
        if year is None and page["year"] is None:
            flash("Essa página ainda não tem ano: informe o ano.", "error")
            return redirect(back)
        if year is not None:
            db.execute("UPDATE articles SET year = ?, date_label = COALESCE(NULLIF(?, ''), date_label) WHERE id = ?",
                       (year, request.form.get("date_label", "").strip()[:120], page_id))
    else:
        title = request.form.get("title", "").strip()[:200]
        if not title or year is None:
            flash("Informe título e ano (pode ser negativo, ex.: -300).", "error")
            return redirect(back)
        if db.execute("SELECT 1 FROM articles WHERE world_id = ? AND lower(title) = lower(?)", (wid, title)).fetchone():
            flash("Já existe uma página com esse título: use “Página existente”.", "error")
            return redirect(back)
        page_id = db.execute(
            """INSERT INTO articles (world_id, title, category, summary, year, date_label, created_by, updated_by)
               VALUES (?, ?, 'evento', ?, ?, ?, ?, ?)""",
            (wid, title, request.form.get("summary", "").strip()[:500], year,
             request.form.get("date_label", "").strip()[:120], g.user["id"], g.user["id"])).lastrowid
    for lid in line_ids:
        db.execute("INSERT OR IGNORE INTO timeline_pages (timeline_id, article_id) VALUES (?, ?)", (lid, page_id))
    touch_world(wid)
    db.commit()
    return redirect(back)


@bp.post("/w/<int:wid>/timelines/<int:tid>/remove/<int:aid>")
@login_required
def timeline_remove(wid, tid, aid):
    get_world(wid)
    _get("timelines", wid, tid)
    db = get_db()
    db.execute("DELETE FROM timeline_pages WHERE timeline_id = ? AND article_id = ?", (tid, aid))
    db.commit()
    return redirect(url_for("history.timelines", wid=wid, t=tid))


# =========================================================================== árvores genealógicas

# laços de família que a árvore desenha
FAMILY_KINDS = ("parent", "adopt", "guardian", "spouse", "ex_spouse", "betrothed", "sibling", "twin", "half_sibling")
SYMMETRIC_KINDS = {"spouse", "ex_spouse", "betrothed", "sibling", "twin", "half_sibling"}
# tipo escolhido na árvore -> (tipo guardado, a outra pessoa vem primeiro?)
LINK_KINDS = {
    "parent": ("parent", True), "child": ("parent", False),
    "spouse": ("spouse", False), "ex_spouse": ("ex_spouse", False), "betrothed": ("betrothed", False),
    "sibling": ("sibling", False), "twin": ("twin", False), "half_sibling": ("half_sibling", False),
    "adoptive_parent": ("adopt", True), "adoptive_child": ("adopt", False),
    "guardian": ("guardian", True), "ward": ("guardian", False),
}


def _add_rel(wid, x, y, kind):
    db = get_db()
    if kind in SYMMETRIC_KINDS:
        exists = db.execute("""SELECT 1 FROM relations WHERE world_id = ? AND kind = ?
                               AND ((a_id = ? AND b_id = ?) OR (a_id = ? AND b_id = ?))""", (wid, kind, x, y, y, x)).fetchone()
    else:
        exists = db.execute("SELECT 1 FROM relations WHERE world_id = ? AND kind = ? AND a_id = ? AND b_id = ?",
                            (wid, kind, x, y)).fetchone()
    if not exists and x != y:
        db.execute("INSERT INTO relations (world_id, a_id, b_id, kind) VALUES (?, ?, ?, ?)", (wid, x, y, kind))


def _tree_data(wid, tid):
    """Pessoas da árvore + laços (pai/mãe e cônjuge) entre elas."""
    db = get_db()
    people = db.execute(
        """SELECT a.id, a.title, a.icon, a.category, a.image_url, a.summary, a.year FROM tree_members m
           JOIN articles a ON a.id = m.article_id WHERE m.tree_id = ?""", (tid,)).fetchall()
    ids = {p["id"] for p in people}
    rels = []
    if ids:
        marks = ",".join("?" * len(ids))
        rels = db.execute(
            f"""SELECT a_id, b_id, kind FROM relations WHERE world_id = ? AND kind IN ({",".join("?" * len(FAMILY_KINDS))})
                AND a_id IN ({marks}) AND b_id IN ({marks})""", (wid, *FAMILY_KINDS, *ids, *ids)).fetchall()
    return {
        "people": [{"id": p["id"], "title": p["title"], "icon": page_icon(p), "cover": p["image_url"],
                    "summary": p["summary"], "year": p["year"],
                    "url": url_for("pages.view", wid=wid, aid=p["id"])} for p in people],
        "rels": [[r["a_id"], r["b_id"], r["kind"]] for r in rels],
    }


@bp.route("/w/<int:wid>/trees")
@login_required
def trees(wid):
    world = get_world(wid)
    db = get_db()
    all_trees = db.execute(
        """SELECT t.*, (SELECT COUNT(*) FROM tree_members m WHERE m.tree_id = t.id) AS n
           FROM trees t WHERE t.world_id = ? ORDER BY t.id""", (wid,)).fetchall()
    tid = request.args.get("t", type=int) or (all_trees[0]["id"] if all_trees else None)
    current = next((t for t in all_trees if t["id"] == tid), None)
    if tid and current is None:
        abort(404)
    data = _tree_data(wid, current["id"]) if current else {"people": [], "rels": []}
    # personagens primeiro no seletor
    pages = db.execute("""SELECT id, title, icon, category FROM articles WHERE world_id = ?
                          ORDER BY category != 'personagem', title COLLATE NOCASE""", (wid,)).fetchall()
    page_list = [{"id": p["id"], "title": p["title"], "icon": page_icon(p), "person": p["category"] == "personagem"}
                 for p in pages]
    return render_template("world/family.html", world=world, trees=all_trees, current=current, data=data,
                           page_list=page_list)


def _person_for(world, body, field_id="other_id", field_new="new_title"):
    """Página existente (por id) ou um personagem novo criado só com o nome."""
    db = get_db()
    if body.get(field_id):
        return get_page(world, int(body[field_id]))["id"]
    title = str(body.get(field_new) or "").strip()[:200]
    if not title:
        abort(400, "Escolha uma pessoa ou digite um nome.")
    row = db.execute("SELECT id FROM articles WHERE world_id = ? AND lower(title) = lower(?)", (world["id"], title)).fetchone()
    if row:
        return row["id"]
    cur = db.execute("""INSERT INTO articles (world_id, title, category, created_by, updated_by)
                        VALUES (?, ?, 'personagem', ?, ?)""", (world["id"], title, g.user["id"], g.user["id"]))
    touch_world(world["id"])
    return cur.lastrowid


@bp.post("/w/<int:wid>/trees/<int:tid>/edit")
@login_required
def tree_edit(wid, tid):
    """API da árvore (JSON): add | link | unlink | remove. Devolve os dados atualizados."""
    world = get_world(wid)
    _get("trees", wid, tid)
    db = get_db()
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    add_member = lambda pid: db.execute("INSERT OR IGNORE INTO tree_members (tree_id, article_id) VALUES (?, ?)", (tid, pid))
    new_id = None
    if action == "add":
        new_id = _person_for(world, body, "person_id")
        add_member(new_id)
    elif action == "link":
        a = get_page(world, int(body.get("person_id") or 0))["id"]
        kind = body.get("kind")
        if kind not in LINK_KINDS:
            abort(400, "Tipo de laço inválido.")
        b = _person_for(world, body)
        if a == b:
            abort(400, "Escolha outra pessoa.")
        new_id = b
        add_member(a)
        add_member(b)
        # a = pessoa selecionada, b = a outra; LINK_KINDS diz quem fica em cada ponta da relação
        stored, b_first = LINK_KINDS[kind]
        x, y = (b, a) if b_first else (a, b)
        parents_of_a = [r["a_id"] for r in db.execute(
            "SELECT a_id FROM relations WHERE world_id = ? AND kind = 'parent' AND b_id = ?", (wid, a))]
        # irmão(ã) de quem já tem pais na árvore vira filho(a) dos mesmos pais (irmão de verdade)
        if kind == "sibling" and parents_of_a:
            stored = None
        if stored:
            _add_rel(wid, x, y, stored)
        if kind in ("sibling", "twin"):
            for p in parents_of_a:
                _add_rel(wid, p, b, "parent")
                add_member(p)
        # filho(a) de alguém com um único cônjuge na árvore vira filho(a) do casal
        if kind == "child":
            sp = db.execute(
                """SELECT CASE WHEN r.a_id = ? THEN r.b_id ELSE r.a_id END AS s FROM relations r
                   JOIN tree_members m ON m.tree_id = ? AND m.article_id = CASE WHEN r.a_id = ? THEN r.b_id ELSE r.a_id END
                   WHERE r.world_id = ? AND r.kind = 'spouse' AND (r.a_id = ? OR r.b_id = ?)""",
                (a, tid, a, wid, a, a)).fetchall()
            if len(sp) == 1 and sp[0]["s"] != b and not db.execute(
                    "SELECT 1 FROM relations WHERE world_id = ? AND kind = 'parent' AND a_id = ? AND b_id = ?",
                    (wid, sp[0]["s"], b)).fetchone():
                db.execute("INSERT INTO relations (world_id, a_id, b_id, kind) VALUES (?, ?, ?, 'parent')", (wid, sp[0]["s"], b))
    elif action == "unlink":
        a, b, kind = int(body.get("a_id") or 0), int(body.get("b_id") or 0), body.get("kind")
        if kind in SYMMETRIC_KINDS:
            db.execute("""DELETE FROM relations WHERE world_id = ? AND kind = ?
                          AND ((a_id = ? AND b_id = ?) OR (a_id = ? AND b_id = ?))""", (wid, kind, a, b, b, a))
        elif kind in FAMILY_KINDS:
            db.execute("DELETE FROM relations WHERE world_id = ? AND kind = ? AND a_id = ? AND b_id = ?", (wid, kind, a, b))
    elif action == "remove":
        db.execute("DELETE FROM tree_members WHERE tree_id = ? AND article_id = ?", (tid, int(body.get("person_id") or 0)))
    else:
        abort(400, "Ação inválida.")
    db.commit()
    return jsonify(data=_tree_data(wid, tid), new_id=new_id)


@bp.post("/w/<int:wid>/trees")
@login_required
def tree_create(wid):
    get_world(wid)
    db = get_db()
    cur = db.execute("INSERT INTO trees (world_id, name) VALUES (?, ?)",
                     (wid, request.form.get("name", "").strip()[:120] or "Nova árvore"))
    db.commit()
    return redirect(url_for("history.trees", wid=wid, t=cur.lastrowid))


@bp.post("/w/<int:wid>/trees/<int:tid>")
@login_required
def tree_update(wid, tid):
    get_world(wid)
    t = _get("trees", wid, tid)
    db = get_db()
    if request.form.get("delete"):
        db.execute("DELETE FROM trees WHERE id = ?", (tid,))
        db.commit()
        flash(f"Árvore “{t['name']}” apagada (as pessoas e os laços continuam nas páginas).", "success")
        return redirect(url_for("history.trees", wid=wid))
    db.execute("UPDATE trees SET name = ? WHERE id = ?", (request.form.get("name", "").strip()[:120] or t["name"], tid))
    db.commit()
    return redirect(url_for("history.trees", wid=wid, t=tid))


@bp.post("/w/<int:wid>/trees/<int:tid>/members")
@login_required
def tree_member(wid, tid):
    """Adiciona/remove uma pessoa da árvore, ou cria um laço (e põe as duas pessoas na árvore)."""
    world = get_world(wid)
    _get("trees", wid, tid)
    db = get_db()
    back = url_for("history.trees", wid=wid, t=tid)
    a = _int(request.form.get("a_id"))
    if request.form.get("remove") and a:
        db.execute("DELETE FROM tree_members WHERE tree_id = ? AND article_id = ?", (tid, a))
        db.commit()
        return redirect(back)
    if not a:
        flash("Escolha uma pessoa.", "error")
        return redirect(back)
    get_page(world, a)
    db.execute("INSERT OR IGNORE INTO tree_members (tree_id, article_id) VALUES (?, ?)", (tid, a))
    kind, b = request.form.get("kind"), _int(request.form.get("b_id"))
    if kind and b:
        if kind not in ("parent", "child", "spouse") or a == b:
            flash("Escolha duas pessoas diferentes e o tipo de laço.", "error")
            return redirect(back)
        get_page(world, b)
        db.execute("INSERT OR IGNORE INTO tree_members (tree_id, article_id) VALUES (?, ?)", (tid, b))
        x, y = (b, a) if kind == "child" else (a, b)
        kind = "parent" if kind == "child" else kind
        exists = db.execute(
            """SELECT 1 FROM relations WHERE world_id = ? AND kind = ?
               AND ((a_id = ? AND b_id = ?) OR (kind = 'spouse' AND a_id = ? AND b_id = ?))""",
            (wid, kind, x, y, y, x)).fetchone()
        if not exists:
            db.execute("INSERT INTO relations (world_id, a_id, b_id, kind) VALUES (?, ?, ?, ?)", (wid, x, y, kind))
    db.commit()
    return redirect(back)
