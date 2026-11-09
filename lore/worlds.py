"""Mundos: lista, criação, página inicial, configurações e colaboradores."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .access import get_world
from .auth import EMAIL_RE, login_required
from .db import get_db
from .files import UploadError, save_upload
from .icons import icon_from_form

bp = Blueprint("worlds", __name__)


@bp.route("/worlds")
@login_required
def list_worlds():
    worlds = get_db().execute(
        """SELECT w.*, m.role, o.name AS owner_name,
                  (SELECT COUNT(*) FROM articles a WHERE a.world_id = w.id) AS n_pages,
                  (SELECT COUNT(*) FROM world_members x WHERE x.world_id = w.id) AS n_members
           FROM worlds w
           JOIN world_members m ON m.world_id = w.id AND m.user_id = ? AND m.role IN ('owner', 'editor')
           JOIN users o ON o.id = w.user_id
           WHERE w.party_of IS NULL
           ORDER BY w.updated_at DESC""",
        (g.user["id"],),
    ).fetchall()
    return render_template("worlds.html", worlds=worlds)


@bp.post("/worlds")
@login_required
def create_world():
    name = request.form.get("name", "").strip()[:120]
    if not name:
        flash("Dê um nome ao seu mundo.", "error")
        return redirect(url_for("worlds.list_worlds"))
    db = get_db()
    cur = db.execute(
        "INSERT INTO worlds (user_id, name, description) VALUES (?, ?, ?)",
        (g.user["id"], name, request.form.get("description", "").strip()[:2000]),
    )
    wid = cur.lastrowid
    db.execute("INSERT INTO world_members (world_id, user_id, role) VALUES (?, ?, 'owner')", (wid, g.user["id"]))
    try:  # o mundo precisa existir antes de guardar uma imagem de ícone no acervo dele
        db.execute("UPDATE worlds SET icon = ? WHERE id = ?", (icon_from_form(wid), wid))
    except UploadError as e:
        flash(f"Mundo criado, mas o ícone não foi salvo: {e}", "error")
    db.execute("INSERT INTO boards (world_id, name) VALUES (?, ?)", (wid, "Mapa mental principal"))
    db.commit()
    return redirect(url_for("worlds.world_home", wid=wid))


@bp.route("/w/<int:wid>")
@login_required
def world_home(wid):
    world = get_world(wid)
    db = get_db()
    recent = db.execute(
        """SELECT a.*, u.name AS editor FROM articles a LEFT JOIN users u ON u.id = a.updated_by
           WHERE a.world_id = ? ORDER BY a.updated_at DESC LIMIT 8""", (wid,)).fetchall()
    members = db.execute(
        """SELECT u.name, u.avatar_url FROM world_members m JOIN users u ON u.id = m.user_id
           WHERE m.world_id = ? ORDER BY m.role DESC, u.name LIMIT 8""", (wid,)).fetchall()
    n_events = db.execute("SELECT COUNT(*) FROM articles WHERE world_id = ? AND year IS NOT NULL", (wid,)).fetchone()[0]
    n_files = db.execute("SELECT COUNT(*) FROM files WHERE world_id = ?", (wid,)).fetchone()[0]
    n_trees = db.execute("SELECT COUNT(*) FROM trees WHERE world_id = ?", (wid,)).fetchone()[0]
    return render_template("world/home.html", world=world, recent=recent, members=members,
                           n_events=n_events, n_files=n_files, n_trees=n_trees)


@bp.route("/w/<int:wid>/settings", methods=["GET", "POST"])
@login_required
def world_settings(wid):
    world = get_world(wid, owner_only=True)
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:120]
        if not name:
            flash("O nome não pode ficar vazio.", "error")
            return redirect(url_for("worlds.world_settings", wid=wid))
        cover = world["cover_url"]
        try:
            icon = icon_from_form(wid)
            if request.files.get("cover") and request.files["cover"].filename:
                cover = url_for("files.serve", fid=save_upload(wid, request.files["cover"], images_only=True))
        except UploadError as e:
            flash(str(e), "error")
            return redirect(url_for("worlds.world_settings", wid=wid))
        if request.form.get("remove_cover"):
            cover = ""
        try:
            pos = max(0, min(100, int(request.form.get("cover_pos", 50))))
        except ValueError:
            pos = 50
        db = get_db()
        db.execute(
            """UPDATE worlds SET name = ?, description = ?, icon = ?, cover_url = ?, cover_pos = ?,
               updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (name, request.form.get("description", "").strip()[:2000],
             icon, cover, pos, wid),
        )
        db.commit()
        flash("Mundo atualizado.", "success")
        return redirect(url_for("worlds.world_home", wid=wid))
    return render_template("world/settings.html", world=world)


