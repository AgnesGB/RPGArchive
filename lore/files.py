"""Uploads (imagens e arquivos de livros) e o Acervo do mundo."""
import os
import secrets
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template,
                   request, send_file, url_for)

from .access import get_file, get_world
from .auth import login_required
from .constants import DOC_TYPES, IMAGE_TYPES, UPLOAD_TYPES
from .db import get_db

bp = Blueprint("files", __name__)


class UploadError(ValueError):
    pass


def _ext(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def is_image(mime):
    return mime.startswith("image/")


def save_upload(world_id, fs, images_only=False):
    """Salva um FileStorage do Flask e devolve o id na tabela files."""
    if not fs or not fs.filename:
        raise UploadError("Nenhum arquivo enviado.")
    ext = _ext(fs.filename)
    allowed = IMAGE_TYPES if images_only else UPLOAD_TYPES
    if ext not in allowed:
        kinds = "imagens (PNG, JPG, GIF, WEBP)" if images_only else "imagens, áudio (MP3, OGG, WAV, M4A), vídeo (MP4, WEBM), PDF, EPUB, TXT, MD, DOCX, ODT ou ZIP"
        raise UploadError(f"Tipo de arquivo não suportado: .{ext or '?'} — envie {kinds}.")
    folder = Path(current_app.config["UPLOAD_DIR"]) / str(world_id)
    folder.mkdir(parents=True, exist_ok=True)
    stored = f"{secrets.token_hex(16)}.{ext}"
    path = folder / stored
    fs.save(path)
    original = os.path.basename(fs.filename)[:200] or stored
    db = get_db()
    cur = db.execute(
        "INSERT INTO files (world_id, user_id, stored_name, original_name, mime, size) VALUES (?, ?, ?, ?, ?, ?)",
        (world_id, g.user["id"], stored, original, allowed[ext], path.stat().st_size),
    )
    db.commit()
    return cur.lastrowid


def file_dict(f):
    return {
        "id": f["id"], "name": f["original_name"], "mime": f["mime"], "size": f["size"],
        "is_image": is_image(f["mime"]), "url": url_for("files.serve", fid=f["id"]),
    }


@bp.route("/f/<int:fid>")
@login_required
def serve(fid):
    db = get_db()
    f = db.execute(
        """SELECT f.* FROM files f JOIN world_members m ON m.world_id = f.world_id AND m.user_id = ?
                                    AND m.role IN ('owner', 'editor')
           WHERE f.id = ?""", (g.user["id"], fid)).fetchone()
    if f is None:
        abort(404)
    path = Path(current_app.config["UPLOAD_DIR"]) / str(f["world_id"]) / f["stored_name"]
    if not path.exists():
        abort(404)
    inline = (is_image(f["mime"]) or f["mime"].startswith(("audio/", "video/"))
              or f["mime"] in ("application/pdf", "text/plain", "text/markdown"))
    resp = send_file(path, mimetype=f["mime"], as_attachment=not inline,
                     download_name=f["original_name"], max_age=60 * 60 * 24 * 30)
    resp.headers["Cache-Control"] = "private, max-age=2592000"
    return resp


@bp.route("/w/<int:wid>/files")
@login_required
def library(wid):
    world = get_world(wid)
    kind = request.args.get("kind")
    rows = get_db().execute(
        """SELECT f.*, u.name AS uploader FROM files f LEFT JOIN users u ON u.id = f.user_id
           WHERE f.world_id = ? ORDER BY f.created_at DESC, f.id DESC""", (wid,)).fetchall()
    if kind == "images":
        rows = [r for r in rows if is_image(r["mime"])]
    elif kind == "docs":
        rows = [r for r in rows if not is_image(r["mime"])]
    return render_template("world/files.html", world=world, files=rows, kind=kind, is_image=is_image)


@bp.post("/w/<int:wid>/files")
@login_required
def upload(wid):
    """Upload pelo Acervo (form) ou via fetch (JSON de volta)."""
    get_world(wid)
    wants_json = request.accept_mimetypes.best == "application/json"
    images_only = request.args.get("images") == "1"
    saved, errors = [], []
    for fs in request.files.getlist("files"):
        try:
            saved.append(save_upload(wid, fs, images_only=images_only))
        except UploadError as e:
            errors.append(str(e))
    if wants_json:
        rows = [get_db().execute("SELECT * FROM files WHERE id = ?", (i,)).fetchone() for i in saved]
        return jsonify(files=[file_dict(r) for r in rows], errors=errors), (201 if saved else 400)
    for e in errors:
        flash(e, "error")
    if saved:
        flash(f"{len(saved)} arquivo(s) adicionados ao acervo.", "success")
    return redirect(url_for("files.library", wid=wid))


@bp.post("/w/<int:wid>/files/<int:fid>/delete")
@login_required
def delete(wid, fid):
    world = get_world(wid)
    f = get_file(world, fid)
    db = get_db()
    # Capas que apontavam para o arquivo deixam de existir
    url = url_for("files.serve", fid=fid)
    db.execute("UPDATE articles SET image_url = '' WHERE world_id = ? AND image_url = ?", (wid, url))
    db.execute("UPDATE worlds SET cover_url = '' WHERE id = ? AND cover_url = ?", (wid, url))
    db.execute("DELETE FROM files WHERE id = ?", (fid,))
    db.commit()
    path = Path(current_app.config["UPLOAD_DIR"]) / str(wid) / f["stored_name"]
    path.unlink(missing_ok=True)
    flash(f"“{f['original_name']}” removido do acervo.", "success")
    back = request.referrer or ""
    return redirect(back if back.startswith(request.host_url) else url_for("files.library", wid=wid))


@bp.route("/w/<int:wid>/files.json")
@login_required
def list_json(wid):
    get_world(wid)
    rows = get_db().execute("SELECT * FROM files WHERE world_id = ? ORDER BY id DESC", (wid,)).fetchall()
    return jsonify([file_dict(r) for r in rows])


__all__ = ["save_upload", "UploadError", "file_dict", "is_image", "DOC_TYPES"]
