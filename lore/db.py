import os
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    password_hash TEXT,
    google_id     TEXT UNIQUE,
    avatar_url    TEXT,
    theme         TEXT NOT NULL DEFAULT 'dark',
    accent        TEXT NOT NULL DEFAULT 'yellow',
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS worlds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,  -- dono
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    color       TEXT NOT NULL DEFAULT 'amber',
    icon        TEXT NOT NULL DEFAULT '',
    cover_url   TEXT NOT NULL DEFAULT '',
    cover_pos   INTEGER NOT NULL DEFAULT 50,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Quem tem acesso ao mundo. role: 'owner' | 'editor'
CREATE TABLE IF NOT EXISTS world_members (
    world_id   INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       TEXT NOT NULL DEFAULT 'editor',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (world_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_members_user ON world_members(user_id);

-- Convites para e-mails que ainda não têm conta: viram membros ao entrar
CREATE TABLE IF NOT EXISTS world_invites (
    world_id   INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    email      TEXT NOT NULL,
    invited_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (world_id, email)
);

CREATE TABLE IF NOT EXISTS files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id      INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    user_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    stored_name   TEXT NOT NULL,
    original_name TEXT NOT NULL,
    mime          TEXT NOT NULL,
    size          INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_files_world ON files(world_id);

-- Páginas (artigos) com capa, ícone e subpáginas
CREATE TABLE IF NOT EXISTS articles (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id   INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    parent_id  INTEGER REFERENCES articles(id) ON DELETE SET NULL,
    title      TEXT NOT NULL,
    icon       TEXT NOT NULL DEFAULT '',
    category   TEXT NOT NULL DEFAULT 'nota',
    summary    TEXT NOT NULL DEFAULT '',
    content    TEXT NOT NULL DEFAULT '',
    image_url  TEXT NOT NULL DEFAULT '',       -- capa
    cover_pos  INTEGER NOT NULL DEFAULT 50,
    year       INTEGER,                        -- linha do tempo (pode ser negativo)
    date_label TEXT NOT NULL DEFAULT '',
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_articles_world ON articles(world_id, category);

-- Relações entre páginas (0..N). kind em constants.RELATION_KINDS
CREATE TABLE IF NOT EXISTS relations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id   INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    a_id       INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    b_id       INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    label      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_relations_a ON relations(a_id);
CREATE INDEX IF NOT EXISTS idx_relations_b ON relations(b_id);

-- Mapas mentais
CREATE TABLE IF NOT EXISTS boards (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id   INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_boards_world ON boards(world_id);

-- kind: note | article | image | file
CREATE TABLE IF NOT EXISTS cards (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id   INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL DEFAULT 'note',
    title      TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL DEFAULT '',
    color      TEXT NOT NULL DEFAULT 'yellow',
    x          INTEGER NOT NULL DEFAULT 0,
    y          INTEGER NOT NULL DEFAULT 0,
    w          INTEGER NOT NULL DEFAULT 240,
    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    file_id    INTEGER REFERENCES files(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cards_board ON cards(board_id);

CREATE TABLE IF NOT EXISTS board_links (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id   INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    from_card  INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    to_card    INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    label      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_links_board ON board_links(board_id);

-- Mapas (imagem) com tokens e marcadores
CREATE TABLE IF NOT EXISTS maps (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id   INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    file_id    INTEGER REFERENCES files(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_maps_world ON maps(world_id);

-- kind: pin | token. x/y em fração (0..1) da imagem
CREATE TABLE IF NOT EXISTS map_pins (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    map_id        INTEGER NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL DEFAULT 'pin',
    x             REAL NOT NULL DEFAULT 0.5,
    y             REAL NOT NULL DEFAULT 0.5,
    label         TEXT NOT NULL DEFAULT '',
    note          TEXT NOT NULL DEFAULT '',
    color         TEXT NOT NULL DEFAULT '#f59e0b',
    article_id    INTEGER REFERENCES articles(id) ON DELETE SET NULL,
    file_id       INTEGER REFERENCES files(id) ON DELETE SET NULL,   -- livro/arquivo anexado
    image_file_id INTEGER REFERENCES files(id) ON DELETE SET NULL,   -- retrato do token
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pins_map ON map_pins(map_id);

-- Várias árvores genealógicas: cada uma é um conjunto de pessoas (as relações são do mundo)
CREATE TABLE IF NOT EXISTS trees (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id   INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tree_members (
    tree_id    INTEGER NOT NULL REFERENCES trees(id) ON DELETE CASCADE,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    PRIMARY KEY (tree_id, article_id)
);

-- Várias linhas do tempo: uma página (com ano) pode estar em várias
CREATE TABLE IF NOT EXISTS timelines (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id   INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    color      TEXT NOT NULL DEFAULT '#f59e0b',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS timeline_pages (
    timeline_id INTEGER NOT NULL REFERENCES timelines(id) ON DELETE CASCADE,
    article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    PRIMARY KEY (timeline_id, article_id)
);
"""

# Colunas adicionadas depois da primeira versão (bancos antigos recebem via ALTER TABLE)
_ADDED_COLUMNS = {
    "users": {"theme": "TEXT NOT NULL DEFAULT 'dark'", "accent": "TEXT NOT NULL DEFAULT 'yellow'"},
    "worlds": {"icon": "TEXT NOT NULL DEFAULT ''", "cover_url": "TEXT NOT NULL DEFAULT ''",
               "cover_pos": "INTEGER NOT NULL DEFAULT 50"},
    "articles": {"parent_id": "INTEGER REFERENCES articles(id) ON DELETE SET NULL",
                 "icon": "TEXT NOT NULL DEFAULT ''", "cover_pos": "INTEGER NOT NULL DEFAULT 50",
                 "year": "INTEGER", "date_label": "TEXT NOT NULL DEFAULT ''",
                 "created_by": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
                 "updated_by": "INTEGER REFERENCES users(id) ON DELETE SET NULL"},
    "cards": {"file_id": "INTEGER REFERENCES files(id) ON DELETE CASCADE"},
    # mapa editável: grade, terrenos, paredes e objetos (JSON) + versão p/ edição simultânea
    "maps": {"data": "TEXT NOT NULL DEFAULT '{}'", "version": "INTEGER NOT NULL DEFAULT 0",
             "thumb": "TEXT NOT NULL DEFAULT ''"},
}


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _migrate(db):
    for table, cols in _ADDED_COLUMNS.items():
        existing = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
        for col, ddl in cols.items():
            if col not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    # Todo mundo antigo ganha o dono como membro
    db.execute("""INSERT OR IGNORE INTO world_members (world_id, user_id, role)
                  SELECT id, user_id, 'owner' FROM worlds""")
    # o antigo ícone padrão (emoji do globo) vira "sem ícone" = ícone pixel padrão do site
    db.execute("UPDATE worlds SET icon = '' WHERE icon IN ('🌍', '🌍️')")

    if db.execute("PRAGMA user_version").fetchone()[0] < 2:
        # v2: dados antigos viram uma "Árvore principal" e uma "Linha principal" por mundo
        for (wid,) in db.execute("SELECT DISTINCT world_id FROM relations WHERE kind IN ('parent', 'spouse')").fetchall():
            tid = db.execute("INSERT INTO trees (world_id, name) VALUES (?, 'Árvore principal')", (wid,)).lastrowid
            db.execute("""INSERT OR IGNORE INTO tree_members (tree_id, article_id)
                          SELECT ?, a_id FROM relations WHERE world_id = ? AND kind IN ('parent', 'spouse')
                          UNION SELECT ?, b_id FROM relations WHERE world_id = ? AND kind IN ('parent', 'spouse')""",
                       (tid, wid, tid, wid))
        for (wid,) in db.execute("SELECT DISTINCT world_id FROM articles WHERE year IS NOT NULL").fetchall():
            lid = db.execute("INSERT INTO timelines (world_id, name) VALUES (?, 'Linha principal')", (wid,)).lastrowid
            db.execute("INSERT INTO timeline_pages (timeline_id, article_id) SELECT ?, id FROM articles WHERE world_id = ? AND year IS NOT NULL",
                       (lid, wid))
        db.execute("PRAGMA user_version = 2")


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        db = get_db()
        # WAL é ótimo localmente, mas não funciona bem em disco de rede (PythonAnywhere): use DELETE lá
        mode = os.environ.get("SQLITE_JOURNAL_MODE", "WAL").upper()
        if mode not in ("WAL", "DELETE", "TRUNCATE", "PERSIST"):
            mode = "WAL"
        db.execute(f"PRAGMA journal_mode = {mode}")
        db.executescript(SCHEMA)
        _migrate(db)
        db.commit()
