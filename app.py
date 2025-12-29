from datetime import datetime
from flask import Flask, render_template, request, redirect, session, url_for
import mysql.connector
from db_config import db_config

app = Flask(__name__)
app.secret_key = 'super_secret_key_123'  # Needed to keep users logged in

# --- Database Connection Helper ---
def get_db_connection():
    return mysql.connector.connect(**db_config)

# --- ROUTES ---

@app.route('/')
def home():
    # 1. Connect to DB
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 2. Fetch all cars that are 'Available'
    cursor.execute("SELECT * FROM cars WHERE status='Available'")
    cars = cursor.fetchall()
    conn.close()
    
    # 3. Check if user is logged in (to show their name)
    user_name = session.get('user_name')
    
    # 4. Send data to HTML
    return render_template('home.html', cars=cars, user_name=user_name)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get data from HTML form
        name = request.form['full_name']
        email = request.form['email']
        password = request.form['password'] 
        license_no = request.form['license_no']
        
        # Insert into Database
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (full_name, email, password, license_no) VALUES (%s, %s, %s, %s)", 
                           (name, email, password, license_no))
            conn.commit()
            return redirect('/login') # Go to login after success
        except mysql.connector.Error as err:
            return f"Error: {err}"
        finally:
            conn.close()
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Check Database
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s", (email, password))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            # Login Success: Save user info in session
            session['user_id'] = user['user_id']
            session['user_name'] = user['full_name']
            return redirect('/') # Go to Home Page
        else:
            return "Invalid Credentials! <a href='/login'>Try Again</a>"
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# --- BOOKING ROUTE ---
@app.route('/book/<int:car_id>', methods=['GET', 'POST'])
def book(car_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        # 1. Get Dates from Form
        start_date_str = request.form['start_date']
        end_date_str = request.form['end_date']
        
        # 2. Calculate Number of Days
        d1 = datetime.strptime(start_date_str, "%Y-%m-%d")
        d2 = datetime.strptime(end_date_str, "%Y-%m-%d")
        delta = d2 - d1
        days = delta.days
        
        if days <= 0:
            return "Error: Return date must be after start date!"
        
        # 3. Get Car Price to Calculate Total
        cursor.execute("SELECT price_per_day FROM cars WHERE car_id = %s", (car_id,))
        car = cursor.fetchone()
        total_price = days * car['price_per_day']
        
        # 4. Save Booking to Database
        user_id = session['user_id']
        cursor.execute("""
            INSERT INTO bookings (user_id, car_id, start_date, end_date, total_amount, booking_status) 
            VALUES (%s, %s, %s, %s, %s, 'Confirmed')
        """, (user_id, car_id, start_date_str, end_date_str, total_price))
        
        # 5. Update Car Status to 'Booked' (so no one else can book it)
        cursor.execute("UPDATE cars SET status='Booked' WHERE car_id = %s", (car_id,))
        
        conn.commit()
        conn.close()
        
        return render_template('confirmation.html', total_price=total_price)

    # --- GET REQUEST (Show the Form) ---
    cursor.execute("SELECT * FROM cars WHERE car_id = %s", (car_id,))
    car = cursor.fetchone()
    conn.close()
    
    return render_template('booking.html', car=car)

# --- ADMIN ROUTES ---

@app.route('/admin')
def admin():
    # In a real app, you would check if session['user_name'] == 'admin'
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Complex Query: Join Bookings, Users, and Cars tables
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
    
    # 1. Update Booking Status to 'Completed'
    cursor.execute("UPDATE bookings SET booking_status='Completed' WHERE booking_id = %s", (booking_id,))
    
    # 2. Make Car Available again
    cursor.execute("UPDATE cars SET status='Available' WHERE car_id = %s", (car_id,))
    
    conn.commit()
    conn.close()
    
    return redirect('/admin')

# --- RUN SERVER ---
if __name__ == '__main__':
    app.run(debug=True)