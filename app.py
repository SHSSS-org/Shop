import os
import sqlite3
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta

# ----- Config -----
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "marketplace.db")

app = Flask(__name__)
CORS(app)

ADMIN_USER = "Rynnox226010"
ADMIN_PASS = "Thad1560"
MAX_ATTEMPTS = 5
FAILED_ATTEMPTS = {}
BLOCKED_USERS = {}

# ----- DB Setup -----
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            email TEXT,
            product TEXT,
            price REAL,
            condition TEXT,
            room TEXT,
            year TEXT,
            description TEXT,
            image TEXT,
            status TEXT DEFAULT 'pending',
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ----- Helpers -----
def validate_phone(phone):
    return re.fullmatch(r"\d{10}", phone) is not None

def record_attempt(ip, success):
    now = datetime.now()
    if ip in BLOCKED_USERS and now < BLOCKED_USERS[ip]:
        return False  # blocked

    if success:
        FAILED_ATTEMPTS[ip] = 0
        return True
    else:
        FAILED_ATTEMPTS[ip] = FAILED_ATTEMPTS.get(ip, 0) + 1
        if FAILED_ATTEMPTS[ip] >= MAX_ATTEMPTS:
            BLOCKED_USERS[ip] = now + timedelta(minutes=15)
        return False

# ----- Routes -----
@app.route("/api/products", methods=["GET"])
def get_products():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, product, price, condition, room, year, description, image, email FROM products WHERE status='approved'")
    rows = c.fetchall()
    conn.close()
    products = [
        {
            "id": r[0],
            "name": r[1],
            "product": r[2],
            "price": r[3],
            "condition": r[4],
            "room": r[5],
            "year": r[6],
            "description": r[7],
            "image": r[8],
            "email": r[9]
        }
        for r in rows
    ]
    return jsonify(products)

@app.route("/api/submit", methods=["POST"])
def submit_product():
    data = request.get_json()  # <-- Read JSON from frontend
    if not data:
        return jsonify({"error": "No JSON data received"}), 400

    name = data.get("name", "")
    phone = data.get("phone", "")
    email = data.get("email", "")
    product = data.get("product", "")
    price = data.get("price", 0)
    condition = data.get("condition", "")
    room = data.get("room", "")
    year = data.get("year", "")
    description = data.get("description", "")
    image_url = data.get("image", "")  # <-- take image URL from user

    if not validate_phone(phone):
        return jsonify({"error": "Invalid phone number"}), 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO products (name, phone, email, product, price, condition, room, year, description, image, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    """, (name, phone, email, product, price, condition, room, year, description, image_url))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ----- Admin Routes -----
@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    ip = request.remote_addr
    data = request.get_json()
    username = data.get("username", "")
    password = data.get("password", "")

    if ip in BLOCKED_USERS and datetime.now() < BLOCKED_USERS[ip]:
        return jsonify({"error": "Too many attempts. Try later."}), 403

    if username == ADMIN_USER and password == ADMIN_PASS:
        record_attempt(ip, True)
        return jsonify({"success": True})
    else:
        record_attempt(ip, False)
        return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/admin/products", methods=["GET"])
def admin_products():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, product, price, condition, room, year, description, image, status FROM products")
    rows = c.fetchall()
    conn.close()
    products = [
        {
            "id": r[0],
            "name": r[1],
            "product": r[2],
            "price": r[3],
            "condition": r[4],
            "room": r[5],
            "year": r[6],
            "description": r[7],
            "image": r[8],
            "status": r[9]
        }
        for r in rows
    ]
    return jsonify(products)

@app.route("/api/admin/approve/<int:pid>", methods=["POST"])
def approve_product(pid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE products SET status='approved' WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/admin/reject/<int:pid>", methods=["POST"])
def reject_product(pid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE products SET status='rejected' WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/admin/delete/<int:pid>", methods=["DELETE"])
def delete_product(pid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ----- Run -----
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
