import hmac
import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, g, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from . import constants as C


def _dev_secret(instance_path: str) -> str:
    """Gera (uma vez) uma chave de desenvolvimento para as sessões sobreviverem a reinícios."""
    path = Path(instance_path) / "secret_key"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()


def create_app() -> Flask:
    # .env da raiz do projeto (não depende da pasta atual — no PythonAnywhere o WSGI roda de outro lugar)
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    app = Flask(__name__, instance_relative_config=True)
    production = os.environ.get("APP_ENV") == "production"

    if production:
        # atrás do proxy HTTPS (PythonAnywhere etc.): respeita X-Forwarded-Proto/For/Host,
        # assim url_for(..., _external=True) gera https:// (callback do Google)
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        if not os.environ.get("SECRET_KEY"):
            raise RuntimeError("Defina SECRET_KEY no .env em produção.")
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or _dev_secret(app.instance_path),
        DATABASE=os.environ.get("DATABASE_PATH") or os.path.join(app.instance_path, "lore.db"),
        UPLOAD_DIR=os.environ.get("UPLOAD_DIR") or os.path.join(app.instance_path, "uploads"),
        MAX_CONTENT_LENGTH=40 * 1024 * 1024,  # 40 MB por requisição
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=production,
        PREFERRED_URL_SCHEME="https" if production else "http",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        GOOGLE_CLIENT_ID=os.environ.get("GOOGLE_CLIENT_ID"),
        GOOGLE_CLIENT_SECRET=os.environ.get("GOOGLE_CLIENT_SECRET"),
    )
    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)

    # mantém a ordem das chaves (ex.: cores dos cards) no jsonify e no filtro |tojson
    app.json.sort_keys = False
    app.jinja_env.policies["json.dumps_kwargs"] = {"sort_keys": False}

    from . import auth, boards, db, files, history, maps, pages, worlds

    db.init_app(app)
    auth.init_app(app)
    for mod in (auth, worlds, pages, history, boards, maps, files):
        app.register_blueprint(mod.bp)

    # --- CSRF simples: token na sessão, enviado em formulários e no header dos fetch() ---
    def csrf_token() -> str:
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return session["csrf"]

    @app.before_request
    def csrf_protect():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
            token = session.get("csrf", "")
            if not token or not hmac.compare_digest(token, sent):
                abort(400, "Token CSRF inválido. Recarregue a página e tente de novo.")

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    def ui_prefs():
        """Tema e cor de destaque: do usuário logado, senão do cookie (visitantes)."""
        if g.get("user"):
            theme, accent = g.user["theme"], g.user["accent"]
        else:
            theme, accent = request.cookies.get("theme"), request.cookies.get("accent")
        return (theme if theme in C.THEMES else "dark", accent if accent in C.ACCENTS else "yellow")

    app.jinja_env.globals.update(
        csrf_token=csrf_token,
        ui_prefs=ui_prefs,
        SITE_NAME=C.SITE_NAME,
        CATEGORIES=C.CATEGORIES,
        CATEGORY_MAP=C.CATEGORY_MAP,
        CARD_COLORS=C.CARD_COLORS,
        ACCENTS=C.ACCENTS,
        ACCENT_SWATCH=C.ACCENT_SWATCH,
        PIN_COLORS=C.PIN_COLORS,
    )

    @app.template_filter("filesize")
    def filesize(n):
        n = n or 0
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024 or unit == "GB":
                return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            n /= 1024

    @app.template_filter("year")
    def year_fmt(y):
        return "" if y is None else str(y)

    @app.route("/")
    def index():
        if g.user:
            return redirect(url_for("worlds.list_worlds"))
        return render_template("index.html")

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, message="Esta página se perdeu nas brumas."), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403, message="Só o dono do mundo pode fazer isso."), 403

    @app.errorhandler(413)
    def too_large(e):
        return render_template("error.html", code=413, message="Arquivo grande demais (máximo 40 MB)."), 413

    @app.errorhandler(400)
    def bad_request(e):
        if request.accept_mimetypes.best == "application/json" or request.is_json:
            return {"error": e.description}, 400
        return render_template("error.html", code=400, message=e.description), 400

    return app
