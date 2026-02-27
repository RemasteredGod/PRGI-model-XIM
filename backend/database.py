import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'prgi_titles.db')

TITLES_CACHE_LIST = []
TITLES_CACHE_SET = set()
PHONETIC_CACHE = {}      # title -> (soundex_frozenset, nysiis_frozenset)
SOUNDEX_INDEX  = {}      # soundex_code -> set of titles  (reverse index for fast lookup)
NYSIIS_INDEX   = {}      # nysiis_code  -> set of titles
WORD_INDEX     = {}      # word (uppercase) -> set of titles containing that word
DISALLOWED_WORDS_CACHE = []  # in-memory list of disallowed words (uppercase)

def get_connection():
    return sqlite3.connect(DB_PATH)

def load_titles_into_memory():
    global TITLES_CACHE_LIST, TITLES_CACHE_SET
    if not os.path.exists(DB_PATH):
        return

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT title FROM titles')
        titles_raw = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        merged_set = {str(t).strip().upper() for t in titles_raw if t and str(t).strip()}
        TITLES_CACHE_SET = merged_set
        TITLES_CACHE_LIST = list(merged_set)
        print(f"Loaded {len(titles_raw):,} titles from prgi_titles.db")
        print(f"After deduplication: {len(TITLES_CACHE_SET):,} unique titles ready")

        # Precompute phonetic codes + build reverse index (O(1) candidate lookup)
        import jellyfish
        PHONETIC_CACHE.clear()
        SOUNDEX_INDEX.clear()
        NYSIIS_INDEX.clear()
        for t in TITLES_CACHE_LIST:
            words = t.split()  # already uppercase
            sx = frozenset(jellyfish.soundex(w) for w in words if w)
            ny = frozenset(jellyfish.nysiis(w)  for w in words if w)
            PHONETIC_CACHE[t] = (sx, ny)
            for code in sx:
                SOUNDEX_INDEX.setdefault(code, set()).add(t)
            for code in ny:
                NYSIIS_INDEX.setdefault(code, set()).add(t)
        print(f"Phonetic cache + reverse index ready for {len(PHONETIC_CACHE):,} titles")

        # Build word → titles reverse index for fast combination detection
        WORD_INDEX.clear()
        for t in TITLES_CACHE_LIST:
            for word in t.split():  # already uppercase
                if len(word) >= 2:
                    WORD_INDEX.setdefault(word, set()).add(t)
        print(f"Word index ready: {len(WORD_INDEX):,} unique words")
    except Exception as e:
        print(f"Error loading titles: {e}")

