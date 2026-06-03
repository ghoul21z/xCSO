import sqlite3
from backend.db import get_db_connection
sqlite3.connect = lambda *args, **kwargs: get_db_connection()
import json
import uuid
import hashlib
import os
from datetime import datetime, timedelta
from main import DB_PATH

def hash_password(password, salt=None):
    """Hash password using PBKDF2-HMAC-SHA256 with 100,000 iterations."""
    if salt is None:
        salt = os.urandom(16).hex()
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return f"{salt}:{key.hex()}"

def verify_password(password, stored_hash):
    """Verify standard PBKDF2 stored hash against plain password."""
    try:
        salt, key_hex = stored_hash.split(":")
        new_hash = hash_password(password, salt)
        return new_hash == stored_hash
    except:
        return False

def init_auth_db():
    """Create user and session tables if not exists, and seed default user accounts."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Create users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'approved',
        created_at TEXT NOT NULL
    )
    """)
    
    # Migration: add status column to existing DB
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'approved'")
        print("  [AUTH-MIGRATION] Added 'status' column to users table")
    except:
        pass  # Column already exists
    
    # 2. Create sessions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        username TEXT NOT NULL,
        role TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)
    
    # 3. Seed Default Accounts
    now = datetime.utcnow().isoformat()
    
    # Seed Admin Account
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        admin_id = str(uuid.uuid4())
        admin_hash = hash_password("adminpassword")
        cursor.execute(
            "INSERT INTO users (id, username, password_hash, role, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (admin_id, "admin", admin_hash, "admin", "approved", now)
        )
        print(f"  [AUTH-SEED] Seeded Admin account: 'admin' | 'adminpassword'")
        
    # Seed Regular User Account
    cursor.execute("SELECT id FROM users WHERE username = 'user'")
    if not cursor.fetchone():
        user_id = str(uuid.uuid4())
        user_hash = hash_password("userpassword")
        cursor.execute(
            "INSERT INTO users (id, username, password_hash, role, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, "user", user_hash, "user", "approved", now)
        )
        print(f"  [AUTH-SEED] Seeded Regular User account: 'user' | 'userpassword'")
        
    conn.commit()
    conn.close()

def parse_cookies(cookie_header):
    """Parse HTTP Cookie header string into dict."""
    cookies = {}
    if not cookie_header:
        return cookies
    for part in cookie_header.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k] = v
    return cookies

def get_current_session(handler):
    """Extract and validate the active session from Request Cookie header.
    Returns session dict (user_id, username, role) if valid, otherwise None.
    """
    cookie_header = handler.headers.get("Cookie")
    cookies = parse_cookies(cookie_header)
    session_id = cookies.get("session_id")
    
    if not session_id:
        return None
        
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT user_id, username, role, expires_at 
            FROM sessions 
            WHERE session_id = ?
        """, (session_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
            
        # Check expiration
        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.utcnow() > expires_at:
            # Session expired, delete it in background
            _delete_session(session_id)
            return None
            
        return {
            "session_id": session_id,
            "user_id": row["user_id"],
            "username": row["username"],
            "role": row["role"]
        }
    except Exception as e:
        print(f"[AUTH-ERROR] get_current_session failed: {str(e)}")
        return None

def _delete_session(session_id):
    """Helper to delete a session from DB by ID."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
    except:
        pass

def handle_register(handler, data):
    """API POST: Register a new operator (user role)."""
    username = data.get("username", "").strip()
    password = data.get("password", "")
    
    if not username or len(username) < 3:
        handler._send_json({"error": "Tên đăng nhập phải có ít nhất 3 ký tự (Username must be at least 3 chars)"}, 400)
        return
        
    if not password or len(password) < 6:
        handler._send_json({"error": "Mật khẩu phải có ít nhất 6 ký tự (Password must be at least 6 chars)"}, 400)
        return
        
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check username uniqueness
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            handler._send_json({"error": "Tên đăng nhập đã tồn tại trên hệ thống (Username already taken)"}, 409)
            return
            
        user_id = str(uuid.uuid4())
        p_hash = hash_password(password)
        now = datetime.utcnow().isoformat()
        
        cursor.execute("""
            INSERT INTO users (id, username, password_hash, role, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, p_hash, "user", "pending", now))
        
        conn.commit()
        conn.close()
        
        handler._send_json({
            "status": "pending",
            "message": "Đăng ký tài khoản thành công! Vui lòng chờ quản trị viên phê duyệt trước khi đăng nhập. (Registration successful! Please wait for admin approval.)"
        }, 201)
        
    except Exception as e:
        handler._send_json({"error": f"Failed to register user: {str(e)}"}, 500)

def handle_login(handler, data):
    """API POST: Authenticate user, store session, and set HttpOnly Cookie."""
    username = data.get("username", "").strip()
    password = data.get("password", "")
    
    if not username or not password:
        handler._send_json({"error": "Vui lòng nhập tên đăng nhập và mật khẩu (Missing credentials)"}, 400)
        return
        
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        
        if not user or not verify_password(password, user["password_hash"]):
            conn.close()
            handler._send_json({"error": "Tên đăng nhập hoặc mật khẩu không đúng (Incorrect username or password)"}, 401)
            return
            
        # Check account approval status
        user_status = user["status"] if "status" in user.keys() else "approved"
        if user_status == 'pending':
            conn.close()
            handler._send_json({"error": "Tài khoản đang chờ quản trị viên phê duyệt. Vui lòng liên hệ admin. (Account pending approval)"}, 403)
            return
        if user_status == 'rejected':
            conn.close()
            handler._send_json({"error": "Tài khoản đã bị từ chối. Vui lòng liên hệ quản trị viên. (Account rejected)"}, 403)
            return
            
        session_id = os.urandom(24).hex()
        expires_at = (datetime.utcnow() + timedelta(days=1)).isoformat() # Valid for 24 hours
        
        cursor.execute("""
            INSERT INTO sessions (session_id, user_id, username, role, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, user["id"], user["username"], user["role"], expires_at))
        
        conn.commit()
        conn.close()
        
        # Set HttpOnly Cookie
        cookie_value = f"session_id={session_id}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400"
        
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Set-Cookie", cookie_value)
        handler._send_cors_headers()
        handler.end_headers()
        
        handler.wfile.write(json.dumps({
            "status": "success",
            "username": user["username"],
            "role": user["role"]
        }).encode("utf-8"))
        
    except Exception as e:
        handler._send_json({"error": f"Failed to login: {str(e)}"}, 500)

