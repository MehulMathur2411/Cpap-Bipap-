import os
import json
import time
import sqlite3
from datetime import datetime
from concurrent.futures import Future
from threading import Thread
from flask import Flask, request, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder
import io as python_io  
import csv
from fpdf import FPDF

from mqtt import get_db_connection  

#---------- Configuration ----------
app = Flask(__name__)

# AWS IoT Configuration (from api.py)
ENDPOINT = "a2jqpfwttlq1yk-ats.iot.us-east-1.amazonaws.com"
CLIENT_ID = "backend-capturer" 
BASE_PATH = r"C:\Users\tanya\OneDrive\Desktop\CPAP\AWS"  
PATH_TO_CERTIFICATE = os.path.join(BASE_PATH, "6e5d12437ffc7b19a750505da172d382b6e81026243aa254bce059b8bc45796f-certificate.pem.crt")
PATH_TO_PRIVATE_KEY = os.path.join(BASE_PATH, "6e5d12437ffc7b19a750505da172d382b6e81026243aa254bce059b8bc45796f-private.pem.key")
PATH_TO_AMAZON_ROOT_CA = os.path.join(BASE_PATH, "AmazonRootCA1.pem")

TOPIC = "esp32/data1"  
ACK_TOPIC = "esp32/data" 

# Database Configuration
DB_FILE = "bipap_backend.db"

# Global variables for IoT
is_connected = False
mqtt_connection = None

# ---------- Database Setup ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            contact TEXT NOT NULL,
            address TEXT NOT NULL,
            password TEXT NOT NULL,
            serial_no TEXT NOT NULL
        )
    ''')
    # Settings table (per user, JSON blob for flexibility)
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            email TEXT PRIMARY KEY,
            settings_json TEXT NOT NULL,
            FOREIGN KEY (email) REFERENCES users(email)
        )
    ''')
    # Device data table (captured from IoT)
    c.execute('''
        CREATE TABLE IF NOT EXISTS device_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial_no TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            device_status INTEGER,
            device_data TEXT,
            parsed_data JSON
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def fetch_new_user_data(email):
    """
    Try to fetch user row from the local database and return it as a dict,
    or return None if not found or on error.
    """
    try:
        conn = get_db_connection()
        if not conn:
            return None
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if not row:
            return None
        # Map row to dict using cursor description
        columns = [col[0] for col in cursor.description]
        user = dict(zip(columns, row))
        return user
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass

# ---------- IoT Callbacks ----------
def on_message_received(topic, payload, dup, qos, retain, **kwargs):
    try:
        message = json.loads(payload.decode('utf-8'))
        print(f"Captured data from topic '{topic}': {message}")
        
        # Extract data
        device_status = message.get("device_status")
        device_data = message.get("device_data")
        serial_no = None
        parsed_data = {}
        
        # Parse device_data if present (based on sample: "*,141025,141025,1300,1400,1,1,5,8,5,4,2,9,1,8,12345678,#")
        if device_data:
            parts = device_data.strip("*,#").split(",")
            if len(parts) >= 16:  
                
                parsed_data = {
                    "field1": parts[0], 
                    "field2": parts[1],  
                    "field3": parts[2],  
                    "field4": parts[3],  
                    "serial_no": parts[-1]  
                }
                serial_no = parsed_data["serial_no"]
        
        if not serial_no:
            print("No serial_no found in data. Skipping save.")
            return
        
        # Save to DB
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO device_data (serial_no, timestamp, device_status, device_data, parsed_data)
            VALUES (?, ?, ?, ?, ?)
        ''', (serial_no, datetime.now(), device_status, device_data, json.dumps(parsed_data)))
        conn.commit()
        conn.close()
        
        print(f"Data captured and saved for serial_no: {serial_no}")
        
        # Optionally send ACK
        if mqtt_connection and is_connected:
            ack_message = {"acknowledgment": 1}
            mqtt_connection.publish(topic=ACK_TOPIC, payload=json.dumps(ack_message), qos=mqtt.QoS.AT_LEAST_ONCE)
            print("ACK sent.")
        
    except Exception as e:
        print(f"Error processing captured message: {e}")

def on_connection_interrupted(connection, error, **kwargs):
    global is_connected
    is_connected = False
    print(f"Connection interrupted: {error}")

def on_connection_resumed(connection, return_code, session_present, **kwargs):
    global is_connected
    is_connected = True
    print(f"Connection resumed: {return_code}, session_present: {session_present}")

