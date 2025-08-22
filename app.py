import os
import sqlite3
import hashlib
import secrets
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS

# ----- App setup -----
APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(APP_DIR, "static")
DB_PATH = os.path.join(APP_DIR, "marketplace.db")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))
CORS(app)  # Same-origin by default; harmless if served from same host


# ----- DB helpers -----
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          seller_name TEXT NOT NULL,
          seller_email TEXT NOT NULL,
          product_name TEXT NOT NULL,
          product_condition TEXT NOT NULL,
          room_number TEXT NOT NULL,
          year_bought INTEGER,
          image_url TEXT NOT NULL,
          description TEXT NOT NULL,
          ip_address TEXT NOT NULL,
          status TEXT DEFAULT 'pending',
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS admin (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS ip_limits (
          ip_address TEXT PRIMARY KEY,
          request_count INTEGER DEFAULT 0,
          last_request_date TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_sessions (
          token TEXT PRIMARY KEY,
          username TEXT NOT NULL,
          expires_at TEXT NOT NULL
        )
        """
    )

    # Seed default admin if missing
    default_user = "admin"
    default_hash = hashlib.sha256("admin123".encode()).hexdigest()
    c.execute(
        "INSERT OR IGNORE INTO admin (username, password_hash) VALUES (?, ?)",
        (default_user, default_hash),
    )

    conn.commit()
    conn.close()


init_db()


# ----- Utilities -----
def client_ip():
    # Render/Proxies place original IP in X-Forwarded-For
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


def within_ip_daily_limit(ip: str, limit: int = 10) -> bool:
    """Simple per-IP daily counter using SQLite."""
    today = datetime.utcnow().date().isoformat()
    conn = db()
    c = conn.cursor()

    c.execute("SELECT request_count, last_request_date FROM ip_limits WHERE ip_address = ?", (ip,))
    row = c.fetchone()

    if row is None:
        c.execute(
            "INSERT INTO ip_limits (ip_address, request_count, last_request_date) VALUES (?, ?, ?)",
            (ip, 1, today),
        )
        conn.commit()
        conn.close()
        return True

    count, last_date = row["request_count"], row["last_request_date"]
    if last_date != today:
        c.execute(
            "UPDATE ip_limits SET request_count = 1, last_request_date = ? WHERE ip_address = ?",
            (today, ip),
        )
        conn.commit()
        conn.close()
        return True

    if count < limit:
        c.execute(
            "UPDATE ip_limits SET request_count = request_count + 1 WHERE ip_address = ?",
            (ip,),
        )
        conn.commit()
        conn.close()
        return True

    conn.close()
    return False


def clean_int(x):
    if x is None:
        return None
    try:
        return int(str(x).strip())
    except Exception:
        return None


# ----- Admin auth (token) -----
def create_session(username: str, hours: int = 12) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.utcnow() + timedelta(hours=hours)).isoformat()
    conn = db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO admin_sessions (token, username, expires_at) VALUES (?, ?, ?)",
        (token, username, expires),
    )
    conn.commit()
    conn.close()
    return token


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"success": False, "message": "Unauthorized"}), 401
        token = auth.split(" ", 1)[1].strip()
        now = datetime.utcnow().isoformat()
        conn = db()
        c = conn.cursor()
        c.execute(
            "SELECT token FROM admin_sessions WHERE token = ? AND expires_at > ?",
            (token, now),
        )
        row = c.fetchone()
        conn.close()
        if not row:
            return jsonify({"success": False, "message": "Unauthorized"}), 401
        return fn(*args, **kwargs)

    return wrapper


# ----- Frontend -----
@app.route("/")
def index():
    # Serve the SPA
    return send_from_directory(STATIC_DIR, "index.html")


# ----- Public API -----
@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/products")
def list_products():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE status = 'approved' ORDER BY created_at DESC")
    products = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(products)


@app.post("/api/products")
def submit_product():
    data = request.get_json(force=True, silent=True) or {}
    ip = client_ip()

    if not within_ip_daily_limit(ip, limit=10):
        return jsonify({"success": False, "message": "Daily limit reached (10 listings per IP)."}), 429

    required = [
        "seller_name",
        "seller_email",
        "product_name",
        "product_condition",
        "room_number",
        "image_url",
        "description",
    ]
    for f in required:
        if not str(data.get(f, "")).strip():
            return jsonify({"success": False, "message": f"Missing required field: {f}"}), 400

    year_bought = clean_int(data.get("year_bought"))

    conn = db()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO products
        (seller_name, seller_email, product_name, product_condition,
         room_number, year_bought, image_url, description, ip_address)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["seller_name"].strip(),
            data["seller_email"].strip(),
            data["product_name"].strip(),
            data["product_condition"].strip(),
            data["room_number"].strip(),
            year_bought,
            data["image_url"].strip(),
            data["description"].strip(),
            ip,
        ),
    )
    pid = c.lastrowid
    conn.commit()
    conn.close()

    return jsonify(
        {"success": True, "message": "Product submitted. Visible after admin approval.", "product_id": pid}
    )


# ----- Admin API -----
@app.post("/api/admin/login")
def admin_login():
    data = request.get_json(force=True, silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()
    if not username or not password:
        return jsonify({"success": False, "message": "Username and password required"}), 400

    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id FROM admin WHERE username = ? AND password_hash = ?", (username, pw_hash))
    ok = c.fetchone()
    conn.close()

    if not ok:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    token = create_session(username)
    return jsonify({"success": True, "message": "Login successful", "token": token})


@app.get("/api/admin/products")
@require_admin
def admin_products():
    status = request.args.get("status", "pending")
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE status = ? ORDER BY created_at DESC", (status,))
    products = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(products)


@app.put("/api/admin/products/<int:product_id>")
@require_admin
def admin_update_product(product_id: int):
    data = request.get_json(force=True, silent=True) or {}
    status = data.get("status")
    if status not in {"pending", "approved"}:
        return jsonify({"success": False, "message": "Status must be 'pending' or 'approved'"}), 400

    conn = db()
    c = conn.cursor()
    c.execute("UPDATE products SET status = ? WHERE id = ?", (status, product_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Product status updated"})


@app.delete("/api/admin/products/<int:product_id>")
@require_admin
def admin_delete_product(product_id: int):
    conn = db()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Product deleted"})


# ----- Static fallback for assets -----
@app.route("/<path:path>")
def send_asset(path):
    file_path = os.path.join(STATIC_DIR, path)
    if os.path.isfile(file_path):
        return send_from_directory(STATIC_DIR, path)
    # Unknown path → SPA index
    if not path.startswith("api/"):
        return send_from_directory(STATIC_DIR, "index.html")
    return abort(404)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=False)
