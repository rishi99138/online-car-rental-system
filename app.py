import os
from flask import Flask, render_template, request, redirect, session, url_for
import mysql.connector
from datetime import datetime
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key')

# --- DATABASE CONFIGURATION ---
# Try to import local config, but don't crash if it doesn't exist (like on Vercel)
try:
    from db_config import db_config
except ImportError:
    db_config = None

def get_db_connection():
    # 1. CHECK FOR CLOUD DATABASE (Vercel)
    if os.environ.get('DATABASE_URL'):
        url = urlparse(os.environ.get('DATABASE_URL'))
        return mysql.connector.connect(
            host=url.hostname,
            user=url.username,
            password=url.password,
            database=url.path[1:],
            port=url.port
        )
    
    # 2. FALLBACK TO LOCAL DATABASE (Laptop)
    elif db_config:
        return mysql.connector.connect(**db_config)
    
    else:
        raise Exception("No database configuration found!")

# --- ROUTES ---

@app.route('/')
def home():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM cars WHERE status='Available'")
        cars = cursor.fetchall()
        conn.close()
    except Exception as e:
        return f"Database Error: {e}"
        
    user_name = session.get('user_name')
    return render_template('home.html', cars=cars, user_name=user_name)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['full_name']
        email = request.form['email']
        password = request.form['password']
        license_no = request.form['license_no']
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (full_name, email, password, license_no) VALUES (%s, %s, %s, %s)", 
                           (name, email, password, license_no))
            conn.commit()
            conn.close()
            return redirect('/login')
        except mysql.connector.Error as err:
            return f"Error: {err}"
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s", (email, password))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['user_id']
            session['user_name'] = user['full_name']
            return redirect('/')
        else:
            return "Invalid Credentials! <a href='/login'>Try Again</a>"
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/book/<int:car_id>', methods=['GET', 'POST'])
def book(car_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        start_date_str = request.form['start_date']
        end_date_str = request.form['end_date']
        
        d1 = datetime.strptime(start_date_str, "%Y-%m-%d")
        d2 = datetime.strptime(end_date_str, "%Y-%m-%d")
        days = (d2 - d1).days
        
        if days <= 0:
            return "Error: Return date must be after start date!"
        
        cursor.execute("SELECT price_per_day FROM cars WHERE car_id = %s", (car_id,))
        car = cursor.fetchone()
        total_price = days * car['price_per_day']
        
        user_id = session['user_id']
        cursor.execute("""
            INSERT INTO bookings (user_id, car_id, start_date, end_date, total_amount, booking_status) 
            VALUES (%s, %s, %s, %s, %s, 'Confirmed')
        """, (user_id, car_id, start_date_str, end_date_str, total_price))
        
        cursor.execute("UPDATE cars SET status='Booked' WHERE car_id = %s", (car_id,))
        
        conn.commit()
        conn.close()
        return render_template('confirmation.html', total_price=total_price)

    cursor.execute("SELECT * FROM cars WHERE car_id = %s", (car_id,))
    car = cursor.fetchone()
    conn.close()
    return render_template('booking.html', car=car)

@app.route('/admin')
def admin():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT bookings.booking_id, bookings.start_date, bookings.end_date, bookings.total_amount,
               users.full_name,
               cars.car_id, cars.brand, cars.model_name
        FROM bookings
        JOIN users ON bookings.user_id = users.user_id
        JOIN cars ON bookings.car_id = cars.car_id
        WHERE bookings.booking_status = 'Confirmed'
    """
    cursor.execute(query)
    bookings = cursor.fetchall()
    conn.close()
    return render_template('admin.html', bookings=bookings)

@app.route('/return/<int:booking_id>/<int:car_id>')
def return_car(booking_id, car_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE bookings SET booking_status='Completed' WHERE booking_id = %s", (booking_id,))
    cursor.execute("UPDATE cars SET status='Available' WHERE car_id = %s", (car_id,))
    conn.commit()
    conn.close()
    return redirect('/admin')

# Vercel requires this
app = app

if __name__ == '__main__':
    app.run(debug=True)