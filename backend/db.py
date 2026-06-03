import os
import sqlite3
import re
import sys

# Ensure stdout/stderr are UTF-8 compliant
if sys.stdout.encoding != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError: pass
if sys.stderr.encoding != 'utf-8':
    try: sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError: pass

# Try to load local .env file if it exists (for local development using external database)
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str and not line_str.startswith("#") and "=" in line_str:
                    key, val = line_str.split("=", 1)
                    os.environ[key.strip()] = val.strip()
    except Exception as e:
        print(f"[DB] Error loading .env file: {e}")

DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = DATABASE_URL is not None

if USE_POSTGRES:
    try:
        import psycopg2
        from psycopg2.extras import DictCursor
        print("[DB] Using PostgreSQL database")
    except ImportError:
        print("[DB-WARNING] DATABASE_URL is set but psycopg2 is not installed. Falling back to SQLite.")
        USE_POSTGRES = False

class PostgresCursorWrapper:
    def __init__(self, pg_cursor):
        self.cursor = pg_cursor
        
    def execute(self, query, params=None):
        query_upper = query.strip().upper()
        
        # Intercept SQLite-specific foreign key pragma
        if "PRAGMA FOREIGN_KEYS" in query_upper:
            return
            
        # Intercept SQLite-specific table columns query
        if "PRAGMA TABLE_INFO" in query_upper:
            match = re.search(r"PRAGMA\s+TABLE_INFO\(([^)]+)\)", query, re.IGNORECASE)
            if match:
                table_name = match.group(1).strip().lower().replace("'", "").replace('"', '')
                pg_query = """
                    SELECT 0, column_name, 'TEXT', 0, NULL, 0 
                    FROM information_schema.columns 
                    WHERE table_name = %s
                """
                self.cursor.execute(pg_query, (table_name,))
                return

        # Convert SQLite "?" placeholders to PostgreSQL "%s" placeholders
        query = query.replace('?', '%s')
        
        # Convert case-sensitive LIKE to case-insensitive ILIKE in PostgreSQL
        query = re.sub(r'\bLIKE\b', 'ILIKE', query, flags=re.IGNORECASE)
        
        # Execute query
        if params is None:
            self.cursor.execute(query)
        else:
            self.cursor.execute(query, params)
            
    def fetchone(self):
        return self.cursor.fetchone()
        
    def fetchall(self):
        return self.cursor.fetchall()
        
    def __iter__(self):
        return iter(self.cursor)
        
    def __getattr__(self, name):
        return getattr(self.cursor, name)

class PostgresConnectionWrapper:
    def __init__(self, pg_conn):
        self.conn = pg_conn
        self._row_factory = None
        
    def cursor(self):
        if self._row_factory is not None:
            # Match sqlite3.Row behavior using DictCursor
            return PostgresCursorWrapper(self.conn.cursor(cursor_factory=DictCursor))
        return PostgresCursorWrapper(self.conn.cursor())
        
    def commit(self):
        self.conn.commit()
        
    def rollback(self):
        self.conn.rollback()
        
    def close(self):
        self.conn.close()
        
    @property
    def row_factory(self):
        return self._row_factory
        
    @row_factory.setter
    def row_factory(self, value):
        self._row_factory = value
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.close()

# Keep a reference to the original sqlite3.connect before any monkey-patching
_orig_sqlite_connect = sqlite3.connect

def get_db_connection():
    if USE_POSTGRES:
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url)
        return PostgresConnectionWrapper(conn)
    else:
        # SQLite path resolution relative to backend/
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(base_dir, "backend", "checksheet.db")
        conn = _orig_sqlite_connect(db_path)
        return conn
