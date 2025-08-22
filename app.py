# app.py
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import sqlite3
from datetime import datetime, date
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Initialize rate limiter
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
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 product_name TEXT NOT NULL,
                 product_condition TEXT NOT NULL,
                 room_number TEXT NOT NULL,
                 seller_name TEXT NOT NULL,
                 seller_email TEXT NOT NULL,
                 seller_phone TEXT,
                 year_bought INTEGER,
                 image_link TEXT NOT NULL,
                 description TEXT NOT NULL,
                 ip_address TEXT NOT NULL,
                 created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 status TEXT DEFAULT 'pending')''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS admin_users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 username TEXT UNIQUE NOT NULL,
                 password_hash TEXT NOT NULL)''')
    
    # Insert default admin user if not exists
    c.execute("SELECT COUNT(*) FROM admin_users")
    if c.fetchone()[0] == 0:
        # In production, use proper password hashing like bcrypt
        c.execute("INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
                  ('admin', 'password'))  # Change this in production
    
    conn.commit()
    conn.close()

# Initialize the database
init_db()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/marketplace')
def marketplace():
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    c.execute("SELECT * FROM items WHERE status='approved' ORDER BY created_date DESC")
    items = c.fetchall()
    conn.close()
    
    # Convert to list of dictionaries
    items_list = []
    for item in items:
        items_list.append({
            'id': item[0],
            'product_name': item[1],
            'product_condition': item[2],
            'room_number': item[3],
            'seller_name': item[4],
            'seller_email': item[5],
            'seller_phone': item[6],
            'year_bought': item[7],
            'image_link': item[8],
            'description': item[9],
            'created_date': item[11]
        })
    
    return render_template('marketplace.html', items=items_list)

@app.route('/list-item', methods=['GET', 'POST'])
@limiter.limit("10 per day")  # Limit to 10 submissions per day per IP
def list_item():
    if request.method == 'POST':
        # Get form data
        product_name = request.form.get('product_name')
        product_condition = request.form.get('product_condition')
        room_number = request.form.get('room_number')
        seller_name = request.form.get('seller_name')
        seller_email = request.form.get('seller_email')
        seller_phone = request.form.get('seller_phone')
        year_bought = request.form.get('year_bought')
        image_link = request.form.get('image_link')
        description = request.form.get('description')
        ip_address = get_remote_address()
        
        # Save to database
        conn = sqlite3.connect('marketplace.db')
        c = conn.cursor()
        c.execute('''INSERT INTO items 
                     (product_name, product_condition, room_number, seller_name, 
                      seller_email, seller_phone, year_bought, image_link, description, ip_address)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (product_name, product_condition, room_number, seller_name, 
                   seller_email, seller_phone, year_bought, image_link, description, ip_address))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Item submitted for approval'})
    
    return render_template('list_item.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Verify credentials (in production, use proper password hashing)
        conn = sqlite3.connect('marketplace.db')
        c = conn.cursor()
        c.execute("SELECT * FROM admin_users WHERE username = ? AND password_hash = ?", 
                  (username, password))
        user = c.fetchone()
        conn.close()
        
        if user:
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error='Invalid credentials')
    
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    # Get pending items
    c.execute("SELECT * FROM items WHERE status='pending' ORDER BY created_date DESC")
    pending_items = c.fetchall()
    
    # Get approved items
    c.execute("SELECT * FROM items WHERE status='approved' ORDER BY created_date DESC")
    approved_items = c.fetchall()
    
    conn.close()
    
    return render_template('admin_dashboard.html', 
                          pending_items=pending_items, 
                          approved_items=approved_items)

@app.route('/admin/approve/<int:item_id>')
def approve_item(item_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    c.execute("UPDATE items SET status='approved' WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:item_id>')
def delete_item(item_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    c.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect(url_for('admin_login'))

if __name__ == '__main__':
    app.run(debug=True)