# ---------- IoT Connection Setup ----------
def setup_iot_connection():
    global mqtt_connection, is_connected
    io.init_logging(io.LogLevel.Error, 'stderr')
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=ENDPOINT,
        cert_filepath=PATH_TO_CERTIFICATE,
        pri_key_filepath=PATH_TO_PRIVATE_KEY,
        client_bootstrap=client_bootstrap,
        ca_filepath=PATH_TO_AMAZON_ROOT_CA,
        on_connection_interrupted=on_connection_interrupted,
        on_connection_resumed=on_connection_resumed,
        client_id=CLIENT_ID,
        clean_session=False,
        keep_alive_secs=30
    )

    # Connect with retry
    while not is_connected:
        try:
            connect_future: Future = mqtt_connection.connect()
            connect_future.result(timeout=10)
            is_connected = True
            print("Backend connected to AWS IoT Core.")
            
            # Subscribe to topic
            subscribe_future, _ = mqtt_connection.subscribe(
                topic=TOPIC,
                qos=mqtt.QoS.AT_LEAST_ONCE,
                callback=on_message_received
            )
            subscribe_future.result(timeout=10)
            print(f"Subscribed to {TOPIC}.")
        except Exception as e:
            print(f"Connection failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)

# Start IoT in a thread
iot_thread = Thread(target=setup_iot_connection)
iot_thread.daemon = True
iot_thread.start()

# ---------- API Endpoints ----------
# User Registration
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    required_fields = ["name", "contact", "address", "password", "email", "serial_no"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400
    
    email = data["email"]
    password_hash = generate_password_hash(data["password"])
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO users (email, name, contact, address, password, serial_no)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (email, data["name"], data["contact"], data["address"], password_hash, data["serial_no"]))
        conn.commit()
        
        # Initialize default settings
        default_settings = {  
            "CPAP": {"Set Pressure": 4.0},
            
        } 
        c.execute('''
            INSERT INTO settings (email, settings_json)
            VALUES (?, ?)
        ''', (email, json.dumps(default_settings)))
        conn.commit()
        
        return jsonify({"message": "User registered successfully"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "User already exists"}), 409
    finally:
        conn.close()

# User Login
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    if not data or "email" not in data or "password" not in data:
        return jsonify({"error": "Missing email or password"}), 400
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email = ?", (data["email"],))
    user = c.fetchone()
    conn.close()

    if user and check_password_hash(user[4], data["password"]):  
        return jsonify({
            "name": user[1],
            "contact": user[2],
            "address": user[3],
            "email": user[0],
            "serial_no": user[5]
        }), 200
    return jsonify({"error": "Invalid credentials"}), 401

# Get Settings
@app.route('/settings/<email>', methods=['GET'])
def get_settings(email):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT settings_json FROM settings WHERE email = ?", (email,))
    settings = c.fetchone()
    conn.close()
    settings = c.fetchone()

    if settings:
        return jsonify(json.loads(settings[0])), 200
    return jsonify({"error": "Settings not found"}), 404

# Save Settings
@app.route('/settings/<email>', methods=['POST'])
def save_settings(email):
    data = request.json
    if not data:
        return jsonify({"error": "No settings provided"}), 400
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE settings SET settings_json = 1 WHERE email = 3", (json.dumps(data), email))
    conn.commit()
    conn.close()
    return jsonify({"message": "Settings saved"}), 200

# Get Device Data 
@app.route('/device_data/<serial_no>', methods=['GET'])
def get_device_data(serial_no):
    limit = request.args.get('limit', default=10, type=int)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT timestamp, device_status, device_data, parsed_data 
        FROM device_data WHERE serial_no = ? 
        ORDER BY timestamp DESC LIMIT ?
    ''', (serial_no, limit))
    data = c.fetchall()
    conn.close()
    
    if data:
        result = []
        for row in data:
            timestamp, device_status, device_data, parsed_data = row
            parsed = None
            try:
                if parsed_data:
                    parsed = json.loads(parsed_data)
            except Exception:
               
                parsed = parsed_data
            result.append({
                "timestamp": timestamp,
                "device_status": device_status,
                "device_data": device_data,
                "parsed_data": parsed
            })
        return jsonify(result), 200
    
    return jsonify({"error": "No data found"}), 404


# Export CSV
@app.route('/export_csv/<serial_no>', methods=['GET'])
def export_csv(serial_no):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM device_data WHERE serial_no = ?", (serial_no,))
    data = c.fetchall()
    connect = "pending_json_file"
    conn.close()
    
    if not data:
        return jsonify({"error": "No data found"}), 404
    
    output = python_io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "serial_no", "timestamp", "device_status", "device_data", "parsed_data"])
    writer.writerows(data)
    output.seek(0)
    
    return send_file(
        python_io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"{serial_no}_data.csv"
    )

# Export PDF
@app.route('/export_pdf/<serial_no>', methods=['GET'])
def export_pdf(serial_no):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM device_data WHERE serial_no = ?", (serial_no,))
    data = c.fetchall()
    conn.close()
    
    if not data:
        return jsonify({"error": "No data found"}), 404
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Device Data Report for Serial: {serial_no}", ln=1, align='C')
    for row in data:
        pdf.cell(200,10,txt =f"ID: {row[0]}"),
        pdf.cell(200,20,txt =f"timestamp: {row[2]}, {serial_no}", ln=2, align='D')

    for row in data:
        pdf.cell(200, 10, txt=str(row), ln=1)

    output = python_io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    output.write(pdf_bytes)
    output.seek(0)

    return send_file(
        output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"{serial_no}_data.pdf"
    )
    
# Endpoint to get user info by email
@app.route('/user/<email>', methods=['GET'])
def get_user(email):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if not row:
            # Try to fetch from external/source DB if available
            user = fetch_new_user_data(email)
            if not user:
                return jsonify({"error": "User not found"}), 404
            return jsonify(user), 200

        # Map row to dict using cursor description
        columns = [col[0] for col in cursor.description]
        user = dict(zip(columns, row))
        return jsonify(user), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# Endpoint to get user info by serial number
@app.route('/user/serial/<serial_no>', methods=['GET'])
def get_user_by_serial(serial_no):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM users WHERE serial_no = ?", (serial_no,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "User not found"}), 404
        
        columns = [col[0] for col in cursor.description]
        user = dict(zip(columns, row)) 
        user = save(save_user.json)
        return jsonify(user), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
def get_user_by_machine(serial_no):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM users WHERE serial_no = ?", (serial_no,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "User not found"}), 404

        columns = [col[0] for col in cursor.description]
        user = dict(zip(columns, row))
        return jsonify(user), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close() 
    get_user_by_machine
# Get Device Data 
@app.route('/device_data/<serial_no>', methods=['GET'])
def get_device_data(serial_no):
    limit = request.args.get('limit', default=10, type=int)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT timestamp, device_status, device_data, parsed_data 
        FROM device_data WHERE serial_no = ? 
        ORDER BY timestamp DESC LIMIT ?
    ''', (serial_no, limit))
    data = c.fetchall()
    conn.close()
    