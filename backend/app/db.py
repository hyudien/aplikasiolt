import contextlib
import os
import sqlite3
import time

def db_path():
    return os.environ.get("OLT_APP_DB", "./data/olt.db")


@contextlib.contextmanager
def connect():
    path = db_path()
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    new = not os.path.exists(path)
    conn = sqlite3.connect(path)
    if new:
        os.chmod(path, 0o600)  # holds the OLT password
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1), host TEXT, port INTEGER, username TEXT, password TEXT);
    CREATE TABLE IF NOT EXISTS onts(ont TEXT PRIMARY KEY, pon TEXT, name TEXT, sn TEXT, pppoe_user TEXT,
        phase TEXT, admin_state TEXT, updated_at REAL);
    CREATE INDEX IF NOT EXISTS onts_pon ON onts(pon);
    """)
    try:
        with conn:  # commit / rollback
            yield conn
    finally:
        conn.close()


def get_settings():
    with connect() as c:
        r = c.execute("SELECT * FROM settings WHERE id=1").fetchone()
    return dict(r) if r else None


def save_settings(host, port, username, password):
    with connect() as c:
        c.execute("INSERT OR REPLACE INTO settings VALUES(1,?,?,?,?)", (host, port, username, password))


def replace_onts(rows):
    now = time.time()
    with connect() as c:
        c.execute("DELETE FROM onts")
        c.executemany("INSERT INTO onts VALUES(:ont,:pon,:name,:sn,:pppoe_user,:phase,:admin_state,:ts)",
                      [{**r, "ts": now} for r in rows])


def upsert_ont(row):
    with connect() as c:
        c.execute("INSERT OR REPLACE INTO onts VALUES(:ont,:pon,:name,:sn,:pppoe_user,:phase,:admin_state,:ts)",
                  {"name": "", "sn": "", "pppoe_user": "", "phase": "", "admin_state": "", **row, "ts": time.time()})


def delete_ont(ont):
    with connect() as c:
        c.execute("DELETE FROM onts WHERE ont=?", (ont,))


def list_onts(pon=None):
    with connect() as c:
        if pon:
            rows = c.execute("SELECT * FROM onts WHERE pon=? ORDER BY ont", (pon,))
        else:
            rows = c.execute("SELECT * FROM onts ORDER BY ont")
        return [dict(r) for r in rows]


def search(q, limit=50):
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with connect() as c:
        rows = c.execute("SELECT * FROM onts WHERE name LIKE ? ESCAPE '\\' OR sn LIKE ? ESCAPE '\\' "
                         "OR pppoe_user LIKE ? ESCAPE '\\' ORDER BY name LIMIT ?", (like, like, like, limit))
        return [dict(r) for r in rows]


def set_pppoe_user(ont, user):
    with connect() as c:
        c.execute("UPDATE onts SET pppoe_user=? WHERE ont=?", (user, ont))
