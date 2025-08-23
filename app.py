import os
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import psycopg
from psycopg.rows import dict_row

# ----- Config -----
app = Flask(__name__)
CORS(app)

ADMIN_USER = "Rynnox226010"
ADMIN_PASS = "Thad1560"
MAX_ATTEMPTS = 5
FAILED_ATTEMPTS = {}
BLOCKED_USERS = {}

# Database connection
DB_HOST = "dpg-d2kguqndiees73c6jh90-a.oregon-postgres.render.com"
DB_PORT = 5432
DB_NAME = "database_azk8"
DB_USER = "database_azk8_user"
DB_PASSWORD = "8fJLBWqwqiDwMWzp8cS7lHHi3spEC4ym"

def get_db_connection():
    return psycopg.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT,
        row_factory=dict_row
    )

# ----- DB Setup -----
def init_db():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
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
        return False

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
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, product, price, condition, room, year, description, image, email FROM products WHERE status='approved'")
        products = cur.fetchall()
    conn.close()
    return jsonify(products)

@app.route("/api/submit", methods=["POST"])
def submit_product():
    data = request.get_json()
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
    image_url = data.get("image", "")

    if not validate_phone(phone):
        return jsonify({"error": "Invalid phone number"}), 400

    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO products (name, phone, email, product, price, condition, room, year, description, image, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')
        """, (name, phone, email, product, price, condition, room, year, description, image_url))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/remove", methods=["POST"])
def remove_ad():
    data = request.get_json()
    product_id = data.get("id")
    email = data.get("email")
    if not product_id or not email:
        return jsonify({"error": "Missing id or email"}), 400

    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM products WHERE id=%s AND email=%s", (product_id, email))
        deleted = cur.rowcount
    conn.commit()
    conn.close()
    if deleted:
        return jsonify({"success": True})
    return jsonify({"error": "No matching ad found"}), 404

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
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, product, price, condition, room, year, description, image, status FROM products")
        products = cur.fetchall()
    conn.close()
    return jsonify(products)

@app.route("/api/admin/approve/<int:pid>", methods=["POST"])
def approve_product(pid):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("UPDATE products SET status='approved' WHERE id=%s", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/admin/reject/<int:pid>", methods=["POST"])
def reject_product(pid):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("UPDATE products SET status='rejected' WHERE id=%s", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/admin/delete/<int:pid>", methods=["DELETE"])
def delete_product(pid):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM products WHERE id=%s", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ----- Run -----
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
