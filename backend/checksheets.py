import sqlite3
from backend.db import get_db_connection
sqlite3.connect = lambda *args, **kwargs: get_db_connection()
import json
import re
import uuid
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from main import DB_PATH

def handle_api(handler, path, method, data):
    # Route Templates
    if path == "/api/v1/templates":
        if method == "GET":
            _handle_get_templates(handler)
        elif method == "POST":
            _handle_create_template(handler, data)
        else:
            handler._send_json({"error": "Method not allowed"}, 405)
        return

    # Route Checksheets List or Create
    parsed_path = urlparse(path)
    if parsed_path.path == "/api/v1/checksheets":
        if method == "GET":
            params = parse_qs(parsed_path.query)
            if params:
                _handle_get_checksheets_filtered(handler, params)
            else:
                _handle_get_checksheets_list(handler)
        elif method == "POST":
            _handle_create_checksheet(handler, data)
        else:
            handler._send_json({"error": "Method not allowed"}, 405)
        return

    # Route Checksheet details, update, delete
    match = re.match(r"^/api/v1/checksheets/([^/]+)$", path)
    if match:
        checksheet_id = match.group(1)
        if method == "GET":
            _handle_get_checksheet_detail(handler, checksheet_id)
        elif method == "PUT":
            _handle_update_checksheet(handler, checksheet_id, data)
        elif method == "DELETE":
            _handle_delete_checksheet(handler, checksheet_id)
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
            # Placeholder for future filter implementation
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

