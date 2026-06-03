import sqlite3
import json
import re
import uuid
from datetime import datetime
from main import DB_PATH

def handle_api(handler, path, method, data):
    # Route Template List, Create, or Filter
    if path == "/api/v1/templates" or path.startswith("/api/v1/templates?"):
        # Check for filter query
        if path.startswith("/api/v1/templates/filter") or "filter" in path:
            # Simple filter handling - parse query params
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(path).query)
            # For now, we ignore filters and return all templates
            _handle_get_templates(handler)
            return
        if method == "GET":
            _handle_get_templates(handler)
        elif method == "POST":
            _handle_create_template(handler, data)
        else:
            handler._send_json({"error": "Method not allowed"}, 405)
        return

    # Route Template details or delete
    match = re.match(r"^/api/v1/templates/([^/]+)$", path)
    if match:
        template_id = match.group(1)
        if method == "GET":
            _handle_get_template_detail(handler, template_id)
        elif method == "DELETE":
            _handle_delete_template(handler, template_id)
        else:
            handler._send_json({"error": "Method not allowed"}, 405)
        return

    handler._send_json({"error": "Route not found"}, 404)


def _handle_get_templates(handler, filters=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        base_query = "SELECT * FROM templates ORDER BY created_at DESC"
        params = []
        if filters:
            # Example filter handling: filter by operation present in items JSON
            # This is a placeholder; actual filter logic can be added later
            pass
        cursor.execute(base_query, params)
        rows = cursor.fetchall()
        
        templates = []
        for row in rows:
            templates.append({
                "id": row["id"],
                "title": row["title"],
                "description": row["description"],
                "items": json.loads(row["items"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            })
        conn.close()
        handler._send_json(templates)
    except Exception as e:
        handler._send_json({"error": f"Failed to get templates: {str(e)}"}, 500)

def _handle_get_template_detail(handler, template_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM templates WHERE id = ?", (template_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            handler._send_json({"detail": "Template not found"}, 404)
            return

        handler._send_json({
            "id": row["id"],
            "title": row["title"],
            "description": row["description"],
            "items": json.loads(row["items"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        })
    except Exception as e:
        handler._send_json({"error": f"Database error: {str(e)}"}, 500)

def _handle_create_template(handler, data):
    if "title" not in data or "items" not in data:
        handler._send_json({"error": "Title and items fields are required"}, 400)
        return

    try:
        template_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO templates (id, title, description, items, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            template_id,
            data["title"],
            data.get("description", ""),
            json.dumps(data["items"]),
            now,
            now
        ))
        conn.commit()
        conn.close()

        handler._send_json({
            "id": template_id,
            "title": data["title"],
            "description": data.get("description", ""),
            "items": data["items"],
            "created_at": now,
            "updated_at": now
        }, 201)

    except Exception as e:
        handler._send_json({"error": f"Failed to save template: {str(e)}"}, 500)

def _handle_delete_template(handler, template_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check existence
        cursor.execute("SELECT id FROM templates WHERE id = ?", (template_id,))
        if not cursor.fetchone():
            conn.close()
            handler._send_json({"detail": "Template not found"}, 404)
            return

        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("DELETE FROM templates WHERE id = ?", (template_id,))
        conn.commit()
        conn.close()
        
        handler.send_response(204)
        handler.end_headers()
    except Exception as e:
        handler._send_json({"error": f"Failed to delete template: {str(e)}"}, 500)

def handle_import_template_by_operation(handler, data):
    """Handle POST /api/v1/templates/by-operation.
    Imports/updates a template for a specific operation.
    """
    try:
        operation = data.get("operation")
        title = data.get("title")
        description = data.get("description", "")
        items = data.get("items", [])
        
        if not operation:
            handler._send_json({"error": "Operation name is required"}, 400)
            return
            
        if not title:
            handler._send_json({"error": "Template title is required"}, 400)
            return
            
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        
        # Search for existing template whose title contains the operation keyword, replacing underscore with wildcard
        search_op = operation.replace('_', '%')
        cursor.execute("SELECT id FROM templates WHERE title LIKE ?", (f"%{search_op}%",))
        existing = cursor.fetchone()
        
        if existing:
            template_id = existing[0]
            cursor.execute(
                "UPDATE templates SET title = ?, description = ?, items = ?, updated_at = ? WHERE id = ?",
                (title, description, json.dumps(items, ensure_ascii=False), now, template_id)
            )
            action = "updated"
        else:
            template_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO templates (id, title, description, items, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (template_id, title, description, json.dumps(items, ensure_ascii=False), now, now)
            )
            action = "created"
            
        conn.commit()
        conn.close()
        
        handler._send_json({
            "status": "success",
            "action": action,
            "template_id": template_id,
            "title": title
        })
    except Exception as e:
        handler._send_json({"error": f"Failed to import/update template: {str(e)}"}, 500)
