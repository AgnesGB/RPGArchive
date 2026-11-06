import functools
import re

from authlib.integrations.flask_client import OAuth, OAuthError
from flask import (Blueprint, current_app, flash, g, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__, url_prefix="/auth")
oauth = OAuth()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def init_app(app):
    oauth.init_app(app)
    enabled = bool(app.config["GOOGLE_CLIENT_ID"] and app.config["GOOGLE_CLIENT_SECRET"])
    if enabled:
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    app.config["GOOGLE_ENABLED"] = enabled
    app.jinja_env.globals["google_enabled"] = enabled


@bp.before_app_request
def load_user():
    uid = session.get("uid")
    g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone() if uid else None


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


def _safe_next(target):
    if target and target.startswith("/") and not target.startswith(("//", "/\\")):
        return target
    return None


def claim_invites(user_id):
    """Convites pendentes para o e-mail do usuário viram acesso aos mundos."""
    db = get_db()
    email = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()["email"]
    db.execute("""INSERT OR IGNORE INTO world_members (world_id, user_id, role)
                  SELECT world_id, ?, 'editor' FROM world_invites WHERE email = ?""", (user_id, email))
    db.execute("DELETE FROM world_invites WHERE email = ?", (email,))
    db.commit()


def _login(user_id, next_url=None):
    claim_invites(user_id)
    session.clear()
    session["uid"] = user_id
    session.permanent = True
    return redirect(_safe_next(next_url) or url_for("worlds.list_worlds"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("worlds.list_worlds"))
    form = {"name": "", "email": ""}
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        form = {"name": name, "email": email}
        db = get_db()
        error = None
        if not name:
            error = "Diga como devemos te chamar."
        elif not EMAIL_RE.match(email):
            error = "E-mail inválido."
        elif len(password) < 8:
            error = "A senha precisa ter pelo menos 8 caracteres."
        elif db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            error = "Já existe uma conta com esse e-mail. Tente entrar."
        if error:
            flash(error, "error")
        else:
            cur = db.execute(
                "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
                (email, name, generate_password_hash(password)),
            )
            db.commit()
            flash(f"Bem-vindo(a), {name}! Crie seu primeiro mundo.", "success")
            return _login(cur.lastrowid, request.args.get("next"))
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("worlds.list_worlds"))
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and not user["password_hash"]:
            flash("Essa conta foi criada com o Google. Use o botão “Entrar com Google”.", "error")
        elif user and check_password_hash(user["password_hash"], password):
            return _login(user["id"], request.args.get("next"))
        else:
            flash("E-mail ou senha incorretos.", "error")
    return render_template("auth/login.html", email=email)


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@bp.post("/prefs")
def prefs():
    """Salva modo claro/escuro e cor de destaque (no usuário e num cookie para visitantes)."""
    from .constants import ACCENTS, THEMES
    data = request.get_json(silent=True) or {}
    theme = data.get("theme") if data.get("theme") in THEMES else None
    accent = data.get("accent") if data.get("accent") in ACCENTS else None
    if g.user:
        db = get_db()
        if theme:
            db.execute("UPDATE users SET theme = ? WHERE id = ?", (theme, g.user["id"]))
        if accent:
            db.execute("UPDATE users SET accent = ? WHERE id = ?", (accent, g.user["id"]))
        db.commit()
    resp = jsonify(ok=True)
    for key, val in (("theme", theme), ("accent", accent)):
        if val:
            resp.set_cookie(key, val, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return resp


@bp.route("/google")
def google_login():
    if not current_app.config["GOOGLE_ENABLED"]:
        flash("Login com Google não está configurado (veja o .env).", "error")
        return redirect(url_for("auth.login"))
    session["after_login"] = _safe_next(request.args.get("next"))
    return oauth.google.authorize_redirect(url_for("auth.google_callback", _external=True))


@bp.route("/google/callback")
def google_callback():
    if not current_app.config["GOOGLE_ENABLED"]:
        return redirect(url_for("auth.login"))
    try:
        token = oauth.google.authorize_access_token()
    except OAuthError as e:
        flash(f"Não foi possível entrar com o Google ({e.error}).", "error")
        return redirect(url_for("auth.login"))

    info = token.get("userinfo") or oauth.google.userinfo(token=token)
    sub = info["sub"]
    email = (info.get("email") or "").lower()
    name = info.get("name") or email.split("@")[0] or "Aventureiro"
    picture = info.get("picture")

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE google_id = ?", (sub,)).fetchone()
    if user is None and email and info.get("email_verified"):
        # Conta já existente com o mesmo e-mail (verificado pelo Google): vincula
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            db.execute("UPDATE users SET google_id = ?, avatar_url = COALESCE(avatar_url, ?) WHERE id = ?",
                       (sub, picture, user["id"]))
    if user is None:
        if not email:
            flash("O Google não forneceu um e-mail para essa conta.", "error")
            return redirect(url_for("auth.login"))
        cur = db.execute(
            "INSERT INTO users (email, name, google_id, avatar_url) VALUES (?, ?, ?, ?)",
            (email, name, sub, picture),
        )
        user_id = cur.lastrowid
    else:
        user_id = user["id"]
    db.commit()
    return _login(user_id, session.get("after_login"))


# ------------------------------------------------------------------ perfil
AVATAR_DIR = "avatars"


def _avatar_path(name):
    from pathlib import Path
    return Path(current_app.config["UPLOAD_DIR"]) / AVATAR_DIR / name


def _delete_local_avatar(url):
    prefix = url_for("auth.avatar", name="")
    if url and url.startswith(prefix):
        _avatar_path(url[len(prefix):]).unlink(missing_ok=True)


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    import secrets
    from .constants import IMAGE_TYPES
    if request.method == "POST":
        db = get_db()
        name = request.form.get("name", "").strip()[:80]
        if not name:
            flash("O nome não pode ficar vazio.", "error")
            return redirect(url_for("auth.profile"))
        avatar = g.user["avatar_url"]
        fs = request.files.get("avatar")
        if fs and fs.filename:
            ext = fs.filename.rsplit(".", 1)[-1].lower() if "." in fs.filename else ""
            if ext not in IMAGE_TYPES:
                flash("Envie uma imagem (PNG, JPG, GIF, WEBP ou AVIF).", "error")
                return redirect(url_for("auth.profile"))
            stored = f"{g.user['id']}_{secrets.token_hex(8)}.{ext}"
            path = _avatar_path(stored)
            path.parent.mkdir(parents=True, exist_ok=True)
            fs.save(path)
            _delete_local_avatar(avatar)
            avatar = url_for("auth.avatar", name=stored)
        elif request.form.get("remove_avatar"):
            _delete_local_avatar(avatar)
            avatar = None
        db.execute("UPDATE users SET name = ?, avatar_url = ? WHERE id = ?", (name, avatar, g.user["id"]))
        db.commit()
        flash("Perfil atualizado.", "success")
        return redirect(url_for("auth.profile"))
    return render_template("auth/profile.html")


@bp.route("/avatar/<name>")
@login_required
def avatar(name):
    from flask import abort, send_file
    if "/" in name or "\\" in name or name.startswith("."):
        abort(404)
    path = _avatar_path(name)
    if not path.is_file():
        abort(404)
    resp = send_file(path, max_age=60 * 60 * 24 * 30)
    resp.headers["Cache-Control"] = "private, max-age=2592000"
    return resp