def _handle_get_checksheets_list(handler):
    """Return all checksheets without filtering"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM checksheets ORDER BY created_at DESC")
        rows = cursor.fetchall()
        checksheets = []
        for row in rows:
            checksheets.append({
                "id": row["id"],
                "template_id": row["template_id"],
                "title": row["title"],
                "status": row["status"],
                "filler_name": row["filler_name"],
                "responses": json.loads(row["responses"]),
                "project": row["project"],
                "operation": row["operation"],
                "conducted_date": row["conducted_date"],
                "line": row["line"] if "line" in row.keys() else "Line 1",
                "machine": row["machine"] if "machine" in row.keys() else "N/A",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })
        conn.close()
        handler._send_json(checksheets)
    except Exception as e:
        handler._send_json({"error": f"Failed to load checksheets list: {str(e)}"}, 500)

def _handle_get_checksheet_detail(handler, checksheet_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT cs.*, t.title as template_title 
            FROM checksheets cs
            JOIN templates t ON cs.template_id = t.id
            WHERE cs.id = ?
        """, (checksheet_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            handler._send_json({"detail": "Checksheet not found"}, 404)
            return

        handler._send_json({
            "id": row["id"],
            "template_id": row["template_id"],
            "title": row["title"],
            "status": row["status"],
            "filler_name": row["filler_name"],
            "responses": json.loads(row["responses"]),
            "project": row["project"],
            "operation": row["operation"],
            "conducted_date": row["conducted_date"],
            "line": row["line"] if "line" in row.keys() else "Line 1",
            "machine": row["machine"] if "machine" in row.keys() else "N/A",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "template_title": row["template_title"]
        })
    except Exception as e:
        handler._send_json({"error": f"Database error: {str(e)}"}, 500)

def _handle_create_checksheet(handler, data):
    if "template_id" not in data or "title" not in data or "responses" not in data:
        handler._send_json({"error": "template_id, title, and responses fields are required"}, 400)
        return

    try:
        checksheet_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Verify template exists
        cursor.execute("SELECT id FROM templates WHERE id = ?", (data["template_id"],))
        if not cursor.fetchone():
            conn.close()
            handler._send_json({"detail": "Template not found"}, 404)
            return

        # Check if a submitted checksheet already exists for the same project, operation, conducted_date, line, and machine
        project = data.get("project", "")
        operation = data.get("operation", "")
        conducted_date = data.get("conducted_date", "")
        line = data.get("line", "Line 1")
        machine = data.get("machine", "N/A")
        if project and operation and conducted_date:
            line_query = "(line = ? OR line IS NULL OR line = '')" if line == "Line 1" else "line = ?"
            machine_query = "(machine = ? OR machine IS NULL OR machine = '')" if machine == "N/A" else "machine = ?"
            
            cursor.execute(f"""
                SELECT id FROM checksheets 
                WHERE project = ? AND operation = ? AND conducted_date = ? AND {line_query} AND {machine_query} AND status = 'Submitted'
            """, (project, operation, conducted_date, line, machine))
            if cursor.fetchone():
                conn.close()
                handler._send_json({"error": "Lượt kiểm tra cho công đoạn này hôm nay đã được gửi và khóa. (Today's inspection for this operation has already been submitted and locked.)"}, 400)
                return

        cursor.execute("""
            INSERT INTO checksheets (id, template_id, title, status, filler_name, responses, project, operation, conducted_date, line, machine, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            checksheet_id,
            data["template_id"],
            data["title"],
            data.get("status", "Draft"),
            data.get("filler_name", "N/A"),
            json.dumps(data["responses"]),
            data.get("project", ""),
            data.get("operation", ""),
            data.get("conducted_date", ""),
            data.get("line", "Line 1"),
            data.get("machine", "N/A"),
            now,
            now
        ))
        conn.commit()
        conn.close()

        # Send response of newly created detail
        _handle_get_checksheet_detail(handler, checksheet_id)

    except Exception as e:
        handler._send_json({"error": f"Failed to create checksheet: {str(e)}"}, 500)

def _handle_update_checksheet(handler, checksheet_id, data):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Verify checksheet exists and get its status
        cursor.execute("SELECT id, status FROM checksheets WHERE id = ?", (checksheet_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            handler._send_json({"detail": "Checksheet not found"}, 404)
            return
            
        current_status = row[1]
        if current_status == "Submitted":
            conn.close()
            handler._send_json({"error": "Phiếu kiểm tra đã được gửi và khóa. Không thể chỉnh sửa lại. (This checksheet has already been submitted and locked.)"}, 400)
            return

        now = datetime.utcnow().isoformat()

        # Dynamic updates
        fields_to_update = []
        params = []

        if "project" in data:
            fields_to_update.append("project = ?")
            params.append(data["project"])
        if "line" in data:
            fields_to_update.append("line = ?")
            params.append(data["line"])
        if "machine" in data:
            fields_to_update.append("machine = ?")
            params.append(data["machine"])
        if "operation" in data:
            fields_to_update.append("operation = ?")
            params.append(data["operation"])
        if "conducted_date" in data:
            fields_to_update.append("conducted_date = ?")
            params.append(data["conducted_date"])
        if "title" in data:
            fields_to_update.append("title = ?")
            params.append(data["title"])
        if "status" in data:
            fields_to_update.append("status = ?")
            params.append(data["status"])
        if "filler_name" in data:
            fields_to_update.append("filler_name = ?")
            params.append(data["filler_name"])
        if "responses" in data:
            fields_to_update.append("responses = ?")
            params.append(json.dumps(data["responses"]))
            
        fields_to_update.append("updated_at = ?")
        params.append(now)

        params.append(checksheet_id)

        update_sql = f"UPDATE checksheets SET {', '.join(fields_to_update)} WHERE id = ?"
        cursor.execute(update_sql, tuple(params))
        conn.commit()
        conn.close()

        _handle_get_checksheet_detail(handler, checksheet_id)

    except Exception as e:
        handler._send_json({"error": f"Failed to update checksheet: {str(e)}"}, 500)

def _handle_delete_checksheet(handler, checksheet_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check existence
        cursor.execute("SELECT id FROM checksheets WHERE id = ?", (checksheet_id,))
        if not cursor.fetchone():
            conn.close()
            handler._send_json({"detail": "Checksheet not found"}, 404)
            return

        cursor.execute("DELETE FROM checksheets WHERE id = ?", (checksheet_id,))
        conn.commit()
        conn.close()
        
        handler.send_response(204)
        handler.end_headers()
    except Exception as e:
        handler._send_json({"error": f"Failed to delete checksheet: {str(e)}"}, 500)
def _handle_get_checksheets_filtered(handler, params):
    """Handle GET /api/v1/checksheets with filtering query parameters.
    Expected params dict values are lists from urllib.parse.parse_qs.
    Supports filtering by project, operation, date (conducted_date), and status.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        query = "SELECT * FROM checksheets WHERE 1=1"
        query_params = []
        # Project filter
        if "project" in params and params["project"] and params["project"][0]:
            query += " AND project = ?"
            query_params.append(params["project"][0])
        # Operation filter
        if "operation" in params and params["operation"] and params["operation"][0]:
            query += " AND operation = ?"
            query_params.append(params["operation"][0])
        # Date filter (conducted_date)
        if "date" in params and params["date"] and params["date"][0]:
            query += " AND conducted_date = ?"
            query_params.append(params["date"][0])
        # Line filter
        if "line" in params and params["line"] and params["line"][0]:
            if params["line"][0] == "Line 1":
                query += " AND (line = ? OR line IS NULL OR line = '')"
                query_params.append("Line 1")
            else:
                query += " AND line = ?"
                query_params.append(params["line"][0])
        # Machine filter
        if "machine" in params and params["machine"] and params["machine"][0]:
            if params["machine"][0] == "N/A":
                query += " AND (machine = ? OR machine IS NULL OR machine = '')"
                query_params.append("N/A")
            else:
                query += " AND machine = ?"
                query_params.append(params["machine"][0])
        # Status filter
        if "status" in params and params["status"] and params["status"][0]:
            query += " AND status = ?"
            query_params.append(params["status"][0])
        cursor.execute(query, tuple(query_params))
        rows = cursor.fetchall()
        checksheets = []
        for row in rows:
            checksheets.append({
                "id": row["id"],
                "template_id": row["template_id"],
                "title": row["title"],
                "status": row["status"],
                "filler_name": row["filler_name"],
                "responses": json.loads(row["responses"]),
                "project": row["project"],
                "operation": row["operation"],
                "conducted_date": row["conducted_date"],
                "line": row["line"] if "line" in row.keys() else "Line 1",
                "machine": row["machine"] if "machine" in row.keys() else "N/A",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            })
        conn.close()
        handler._send_json(checksheets)
    except Exception as e:
        handler._send_json({"error": f"Failed to load filtered checksheets: {str(e)}"}, 500)

def handle_template_by_operation(handler, path):
    """Handle GET /api/v1/templates/by-operation?operation=xxx.
    Finds a template whose title matches the operation keyword.
    """
    try:
        from urllib.parse import urlparse, parse_qs
        parsed_path = urlparse(path)
        params = parse_qs(parsed_path.query)
        operation = params.get("operation", [None])[0]
        
        if not operation:
            handler._send_json({"error": "Operation parameter is required"}, 400)
            return
            
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 1. Search with the prefixed operation (e.g. 'co_mvi' -> '%co%mvi%')
        search_op = operation.replace('_', '%')
        cursor.execute("SELECT * FROM templates WHERE title LIKE ?", (f"%{search_op}%",))
        row = cursor.fetchone()
        
        # 2. Fallback: If not found, and it has a co_ or se_ prefix, search without it (generic template)
        if not row and (operation.startswith("co_") or operation.startswith("se_")):
            clean_op = operation[3:] # Strip "co_" or "se_"
            search_op_fallback = clean_op.replace('_', '%')
            cursor.execute("SELECT * FROM templates WHERE title LIKE ?", (f"%{search_op_fallback}%",))
            row = cursor.fetchone()
        
        if not row:
            conn.close()
            handler._send_json({"error": f"No template found for operation '{operation}'"}, 404)
            return
            
        template = {
            "id": row["id"],
            "title": row["title"],
            "description": row["description"],
            "items": json.loads(row["items"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }
        conn.close()
        handler._send_json(template)
    except Exception as e:
        handler._send_json({"error": f"Failed to retrieve template by operation: {str(e)}"}, 500)
