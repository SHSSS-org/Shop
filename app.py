import os
import sqlite3
import re
import secrets
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_from_directory, abort
from werkzeug.utils import secure_filename
from flask_cors import CORS

# --- Config ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "marketplace.db")
UPLOAD_DIR = os.path.join(APP_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ADMIN_USER = "Rynnox226010"
ADMIN_PASS = "Thad1560"
MAX_LOGIN_ATTEMPTS = 5

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = secrets.token_hex(16)
CORS(app)

# Track login attempts
login_attempts = {}

# --- DB Init ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        condition TEXT,
        room_no TEXT,
        seller TEXT,
        year TEXT,
        email TEXT,
        phone TEXT,
        description TEXT,
        price REAL,
        image TEXT,
        approved INTEGER DEFAULT 0
    )""")
    conn.commit()
    conn.close()

init_db()

# --- Helpers ---
def check_phone(phone):
    """Validate phone number (10 digits only)."""
    return re.match(r"^[0-9]{10}$", phone)

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper

# --- Routes ---

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/submit")
def submit_page():
    return render_template("submit.html")

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    ip = request.remote_addr
    if ip not in login_attempts:
        login_attempts[ip] = {"count": 0, "blocked_until": None}

    attempt = login_attempts[ip]

    if attempt["blocked_until"] and datetime.now() < attempt["blocked_until"]:
        return "Too many failed attempts. Try again later.", 403

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == ADMIN_USER and password == ADMIN_PASS:
            session["logged_in"] = True
            login_attempts[ip] = {"count": 0, "blocked_until": None}
            return redirect(url_for("admin_panel"))
        else:
            attempt["count"] += 1
            if attempt["count"] >= MAX_LOGIN_ATTEMPTS:
                attempt["blocked_until"] = datetime.now() + timedelta(minutes=10)
            return "Invalid credentials", 403

    return render_template("admin.html")

@app.route("/admin/panel")
@login_required
def admin_panel():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM products")
    products = c.fetchall()
    conn.close()
    return render_template("admin_panel.html", products=products)

@app.route("/api/products")
def get_products():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE approved=1")
    rows = c.fetchall()
    conn.close()
    products = []
    for r in rows:
        products.append({
            "id": r[0], "name": r[1], "condition": r[2],
            "room_no": r[3], "seller": r[4], "year": r[5],
            "email": r[6], "phone": r[7], "description": r[8],
            "price": r[9], "image": r[10]
        })
    return jsonify(products)

@app.route("/api/submit", methods=["POST"])
def submit_product():
    data = request.form
    file = request.files.get("image")

    if not check_phone(data.get("phone", "")):
        return jsonify({"error": "Invalid phone number format"}), 400

    filename = None
    if file:
        filename = secure_filename(file.filename)
        file.save(os.path.join(UPLOAD_DIR, filename))
        filename = f"/static/uploads/{filename}"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO products
        (name, condition, room_no, seller, year, email, phone, description, price, image, approved)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (data["name"], data["condition"], data["room_no"], data.get("seller"),
         data.get("year"), data["email"], data["phone"], data["description"], data["price"], filename))
    conn.commit()
    conn.close()
    return jsonify({"message": "Submitted successfully, pending approval"})

@app.route("/api/admin/approve/<int:pid>", methods=["POST"])
@login_required
def approve_product(pid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE products SET approved=1 WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))

@app.route("/api/admin/reject/<int:pid>", methods=["POST"])
@login_required
def reject_product(pid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))

@app.route("/api/admin/delete/<int:pid>", methods=["POST"])
@login_required
def delete_product(pid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))

if __name__ == "__main__":
    app.run(debug=True)
