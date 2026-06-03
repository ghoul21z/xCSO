import sqlite3
from backend.db import get_db_connection
sqlite3.connect = lambda *args, **kwargs: get_db_connection()
import json
from main import DB_PATH

def handle_api(handler, path, method, data):
    if method == "GET" and (path == "/api/v1/stats" or path.startswith("/api/v1/stats?")):
        _handle_get_stats(handler, path)
    else:
        handler._send_json({"error": "Method not allowed for stats"}, 405)

def _handle_get_stats(handler, path):
    try:
        from urllib.parse import urlparse, parse_qs
        parsed_path = urlparse(path)
        params = parse_qs(parsed_path.query)
        date_val = params.get("date", [None])[0]
        
        # If date is empty or null, default to today's date in YYYY-MM-DD
        if not date_val:
            from datetime import datetime
            date_val = datetime.now().strftime("%Y-%m-%d")

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Templates count (all-time)
        cursor.execute("SELECT COUNT(*) FROM templates")
        total_templates = cursor.fetchone()[0]

        # Checksheets count total and by status for the selected date
        cursor.execute("SELECT COUNT(*) FROM checksheets WHERE conducted_date = ?", (date_val,))
        total_checksheets = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM checksheets WHERE conducted_date = ? AND status = 'Submitted'", (date_val,))
        submitted_checksheets = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM checksheets WHERE conducted_date = ? AND status = 'Draft'", (date_val,))
        draft_checksheets = cursor.fetchone()[0]

        # SE project stats for selected date
        cursor.execute("SELECT COUNT(*) FROM checksheets WHERE project = 'SE' AND conducted_date = ? AND status = 'Submitted'", (date_val,))
        se_submitted = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM checksheets WHERE project = 'SE' AND conducted_date = ? AND status = 'Draft'", (date_val,))
        se_draft = cursor.fetchone()[0]
        # Total operations/checksheets to be completed for SE is 12
        se_total = 12

        # Co-molded project stats for selected date
        cursor.execute("SELECT COUNT(*) FROM checksheets WHERE project = 'Co-molded' AND conducted_date = ? AND status = 'Submitted'", (date_val,))
        co_submitted = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM checksheets WHERE project = 'Co-molded' AND conducted_date = ? AND status = 'Draft'", (date_val,))
        co_draft = cursor.fetchone()[0]
        # Total operations/checksheets to be completed for Co-molded is 18
        co_total = 18

        # Compliance metrics for selected date
        cursor.execute("SELECT responses FROM checksheets WHERE status = 'Submitted' AND conducted_date = ?", (date_val,))
        all_submitted = cursor.fetchall()
        
        pass_count = 0
        fail_count = 0
        na_count = 0

        for row in all_submitted:
            try:
                responses = json.loads(row["responses"]) or {}
            except:
                responses = {}
            
            for item_id, resp in responses.items():
                if item_id == "__signature__":
                    continue
                status = resp.get("status")
                if status == "Pass":
                    pass_count += 1
                elif status == "Fail":
                    fail_count += 1
                elif status == "NA":
                    na_count += 1

        total_items = pass_count + fail_count + na_count
        overall_pass_rate = 0.0
        overall_fail_rate = 0.0
        overall_na_rate = 0.0

        if total_items > 0:
            overall_pass_rate = round((pass_count / total_items) * 100, 1)
            overall_fail_rate = round((fail_count / total_items) * 100, 1)
            overall_na_rate = round((na_count / total_items) * 100, 1)

        # 5 recent submissions
        cursor.execute("""
            SELECT cs.id, cs.title, cs.status, cs.filler_name, cs.created_at, t.title as template_title
            FROM checksheets cs
            JOIN templates t ON cs.template_id = t.id
            ORDER BY cs.updated_at DESC LIMIT 5
        """)
        recent_rows = cursor.fetchall()
        recent_submissions = []
        
        for row in recent_rows:
            recent_submissions.append({
                "id": row["id"],
                "title": row["title"],
                "template_title": row["template_title"],
                "status": row["status"],
                "filler_name": row["filler_name"],
                "created_at": row["created_at"]
            })

        conn.close()

        handler._send_json({
            "total_templates": total_templates,
            "total_checksheets": total_checksheets,
            "submitted_checksheets": submitted_checksheets,
            "draft_checksheets": draft_checksheets,
            "se_stats": {
                "total": se_total,
                "submitted": se_submitted,
                "draft": se_draft
            },
            "co_stats": {
                "total": co_total,
                "submitted": co_submitted,
                "draft": co_draft
            },
            "overall_pass_rate": overall_pass_rate,
            "overall_fail_rate": overall_fail_rate,
            "overall_na_rate": overall_na_rate,
            "recent_submissions": recent_submissions
        })

    except Exception as e:
        handler._send_json({"error": f"Failed to load dashboard metrics: {str(e)}"}, 500)