def handle_logout(handler):
    """API POST: Delete session token and clear dynamic cookie."""
    cookie_header = handler.headers.get("Cookie")
    cookies = parse_cookies(cookie_header)
    session_id = cookies.get("session_id")
    
    if session_id:
        _delete_session(session_id)
        
    # Clear cookie
    clear_cookie = "session_id=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
    
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Set-Cookie", clear_cookie)
    handler._send_cors_headers()
    handler.end_headers()
    
    handler.wfile.write(json.dumps({
        "status": "success",
        "message": "Logged out successfully"
    }).encode("utf-8"))

def handle_me(handler):
    """API GET: Retrieve authenticated session details or 401."""
    session = get_current_session(handler)
    if not session:
        handler._send_json({"authenticated": False}, 401)
        return
        
    handler._send_json({
        "authenticated": True,
        "username": session["username"],
        "role": session["role"]
    })


# ========== Admin User Management ==========

def handle_admin_list_users(handler):
    """API GET: List all users (admin only). Returns list with id, username, role, status, created_at."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, role, status, created_at FROM users ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        users = []
        for row in rows:
            users.append({
                "id": row["id"],
                "username": row["username"],
                "role": row["role"],
                "status": row["status"] if "status" in row.keys() else "approved",
                "created_at": row["created_at"]
            })
        
        handler._send_json({"users": users})
    except Exception as e:
        handler._send_json({"error": f"Failed to list users: {str(e)}"}, 500)

def handle_admin_approve_user(handler, user_id):
    """API PUT: Approve a pending user account (admin only)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = 'approved' WHERE id = ?", (user_id,))
        if cursor.rowcount == 0:
            conn.close()
            handler._send_json({"error": "Không tìm thấy tài khoản (User not found)"}, 404)
            return
        conn.commit()
        conn.close()
        handler._send_json({"status": "success", "message": "Tài khoản đã được phê duyệt (Account approved)"})
    except Exception as e:
        handler._send_json({"error": f"Failed to approve user: {str(e)}"}, 500)

def handle_admin_set_role(handler, user_id, data):
    """API PUT: Change a user's role (admin only). Body: {"role": "admin"} or {"role": "user"}"""
    new_role = data.get("role", "").strip().lower()
    if new_role not in ("admin", "user"):
        handler._send_json({"error": "Quyền không hợp lệ. Chỉ chấp nhận 'admin' hoặc 'user'. (Invalid role)"}, 400)
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
        if cursor.rowcount == 0:
            conn.close()
            handler._send_json({"error": "Không tìm thấy tài khoản (User not found)"}, 404)
            return
        # Also update any active sessions for this user
        cursor.execute("UPDATE sessions SET role = ? WHERE user_id = ?", (new_role, user_id))
        conn.commit()
        conn.close()
        handler._send_json({"status": "success", "message": f"Đã cập nhật quyền thành '{new_role}' (Role updated)"})
    except Exception as e:
        handler._send_json({"error": f"Failed to update role: {str(e)}"}, 500)

def handle_admin_delete_user(handler, user_id):
    """API DELETE: Delete a user account (admin only)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Prevent deleting yourself
        session = get_current_session(handler)
        if session and session["user_id"] == user_id:
            conn.close()
            handler._send_json({"error": "Không thể xóa tài khoản của chính mình (Cannot delete own account)"}, 400)
            return
        # Delete sessions first, then user
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        if cursor.rowcount == 0:
            conn.close()
            handler._send_json({"error": "Không tìm thấy tài khoản (User not found)"}, 404)
            return
        conn.commit()
        conn.close()
        handler._send_json({"status": "success", "message": "Đã xóa tài khoản (User deleted)"})
    except Exception as e:
        handler._send_json({"error": f"Failed to delete user: {str(e)}"}, 500)
