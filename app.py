import os
import sqlite3
import hashlib
from datetime import date
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(APP_DIR, "static")

app = Flask(__name__, static_folder=STATIC_DIR)
app.secret_key = os.urandom(24)
CORS(app)

DB_PATH = os.path.join(APP_DIR, "marketplace.db")


# ---------- DB ----------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
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
            last_request_date DATE
        )
        """
    )

    # seed admin
    default_user = "admin"
    default_pass_hash = hashlib.sha256("admin123".encode()).hexdigest()
    c.execute(
        "INSERT OR IGNORE INTO admin (username, password_hash) VALUES (?, ?)",
        (default_user, default_pass_hash),
    )

    conn.commit()
    conn.close()


init_db()


# ---------- Helpers ----------
def check_ip_limit(ip_address: str, daily_limit: int = 10) -> bool:
    """Simple per-IP daily counter in SQLite."""
    conn = get_db()
    c = conn.cursor()
    today = date.today().isoformat()

    c.execute("SELECT request_count, last_request_date FROM ip_limits WHERE ip_address = ?", (ip_address,))
    row = c.fetchone()

    if row is None:
        c.execute(
            "INSERT INTO ip_limits (ip_address, request_count, last_request_date) VALUES (?, ?, ?)",
            (ip_address, 1, today),
        )
        conn.commit()
        conn.close()
        return True

    count, last_date = row["request_count"], row["last_request_date"]
    if last_date != today:
        c.execute(
            "UPDATE ip_limits SET request_count = 1, last_request_date = ? WHERE ip_address = ?",
            (today, ip_address),
        )
        conn.commit()
        conn.close()
        return True

    if count < daily_limit:
        c.execute("UPDATE ip_limits SET request_count = request_count + 1 WHERE ip_address = ?", (ip_address,))
        conn.commit()
        conn.close()
        return True

    conn.close()
    return False


def clean_int(value):
    """Return int or None from form/JSON."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


# ---------- Routes: Frontend ----------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_files(path):
    """Serve any other static asset (CSS, JS, images)."""
    full = os.path.join(app.static_folder, path)
    if os.path.isfile(full):
        return send_from_directory(app.static_folder, path)
    # Fallback for client-side routing (if any)
    return send_from_directory(app.static_folder, "index.html")


@app.get("/health")
def health():
    return {"ok": True}


# ---------- Routes: Public API ----------
@app.get("/api/products")
def get_products():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE status = 'approved' ORDER BY created_at DESC")
    products = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(products)


@app.post("/api/products")
def add_product():
    data = request.get_json(force=True, silent=True) or {}
    ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"

    # IP limit
    if not check_ip_limit(ip):
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

    conn = get_db()
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
    product_id = c.lastrowid
    conn.commit()
    conn.close()

    return jsonify(
        {
            "success": True,
            "message": "Product submitted. Visible after admin approval.",
            "product_id": product_id,
        }
    )


# ---------- Routes: Admin (simple, no session) ----------
@app.post("/api/admin/login")
def admin_login():
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"success": False, "message": "Username and password required"}), 400

    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM admin WHERE username = ? AND password_hash = ?", (username, pw_hash))
    row = c.fetchone()
    conn.close()

    if row:
        return jsonify({"success": True, "message": "Login ok"})
    return jsonify({"success": False, "message": "Invalid credentials"}), 401


@app.get("/api/admin/products")
def admin_list_products():
    status = request.args.get("status", "pending")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE status = ? ORDER BY created_at DESC", (status,))
    products = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(products)


@app.put("/api/admin/products/<int:product_id>")
def admin_update_product(product_id):
    data = request.get_json(force=True, silent=True) or {}
    status = data.get("status")
    if status not in {"pending", "approved"}:
        return jsonify({"success": False, "message": "Status must be 'pending' or 'approved'"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE products SET status = ? WHERE id = ?", (status, product_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Product status updated"})


@app.delete("/api/admin/products/<int:product_id>")
def admin_delete_product(product_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Product deleted"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=False)
