import os
import json
import sqlite3
import re
import sys
import uuid

# Force terminal encoding to UTF-8 to prevent cp1252 print crashes on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# Determine project directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DB_PATH = os.path.join(BASE_DIR, "backend", "checksheet.db")

# Create database and tables automatically on startup
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create templates table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS templates (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT,
        items TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    
    # Create checksheets table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS checksheets (
        id TEXT PRIMARY KEY,
        template_id TEXT NOT NULL,
        title TEXT NOT NULL,
        status TEXT NOT NULL,
        filler_name TEXT,
        responses TEXT NOT NULL,
        project TEXT,
        operation TEXT,
        conducted_date TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE
    );
    """)
    
    # Run migrations for checksheets table to add project, operation, conducted_date if missing
    cursor.execute("PRAGMA table_info(checksheets)")
    columns = [col[1] for col in cursor.fetchall()]
    if "project" not in columns:
        cursor.execute("ALTER TABLE checksheets ADD COLUMN project TEXT")
    if "operation" not in columns:
        cursor.execute("ALTER TABLE checksheets ADD COLUMN operation TEXT")
    if "conducted_date" not in columns:
        cursor.execute("ALTER TABLE checksheets ADD COLUMN conducted_date TEXT")
    if "line" not in columns:
        cursor.execute("ALTER TABLE checksheets ADD COLUMN line TEXT")
    if "machine" not in columns:
        cursor.execute("ALTER TABLE checksheets ADD COLUMN machine TEXT")
        
    conn.commit()
    conn.close()
    print(f"Database initialized successfully at: {DB_PATH}")

def seed_operation_templates():
    """Seed default QA templates for each operation if they don't already exist."""
    OPERATION_TEMPLATES = [
        {
            "operation": "laser",
            "title": "Kiểm Tra Công Đoạn Laser",
            "description": "Checklist kiểm tra chất lượng công đoạn cắt laser",
            "items": [
                {"id": "laser_1", "type": "pass_fail", "label": "Kiểm tra năng lượng laser (Power check)", "required": True},
                {"id": "laser_2", "type": "pass_fail", "label": "Kiểm tra độ sắc nét đường cắt (Cut edge quality)", "required": True},
                {"id": "laser_3", "type": "pass_fail", "label": "Không có cháy xém trên bề mặt (No burn marks)", "required": True},
                {"id": "laser_4", "type": "pass_fail", "label": "Kiểm tra kích thước sau laser (Post-laser dimensions)", "required": True},
                {"id": "laser_5", "type": "pass_fail", "label": "Bề mặt sạch, không bụi bẩn sau laser (Surface cleanliness)", "required": True},
                {"id": "laser_6", "type": "pass_fail", "label": "Kiểm tra đường hàn / vị trí cắt đúng tọa độ (Cut position accuracy)", "required": True},
                {"id": "laser_7", "type": "text",      "label": "Ghi chú / Nhận xét thêm (Notes)", "required": False},
            ]
        },
        {
            "operation": "plasma",
            "title": "Kiểm Tra Công Đoạn Plasma",
            "description": "Checklist kiểm tra chất lượng công đoạn xử lý plasma",
            "items": [
                {"id": "plasma_1", "type": "pass_fail", "label": "Kiểm tra áp suất khí plasma đúng thông số (Gas pressure OK)", "required": True},
                {"id": "plasma_2", "type": "pass_fail", "label": "Kiểm tra cường độ dòng điện (Current setting correct)", "required": True},
                {"id": "plasma_3", "type": "pass_fail", "label": "Kiểm tra bề mặt sau xử lý plasma (Surface after treatment)", "required": True},
                {"id": "plasma_4", "type": "pass_fail", "label": "Không có bavia sau cắt (No burrs)", "required": True},
                {"id": "plasma_5", "type": "pass_fail", "label": "Kiểm tra nhiệt độ bề mặt sau gia công (Surface temperature OK)", "required": True},
                {"id": "plasma_6", "type": "pass_fail", "label": "Độ bám dính sau plasma đạt yêu cầu (Adhesion test OK)", "required": True},
                {"id": "plasma_7", "type": "text",      "label": "Ghi chú / Nhận xét thêm (Notes)", "required": False},
            ]
        },
        {
            "operation": "oca",
            "title": "Kiểm Tra Công Đoạn OCA",
            "description": "Checklist kiểm tra chất lượng dán keo OCA",
            "items": [
                {"id": "oca_1", "type": "pass_fail", "label": "Không có bong bóng khí trong lớp OCA (No air bubbles)", "required": True},
                {"id": "oca_2", "type": "pass_fail", "label": "Độ bám dính keo OCA đạt yêu cầu (Adhesion OK)", "required": True},
                {"id": "oca_3", "type": "pass_fail", "label": "Độ trong suốt lớp OCA (Optical clarity OK)", "required": True},
                {"id": "oca_4", "type": "pass_fail", "label": "Canh chỉnh vị trí đúng tâm (Alignment correct)", "required": True},
                {"id": "oca_5", "type": "pass_fail", "label": "Độ dày lớp OCA đúng thông số (OCA thickness within spec)", "required": True},
                {"id": "oca_6", "type": "pass_fail", "label": "Không có bụi/tạp chất trong lớp dán (No contamination)", "required": True},
                {"id": "oca_7", "type": "text",      "label": "Ghi chú / Nhận xét thêm (Notes)", "required": False},
            ]
        },
        {
            "operation": "demold",
            "title": "Kiểm Tra Công Đoạn Demold",
            "description": "Checklist kiểm tra chất lượng công đoạn tháo khuôn",
            "items": [
                {"id": "demold_1", "type": "pass_fail", "label": "Không nứt vỡ sau khi tháo khuôn (No cracks after demold)", "required": True},
                {"id": "demold_2", "type": "pass_fail", "label": "Bề mặt sản phẩm không bị xước (No surface scratches)", "required": True},
                {"id": "demold_3", "type": "pass_fail", "label": "Kích thước sản phẩm đúng bản vẽ (Dimensions within spec)", "required": True},
                {"id": "demold_4", "type": "pass_fail", "label": "Không có vết lõm (sink marks) (No sink marks)", "required": True},
                {"id": "demold_5", "type": "pass_fail", "label": "Không có đường hàn nổi (No visible weld lines)", "required": True},
                {"id": "demold_6", "type": "pass_fail", "label": "Màu sắc đồng đều, không biến màu (Color uniformity OK)", "required": True},
                {"id": "demold_7", "type": "text",      "label": "Ghi chú / Nhận xét thêm (Notes)", "required": False},
            ]
        },
        {
            "operation": "uv",
            "title": "Kiểm Tra Công Đoạn UV",
            "description": "Checklist kiểm tra chất lượng lớp phủ UV",
            "items": [
                {"id": "uv_1", "type": "pass_fail", "label": "Lớp UV đóng rắn hoàn toàn (UV curing complete)", "required": True},
                {"id": "uv_2", "type": "pass_fail", "label": "Không bong tróc lớp UV (No peeling)", "required": True},
                {"id": "uv_3", "type": "pass_fail", "label": "Độ bóng bề mặt đạt yêu cầu (Gloss level OK)", "required": True},
                {"id": "uv_4", "type": "pass_fail", "label": "Màu sắc đồng đều sau UV (Color after UV OK)", "required": True},
                {"id": "uv_5", "type": "pass_fail", "label": "Độ dày lớp UV đúng thông số (UV coating thickness OK)", "required": True},
                {"id": "uv_6", "type": "pass_fail", "label": "Không có bụi/lỗ kim châm trên bề mặt (No pinholes or dust)", "required": True},
                {"id": "uv_7", "type": "text",      "label": "Ghi chú / Nhận xét thêm (Notes)", "required": False},
            ]
        },
    ]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()

    for tpl in OPERATION_TEMPLATES:
        # Check if a template tagged with this operation already exists (by title)
        cursor.execute("SELECT id FROM templates WHERE title = ?", (tpl["title"],))
        existing = cursor.fetchone()
        if not existing:
            tpl_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO templates (id, title, description, items, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (tpl_id, tpl["title"], tpl["description"], json.dumps(tpl["items"], ensure_ascii=False), now, now)
            )
            print(f"  [SEED] Created template: {tpl['title']}")
        else:
            print(f"  [SEED] Template already exists: {tpl['title']}")

    conn.commit()
    conn.close()