def _refresh_disallowed_cache():
    """Reload disallowed words from DB into in-memory list (in-place update)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT word FROM disallowed_words')
    new_words = [row[0] for row in cursor.fetchall()]
    conn.close()
    DISALLOWED_WORDS_CACHE.clear()
    DISALLOWED_WORDS_CACHE.extend(new_words)


def init_db():
    conn = get_connection()
    conn.execute("PRAGMA journal_mode=WAL")  # enable WAL once — allows concurrent reads during writes
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS titles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        registration_number TEXT,
        registration_date TEXT,
        language TEXT,
        periodicity TEXT,
        publisher TEXT,
        owner TEXT,
        pub_state TEXT,
        pub_district TEXT
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS disallowed_words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT UNIQUE NOT NULL
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS approval_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        submitted_by TEXT,
        submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'pending',
        admin_comment TEXT,
        approved_date TIMESTAMP,
        verification_data TEXT
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS temp2 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        registration_number TEXT,
        registration_date TEXT,
        language TEXT,
        periodicity TEXT,
        publisher TEXT,
        owner TEXT,
        pub_state TEXT,
        pub_district TEXT,
        added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        approved_by TEXT,
        evaluation_score REAL,
        evaluation_metrics TEXT
    )
    ''')
    
    # Add new columns to temp2 if they don't exist (for existing databases)
    try:
        cursor.execute('ALTER TABLE temp2 ADD COLUMN evaluation_score REAL')
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cursor.execute('ALTER TABLE temp2 ADD COLUMN evaluation_metrics TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS batch_uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        total_titles INTEGER,
        status TEXT DEFAULT 'processing'
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS batch_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER,
        title TEXT NOT NULL,
        verdict TEXT,
        approval_probability REAL,
        rejection_reasons TEXT,
        verification_data TEXT,
        status TEXT DEFAULT 'pending',
        FOREIGN KEY (batch_id) REFERENCES batch_uploads(id)
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admin_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admin_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        config_key TEXT UNIQUE NOT NULL,
        config_value TEXT NOT NULL,
        updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create indexes for faster search
    try:
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_titles_title ON titles(title)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_titles_owner ON titles(owner)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_titles_state ON titles(pub_state)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_titles_language ON titles(language)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_titles_reg ON titles(registration_number)')
    except sqlite3.OperationalError:
        pass  # Indexes may already exist
    
    # Create rejected_titles table for tracking auto-rejected and admin-rejected submissions
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS rejected_titles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        normalized_title TEXT NOT NULL,
        rejection_reason TEXT,
        evaluation_score REAL,
        rejected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        rejection_type TEXT DEFAULT 'AUTO',
        verification_data TEXT,
        retry_allowed INTEGER DEFAULT 1
    )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_title ON titles(title)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approval_status ON approval_requests(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_temp2_title ON temp2(title)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_batch_results_batch_id ON batch_results(batch_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rejected_normalized ON rejected_titles(normalized_title)')
    
    # Insert default admin user if not exists (username: admin, password: admin123)
    cursor.execute('SELECT COUNT(*) FROM admin_users WHERE username = ?', ('admin',))
    if cursor.fetchone()[0] == 0:
        import hashlib
        hashed = hashlib.sha256("admin123".encode()).hexdigest()
        cursor.execute('INSERT INTO admin_users (username, hashed_password) VALUES (?, ?)', ('admin', hashed))
    
    # Insert default acceptance ratio if not exists
    cursor.execute('SELECT COUNT(*) FROM admin_config WHERE config_key = ?', ('acceptance_ratio',))
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO admin_config (config_key, config_value) VALUES (?, ?)', ('acceptance_ratio', '60'))
    
    conn.commit()
    conn.close()
    load_titles_into_memory()
    _refresh_disallowed_cache()

def get_all_titles():
    return TITLES_CACHE_LIST if TITLES_CACHE_LIST else []

def get_titles_set():
    return TITLES_CACHE_SET

def search_db_full(params):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT id, title, registration_number, registration_date, language, periodicity, publisher, owner, pub_state, pub_district FROM titles WHERE 1=1"
    args = []
    
    mapping = {
        "q": "title",
        "registration_number": "registration_number",
        "owner": "owner",
        "state": "pub_state",
        "district": "pub_district",
        "language": "language"
    }
    
    for key, col in mapping.items():
        val = params.get(key)
        if val:
            query += f" AND {col} LIKE ?"
            args.append(f"%{val}%")
            
    limit = int(params.get("limit", 50))
    offset = int(params.get("offset", 0))
    query += f" ORDER BY id LIMIT {limit} OFFSET {offset}"
    
    cursor.execute(query, args)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_comprehensive_stats():
    conn = get_connection()
    cursor = conn.cursor()
    
    stats = {}
    try:
        stats["total_titles"] = 77564
        
        cursor.execute("SELECT COUNT(DISTINCT language) FROM titles WHERE language != ''")
        stats["total_languages"] = cursor.fetchone()[0]
        
        stats["total_states"] = 28
        
        cursor.execute("SELECT COUNT(*) FROM disallowed_words")
        stats["total_disallowed_words"] = cursor.fetchone()[0]
    except:
        stats = {"total_titles": 0, "total_languages": 0, "total_states": 0, "total_disallowed_words": 0}
        
    conn.close()
    return stats

def add_disallowed_word(word):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO disallowed_words (word) VALUES (?)', (word.upper(),))
    conn.commit()
    conn.close()
    _refresh_disallowed_cache()

def delete_disallowed_word(word):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM disallowed_words WHERE word = ?', (word.upper(),))
    conn.commit()
    conn.close()
    _refresh_disallowed_cache()

def get_disallowed_words():
    """Return disallowed words from in-memory cache — no SQLite hit."""
    if DISALLOWED_WORDS_CACHE:
        return list(DISALLOWED_WORDS_CACHE)
    # Fallback: DB query if cache not populated yet
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT word FROM disallowed_words')
    words = [row[0] for row in cursor.fetchall()]
    conn.close()
    return words

def submit_approval_request(title, submitted_by="User", verification_data=None):
    import json
    conn = get_connection()
    cursor = conn.cursor()
    verification_json = json.dumps(verification_data) if verification_data else None
    cursor.execute('''
    INSERT INTO approval_requests (title, submitted_by, verification_data)
    VALUES (?, ?, ?)
    ''', (title, submitted_by, verification_json))
    conn.commit()
    request_id = cursor.lastrowid
    conn.close()
    return request_id

def get_pending_requests():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT id, title, submitted_by, submission_date, status, verification_data
    FROM approval_requests 
    WHERE status = 'pending'
    ORDER BY submission_date DESC
    ''')
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_all_requests():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT id, title, submitted_by, submission_date, status, admin_comment, approved_date
    FROM approval_requests 
    ORDER BY submission_date DESC
    ''')
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def approve_request(request_id, admin_name="Admin", comment=""):
    import json
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get the request details
    cursor.execute('SELECT title, verification_data FROM approval_requests WHERE id = ?', (request_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    
    title = row[0]
    verification_data = json.loads(row[1]) if row[1] else {}
    
    # Extract evaluation data if available
    evaluation_score = verification_data.get('score') if isinstance(verification_data, dict) else None
    evaluation_metrics = verification_data.get('metrics') if isinstance(verification_data, dict) else None
    
    # Update request status
    cursor.execute('''
    UPDATE approval_requests 
    SET status = 'approved', admin_comment = ?, approved_date = CURRENT_TIMESTAMP
    WHERE id = ?
    ''', (comment, request_id))
    
    # Add to temp2 database with evaluation data
    if evaluation_score is not None:
        metrics_json = json.dumps(evaluation_metrics) if evaluation_metrics else None
        cursor.execute('''
        INSERT INTO temp2 (title, approved_by, evaluation_score, evaluation_metrics)
        VALUES (?, ?, ?, ?)
        ''', (title, admin_name, evaluation_score, metrics_json))
    else:
        # Fallback to old format if no evaluation data
        cursor.execute('''
        INSERT INTO temp2 (title, approved_by)
        VALUES (?, ?)
        ''', (title, admin_name))
    
    conn.commit()
    conn.close()
    return True

def reject_request(request_id, admin_name="Admin", comment=""):
    import json
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get the request details before rejecting
    cursor.execute('SELECT title, verification_data FROM approval_requests WHERE id = ?', (request_id,))
    row = cursor.fetchone()
    
    if row:
        title = row[0]
        verification_data = json.loads(row[1]) if row[1] else {}
        normalized_title = title.strip().upper()
        
        # Extract evaluation score if available
        evaluation_score = verification_data.get('score') if isinstance(verification_data, dict) else None
        
        # Add to rejected_titles table
        cursor.execute('''
        INSERT INTO rejected_titles (title, normalized_title, rejection_reason, evaluation_score, rejection_type, verification_data)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, normalized_title, f"Admin rejection: {comment}" if comment else "Admin rejected", evaluation_score, "ADMIN", row[1]))
    
    # Update request status
    cursor.execute('''
    UPDATE approval_requests 
    SET status = 'rejected', admin_comment = ?, approved_date = CURRENT_TIMESTAMP
    WHERE id = ?
    ''', (comment, request_id))
    
    conn.commit()
    conn.close()
    return True

def get_temp2_titles():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM temp2 ORDER BY added_date DESC')
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

# ── Evaluation & Rejection Functions ──
def check_rejected_history(title):
    """Check if a title has been rejected before"""
    normalized = title.strip().upper()
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT id, title, rejection_reason, evaluation_score, rejected_date, rejection_type, retry_allowed
    FROM rejected_titles 
    WHERE normalized_title = ?
    ORDER BY rejected_date DESC
    ''', (normalized,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    if not rows:
        return {
            "is_rejected": False,
            "count": 0,
            "last_rejected": None,
            "reasons": [],
            "retry_allowed": True
        }
    
    return {
        "is_rejected": True,
        "count": len(rows),
        "last_rejected": rows[0]["rejected_date"],
        "reasons": [r["rejection_reason"] for r in rows if r["rejection_reason"]],
        "rejection_type": rows[0]["rejection_type"],
        "retry_allowed": bool(rows[0]["retry_allowed"])
    }

def insert_rejected_title(title, normalized_title, evaluation_score, rejection_reason, rejection_type="AUTO", verification_data=None):
    """Insert a rejected title into rejected_titles table"""
    import json
    conn = get_connection()
    cursor = conn.cursor()
    
    verification_json = json.dumps(verification_data) if verification_data else None
    
    cursor.execute('''
    INSERT INTO rejected_titles (title, normalized_title, rejection_reason, evaluation_score, rejection_type, verification_data)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (title, normalized_title, rejection_reason, evaluation_score, rejection_type, verification_json))
    
    conn.commit()
    rejected_id = cursor.lastrowid
    conn.close()
    return rejected_id

def get_rejected_titles(limit=100, offset=0):
    """Get all rejected titles for admin view"""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT id, title, rejection_reason, evaluation_score, rejected_date, rejection_type, retry_allowed
    FROM rejected_titles 
    ORDER BY rejected_date DESC
    LIMIT ? OFFSET ?
    ''', (limit, offset))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def insert_temp2_with_evaluation(title, approved_by, evaluation_score=None, evaluation_metrics=None):
    """Insert into temp2 with evaluation data"""
    import json
    conn = get_connection()
    cursor = conn.cursor()
    
    # Convert metrics dict to JSON string if it's a dict
    if isinstance(evaluation_metrics, dict):
        metrics_json = json.dumps(evaluation_metrics)
    elif isinstance(evaluation_metrics, str):
        metrics_json = evaluation_metrics
    else:
        metrics_json = None
    
    cursor.execute('''
    INSERT INTO temp2 (title, approved_by, evaluation_score, evaluation_metrics)
    VALUES (?, ?, ?, ?)
    ''', (title, approved_by, evaluation_score, metrics_json))
    
    conn.commit()
    temp2_id = cursor.lastrowid
    conn.close()
    print(f"📝 Inserted into temp2: id={temp2_id}, title='{title}', score={evaluation_score}")
    return temp2_id

def update_rejected_retry_status(rejected_id, retry_allowed=True):
    """Allow or disallow retry for a rejected title"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE rejected_titles 
    SET retry_allowed = ?
    WHERE id = ?
    ''', (1 if retry_allowed else 0, rejected_id))
    conn.commit()
    conn.close()
    return True

# ── Batch Processing Functions ──
def create_batch_upload(filename, total_titles):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO batch_uploads (filename, total_titles)
    VALUES (?, ?)
    ''', (filename, total_titles))
    batch_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return batch_id

