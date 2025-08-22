from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime, date
import hashlib

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# Initialize rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

# Database setup
def init_db():
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    # Create products table
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Create admin table
    c.execute('''CREATE TABLE IF NOT EXISTS admin
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 username TEXT UNIQUE NOT NULL,
                 password_hash TEXT NOT NULL)''')
    
    # Create IP limits table
    c.execute('''CREATE TABLE IF NOT EXISTS ip_limits
                 (ip_address TEXT PRIMARY KEY,
                 request_count INTEGER DEFAULT 0,
                 last_request_date DATE)''')
    
    # Insert default admin user if not exists
    password_hash = hashlib.sha256('admin123'.encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO admin (username, password_hash) VALUES (?, ?)", 
              ('admin', password_hash))
    
    conn.commit()
    conn.close()

init_db()

# Helper function to get database connection
def get_db():
    conn = sqlite3.connect('marketplace.db')
    conn.row_factory = sqlite3.Row
    return conn

# Check IP rate limit
def check_ip_limit(ip_address):
    conn = get_db()
    c = conn.cursor()
    
    today = date.today().isoformat()
    
    c.execute("SELECT * FROM ip_limits WHERE ip_address = ?", (ip_address,))
    ip_data = c.fetchone()
    
    if ip_data:
        if ip_data['last_request_date'] != today:
            # Reset counter for new day
            c.execute("UPDATE ip_limits SET request_count = 1, last_request_date = ? WHERE ip_address = ?", 
                     (today, ip_address))
            conn.commit()
            conn.close()
            return True
        elif ip_data['request_count'] < 10:
            # Increment counter
            c.execute("UPDATE ip_limits SET request_count = request_count + 1 WHERE ip_address = ?", 
                     (ip_address,))
            conn.commit()
            conn.close()
            return True
        else:
            # Limit exceeded
            conn.close()
            return False
    else:
        # First request from this IP today
        c.execute("INSERT INTO ip_limits (ip_address, request_count, last_request_date) VALUES (?, ?, ?)", 
                 (ip_address, 1, today))
        conn.commit()
        conn.close()
        return True

# Routes
@app.route('/api/products', methods=['GET'])
def get_products():
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM products WHERE status = 'approved' ORDER BY created_at DESC")
    products = c.fetchall()
    
    conn.close()
    
    # Convert rows to dictionaries
    products_list = [dict(product) for product in products]
    return jsonify(products_list)

@app.route('/api/products', methods=['POST'])
@limiter.limit("10 per day")
def add_product():
    data = request.json
    ip_address = request.remote_addr
    
    # Check IP-based rate limit
    if not check_ip_limit(ip_address):
        return jsonify({
            'success': False,
            'message': 'You have exceeded the daily limit of 10 product listings.'
        }), 429
    
    # Validate required fields
    required_fields = ['seller_name', 'seller_email', 'product_name', 
                       'product_condition', 'room_number', 'image_url', 'description']
    for field in required_fields:
        if field not in data or not data[field].strip():
            return jsonify({
                'success': False,
                'message': f'Missing required field: {field}'
            }), 400
    
    # Insert product into database
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''INSERT INTO products 
                 (seller_name, seller_email, product_name, product_condition, 
                  room_number, year_bought, image_url, description, ip_address) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (data['seller_name'], data['seller_email'], data['product_name'],
               data['product_condition'], data['room_number'], data.get('year_bought'),
               data['image_url'], data['description'], ip_address))
    
    conn.commit()
    product_id = c.lastrowid
    conn.close()
    
    return jsonify({
        'success': True,
        'message': 'Product listed successfully. It will be visible after admin approval.',
        'product_id': product_id
    })

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    
    if 'username' not in data or 'password' not in data:
        return jsonify({
            'success': False,
            'message': 'Username and password required'
        }), 400
    
    username = data['username']
    password = data['password']
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM admin WHERE username = ? AND password_hash = ?", 
              (username, password_hash))
    admin = c.fetchone()
    conn.close()
    
    if admin:
        return jsonify({
            'success': True,
            'message': 'Login successful'
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Invalid username or password'
        }), 401

@app.route('/api/admin/products', methods=['GET'])
def get_admin_products():
    # In a real implementation, this would check for admin authentication
    status = request.args.get('status', 'pending')
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM products WHERE status = ? ORDER BY created_at DESC", (status,))
    products = c.fetchall()
    
    conn.close()
    
    products_list = [dict(product) for product in products]
    return jsonify(products_list)

@app.route('/api/admin/products/<int:product_id>', methods=['PUT'])
def update_product_status(product_id):
    # In a real implementation, this would check for admin authentication
    data = request.json
    
    if 'status' not in data:
        return jsonify({
            'success': False,
            'message': 'Status field is required'
        }), 400
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("UPDATE products SET status = ? WHERE id = ?", (data['status'], product_id))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': 'Product status updated'
    })

@app.route('/api/admin/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    # In a real implementation, this would check for admin authentication
    conn = get_db()
    c = conn.cursor()
    
    c.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': 'Product deleted'
    })

if __name__ == '__main__':
    app.run(debug=True)