class ChecksheetRequestHandler(BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {format%args}\n")

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    # --- HTTP GET Request Routing ---
    def do_GET(self):
        path = self.path

        # 1. API GET Dispatchers
        if path.startswith("/api/v1/"):
            
            # API: Authentication Info (Me)
            if path == "/api/v1/auth/me":
                from backend.auth import handle_me
                handle_me(self)
                return

            # For other API calls, check authentication session
            from backend.auth import get_current_session
            session = get_current_session(self)
            if not session:
                self._send_json({"error": "Unauthorized (Vui lòng đăng nhập)"}, 401)
                return

            # API: Stats / Dashboard
            if path == "/api/v1/stats" or path.startswith("/api/v1/stats?"):
                from backend.dashboard import handle_api
                handle_api(self, path, "GET", None)
                return

            # API: Template by operation keyword
            if path.startswith("/api/v1/templates/by-operation"):
                from backend.checksheets import handle_template_by_operation
                handle_template_by_operation(self, path)
                return

            # API: Templates GET
            if path.startswith("/api/v1/templates"):
                from backend.templates import handle_api
                handle_api(self, path, "GET", None)
                return

            # API: Checksheets GET
            if path.startswith("/api/v1/checksheets"):
                from backend.checksheets import handle_api
                handle_api(self, path, "GET", None)
                return

            # API: Admin - List Users (Requires admin role)
            if path == "/api/v1/admin/users":
                if session["role"] != "admin":
                    self._send_json({"error": "Forbidden: Chỉ quản trị viên (Admin only)"}, 403)
                    return
                from backend.auth import handle_admin_list_users
                handle_admin_list_users(self)
                return

            self._send_json({"error": "API route not found"}, 404)
            return

        # 2. Serves modular HTML frontend pages
        self._handle_serve_static(path)

    # --- HTTP POST Request Routing ---
    def do_POST(self):
        path = self.path

        if not path.startswith("/api/v1/"):
            self._send_json({"error": "Invalid API path"}, 404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body) if body else {}
        except Exception as e:
            self._send_json({"error": f"Invalid JSON payload: {str(e)}"}, 400)
            return

        # API: Authentication Login / Register / Logout
        if path == "/api/v1/auth/login":
            from backend.auth import handle_login
            handle_login(self, data)
            return

        if path == "/api/v1/auth/register":
            from backend.auth import handle_register
            handle_register(self, data)
            return

        if path == "/api/v1/auth/logout":
            from backend.auth import handle_logout
            handle_logout(self)
            return

        # For all other POST API endpoints, check authentication
        from backend.auth import get_current_session
        session = get_current_session(self)
        if not session:
            self._send_json({"error": "Unauthorized (Vui lòng đăng nhập)"}, 401)
            return

        # API: Create Template (Requires admin role)
        if path == "/api/v1/templates":
            if session["role"] != "admin":
                self._send_json({"error": "Forbidden: Chỉ quản trị viên mới có quyền tạo mẫu (Admin only)"}, 403)
                return
            from backend.templates import handle_api
            handle_api(self, path, "POST", data)
            return

        # API: Import/Update Template by Operation (Requires admin role)
        if path == "/api/v1/templates/by-operation":
            if session["role"] != "admin":
                self._send_json({"error": "Forbidden: Chỉ quản trị viên mới có quyền nhập dữ liệu (Admin only)"}, 403)
                return
            from backend.templates import handle_import_template_by_operation
            handle_import_template_by_operation(self, data)
            return

        # API: Create Checksheet (Both admin and user role can create/save drafts)
        if path == "/api/v1/checksheets":
            from backend.checksheets import handle_api
            handle_api(self, path, "POST", data)
            return

        self._send_json({"error": "API route not found"}, 404)

    # --- HTTP PUT Request Routing ---
    def do_PUT(self):
        path = self.path

        # Check authentication for all PUT requests
        from backend.auth import get_current_session
        session = get_current_session(self)
        if not session:
            self._send_json({"error": "Unauthorized (Vui lòng đăng nhập)"}, 401)
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body) if body else {}
        except Exception as e:
            self._send_json({"error": f"Invalid JSON payload: {str(e)}"}, 400)
            return

        # API: Checksheets PUT
        if path.startswith("/api/v1/checksheets/"):
            from backend.checksheets import handle_api
            handle_api(self, path, "PUT", data)
            return

        # API: Admin - Approve User
        import re
        approve_match = re.match(r'^/api/v1/admin/users/([^/]+)/approve$', path)
        if approve_match:
            if session["role"] != "admin":
                self._send_json({"error": "Forbidden: Chỉ quản trị viên (Admin only)"}, 403)
                return
            from backend.auth import handle_admin_approve_user
            handle_admin_approve_user(self, approve_match.group(1))
            return

        # API: Admin - Set User Role
        role_match = re.match(r'^/api/v1/admin/users/([^/]+)/role$', path)
        if role_match:
            if session["role"] != "admin":
                self._send_json({"error": "Forbidden: Chỉ quản trị viên (Admin only)"}, 403)
                return
            from backend.auth import handle_admin_set_role
            handle_admin_set_role(self, role_match.group(1), data)
            return

        self._send_json({"error": "API route not found"}, 404)

    # --- HTTP DELETE Request Routing ---
    def do_DELETE(self):
        path = self.path

        # Check authentication
        from backend.auth import get_current_session
        session = get_current_session(self)
        if not session:
            self._send_json({"error": "Unauthorized (Vui lòng đăng nhập)"}, 401)
            return

        # Delete Template (Requires admin)
        if path.startswith("/api/v1/templates/"):
            if session["role"] != "admin":
                self._send_json({"error": "Forbidden: Chỉ quản trị viên mới có quyền xóa mẫu (Admin only)"}, 403)
                return
            from backend.templates import handle_api
            handle_api(self, path, "DELETE", None)
            return

        # Delete Checksheet (Requires admin)
        if path.startswith("/api/v1/checksheets/"):
            if session["role"] != "admin":
                self._send_json({"error": "Forbidden: Chỉ quản trị viên mới có quyền xóa bảng kiểm tra (Admin only)"}, 403)
                return
            from backend.checksheets import handle_api
            handle_api(self, path, "DELETE", None)
            return

        # Delete User (Requires admin)
        import re
        user_delete_match = re.match(r'^/api/v1/admin/users/([^/]+)$', path)
        if user_delete_match:
            if session["role"] != "admin":
                self._send_json({"error": "Forbidden: Chỉ quản trị viên (Admin only)"}, 403)
                return
            from backend.auth import handle_admin_delete_user
            handle_admin_delete_user(self, user_delete_match.group(1))
            return

        self._send_json({"error": "API route not found"}, 404)

    # --- Helper methods for serving files and JSON ---
    def _send_json(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _handle_serve_static(self, path):
        # Default route map
        clean_path = path.split("?")[0].rstrip("/")
        
        # Determine if it's a static asset (skip authentication redirection for assets)
        is_asset = any(clean_path.endswith(ext) for ext in [".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".json", ".ico"])

        # Check user authentication session for HTML page requests
        from backend.auth import get_current_session
        session = get_current_session(self)

        if not is_asset:
            if clean_path in ("/login", "/login.html"):
                # If logged in, redirect away from login page to dashboard
                if session:
                    self.send_response(302)
                    self.send_header("Location", "/dashboard")
                    self.end_headers()
                    return
                file_name = "login.html"
            else:
                # If not logged in, redirect to login page
                if not session:
                    self.send_response(302)
                    self.send_header("Location", "/login")
                    self.end_headers()
                    return
                
                # Check clean path maps
                if clean_path in ("", "/", "/dashboard", "/dashboard.html", "/checksheets", "/checksheets.html"):
                    file_name = "dashboard.html"
                elif clean_path in ("/templates", "/templates.html"):
                    file_name = "templates.html"
                else:
                    file_name = clean_path.lstrip("/")
        else:
            file_name = clean_path.lstrip("/")

        file_path = os.path.join(FRONTEND_DIR, file_name)
        
        # Prevent Directory Traversal
        if not os.path.abspath(file_path).startswith(os.path.abspath(FRONTEND_DIR)):
            self.send_error(403, "Access Denied")
            return

        if not os.path.exists(file_path) or os.path.isdir(file_path):
            # Fallback to dashboard.html or 404
            file_path = os.path.join(FRONTEND_DIR, "dashboard.html")
            if not os.path.exists(file_path):
                self.send_error(404, "File Not Found")
                return

        # Map MIME Types
        mime_type = "text/html"
        if file_path.endswith(".css"):
            mime_type = "text/css"
        elif file_path.endswith(".js"):
            mime_type = "application/javascript"
        elif file_path.endswith(".json"):
            mime_type = "application/json"
        elif file_path.endswith(".png"):
            mime_type = "image/png"
        elif file_path.endswith(".jpg") or file_path.endswith(".jpeg"):
            mime_type = "image/jpeg"
        elif file_path.endswith(".svg"):
            mime_type = "image/svg+xml"

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", len(content))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Internal Server Error: {str(e)}")

# --- Server Start Routine ---
def run_server(port=8000):
    init_db()
    seed_operation_templates()
    from backend.auth import init_auth_db
    init_auth_db()
    server_address = ("", port)
    httpd = HTTPServer(server_address, ChecksheetRequestHandler)
    print(f"\n=======================================================")
    print(f"  xOCS Web Server is running on: http://127.0.0.1:{port}")
    print(f"  Unified Multi-Page Architecture Router active.")
    print(f"=======================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web server...")
        httpd.server_close()
        print("Web server stopped.")

if __name__ == "__main__":
    port_arg = int(os.environ.get("PORT", 8000))
    if len(sys.argv) > 1:
        try:
            port_arg = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port_arg)