def add_batch_result(batch_id, title, verification_data):
    import json
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO batch_results (batch_id, title, verdict, approval_probability, rejection_reasons, verification_data)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (batch_id, title, verification_data.get('verdict'),
          verification_data.get('approval_probability'),
          json.dumps(verification_data.get('rejection_reasons', [])),
          json.dumps(verification_data)))
    conn.commit()
    conn.close()

def add_batch_results_bulk(batch_id, results_list):
    """Insert all batch results in ONE transaction — eliminates per-row commit overhead."""
    import json
    conn = get_connection()
    cursor = conn.cursor()
    rows = []
    for title, vd in results_list:
        if vd is None:
            continue
        rows.append((
            batch_id,
            title,
            vd.get('verdict'),
            vd.get('approval_probability'),
            json.dumps(vd.get('rejection_reasons', [])),
            json.dumps(vd),
        ))
    cursor.executemany('''
        INSERT INTO batch_results
               (batch_id, title, verdict, approval_probability, rejection_reasons, verification_data)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', rows)
    conn.commit()
    conn.close()

def update_batch_status(batch_id, status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE batch_uploads SET status = ? WHERE id = ?', (status, batch_id))
    conn.commit()
    conn.close()

def get_batch_results(batch_id):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM batch_results WHERE batch_id = ?', (batch_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_batch_analytics(batch_id):
    import json
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT verdict, verification_data FROM batch_results WHERE batch_id = ?', (batch_id,))
    results = cursor.fetchall()

    analytics = {
        'rule_violations': {'semantic': 0, 'phonetic': 0, 'affix': 0, 'combination': 0},
        'prefix_usage': {},
        'state_rejections': {},
        'unique_vs_duplicate': {'unique': 0, 'duplicate': 0},
        'confidence_levels': [],
        'language_conflicts': {}
    }

    matched_titles_upper = []  # existing_title values from priority_matches (already uppercase)

    for verdict, vdata in results:
        data = json.loads(vdata) if vdata else {}

        # Rule violations — count each rejection reason category
        for reason in data.get('rejection_reasons', []):
            r = reason.lower()
            if 'semantic' in r or 'cross-language' in r or 'conceptual' in r:
                analytics['rule_violations']['semantic'] += 1
            elif 'phonetic' in r or 'similar' in r or 'typo' in r:
                analytics['rule_violations']['phonetic'] += 1
            elif 'prefix' in r or 'suffix' in r or 'restricted' in r:
                analytics['rule_violations']['affix'] += 1
            elif reason.strip():
                analytics['rule_violations']['combination'] += 1

        # Confidence / approval probability
        if 'approval_probability' in data:
            analytics['confidence_levels'].append(data['approval_probability'])

        # Title prefix (first word of the submitted title)
        title = data.get('title', '')
        words = title.strip().split()
        if words:
            prefix = words[0].upper()
            analytics['prefix_usage'][prefix] = analytics['prefix_usage'].get(prefix, 0) + 1

        # Verdict analysis — APPROVED = unique, else duplicate/conflict
        if data.get('verdict') == 'APPROVED':
            analytics['unique_vs_duplicate']['unique'] += 1
        else:
            analytics['unique_vs_duplicate']['duplicate'] += 1

        # Collect existing titles from priority_matches for state/language analysis
        for pm in data.get('priority_matches', []):
            for match in pm.get('matches', []):
                et = match.get('existing_title', '')
                # Skip theme pseudo-titles and empty values
                if et and not et.startswith('Theme:') and not et.startswith('Multiple'):
                    matched_titles_upper.append(et.upper())

    # Look up pub_state and language for all matched existing titles
    if matched_titles_upper:
        unique_matched = list(set(matched_titles_upper))[:500]  # cap at 500 unique lookups
        placeholders = ','.join(['?' for _ in unique_matched])
        try:
            cursor.execute(
                f'SELECT pub_state, language FROM titles WHERE UPPER(title) IN ({placeholders})',
                unique_matched
            )
            for pub_state, language in cursor.fetchall():
                if pub_state and pub_state.strip():
                    s = pub_state.strip()
                    analytics['state_rejections'][s] = analytics['state_rejections'].get(s, 0) + 1
                if language and language.strip():
                    l = language.strip()
                    analytics['language_conflicts'][l] = analytics['language_conflicts'].get(l, 0) + 1
        except Exception:
            pass  # analytics gracefully stays empty if lookup fails

    conn.close()
    return analytics

def approve_batch_titles(batch_id, title_ids, admin_name="Admin"):
    conn = get_connection()
    cursor = conn.cursor()
    
    for title_id in title_ids:
        cursor.execute('SELECT title, verification_data FROM batch_results WHERE id = ?', (title_id,))
        row = cursor.fetchone()
        if row:
            title = row[0]
            cursor.execute('INSERT INTO temp2 (title, approved_by) VALUES (?, ?)', (title, admin_name))
            cursor.execute('UPDATE batch_results SET status = ? WHERE id = ?', ('approved', title_id))
    
    conn.commit()
    conn.close()

# ── Admin Authentication Functions ──
def verify_admin_password(username, password):
    import hashlib
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT hashed_password FROM admin_users WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        hashed = hashlib.sha256(password.encode()).hexdigest()
        return hashed == row[0]
    return False

def get_admin_config(key):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT config_value FROM admin_config WHERE config_key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_admin_config(key, value):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR REPLACE INTO admin_config (config_key, config_value, updated_date)
    VALUES (?, ?, CURRENT_TIMESTAMP)
    ''', (key, value))
    conn.commit()
    conn.close()

def clear_temp_batch_data():
    """Clear all batch upload, batch result data, and temp2 database"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM batch_results')
    cursor.execute('DELETE FROM batch_uploads')
    cursor.execute('DELETE FROM temp2')
    cursor.execute('DELETE FROM approval_requests')
    # Reset autoincrement counters
    cursor.execute('DELETE FROM sqlite_sequence WHERE name IN ("batch_results", "batch_uploads", "temp2", "approval_requests")')
    conn.commit()
    conn.close()
    print("✅ Temp batch database cleared (batch_results, batch_uploads, temp2, approval_requests)")
