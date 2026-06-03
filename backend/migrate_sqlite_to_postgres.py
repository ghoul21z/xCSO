import os
import sqlite3
import psycopg2
import sys

# Ensure stdout/stderr are UTF-8 compliant
if sys.stdout.encoding != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError: pass
if sys.stderr.encoding != 'utf-8':
    try: sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError: pass

def migrate():
    # 1. Load .env
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(base_dir, ".env")
    database_url = None
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str and not line_str.startswith("#") and "=" in line_str:
                    key, val = line_str.split("=", 1)
                    if key.strip() == "DATABASE_URL":
                        database_url = val.strip()
                        
    if not database_url:
        print("Error: DATABASE_URL not found in .env file!")
        return
        
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        
    db_path = os.path.join(base_dir, "backend", "checksheet.db")
    print(f"Connecting to SQLite: {db_path}")
    sqlite_conn = sqlite3.connect(db_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()
    
    print(f"Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(database_url)
    pg_cur = pg_conn.cursor()
    
    # Migrate users
    print("Migrating users...")
    sqlite_cur.execute("SELECT * FROM users")
    users = sqlite_cur.fetchall()
    for u in users:
        status_val = u["status"] if "status" in u.keys() else "approved"
        pg_cur.execute("""
            INSERT INTO users (id, username, password_hash, role, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (username) DO NOTHING
        """, (u["id"], u["username"], u["password_hash"], u["role"], status_val, u["created_at"]))
    pg_conn.commit()
    print(f"Migrated {len(users)} users.")
    
    # Migrate templates
    print("Migrating templates...")
    sqlite_cur.execute("SELECT * FROM templates")
    templates = sqlite_cur.fetchall()
    for t in templates:
        pg_cur.execute("""
            INSERT INTO templates (id, title, description, items, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                items = EXCLUDED.items,
                updated_at = EXCLUDED.updated_at
        """, (t["id"], t["title"], t["description"], t["items"], t["created_at"], t["updated_at"]))
    pg_conn.commit()
    print(f"Migrated {len(templates)} templates.")
    
    # Migrate checksheets
    print("Migrating checksheets...")
    sqlite_cur.execute("SELECT * FROM checksheets")
    checksheets = sqlite_cur.fetchall()
    migrated_cs_count = 0
    for cs in checksheets:
        line_val = cs["line"] if "line" in cs.keys() else "Line 1"
        machine_val = cs["machine"] if "machine" in cs.keys() else "N/A"
        project_val = cs["project"] if "project" in cs.keys() else ""
        operation_val = cs["operation"] if "operation" in cs.keys() else ""
        conducted_date_val = cs["conducted_date"] if "conducted_date" in cs.keys() else ""
        
        pg_cur.execute("""
            INSERT INTO checksheets (id, template_id, title, status, filler_name, responses, project, operation, conducted_date, line, machine, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (
            cs["id"], cs["template_id"], cs["title"], cs["status"], cs["filler_name"], cs["responses"],
            project_val, operation_val, conducted_date_val, line_val, machine_val,
            cs["created_at"], cs["updated_at"]
        ))
        migrated_cs_count += 1
    pg_conn.commit()
    print(f"Migrated {migrated_cs_count} checksheets.")
    
    sqlite_conn.close()
    pg_conn.close()
    print("Migration completed successfully!")

if __name__ == "__main__":
    migrate()
