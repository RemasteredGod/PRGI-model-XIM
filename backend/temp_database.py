import sqlite3
import os
import json
from datetime import datetime

TEMP_DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'temp.db')
ADMIN_TOKEN  = "prgi_admin_token_2024"

def get_temp_conn():
    conn = sqlite3.connect(TEMP_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_temp_db():
    conn = get_temp_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS temp_titles (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        title               TEXT    NOT NULL,
        verdict             TEXT,
        approval_probability REAL,
        rejection_reasons   TEXT,
        batch_id            TEXT,
        submitted_at        TEXT,
        language            TEXT DEFAULT '',
        state               TEXT DEFAULT '',
        status              TEXT DEFAULT 'pending',
        top_match           TEXT DEFAULT '',
        top_match_score     REAL DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin_settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    )''')
    c.execute("INSERT OR IGNORE INTO admin_settings VALUES ('acceptance_threshold','50')")
    c.execute("INSERT OR IGNORE INTO admin_settings VALUES ('admin_password','prgi@2024')")
    conn.commit()
    conn.close()

def store_batch(batch_id: str, results: list):
    conn = get_temp_conn()
    c = conn.cursor()
    for r in results:
        top_match, top_score = '', 0.0
        for pg in r.get('priority_matches', []):
            if pg.get('matches'):
                top_match  = pg['matches'][0]['existing_title']
                top_score  = pg['matches'][0]['match_percentage']
                break
        c.execute(
            '''INSERT INTO temp_titles
               (title, verdict, approval_probability, rejection_reasons,
                batch_id, submitted_at, language, state, top_match, top_match_score)
               VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (r['title'], r['verdict'], r['approval_probability'],
             json.dumps(r.get('rejection_reasons', [])),
             batch_id, datetime.now().isoformat(),
             r.get('language', ''), r.get('state', ''),
             top_match, top_score)
        )
    conn.commit()
    conn.close()

def get_all_temp():
    conn = get_temp_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM temp_titles ORDER BY submitted_at DESC, id DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_pending_batch(batch_id: str):
    conn = get_temp_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM temp_titles WHERE batch_id=? ORDER BY id", (batch_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def update_status(ids: list, status: str):
    if not ids:
        return
    conn = get_temp_conn()
    c = conn.cursor()
    ph = ','.join('?' * len(ids))
    c.execute(f"UPDATE temp_titles SET status=? WHERE id IN ({ph})", [status] + ids)
    conn.commit()
    conn.close()

def get_approved():
    conn = get_temp_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM temp_titles WHERE status='approved'")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_settings():
    conn = get_temp_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM admin_settings")
    result = {r['key']: r['value'] for r in c.fetchall()}
    conn.close()
    return result

def set_setting(key: str, value: str):
    conn = get_temp_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO admin_settings VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()