@bp.post("/w/<int:wid>/delete")
@login_required
def world_delete(wid):
    world = get_world(wid, owner_only=True)
    if request.form.get("confirm", "").strip() != world["name"]:
        flash("Digite o nome do mundo exatamente para confirmar.", "error")
        return redirect(url_for("worlds.world_settings", wid=wid))
    db = get_db()
    db.execute("DELETE FROM worlds WHERE id = ?", (wid,))
    db.commit()
    flash(f"“{world['name']}” foi apagado.", "success")
    return redirect(url_for("worlds.list_worlds"))


# --------------------------------------------------------------------------- colaboradores

@bp.route("/w/<int:wid>/members")
@login_required
def members(wid):
    world = get_world(wid)
    db = get_db()
    rows = db.execute(
        """SELECT u.id, u.name, u.email, u.avatar_url, m.role, m.created_at FROM world_members m
           JOIN users u ON u.id = m.user_id WHERE m.world_id = ?
           ORDER BY m.role DESC, u.name COLLATE NOCASE""", (wid,)).fetchall()
    invites = db.execute("SELECT * FROM world_invites WHERE world_id = ? ORDER BY created_at", (wid,)).fetchall()
    return render_template("world/members.html", world=world, members=rows, invites=invites)


@bp.post("/w/<int:wid>/members")
@login_required
def invite(wid):
    get_world(wid, owner_only=True)
    email = request.form.get("email", "").strip().lower()
    if not EMAIL_RE.match(email):
        flash("E-mail inválido.", "error")
        return redirect(url_for("worlds.members", wid=wid))
    db = get_db()
    user = db.execute("SELECT id, name FROM users WHERE email = ?", (email,)).fetchone()
    if user:
        db.execute("INSERT OR IGNORE INTO world_members (world_id, user_id, role) VALUES (?, ?, 'editor')",
                   (wid, user["id"]))
        db.execute("UPDATE world_members SET role = 'editor' WHERE world_id = ? AND user_id = ? AND role = 'player'",
                   (wid, user["id"]))   # antigo jogador da Mesa (removida) vira colaborador
        flash(f"{user['name']} agora tem acesso a este mundo.", "success")
    else:
        db.execute("INSERT OR IGNORE INTO world_invites (world_id, email, invited_by) VALUES (?, ?, ?)",
                   (wid, email, g.user["id"]))
        flash(f"Convite guardado: assim que {email} criar a conta (ou entrar com Google), o mundo aparece para essa pessoa.", "success")
    db.commit()
    return redirect(url_for("worlds.members", wid=wid))


@bp.post("/w/<int:wid>/members/<int:uid>/remove")
@login_required
def remove_member(wid, uid):
    world = get_world(wid)
    leaving = uid == g.user["id"]
    if not leaving and world["role"] != "owner":
        abort(403)
    if uid == world["user_id"]:
        flash("O dono não pode sair do próprio mundo. Apague o mundo nas configurações.", "error")
        return redirect(url_for("worlds.members", wid=wid))
    db = get_db()
    db.execute("DELETE FROM world_members WHERE world_id = ? AND user_id = ? AND role != 'owner'", (wid, uid))
    db.commit()
    if leaving:
        flash(f"Você saiu de “{world['name']}”.", "success")
        return redirect(url_for("worlds.list_worlds"))
    flash("Acesso removido.", "success")
    return redirect(url_for("worlds.members", wid=wid))


@bp.post("/w/<int:wid>/invites/remove")
@login_required
def remove_invite(wid):
    get_world(wid, owner_only=True)
    db = get_db()
    db.execute("DELETE FROM world_invites WHERE world_id = ? AND email = ?", (wid, request.form.get("email", "")))
    db.commit()
    return redirect(url_for("worlds.members", wid=wid))
