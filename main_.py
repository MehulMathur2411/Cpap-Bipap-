from cProfile import label
import sys, json, os, time, threading
from functools import partial
from tkinter.font import Font
import requests  
import re  # Added for safe parsing

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QStackedWidget, QMessageBox, QFormLayout, QFrame, QHBoxLayout, QDialog,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QSizePolicy, QGridLayout,
    QCalendarWidget, QDateEdit, QTableWidget, QTableWidgetItem, QFileDialog, QScrollArea,
    QComboBox, QSpacerItem, QHeaderView, QToolTip
)
from PyQt5.QtGui import QColor, QPainter, QPixmap, QFont, QPen, QMouseEvent, QIcon
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QEventLoop, QTimer, pyqtSlot, QRect, pyqtSignal, QObject, QDate, QSize

# Import AWS IoT related modules
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder
from concurrent.futures import Future
import queue  
from datetime import datetime
import calendar

# Import matplotlib for pie chart
# import matplotlib.pyplot as plt
# from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
# from matplotlib.figure import Figure
from collections import Counter
# import numpy as np  # Added for pie chart colors

USER_FILE = "users.json"
# --- THEME COLORS (auto-inserted) ---
THEME_PRIMARY = "#06919B"   # A slightly softer, more modern orange
THEME_PRIMARY_2 = "#08B0BB"  # A lighter shade for hover effects
THEME_TEXT_SOFT = "#607D8B" # Softer text color for secondary elements
THEME_BG = "#fbfbfb"
THEME_CARD = "#FFFFFF"
THEME_TEXT = "#111827"
THEME_ACCENT = "#1f6feb"
# End theme block

# --- Color Coding Styles (Sidebar & Buttons) ---
def apply_sidebar_and_button_styles(window):
    sidebar_style = """
    QFrame#sidebar {
        background-color: #0F172A;
    }
    QPushButton {
        color: #CBD5E1;
        background: transparent;
        border: none;
        padding: 10px;
        text-align: left;
    }
    QPushButton:hover {
        background-color: #1E293B;
    }
    QPushButton:checked {
        background-color: #2563EB;
        color: white;
    }
    """
    window.setStyleSheet(sidebar_style)

SETTINGS_FILE = "settings.json"
ACTIVE_USERS_FILE = "active_users.json"
LOGS_FILE = "logs.json"

# -------- Device Status Signal --------
class DeviceStatusSignal(QObject):
    status_changed = pyqtSignal(bool)  # True = connected, False = disconnected

device_status_signal = DeviceStatusSignal()

card_style = """
    QFrame {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFFFFF, stop:1 #FAFBFC);
        border-radius: 20px;
        border: none;
        padding: 24px;
    }
    QLabel {
        font-size: 15px;
        color: #374151;
        font-family: 'Segoe UI', sans-serif;
        padding: 4px;
        font-weight: 500;
    }
"""

class MonthlyActiveBar(QFrame):
    def __init__(self):
        super().__init__()

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("QFrame{background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;}")
        self.monthly_data = self.get_monthly_active_serials()
        self.setMouseTracking(True)
        self.tooltip_month = -1

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_data_and_repaint)
        self.timer.start(10000) # Refresh every 10 seconds

    def get_monthly_active_serials(self):
        active_users_data = load_active_users_file()
        # Ensure data is in correct monthly order (Jan-Dec)
        months_abbr = [calendar.month_abbr[i] for i in range(1, 13)]
        return [active_users_data.get(month, 0) for month in months_abbr]

    def update_data_and_repaint(self):
        self.monthly_data = self.get_monthly_active_serials()
        self.update() # Trigger repaint

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        
        width = self.width()
        height = self.height()
        margin = 24
        
        bar_width = (width - 2 * margin) / 12
        max_val = max(self.monthly_data) if self.monthly_data else 1
        
        for i, value in enumerate(self.monthly_data):
            x = margin + i * bar_width
            bar_height = (height - 2 * margin) * (value / max_val)
            
            if i == self.tooltip_month:
                qp.setBrush(QColor("#FF6A00"))
            else:
                qp.setBrush(QColor("#2563EB"))
            
            qp.setPen(Qt.NoPen)
            rect_x = x + bar_width * 0.14
            rect_width = bar_width * 0.72
            rect_y = height - margin - bar_height
            radius = min(rect_width, bar_height) * 0.4
            qp.drawRoundedRect(
                int(rect_x),
                int(rect_y),
                int(rect_width),
                int(bar_height),
                int(radius),
                int(radius),
            )
        
        # Draw month labels
        qp.setPen(QColor(THEME_TEXT_SOFT))
        qp.setFont(QFont("Segoe UI", 9))
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        for i, month in enumerate(months):
            x = margin + i * bar_width + bar_width / 2 - qp.fontMetrics().width(month) / 2
            qp.drawText(int(x), int(height - margin + 18), month)

        qp.end()

    def mouseMoveEvent(self, event):
        width = self.width()
        height = self.height()
        margin = 24
        bar_width = (width - 2 * margin) / 12
        
        hover_month = -1
        for i in range(12):
            x_start = margin + i * bar_width + bar_width * 0.1
            x_end = x_start + bar_width * 0.8
            
            if x_start <= event.x() <= x_end and margin <= event.y() <= height - margin:
                hover_month = i
                break
        
        if hover_month != self.tooltip_month:
            self.tooltip_month = hover_month
            self.update() # Trigger repaint to highlight bar
            
            if self.tooltip_month != -1:
                month_name = ["January", "February", "March", "April", "May", "June", 
                              "July", "August", "September", "October", "November", "December"][self.tooltip_month]
                active_count = self.monthly_data[self.tooltip_month]
                QToolTip.showText(event.globalPos(), f"{month_name}: {active_count}")
            else:
                QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.tooltip_month = -1
        self.update()
        QToolTip.hideText()
        super().leaveEvent(event)


def load_all_settings(serial_no: str = None) -> dict:
    """
    Load settings from file. If serial_no is provided, returns settings for that serial.
    If serial_no is None, returns the entire settings structure (all serials).
    """
    try:
        with open(SETTINGS_FILE, "r") as f:
            all_data = json.load(f)
            # Check if it's the old format (flat) or new format (per serial)
            if serial_no and serial_no in all_data:
                # New format: per serial number
                return all_data[serial_no]
            elif serial_no:
                # Serial not found, return empty dict
                return {}
            elif any(key in all_data for key in ["CPAP", "Settings", "S", "T", "ST", "VAPS", "AutoCPAP"]):
                # Old format (flat structure) - return as is for backward compatibility
                return all_data
            else:
                # New format but no serial specified - return all
                return all_data
    except Exception:
        return {}


def load_logs(serial_no: str = None) -> dict:
    """
    Load logs from file. If serial_no is provided, returns logs for that serial.
    If serial_no is None, returns all logs (all serials).
    Structure: {serial_no: {"fetched": [...], "sent": [...]}}
    Each entry: {"string": "...", "timestamp": "YYYY-MM-DD HH:MM:SS"}
    """
    try:
        with open(LOGS_FILE, "r") as f:
            all_logs = json.load(f)
            if serial_no and serial_no in all_logs:
                return all_logs[serial_no]
            elif serial_no:
                return {"fetched": [], "sent": []}
            else:
                return all_logs
    except Exception:
        return {}


def normalize_serial(serial: str) -> str:
    """
    Normalize a device serial number so the same physical device always uses
    the same key everywhere (settings, logs, dashboard).

    The device protocol sometimes appends a machine-type suffix to the serial
    (e.g. '12345678B' for BIPAP, '12345678C' for CPAP). For the UI and for file
    keys we strip this trailing type letter and only keep the numeric part,
    so that:
      - Logs for a device are always under '12345678'
      - Settings are stored per base serial
      - The type is still encoded only in the CSV / MQTT payload.
    """
    if not serial:
        return ""
    s = str(serial).strip()
    if len(s) > 1 and s[-1] in ("B", "C") and s[:-1].isdigit():
        return s[:-1]
    return s


def save_log(serial_no: str, log_type: str, data_string: str):
    """
    Save a log entry (fetched or sent) for a serial number.
    log_type: "fetched" or "sent"
    """
    if not serial_no or not serial_no.strip():
        return
    
    # Always log against the normalized (base) serial so one device
    # does not get split across '12345678', '12345678B', '12345678C', etc.
    serial_key = normalize_serial(serial_no)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        # Load existing logs
        try:
            with open(LOGS_FILE, "r") as f:
                all_logs = json.load(f)
        except Exception:
            all_logs = {}
        
        # Initialize serial entry if needed
        if serial_key not in all_logs:
            all_logs[serial_key] = {"fetched": [], "sent": []}
        
        # Add new log entry
        log_entry = {
            "string": data_string,
            "timestamp": timestamp
        }
        all_logs[serial_key][log_type].append(log_entry)
        
        # Keep only last 100 entries per type per serial (to prevent file from growing too large)
        if len(all_logs[serial_key][log_type]) > 100:
            all_logs[serial_key][log_type] = all_logs[serial_key][log_type][-100:]
        
        # Save back to file
        with open(LOGS_FILE, "w") as f:
            json.dump(all_logs, f, indent=2)
    except Exception as e:
        print(f"Error saving log: {e}")
 
def load_users():
    if not os.path.exists(USER_FILE):
        print(f"File {USER_FILE} does not exist, returning empty users")
        return {}
    try:
        with open(USER_FILE, "r") as f:
            users = json.load(f)
            print(f"Loaded users from {USER_FILE}: {users}")
            required_keys = ["name", "contact", "address", "password", "serial_no"]
            for email, data in users.items():
                if not all(key in data for key in required_keys):
                    print(f"Warning: Invalid user data for {email}. Missing keys: {[k for k in required_keys if k not in data]}")
            return users
    except Exception as e:
        print(f"Error loading users from {USER_FILE}: {e}")
        return {}
def save_users(users):
    try:
        with open(USER_FILE, "w") as f:
            json.dump(users, f, indent=4)
            print(f"Saved users to {USER_FILE}: {users}")
    except Exception as e:
        print(f"Error saving users to {USER_FILE}: {e}")
        raise
def load_active_users_file():
    """Load or initialize active users per-month counts (Jan-Dec).
    Returns dict with short month names as keys (Jan..Dec) and integer counts.
    """
    months = [calendar.month_abbr[i] for i in range(1,13)]
    if not os.path.exists(ACTIVE_USERS_FILE):
        sample = {m: 0 for m in months}
        # Provide some sample data
        sample.update({months[i]: v for i, v in enumerate([5,3,2,4,6,1,2,3,4,5,2,1])})
        try:
            with open(ACTIVE_USERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(sample, f, indent=2)
        except Exception as e:
            print(f"Failed to create {ACTIVE_USERS_FILE}: {e}")
        return sample
    try:
        with open(ACTIVE_USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Ensure all months present
        for m in months:
            if m not in data:
                data[m] = 0
        return data
    except Exception as e:
        print(f"Error loading {ACTIVE_USERS_FILE}: {e}")
        return {calendar.month_abbr[i]: 0 for i in range(1,13)}

def save_active_users_file(data: dict):
    try:
        with open(ACTIVE_USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Failed to save {ACTIVE_USERS_FILE}: {e}")

def get_total_active_devices():
    """Calculates the total number of active devices from the active_users.json file."""
    active_users_data = load_active_users_file()
    return sum(active_users_data.values())
class OTPDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OTP Verification")
        self.setFixedSize(400, 250)
        self.setWindowFlags(Qt.Window)

        layout = QVBoxLayout()
        container = QFrame()
        container.setStyleSheet('''
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(255, 255, 255, 0.95), stop:1 rgba(248, 249, 250, 0.95));
                border-radius: 16px;
                border: 1px solid rgba(52, 152, 219, 0.2);
            }
            QLabel { font-size: 17px; color: #1f2937; }
            QLineEdit { padding: 8px; font-size: 14px; }
            QPushButton { padding: 10px; font-size: 14px; }
        ''')
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vbox = QVBoxLayout()
        vbox.setSpacing(20)
        label = QLabel("Enter OTP (Demo: 123456)")
        label.setAlignment(Qt.AlignCenter)
        self.otp_input = QLineEdit()
        self.otp_input.setPlaceholderText("Enter OTP")
        self.otp_input.setMaxLength(6)
        self.otp_input.setAlignment(Qt.AlignCenter)
        self.otp_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn = QPushButton("Verify OTP")
        btn.clicked.connect(self.verify_otp)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        vbox.addWidget(label)
        vbox.addWidget(self.otp_input)
        vbox.addWidget(btn)
        vbox.addStretch()
        container.setLayout(vbox)
        layout.addWidget(container)
        layout.setContentsMargins(30, 30, 30, 30)
        self.setLayout(layout)

    def verify_otp(self):
        if self.otp_input.text() == "123456":
            QMessageBox.information(self, "Success", "OTP Verified Successfully!")
            self.accept()
        else:
            QMessageBox.warning(self, "Error", "Invalid OTP. Try again.")

# ---------- Main Window ----------
class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BIPAP Dashboard")
        self.setFixedSize(900,600)
        self.users = load_users()
        self.setWindowFlags(Qt.Window)

        # ---------- Main Layout ----------
        main_layout = QHBoxLayout()
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Left Panel
        self.left_panel = QFrame()
        self.left_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.left_panel.setStyleSheet("QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(31, 41, 55, 0.95), stop:1 rgba(17, 24, 39, 0.95)); border: none; }")

        # Right Panel
        self.right_panel = QFrame()
        self.right_panel.setStyleSheet("QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(255, 255, 255, 0.98), stop:1 rgba(250, 251, 252, 0.98)); border-radius: 24px; border: 1px solid rgba(255, 106, 0, 0.15); }")
        self.right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(40, 40, 40, 40)
        right_layout.setSpacing(20)
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.stack.addWidget(self.login_page())
        self.stack.addWidget(self.register_page())
        right_layout.addWidget(self.stack)
        right_layout.addStretch()
        self.right_panel.setLayout(right_layout)

        # Enhanced shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.right_panel.setGraphicsEffect(shadow)

        # Hover animation
        self.right_panel.enterEvent = lambda event: self.hover_card(True)
        self.right_panel.leaveEvent = lambda event: self.hover_card(False)

        main_layout.addWidget(self.left_panel, 1)
        main_layout.addWidget(self.right_panel, 1)
        self.setLayout(main_layout)

        # Fade-in animation
        self.opacity_effect = QGraphicsOpacityEffect()
        self.right_panel.setGraphicsEffect(self.opacity_effect)
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setDuration(1000)
        self.anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.anim.start()

        # Slide-in animation
        self.slide_anim = QPropertyAnimation(self.right_panel, b"pos")
        self.slide_anim.setDuration(1000)
        self.slide_anim.setStartValue(self.right_panel.pos() + QPoint(100, 0))
        self.slide_anim.setEndValue(self.right_panel.pos())
        self.slide_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.slide_anim.start()

    def hover_card(self, hover):
        anim = QPropertyAnimation(self.right_panel, b"geometry")
        anim.setDuration(200)
        rect = self.right_panel.geometry()
        if hover:
            anim.setEndValue(rect.adjusted(-2, -2, 2, 2))
        else:
            anim.setEndValue(rect.adjusted(2, 2, -2, -2))
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bg = QPixmap("C:assets\\sign in background.jpg")
        scaled_bg = bg.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = (self.width() - scaled_bg.width()) // 2
        y = (self.height() - scaled_bg.height()) // 2
        painter.drawPixmap(x, y, scaled_bg)

    def login_page(self):
        page = QFrame()
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(255, 255, 255, 1), stop:1 rgba(252, 253, 254, 1));
                border-radius: 24px;
                border: 1px solid rgba(255, 106, 0, 0.12);
                padding: 40px;
            }
        """)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container_layout = QVBoxLayout()
        container_layout.setSpacing(20)
        

        title = QLabel("<h1 style='color:#111827; margin:0; font-size:36px; font-family: 'Segoe UI', sans-serif; font-weight: 700; letter-spacing: -0.5px;'>CPAP/BIPAP Dashboard</h1>"
                       "<h2 style='color:" + THEME_TEXT_SOFT + "; margin:8px 0 0 0; font-size:18px; font-family: 'Segoe UI', sans-serif; font-weight: 500;'>DeckMount Electronics Ltd.</h2>")
        title.setAlignment(Qt.AlignCenter)

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("Email ID")
        self.user_input.setStyleSheet(self.input_style())
        self.user_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.user_input.setFixedHeight(50)
        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("Password")
        self.pass_input.setEchoMode(QLineEdit.Password)
        self.pass_input.setStyleSheet(self.input_style())
        self.pass_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        login_btn = QPushButton("Login")
        login_btn.setStyleSheet(self.button_style())
        login_btn.clicked.connect(self.do_login)
        login_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        #reg_btn = QPushButton("New User? Register Here")
        #reg_btn.setStyleSheet("background:none;color:#1f6feb;border:none;font-size:14px; font-family: 'Segoe UI', sans-serif; font-weight: 500; text-decoration: underline;")
        #reg_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        #reg_btn.setFixedHeight(30)

        container_layout.addWidget(title)
        container_layout.addWidget(self.user_input)
        container_layout.addWidget(self.pass_input)
        container_layout.addWidget(login_btn)
        #container_layout.addWidget(reg_btn, alignment=Qt.AlignCenter)
        container_layout.addStretch()
        container.setLayout(container_layout)
        layout.addWidget(container)
        layout.addWidget
        page.setLayout(layout)
        return page

    def register_page(self):
        page = QFrame()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.addStretch()

        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(255, 255, 255, 1), stop:1 rgba(252, 253, 254, 1));
                border-radius: 24px; 
                border: 1px solid rgba(255, 106, 0, 0.12);
                padding: 40px;
            }
        """)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(15)
        form_layout.setHorizontalSpacing(20)
        form_layout.setLabelAlignment(Qt.AlignRight)

        title = QLabel("<h1 style='color:#111827; margin:5px; font-size:32px; font-family: 'Segoe UI', sans-serif; font-weight: 700; letter-spacing: -0.5px;'>New User Registration</h1>")
        title.setAlignment(Qt.AlignCenter)
        form_layout.addRow(title)

        self.name_input = QLineEdit()
        self.contact_input = QLineEdit()
        self.address_input = QLineEdit()
        self.pass_reg_input = QLineEdit()
        self.pass_reg_input.setEchoMode(QLineEdit.Password)
        self.email_input = QLineEdit()
        self.serial_input = QLineEdit()
        for w in [self.name_input, self.contact_input, self.address_input, self.pass_reg_input, self.email_input, self.serial_input]:
            w.setStyleSheet(self.input_style())
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            w.setFixedHeight(50)

        form_layout.addRow("Name:", self.name_input)
        form_layout.addRow("Contact:", self.contact_input)
        form_layout.addRow("Address:", self.address_input)
        form_layout.addRow("Password:", self.pass_reg_input)
        form_layout.addRow("Email:", self.email_input)
        form_layout.addRow("Serial No:", self.serial_input)

        reg_btn = QPushButton("Register")
        reg_btn.setStyleSheet(self.button_style())
        reg_btn.clicked.connect(self.register_user)
        reg_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        reg_btn.setFixedHeight(50)
        back_btn = QPushButton("Back to Login")
        back_btn.setStyleSheet("background:none;color:#1f6feb;border:none;font-size:15px; font-family: 'Segoe UI', sans-serif; font-weight: 500; padding: 8px;")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        back_btn.setFixedHeight(30)
        form_layout.addRow(reg_btn)
        form_layout.addRow(back_btn)

        container.setLayout(form_layout)
        main_layout.addWidget(container, alignment=Qt.AlignCenter)
        main_layout.addStretch()
      
        page.setLayout(main_layout)
        return page

    def input_style(self):
        return """
        QLineEdit {
            border: 2px solid rgba(229, 231, 235, 1);
            border-radius: 16px;
            padding: 14px 18px;
            background: #FFFFFF;
            font-size: 16px;
            font-family: 'Segoe UI', sans-serif;
            color: #111827;
            font-weight: 500;
        }
        QLineEdit:focus { 
            border: 2px solid #FF6A00; 
            background: #FFFFFF;
        }
        QLineEdit:hover {
            border: 2px solid rgba(255, 106, 0, 0.4);
        }
        QLineEdit::placeholder {
            color: #9CA3AF;
            font-weight: 400;
        }
        """

    def button_style(self):
        return """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FF6A00, stop:1 #FF8A00);
            color: white; 
            border-radius: 18px; 
            font-weight: 600; 
            padding: 16px 28px;
            font-size: 18px;
            font-family: 'Segoe UI', sans-serif;
            border: none;
            letter-spacing: 0.3px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FF8A00, stop:1 #FF6A00);
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E55A00, stop:1 #CC4A00);
        }
        """
    def do_login(self):
        email = self.user_input.text().strip()
        pwd = self.pass_input.text().strip()
        print(f"Login attempt: {email}")
        if email == "mehul@admin" and pwd == "admin":
                QMessageBox.information(self, "Success", "Welcome Admin!")
                self.admin_dashboard = AdminDashboard(user_name="Admin", machine_serial="", login_window=self, user_data={})
                self.admin_dashboard.showMaximized()
                self.hide()
        elif email in self.users and self.users[email]["password"] == pwd:
            user_name = self.users[email].get("name", "User")
            serial_no = self.users[email].get("serial_no", "")
            user_data = self.users[email]
            user_data["email"] = email

            QMessageBox.information(self, "Success", f"Welcome {user_name}!")

            self.dashboard = Dashboard(
                user_name=user_name,
                machine_serial=serial_no,
                login_window=self,
                user_data=user_data
            )
            self.dashboard.showMaximized()
            self.hide()
        else:
            QMessageBox.warning(self, "Failed", "Invalid Username or Password")

    def register_user(self):
        name = self.name_input.text().strip()
        contact = self.contact_input.text().strip()
        address = self.address_input.text().strip()
        password = self.pass_reg_input.text().strip()
        email = self.email_input.text().strip()
        serial = self.serial_input.text().strip()
        
        if not all([name, contact, address, password, email, serial]):
            QMessageBox.warning(self, "Error", "All fields are required!")
            return

        if email in self.users:
            QMessageBox.warning(self, "Error", "User already exists!")
            return

        otp_dialog = OTPDialog(self) 
        if otp_dialog.exec_() != QDialog.Accepted:
            return 

        self.users[email] = {
            "name": name,
            "contact": contact,
            "address": address,
            "password": password,
            "serial_no": serial
        }

        save_users(self.users)
        self.users = load_users()

        QMessageBox.information(self, "Success", "User Registered Successfully!")
        self.stack.setCurrentIndex(0)

# -------- Device Status Widget --------
class DeviceStatusIndicator(QFrame):
    """Real-time device connection status indicator"""
    
    def __init__(self, machine_type="BIPAP", parent=None):
        super().__init__(parent)
        self.is_connected = False
        self.machine_type = machine_type
        self.init_ui()
        
        # Connect to device status signal
        device_status_signal.status_changed.connect(self.update_status)
    
    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignVCenter)
        
        # Status indicator (modern dot)
        self.indicator_label = QLabel("●")
        self.indicator_label.setAlignment(Qt.AlignVCenter | Qt.AlignHCenter)
        self.indicator_label.setStyleSheet("""
            QLabel {
                color: #EF4444;
                font-size: 12px;
                font-weight: bold;
                min-width: 20px;
            }
        """)
        
        # Status text
        self.status_label = QLabel("Device Disconnected")
        self.status_label.setAlignment(Qt.AlignVCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                color: THEME_TEXT_SOFT;
                font-size: 13px;
                font-weight: 500;
                font-family: 'Segoe UI', sans-serif;
            }
        """)

        self.badge_label = QLabel(self.machine_type) # Default text, will be updated
        self.badge_label.setObjectName("HeaderBadge")
        self.badge_label.setAlignment(Qt.AlignCenter)
        self.badge_label.setStyleSheet("""
            QLabel#HeaderBadge {
                background-color: #FFF3E8;
                color: #FF7A00;
                padding: 6px 12px;
                border-radius: 12px;
                font-size: 13px;
            }
        """)
        
        layout.addWidget(self.indicator_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.badge_label)
        layout.addStretch()
        
        self.setStyleSheet("""
            QFrame {
                background: #F9FAFB;
                border-radius: 8px;
                border: none;
                padding: 0px;
            }
        """)
    
    def update_status(self, is_connected):
        """Update status display"""
        self.is_connected = is_connected
        
        if is_connected:
            self.indicator_label.setAlignment(Qt.AlignVCenter | Qt.AlignHCenter)
            self.indicator_label.setStyleSheet("""
                QLabel {
                    color: #10B981;
                    font-size: 14px;
                    font-weight: bold;
                    min-width: 20px;
                }
            """)
            self.status_label.setText("Device Connected")
            self.status_label.setStyleSheet("""
                QLabel {
                    color: #374151;
                    font-size: 14px;
                    font-weight: 500;
                    font-family: 'Segoe UI', sans-serif;
                }
            """)
            self.badge_label.setText(self.machine_type) 
            self.setStyleSheet("""
                QFrame {
                    background: #F0FDF4;
                    border-radius: 10px;
                    border: none;
                    padding: 0px;
                }
            """)
        else:
            self.indicator_label.setAlignment(Qt.AlignVCenter | Qt.AlignHCenter)
            self.indicator_label.setStyleSheet("""
                QLabel {
                    color: #EF4444;
                    font-size: 14px;
                    font-weight: bold;
                    min-width: 20px;
                }
            """)
            self.status_label.setText("Device Disconnected")
            self.status_label.setStyleSheet("""
                QLabel {
                    color: THEME_TEXT_SOFT;
                    font-size: 14px;
                    font-weight: 500;
                    font-family: 'Segoe UI', sans-serif;
                }
            """)
            self.badge_label.setText(self.machine_type)
            self.setStyleSheet("""
                QFrame {
                    background: #F9FAFB;
                    border-radius: 8px;
                    border: none;
                    padding: 0px;
                }
            """)

# ---------------- Dashboard ----------------
class Dashboard(QWidget):
    def __init__(self, user_name="Sample User", machine_serial="SN123456", login_window=None, user_data=None):
        super().__init__()
        self.setWindowFlags(Qt.Window)
        self.login_window = login_window
        self.user_data = user_data or {}
        self.setWindowTitle("Dashboard")
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fbfbfb, stop:1 #f6f6f6);
                font-family: 'Segoe UI', sans-serif;
            }
        """)

        self.user_name = user_name
        self.machine_serial = machine_serial
        try:
            self.update_recent_serial(self.machine_serial)
            self.update_active_serial_numbers_display()
        except Exception:
            pass
        self.machine_type = "BIPAP"  
        self.start_time = time.time()
        self.therapy_active = True
        self.current_mode = None
        self.current_mode_str = "MANUALMODE"  # Default for CPAP
        self.is_connected = False
        self.is_connected = True 
        self.is_connected
        # Default values - 
        self.default_values = {
            "CPAP": {"Set Pressure": 4.0},
            "AutoCPAP": {"Min Pressure": 4.0, "Max Pressure": 20.0},
            "S": {"IPAP": 6.0, "EPAP": 4.0, "Start EPAP": 4.0,
                  "Ti.Min": 0.2, "Ti.Max": 3.0,
                  "Sensitivity": 1.0, "Rise Time": 50.0},
            "T": {"IPAP": 6.0, "EPAP": 4.0, "Start EPAP": 4.0,
                  "Respiratory Rate": 10.0, "Ti.Min": 1.0, "Ti.Max": 2.0, "Sensitivity": 1.0, "Rise Time": 200.0},
            "VAPS": {"Height": 170.0, "Tidal Volume": 500.0, "Max IPAP": 20.0,
                     "Min IPAP": 10.0, "EPAP": 5.0, "Respiratory Rate": 10.0,
                     "Ti.Min": 1.0, "Ti.Max": 2.0, "Rise Time": 200.0, "Sensitivity": 1.0},
            "ST": {"IPAP": 6.0, "EPAP": 4.0, "Start EPAP": 4.0, "Backup Rate": 10.0,
                   "Ti.Min": 1.0, "Ti.Max": 2.0, "Rise Time": 200.0, "Sensitivity": 3.0},
            "Settings": {"I Mode": "OFF", "Leak alert": "OFF", "Gender": "MALE",
                         "Sleep Mode": "OFF", "Mask Type": "Full face", "Tubetype": "Standard", "Ramp Time": 5.0}
        }

        self.mode_map = {
            "CPAP": (0, 0),
            "AutoCPAP": (0, 1),
            "S": (1, 2),
            "T": (1, 3),
            "ST": (1, 4),
            "VAPS": (1, 5),
        }

        self.int_fields = {
            "Sensitivity", "Rise Time", "Respiratory Rate", "Backup Rate",
            "Height", "Tidal Volume", "Ramp Time", "Humidifier", "Flex Level"
        }

        self.card_color = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffffff, stop:1 #fbfbfb)"
        self.value_labels = {}
        self.info_label = None 
        self.recent_sends = {}
        
        # Initialize search history for pie chart
        # self.search_history = {}  # Dict to store serial no and their search counts
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---------------- Sidebar ----------------
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.sidebar_frame.setStyleSheet("background: white; border: none; border-radius: 24px 0 0 24px;")
        sidebar = QVBoxLayout()
        sidebar.setContentsMargins(15, 15, 15, 15)
        sidebar.setSpacing(8)
        self.sidebar_buttons = []
        self.selected_btn = None

        logo_path = "C:/Users/tanya/OneDrive/Pictures/logo.png.PNG" # Path to your logo image
        logo_pixmap = QPixmap(logo_path)
        
        logo_label = QLabel()
        logo_label.setPixmap(logo_pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)) # Scale as needed
        logo_label.setAlignment(Qt.AlignCenter)
        sidebar.addWidget(logo_label)

        self.normal_btn_style = """
            QPushButton {
                background: transparent;

                
                color: #06919B;
                font-weight: 600;
                font-size: 16px;
                text-align: center;
                padding: 14px 20px;
                border-radius: 14px;
                font-family: 'Segoe UI', sans-serif;
                border-left: 3px solid transparent;
            }
            QPushButton:hover {
                background: rgba(6, 145, 155, 0.15);
                color: #06919B;
                border-left: 3px solid #06919B;
            }
        """
        self.selected_btn_style = self.normal_btn_style + """
            QPushButton {
                background: rgba(6, 145, 155, 0.25);
                color: #06919B;
                border-left: 3px solid #06919B;
                font-weight: 600;
            }
        """
        for text in ["Dashboard", "CPAP Mode", "AutoCPAP Mode", "S Mode", "T Mode", "VAPS Mode", "ST Mode", "Report", "Settings", "Logs"]:
            btn = QPushButton(text)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet(self.normal_btn_style)
            sidebar.addWidget(btn)
            self.sidebar_buttons.append(btn)

        # Add Info button
        info_btn = QPushButton("Info")
        info_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        info_btn.setFixedHeight(45)
        info_btn.setStyleSheet(self.normal_btn_style)
        sidebar.addWidget(info_btn)
        self.sidebar_buttons.append(info_btn)

        # Add Logout button
        logout_btn = QPushButton("Logout")
        logout_btn.setFixedSize(140, 45)
        logout_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        logout_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #EF4444, stop:1 #DC2626);
                color: #ffffff;
                font-weight: 600;
                font-size: 15px;
                border-radius: 14px;
                padding: 12px 20px;
                font-family: 'Segoe UI', sans-serif;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #DC2626, stop:1 #B91C1C);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B91C1C, stop:1 #991B1B);
            }
        """)
        logout_btn.clicked.connect(self.do_logout)
        sidebar.addStretch()
        # Center the logout button horizontally
        logout_layout = QHBoxLayout()
        logout_layout.addStretch()
        logout_layout.addWidget(logout_btn)
        logout_layout.addStretch()
        sidebar.addLayout(logout_layout)
        self.sidebar_frame.setLayout(sidebar)
        # ---------------- Content ----------------
        content_frame = QFrame()
        content_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout = QVBoxLayout(content_frame)
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(15, 15, 15, 15)

        # Device Status Indicator (added at top)
        self.device_status = DeviceStatusIndicator(machine_type=self.machine_type)
        self.device_status.setFixedHeight(40)
        self.device_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        content_layout.addWidget(self.device_status)

        self.info_label = QLabel(f"User: ({self.user_name})    |    Machine S/N: ({self.machine_serial})")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("font-size: 20px; font-weight: 600; color: #111827; font-family: 'Segoe UI', sans-serif; padding: 8px;")
        self.info_label.setWordWrap(True)
        content_layout.addWidget(self.info_label)

        self.current_mode_label = QLabel("Current Mode: Dashboard")
        self.current_mode_label.setObjectName("HeaderMode")
        self.current_mode_label.setAlignment(Qt.AlignCenter)
        self.current_mode_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #111827;")
        content_layout.addWidget(self.current_mode_label)
        
           
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout.addWidget(self.stack)

        # Mode pages
        self.pages = []
        for mode_name in ["Dashboard", "CPAP", "AutoCPAP", "S", "T", "VAPS", "ST", "Report", "Settings", "Logs", "Info"]:
            if mode_name == "Dashboard":
                page = self.create_dashboard_page()
            elif mode_name == "Logs":
                page = self.create_logs_page()
            elif mode_name == "Info":
                page = self.create_info_page()
            elif mode_name in self.default_values:
                page = self.create_mode_page(mode_name, self.default_values[mode_name], options_mode=(mode_name == "Settings"))
            else:
                page = self.create_page(f"{mode_name} Page")
            self.pages.append(page)
            self.stack.addWidget(page)

        main_layout.addWidget(self.sidebar_frame, 0)
        main_layout.addWidget(content_frame, 1)  

        # Button actions - use functools.partial to avoid closure issues
        for i, btn in enumerate(self.sidebar_buttons):
            btn_name = btn.text()  # Capture the button text outside lambda
            # Use partial to properly capture the index and name (clicked signal emits bool, we ignore it)
            btn.clicked.connect(lambda checked, idx=i, name=btn_name: self.set_mode(idx, name))

        self.update_button_states()
        self.load_settings()
        self.set_mode(0, "Dashboard")
        # Load active users data and render pie chart
        # try:
        #     self.active_users = load_active_users_file()
        #     self.update_pie_chart()
        # except Exception as e:
        #     print(f"Failed to initialize active users chart: {e}")
        

        # Timer for real-time stats
        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self.update_stats)
        self.stats_timer.start(1000)

        # AWS IoT Integration
        self.aws_send_queue = queue.Queue()
        self.aws_receive_queue = queue.Queue()
        self.aws_thread = threading.Thread(target=self.aws_iot_loop)
        self.aws_thread.daemon = True
        self.aws_thread.start()

    def update_button_states(self):
        active_modes = {
            "CPAP": {"CPAP", "AutoCPAP"},
            "BIPAP": {"CPAP", "AutoCPAP", "S", "T", "ST", "VAPS"}
        }
        active_set = active_modes.get(self.machine_type, {"CPAP", "AutoCPAP", "S", "T", "ST", "VAPS"})

        disabled_style = self.normal_btn_style + f"""
            QPushButton:disabled {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #E0E0E0, stop:1 #CCCCCC);
                color: #AAAAAA;
            }}
        """

        # Always enabled buttons (not mode-dependent)
        always_enabled = ["Dashboard", "Report", "Settings", "Logs", "Info"]
        
        for btn in self.sidebar_buttons:
            btn_text = btn.text()
            # Remove " Mode" suffix if present (compatible with older Python versions)
            if btn_text.endswith(" Mode"):
                btn_text = btn_text[:-5]
            
            # Enable if it's in always_enabled list or in active_set
            if btn_text in always_enabled or btn_text in active_set:
                btn.setEnabled(True)
                btn.setStyleSheet(self.normal_btn_style)
            else:
                btn.setEnabled(False)
                btn.setStyleSheet(disabled_style)

    def update_serial_from_input(self):
        """
        Force-update the current device serial number from the dashboard/Admin
        serial input and propagate it everywhere (header, logs, active list,
        and for future sends).

        This does NOT call the API – it just treats the typed serial as the
        new active device for this session.
        """
        # Only proceed if there is a serial_input field (AdminDashboard provides it)
        if not hasattr(self, "serial_input") or self.serial_input is None:
            QMessageBox.warning(self, "Error", "Serial input field is not available on this dashboard.")
            return

        raw_serial = self.serial_input.text().strip()
        if not raw_serial:
            QMessageBox.warning(self, "Error", "Please enter a serial number.")
            return

        # Normalize for internal usage (settings/logs/UI) so one device has one key.
        base_serial = normalize_serial(raw_serial)
        if not base_serial:
            QMessageBox.warning(self, "Error", "Invalid serial number.")
            return

        # Set as current machine serial
        self.machine_serial = base_serial

        # Keep all key UI elements in sync
        self.serial_input.setText(base_serial)
        if hasattr(self, "logs_serial_input") and self.logs_serial_input:
            self.logs_serial_input.setText(base_serial)
        if hasattr(self, "info_label") and self.info_label:
            self.info_label.setText(f"User: ({self.user_name})    |    Machine S/N: ({base_serial})")

        # Track as active / recent device
        try:
            self.add_active_serial_to_list(base_serial, self.machine_type)
            self.update_recent_serial(base_serial)
            self.update_active_serial_numbers_display()
        except Exception:
            pass

        # Optionally load any existing settings for this serial (from local file)
        try:
            self.load_settings()
            self.update_alerts()
            self.update_button_states()
        except Exception:
            pass

        QMessageBox.information(self, "Serial Updated", f"Active device serial updated to: {base_serial}")

    def record_login_search(self):
        """Records a login search event for monthly active users."""
        current_month_abbr = calendar.month_abbr[datetime.now().month]
        active_users_data = load_active_users_file()
        active_users_data[current_month_abbr] = active_users_data.get(current_month_abbr, 0) + 1
        save_active_users_file(active_users_data)
        print("Recorded login search for {}. New count: {}".format(current_month_abbr, active_users_data.get(current_month_abbr, 0)))

    def get_mode_str(self, mode_name):
        """Generate mode string for CSV based on machine_type and mode_name."""
        if self.machine_type == "CPAP":
            if mode_name == "CPAP":
                return "MANUALMODE"
            elif mode_name == "AutoCPAP":
                return "AUTOMODE"
        else:  
            mode_dict = {
                "CPAP": "CPAPMODE",
                "AutoCPAP": "AUTOMODE",
                "S": "S_MODE",
                "T": "T_MODE",
                "ST": "ST_MODE",
                "VAPS": "VAPS_MODE"
            }
            return mode_dict.get(mode_name, "")
        return ""

    def format_for_csv(self, v):
        if isinstance(v, str):
            try:
                return f"{float(v):.1f}"
            except ValueError:
                return v
        if isinstance(v, (int, float)):
            return f"{float(v):.1f}"
        return str(v)

    def create_dashboard_page(self):
        page = QWidget()
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout = QVBoxLayout(page)
        main_layout.setSpacing(18)
        main_layout.setContentsMargins(20, 20, 20, 20)
        # Patient Information
        patient_frame = QFrame()
        patient_frame.setStyleSheet(card_style)
        patient_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        shadow_patient = QGraphicsDropShadowEffect(self)
        shadow_patient.setBlurRadius(24)
        shadow_patient.setOffset(0, 6)
        shadow_patient.setColor(QColor(0, 0, 0, 20))
        patient_frame.setGraphicsEffect(shadow_patient)
        patient_layout = QFormLayout(patient_frame)
        patient_layout.setLabelAlignment(Qt.AlignRight)
        patient_layout.setFormAlignment(Qt.AlignHCenter)
        patient_layout.setSpacing(8)
        patient_layout.addRow("Serial No:", QLabel(f"({self.user_data.get('serial_no', 'N/A')})"))
        patient_title = QLabel("Patient Information")
        patient_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #1f2937; margin: 0 0 8px 4px; padding: 0; font-family: 'Segoe UI', sans-serif;")

        # Usage Status
        stats_frame = QFrame()
        stats_frame.setStyleSheet(card_style)
        stats_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        shadow_stats = QGraphicsDropShadowEffect(self)
        shadow_stats.setBlurRadius(24)
        shadow_stats.setOffset(0, 6)
        shadow_stats.setColor(QColor(0, 0, 0, 20))
        stats_frame.setGraphicsEffect(shadow_stats)
        stats_layout = QFormLayout(stats_frame)
        stats_layout.setLabelAlignment(Qt.AlignRight)
        stats_layout.setFormAlignment(Qt.AlignHCenter)
        stats_layout.setSpacing(8)
        self.therapy_usage_label = QLabel("(0.0) hours")
        self.machine_up_time_label = QLabel("(0.0) hours")
        stats_layout.addRow("Therapy Usage:", self.therapy_usage_label)
        stats_layout.addRow("Machine Up Time:", self.machine_up_time_label)
        stats_title = QLabel("Usage Stats")
        stats_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #1f2937; margin: 0 0 8px 4px; padding: 0; font-family: 'Segoe UI', sans-serif;")
        stats_title.setStyleSheet()
        # Recently Searched Serial No (NEW BOX)
        recent_frame = QFrame()
        recent_frame.setStyleSheet(card_style)
        recent_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        shadow_recent = QGraphicsDropShadowEffect(self)
        shadow_recent.setBlurRadius(24)
        shadow_recent.setOffset(0, 6)
        shadow_recent.setColor(QColor(0, 0, 0, 20))
        recent_frame.setGraphicsEffect(shadow_recent)
        recent_layout = QFormLayout(recent_frame)
        recent_layout.setLabelAlignment(Qt.AlignRight)
        recent_layout.setFormAlignment(Qt.AlignHCenter)

        # Live labels (initial values)
        self.recent_serial_label = QLabel("(None)")
        self.recent_time_label = QLabel("(--)")
        self.recent_serial_label.setAlignment(Qt.AlignCenter)
        self.recent_time_label.setAlignment(Qt.AlignCenter)

        recent_layout.addRow("Serial No:", self.recent_serial_label)
        recent_layout.addRow("Date/Time:", self.recent_time_label)
        recent_title = QLabel("Recently Searched Serial No")
        recent_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #1f2937; margin: 0 0 8px 4px; padding: 0; font-family: 'Segoe UI', sans-serif;")

        # Pie Chart for Search History - BIGGER SIZE
        # pie_frame = QFrame()
        # pie_frame.setStyleSheet(card_style)
        # pie_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # pie_frame.setMinimumHeight(400)  # Increased minimum height
        # pie_layout = QVBoxLayout(pie_frame)
        # pie_layout.setContentsMargins(5, 5, 5, 5)
        # pie_layout.setSpacing(5)
        
        # # Create matplotlib figure for pie chart - BIGGER
        # self.fig = Figure(figsize=(8, 6), dpi=80)  # Increased figure size
        # self.ax = self.fig.add_subplot(111)
        # self.canvas = FigureCanvas(self.fig)
        # # ensure canvas expands to available space
        # self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # self.fig.tight_layout()
        # try:
        #     self.canvas.draw()
        # except Exception:
        #     pass
        # pie_layout.addWidget(self.canvas, 1)  # Give it stretch factor 1
        
        # pie_title = QLabel("Search History Chart")
        # pie_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ff6a00; margin-bottom: 8px; padding: 2px; font-family: 'Segoe UI', sans-serif;")

        # Alerts
        alerts_frame = QFrame()
        alerts_frame.setStyleSheet(card_style)
        alerts_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        shadow_alerts = QGraphicsDropShadowEffect(self)
        shadow_alerts.setBlurRadius(24)
        shadow_alerts.setOffset(0, 6)
        shadow_alerts.setColor(QColor(0, 0, 0, 20))
        alerts_frame.setGraphicsEffect(shadow_alerts)
        alerts_layout = QVBoxLayout(alerts_frame)
        alerts_layout.setSpacing(6)
        self.alert_labels = {}
        for setting in ["IMODE", "Leak Alert", "Sleep Mode", "Mask Type", "Ramp Time", "Humidifier"]:
            label = QLabel(f"{setting}: (OFF)")
            label.setWordWrap(True)
            alerts_layout.addWidget(label)
            self.alert_labels[setting] = label
        alerts_title = QLabel("Alerts & Settings")
        alerts_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #1f2937; margin: 0 0 8px 4px; padding: 0; font-family: 'Segoe UI', sans-serif;")
        

        # Report with BIGGER Calendar
        report_frame = QFrame()
        report_frame.setStyleSheet(card_style)
        report_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        report_frame.setMinimumHeight(450)  # Increased minimum height
        shadow_report = QGraphicsDropShadowEffect(self)
        shadow_report.setBlurRadius(24)
        shadow_report.setOffset(0, 6)
        shadow_report.setColor(QColor(0, 0, 0, 20))
        report_frame.setGraphicsEffect(shadow_report)
        report_layout = QVBoxLayout(report_frame)
        report_layout.setSpacing(10)
        
        # BIGGER Calendar
        calendar = QCalendarWidget()
        calendar.setGridVisible(True)
        calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)

        calendar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Style the calendar to make it bigger
        calendar.setStyleSheet("""
            QCalendarWidget {
                background-color: white;
                font-size: 14px;  /* Increased font size */
                font-family: 'Segoe UI', sans-serif;
            }
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background-color: white;
                border: none;
                min-height: 40px;  /* Increased height */
            }
            QCalendarWidget QToolButton {
                color: black;
                font-size: 16px;  /* Increased font size */
                font-weight: bold;
                border: none;
                background: none;
                padding: 8px;  /* Increased padding */
            }
            QCalendarWidget QToolButton:hover {
                background-color: #f0f0f0;
            }
            QCalendarWidget QToolButton:pressed {
                background-color: #e0e0e0;
            }
            QCalendarWidget QAbstractItemView {
                font-size: 13px;  /* Increased font size */
                background-color: white;
                color: black;
                selection-background-color: #0078d7;
                selection-color: white;
                alternate-background-color: #fbfbfb;
            }
            QCalendarWidget QAbstractItemView::item {
                padding: 8px;  /* Increased padding */
                min-height: 40px;  /* Increased cell height */
                min-width: 40px;  /* Increased cell width */
            }
            QCalendarWidget QAbstractItemView::item:selected {
                background-color: #0078d7;
                color: white;
                border-radius: 6px;
            }
        """)
        
        table = QTableWidget(5, 5)
        table.setHorizontalHeaderLabels(["Date", "Usage", "AHI", "Leaks", "Pressure"])
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        for i in range(5):
            for j in range(5):
                table.setItem(i, j, QTableWidgetItem(f"Data {i+1}-{j+1}"))
        pdf_btn = QPushButton("Export PDF")
        pdf_btn.clicked.connect(self.export_pdf)
        pdf_btn.setMinimumHeight(40)
        pdf_btn.setStyleSheet("QPushButton { background: #f3f4f6; color: #111827; border: 1px solid #e5e7eb; border-radius: 10px; } QPushButton:hover { background: #eef2f7; }")
        csv_btn = QPushButton("Export CSV")
        csv_btn.clicked.connect(self.export_csv)
        csv_btn.setMinimumHeight(40)
        csv_btn.setStyleSheet("QPushButton { background: #f3f4f6; color: #111827; border: 1px solid #e5e7eb; border-radius: 10px; } QPushButton:hover { background: #eef2f7; }")
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(pdf_btn)
        btn_layout.addWidget(csv_btn)
        report_layout.addWidget(calendar, 2)  # Give calendar more space
        report_layout.addWidget(table, 1)
        report_layout.addLayout(btn_layout)
        report_title = QLabel("Report")
        report_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #1f2937; margin: 0 0 8px 4px; padding: 0; font-family: 'Segoe UI', sans-serif;")
        
        header_frame = QFrame()
        header_frame.setStyleSheet("QFrame { background: #F8FAFC; border: 1px solid #e5e7eb; border-radius: 18px; }")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(12)
        
        greet = QLabel(f"Hello, {self.user_name}")
        greet.setStyleSheet("font-size: 20px; font-weight: 700; color: #1f2937;")
        search = QLineEdit()
        search.setPlaceholderText("Search")
        search.setFixedHeight(40)
        search.setStyleSheet("QLineEdit { border: 1px solid #e5e7eb; border-radius: 10px; padding: 0 14px; font-size: 14px; } QLineEdit:focus { border-color: #1f6feb; }")
        header_layout.addWidget(greet)
        header_layout.addStretch(1) # Pushes everything to the left
        header_layout.addWidget(search, 2)
        header_layout.addStretch(1) # Pushes icons to the right
        
        # Bell Icon
        bell_icon_button = QPushButton()
        bell_icon_button.setIcon(QIcon('assets/bell.png')) # Assuming bell.png exists in assets folder
        bell_icon_button.setIconSize(QSize(24, 24))
        bell_icon_button.setStyleSheet("QPushButton { border: none; background-color: transparent; padding: 5px; }")
        bell_icon_button.setFixedSize(34, 34) # Make button slightly larger than icon

        # Profile Icon
        profile_icon_button = QPushButton()
        profile_icon_button.setIcon(QIcon('assets/profile.png')) # Assuming profile.png exists in assets folder
        profile_icon_button.setIconSize(QSize(24, 24))
        profile_icon_button.setStyleSheet("QPushButton { border: none; background-color: transparent; padding: 5px; }")
        profile_icon_button.setFixedSize(34, 34) # Make button slightly larger than icon

        header_layout.addWidget(bell_icon_button)
        header_layout.addWidget(profile_icon_button)

        shadow_header = QGraphicsDropShadowEffect(self)
        shadow_header.setBlurRadius(24)
        shadow_header.setOffset(0, 6)
        shadow_header.setColor(QColor(0, 0, 0, 20))
        header_frame.setGraphicsEffect(shadow_header)
        
        mini_card_style = "QFrame { background: #FFFFFF; border: 1px solid #e5e7eb; border-radius: 14px; padding: 14px; } QLabel { font-family: 'Segoe UI', sans-serif; }"
        stat1 = QFrame()
        stat1.setStyleSheet(mini_card_style)
        s1 = QVBoxLayout(stat1)
        s1.setSpacing(4)
        s1.addWidget(QLabel("Therapy Usage", styleSheet="color:#6b7280; font-size:12px;"))
        self.therapy_usage_label.setStyleSheet("font-size:20px; font-weight:700; color:#111827;")
        s1.addWidget(self.therapy_usage_label)
        stat2 = QFrame()
        stat2.setStyleSheet(mini_card_style)
        s2 = QVBoxLayout(stat2)
        s2.setSpacing(4)
        s2.addWidget(QLabel("Machine Up Time", styleSheet="color:#6b7280; font-size:12px;"))
        self.machine_up_time_label.setStyleSheet("font-size:20px; font-weight:700; color:#111827;")
        s2.addWidget(self.machine_up_time_label)
        stat3 = QFrame()
        stat3.setStyleSheet(mini_card_style)
        s3 = QVBoxLayout(stat3)
        s3.setSpacing(4)
        s3.addWidget(QLabel("Recent Serial", styleSheet="color:#6b7280; font-size:12px;"))
        self.recent_serial_label.setStyleSheet("font-size:20px; font-weight:700; color:#111827;")
        s3.addWidget(self.recent_serial_label)
        stat4 = QFrame()
        stat4.setStyleSheet(mini_card_style)
        s4 = QVBoxLayout(stat4)
        s4.setSpacing(4)
        s4.addWidget(QLabel("Last Update", styleSheet="color:#6b7280; font-size:12px;"))
        self.recent_time_label.setStyleSheet("font-size:20px; font-weight:700; color:#111827;")
        s4.addWidget(self.recent_time_label)
        
        right_column = QFrame()
        right_column.setStyleSheet("QFrame { background: transparent; }")
        rc_layout = QVBoxLayout(right_column)
        rc_layout.setSpacing(16)
        rc_layout.setContentsMargins(0,0,0,0)
        rc_layout.addWidget(alerts_title)
        rc_layout.addWidget(alerts_frame)
        rc_layout.addWidget(recent_title)
        rc_layout.addWidget(recent_frame)
        rc_layout.addWidget(patient_title)
        rc_layout.addWidget(patient_frame)


        # Create grid layout for dashboard
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(20)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(header_frame, 0, 0, 1, 4)
        grid.addWidget(stat1, 1, 0)
        grid.addWidget(stat2, 1, 1)
        grid.addWidget(stat3, 1, 2)
        grid.addWidget(stat4, 1, 3)
        grid.addWidget(report_title, 2, 0, 1, 2)
        grid.addWidget(report_frame, 3, 0, 1, 2)
        grid.addWidget(right_column, 2, 2, 2, 2)
        
        # Set stretch factors
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)
        
        grid.setRowStretch(3, 3)
        
        main_layout.addLayout(grid)
        
        return page

    def create_logs_page(self):
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        from PyQt5.QtWidgets import QProxyStyle, QStyle, QAbstractButton 
        from PyQt5.QtGui import QPainter, QPolygon, QColor
        from PyQt5.QtCore import QPoint
        class ArrowColorStyle(QProxyStyle):
            def __init__(self, base, color):
                super().__init__(base)
                self._color = QColor(color)
            def drawPrimitive(self, element, option, painter, widget=None):
                if element == QStyle.PE_IndicatorArrowDown:
                    painter.save()
                    painter.setRenderHint(QPainter.Antialiasing)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(self._color)
                    r = option.rect
                    cx = r.center().x()
                    cy = r.center().y()
                    pts = QPolygon([QPoint(cx - 6, cy - 2), QPoint(cx + 6, cy - 2), QPoint(cx, cy + 6)])
                    painter.drawPolygon(pts)
                    painter.restore()
                    return
                super().drawPrimitive(element, option, painter, widget)
        def ensure_calendar_button_visible(date_edit):
            for child in date_edit.findChildren(QAbstractButton):
                child.setText("▼")
                child.setCursor(Qt.PointingHandCursor)
                child.setStyleSheet("""
                    QToolButton {
                        color: #111827;
                        background: transparent;
                        border-left: 1px solid #e5e7eb;
                    }
                    QToolButton:hover {
                        background: #f3f4f6;
                    }
                """)
                child.setFixedWidth(28)
        
        # Header / Filter Section
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(15)
        
        filter_label = QLabel("Serial Number:")
        filter_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #333;")
        
        self.logs_serial_input = QLineEdit()
        self.logs_serial_input.setPlaceholderText("Enter Serial Number...")
        self.logs_serial_input.setFixedWidth(200)
        self.logs_serial_input.setFixedHeight(45)
        self.logs_serial_input.setStyleSheet("""
            QLineEdit {
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                padding: 0 15px;
                font-size: 14px;
                background: white;
            }
            QLineEdit:focus {
                border: 2px solid #FF6A00;
            }
        """)
        # Set default serial if available
        if self.machine_serial:
            self.logs_serial_input.setText(self.machine_serial)
        
        # Date range filter controls
        from_label = QLabel("From")
        from_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #333;")
        self.logs_from_date = QDateEdit()
        self.logs_from_date.setCalendarPopup(True)
        self.logs_from_date.setDisplayFormat("yyyy-MM-dd")
        self.logs_from_date.setDate(QDate.currentDate().addDays(-7))
        self.logs_from_date.setFixedWidth(150)
        self.logs_from_date.setFixedHeight(45)
        self.logs_from_date.setStyleSheet("""
            QDateEdit {
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                padding: 0 10px;
                padding-right: 28px;
                font-size: 14px;
                background: white    
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 24px;
                border-left: 1px solid #e5e7eb;
                background: white;
            }
        """)
        self._from_arrow_style = ArrowColorStyle(self.logs_from_date.style(), "#374151")
        self.logs_from_date.setStyle(self._from_arrow_style)
        ensure_calendar_button_visible(self.logs_from_date)
        self.logs_from_date.calendarWidget().setStyleSheet("""
            QCalendarWidget { background-color: #ffffff; color: #111827; border: 1px solid #e5e7eb; border-radius: 10px; }
            QCalendarWidget QWidget { background-color: #ffffff; color: #111827; }
            QCalendarWidget QToolButton { background: #ffffff; color: #111827; border: none; padding: 6px; }
            QCalendarWidget QMenu { background-color: #ffffff; color: #111827; }
            QCalendarWidget QSpinBox { background-color: #ffffff; color: #111827; }
            QCalendarWidget QAbstractItemView:enabled { background-color: #ffffff; color: #111827; selection-background-color: #FF6A00; selection-color: #ffffff; }
            QCalendarWidget QAbstractItemView:disabled { color: #9ca3af; }
        """)
        to_label = QLabel("To")
        to_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #333;")
        self.logs_to_date = QDateEdit()
        self.logs_to_date.setCalendarPopup(True)
        self.logs_to_date.setDisplayFormat("yyyy-MM-dd")
        self.logs_to_date.setDate(QDate.currentDate())
        self.logs_to_date.setFixedWidth(150)
        self.logs_to_date.setFixedHeight(45)
        self.logs_to_date.setStyleSheet("""
            QDateEdit {
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                padding: 0 10px;
                padding-right: 28px;
                font-size: 14px;
                background: white;
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 24px;
                border-left: 1px solid #e5e7eb;
                background: white;
            }
        """)
        self._to_arrow_style = ArrowColorStyle(self.logs_to_date.style(), "#374151")
        self.logs_to_date.setStyle(self._to_arrow_style)
        ensure_calendar_button_visible(self.logs_to_date)
        self.logs_to_date.calendarWidget().setStyleSheet("""
            QCalendarWidget { background-color: #ffffff; color: #111827; border: 1px solid #e5e7eb; border-radius: 10px; }
            QCalendarWidget QWidget { background-color: #ffffff; color: #111827; }
            QCalendarWidget QToolButton { background: #ffffff; color: #111827; border: none; padding: 6px; }
            QCalendarWidget QMenu { background-color: #ffffff; color: #111827; }
            QCalendarWidget QSpinBox { background-color: #ffffff; color: #111827; }
            QCalendarWidget QAbstractItemView:enabled { background-color: #ffffff; color: #111827; selection-background-color: #FF6A00; selection-color: #ffffff; }
            QCalendarWidget QAbstractItemView:disabled { color: #9ca3af; }
        """)
            
        refresh_btn = QPushButton("Load Logs")
        refresh_btn.setFixedHeight(45)
        refresh_btn.setFixedWidth(120)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FF6A00, stop:1 #FF8A00);
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FF8A00, stop:1 #FFAA00);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E65100, stop:1 #FF6A00);
            }
        """)
        refresh_btn.clicked.connect(self.load_all_logs)
        search_btn = QPushButton("Search")
        search_btn.setFixedHeight(45)
        search_btn.setFixedWidth(100)
        search_btn.setStyleSheet("""
            QPushButton {
                background: #1f6feb;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #2563eb;
            }
            QPushButton:pressed {
                background: #1e40af;
            }
        """)
        search_btn.clicked.connect(self.search_logs)
        
        test_btn = QPushButton("Add Test Data")
        test_btn.setFixedHeight(45)
        test_btn.setFixedWidth(150)
        test_btn.setStyleSheet("""
            QPushButton {
                background: #9c27b0;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #ab47bc;
            }
        """)
        test_btn.clicked.connect(self.add_test_fetched_string)
        
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.logs_serial_input)
        filter_layout.addWidget(from_label)
        filter_layout.addWidget(self.logs_from_date)
        filter_layout.addWidget(to_label)
        filter_layout.addWidget(self.logs_to_date)
        filter_layout.addWidget(search_btn)
        filter_layout.addWidget(refresh_btn)
        filter_layout.addWidget(test_btn)
        filter_layout.addStretch()
        filter
        
        main_layout.addLayout(filter_layout)
        
        header = QFrame()
        header.setStyleSheet("QFrame { background: #F6F8FA; border: 1px solid #eaecef; border-radius: 10px; padding: 10px; }")
        header_layout = QHBoxLayout(header)
        header_layout.setSpacing(4)
        header_layout.setContentsMargins(8, 6, 8, 6)
        h_date = QLabel("Date/Time")
        h_date.setStyleSheet("font-size: 13px; font-weight: 700; color: #374151;")
        h_date.setFixedWidth(100)
        h_date.setAlignment(Qt.AlignCenter)
        h_mode = QLabel("Mode")
        h_mode.setStyleSheet("font-size: 13px; font-weight: 700; color: #374151;")
        h_mode.setFixedWidth(90)
        h_mode.setAlignment(Qt.AlignCenter)
        h_string = QLabel("String")
        h_string.setStyleSheet("font-size: 13px; font-weight: 700; color: #374151;")
        h_type = QLabel("Type")
        h_type.setStyleSheet("font-size: 13px; font-weight: 700; color: #374151;")
        h_type.setFixedWidth(60)
        h_type.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(h_date)
        header_layout.addWidget(h_mode)
        header_layout.addWidget(h_string, 1)
        header_layout.addWidget(h_type)
        main_layout.addWidget(header)
        
        # Logs Container (Scroll Area)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        # Disable horizontal scrolling so logs stay on the same page width
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                width: 8px;
                background: transparent;
                margin: 12px 4px 12px 0px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FF6A00, stop:1 #FF8A00);
                border-radius: 4px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FF8A00, stop:1 #FFAA00);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                background: none;
                height: 0px;
                width: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: #e5e7eb;
                border-radius: 4px;
            }
            /* Horizontal scrollbar is disabled in code, so no styling needed here */
        """)
        
        scroll_widget = QWidget()
        self.logs_container = QVBoxLayout(scroll_widget)
        self.logs_container.setSpacing(15)
        self.logs_container.setContentsMargins(0, 0, 0, 0)
        self.logs_container.addStretch()
        
        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)
        
        # Initial load if serial is present
        if self.machine_serial:
            QTimer.singleShot(100, self.refresh_logs)
            
        return page

    def refresh_logs(self):
        # Clear existing logs
        # Remove all widgets from layout except the last stretch item (if we want to keep it, but easier to just clear all)
        while self.logs_container.count():
            item = self.logs_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        serial_no = self.logs_serial_input.text().strip()
        if not serial_no:
            no_data = QLabel("Please enter a serial number to view logs")
            no_data.setStyleSheet("color: #666; font-size: 14px; margin: 20px;")
            no_data.setAlignment(Qt.AlignCenter)
            self.logs_container.addWidget(no_data)
            self.logs_container.addStretch()
            return

        logs = load_logs(serial_no)
        fetched = logs.get("fetched", [])
        sent = logs.get("sent", [])
        
        if not fetched and not sent:
            no_data = QLabel(f"No logs found for serial {serial_no}")
            no_data.setStyleSheet("color: #666; font-size: 14px; margin: 20px;")
            no_data.setAlignment(Qt.AlignCenter)
            self.logs_container.addWidget(no_data)
            self.logs_container.addStretch()
            return
            
        # Combine and sort
        all_logs = []
        for l in fetched:
            all_logs.append(("fetched", l))
        for l in sent:
            all_logs.append(("sent", l))
            
        # Date range filter (optional)
        if getattr(self, "use_date_filter", False):
            try:
                start_date_q = self.logs_from_date.date()
                end_date_q = self.logs_to_date.date()
                start_dt = datetime(start_date_q.year(), start_date_q.month(), start_date_q.day(), 0, 0, 0)
                end_dt = datetime(end_date_q.year(), end_date_q.month(), end_date_q.day(), 23, 59, 59)
                def in_range(ts: str) -> bool:
                    try:
                        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                        return start_dt <= dt <= end_dt
                    except Exception:
                        return True
                all_logs = [(t, e) for (t, e) in all_logs if in_range(e.get("timestamp", ""))]
            except Exception:
                pass
        
        # Sort by timestamp descending
        all_logs.sort(key=lambda x: x[1].get("timestamp", ""), reverse=True)
        
        for idx, (log_type, log_entry) in enumerate(all_logs):
            self.add_log_entry(log_type, log_entry, serial_no, idx)
            
        self.logs_container.addStretch()

    def load_all_logs(self):
        self.use_date_filter = False
        self.refresh_logs()

    def search_logs(self):
        self.use_date_filter = True
        self.refresh_logs()

    def add_test_fetched_string(self):
        """Add a test fetched string for the current serial number"""
        serial_no = self.logs_serial_input.text().strip() or "12345678"
        
        if not serial_no:
            QMessageBox.warning(self, "Error", "Please enter a serial number first.")
            return
        
        # Create a sample BIPAP fetched string
        # Format: *,S,DATE,TIME,MODE,A,CPAP_PRESSURE,MASK,B,IPAP,EPAP,STARTEPAP,TMIN,TMAX,SENSITIVITY,RISETIME,MASK,C,IPAP,EPAP,STARTEPAP,RESPIRATE,TMIN,TMAX,SENSITIVITY,RISETIME,MASK,D,IPAP,EPAP,STARTEPAP,BACKUPRATE,TMIN,TMAX,SENSITIVITY,RISETIME,MASK,E,MAXIPAP,MINIPAP,EPAP,RESPIRATE,TMIN,TMAX,SENSITIVITY,RISETIME,MASK,HEIGHT,TIDALVOLUME,F,RAMPTIME,HUMIDIFIER,TUBETYPE,IMODE,LEAKALERT,GENDER,SLEEPMODE,SERIALNO#
        now = datetime.now()
        date = now.strftime("%d%m%y")
        time_str = now.strftime("%H%M")
        
        # Sample BIPAP string with typical values
        # Format: *,S,DATE,TIME,MODE,A,CPAP_PRESSURE,MASK,B,IPAP,EPAP,STARTEPAP,TMIN,TMAX,SENSITIVITY,RISETIME,MASK,C,IPAP,EPAP,STARTEPAP,RESPIRATE,TMIN,TMAX,SENSITIVITY,RISETIME,MASK,D,IPAP,EPAP,STARTEPAP,BACKUPRATE,TMIN,TMAX,SENSITIVITY,RISETIME,MASK,E,MAXIPAP,MINIPAP,EPAP,RESPIRATE,TMIN,TMAX,SENSITIVITY,RISETIME,MASK,HEIGHT,TIDALVOLUME,F,RAMPTIME,HUMIDIFIER,TUBETYPE,IMODE,LEAKALERT,GENDER,SLEEPMODE,SERIALNO#
        # Note: TMIN and TMAX are stored as integers (multiplied by 10), so 1.5 seconds = 15
        sample_string = f"*,S,{date},{time_str},S_MODE,A,12.0,1.0,B,18.0,8.0,6.0,15,30,2.0,200.0,1.0,C,20.0,10.0,8.0,15.0,20,35,3.0,250.0,1.0,D,22.0,12.0,10.0,12.0,25,40,4.0,300.0,1.0,E,25.0,15.0,10.0,16.0,30,45,5.0,350.0,1.0,170.0,500.0,F,10.0,3.0,1.0,0.0,0.0,1.0,0.0,{serial_no},#"
        
        # Save as fetched log
        save_log(serial_no, "fetched", sample_string)
        
        QMessageBox.information(
            self, 
            "Test Data Added", 
            f"Test fetched string has been added for serial number: {serial_no}\n\n"
            f"Now you can:\n"
            f"1. Go to any mode and change some values\n"
            f"2. Save the settings (this will create a sent string)\n"
            f"3. Come back to Logs to see the changes highlighted with circles"
        )   
        
        # Refresh the logs display
        self.refresh_logs()

    def create_info_page(self):
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("Application Information")
        title.setStyleSheet("font-size: 28px; font-weight: 700; color: #FF6A00; padding: 16px; font-family: 'Segoe UI', sans-serif;")
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)
        
        # Scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                border-radius: 16px;
                background-color: #FAFBFC;
            }
            QScrollBar:vertical {
                border: none;
                background: #f5f5f5;
                width: 12px;
                margin: 0px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF6A00, stop:0.5 #FF8A00, stop:1 #FF6A00);
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF8A00, stop:0.5 #FF6A00, stop:1 #FF8A00);
            }
        """)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(15)
        scroll_layout.setContentsMargins(20, 20, 20, 20)
        
        # Application Info Card
        app_card = QFrame()
        app_card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFFFFF, stop:1 #FAFBFC);
                border-radius: 20px;
                border: none;
                padding: 24px;
            }
        """)
        app_layout = QVBoxLayout(app_card)
        app_layout.setSpacing(10)
        
        app_title = QLabel("CPAP/BIPAP Device Management System")
        app_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #111827; padding-bottom: 12px; font-family: 'Segoe UI', sans-serif;")
        app_layout.addWidget(app_title)
        
        app_info = QLabel(
            "This application provides comprehensive management and monitoring capabilities "
            "for CPAP and BIPAP devices. It allows users to configure device settings, "
            "monitor device status, view logs, and manage therapy modes."
        )
        app_info.setStyleSheet("font-size: 15px; color: #374151; line-height: 1.7; font-family: 'Segoe UI', sans-serif; font-weight: 400;")
        app_info.setWordWrap(True)
        app_layout.addWidget(app_info)
        
        scroll_layout.addWidget(app_card)

        # System Information Card
        system_card = QFrame()
        system_card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFFFFF, stop:1 #FAFBFC);
                border-radius: 20px;
                border: none;
                padding: 24px;
            }
        """)
        system_layout = QVBoxLayout(system_card)
        system_layout.setSpacing(10)
        
        system_title = QLabel("String Data Format Specifications")
        system_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #111827; padding-bottom: 12px; font-family: 'Segoe UI', sans-serif;")
        system_layout.addWidget(system_title)
        
        # VT-60 Data Format Specification
        data_format_text = """-(VT-60) (BIPAP) - *, DATE,TIME,MODE,
A,STARTPRESSURE,MASKTYPE,
B,IPAP,EPAP,STARTEPAP,TMIN,TMAX,SENSITIVITY,RISETIME,MASKTYPE,
C,IPAP,EPAP,STARTEPAP,RESPIRATE,TMIN,TMAX,SENSITIVITY,RISETIME,MASKTYPE,
D,IPAP,EPAP,STARTEPAP,BACKUPRATE,TMIN,TMAX,SENSITIVITY,RISETIME,MASKTYPE,
E,MAXIPAP,MINIPAP,EPAP,RESPIRATE,TMIN,TMAX,SENSITIVITY,RISETIME,MASKTYPE,HEIGHT,TIDALVOLUME,
F,RAMPTIME,HUMIDIFIER,TUBETYPE,IMODE,LEAKALERT,GENDER,SLEEPMODE,SERIALNO
#"""
        
        data_format_label = QLabel(data_format_text)
        data_format_label.setStyleSheet("""
            font-size: 13px; 
            color: #374151; 
            padding: 18px; 
            background-color: #F9FAFB; 
            border: none; 
            border-radius: 12px;
            font-family: 'Courier New', monospace;
        """)
        data_format_label.setWordWrap(False)
        data_format_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        system_layout.addWidget(data_format_label)
        system_layout.addStretch()
        system_layout.addWidget(QLabel("""data format spectification for VT-60 (BIPAP) """))
        
        spacer = QLabel("")
        spacer.setFixedHeight(15)
        system_layout.addWidget(spacer)
        
        # VT-30 (CPAP) Data Format Specification
        data_format_text_vt30 = """VT-30 (CPAP) - *,DATE,TIME,MODE,
G,STARTPRESSURE,MASKTYPE,
H,STARTPRESSURE,MINPRESSURE,MAXPRESSURE,MASKTYPE,
I,RAMPTIME,HUMIDIFIER,TUBETYPE,IMODE,LEAKALERT,GENDER,SLEEPMODE,SERIALNO
#"""
        data_format_label_vt30 = QLabel(data_format_text_vt30)
        data_format_label_vt30.setStyleSheet("""
            font-size: 13px; 
            color: #2c3e50; 
            padding: 15px; 
            background-color: #f8f9fa; 
            border: none; 
            border-radius: 8px;
            font-family: 'Courier New', monospace;
        """)
        data_format_label_vt30.setWordWrap(False)
        data_format_label_vt30.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        system_layout.addWidget(data_format_label_vt30)
       
        scroll_layout.addWidget(system_card)
        # Features Card
        features_card = QFrame()
        features_card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFFFFF, stop:1 #FAFBFC);
                border-radius: 20px;
                border: none;
                padding: 24px;
            }   
        """)
        features_layout = QVBoxLayout(features_card)
        features_layout.setSpacing(10)
        
        features_title = QLabel("Key Features")
        features_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #111827; padding-bottom: 12px; font-family: 'Segoe UI', sans-serif;")
        features_layout.addWidget(features_title)
        
        features_list = [
            "• Real-time device status monitoring",
            "• Multiple therapy mode configurations (CPAP, AutoCPAP, S, T, ST, VAPS)",
            "• Settings management and customization",
            "• Comprehensive logging and audit trail",
            "• Report generation and data export",
            "• Cloud connectivity via AWS IoT",
            "• User authentication and session management"
        ]
        
        for feature in features_list:
            feature_label = QLabel(feature)
            feature_label.setStyleSheet("font-size: 15px; color: #374151; padding: 6px 0px; font-family: 'Segoe UI', sans-serif; font-weight: 400;")
            feature_label.setWordWrap(True)
            features_layout.addWidget(feature_label)
        
        scroll_layout.addWidget(features_card)
        
        # Version/Contact Card (optional)
        contact_card = QFrame()
        contact_card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFFFFF, stop:1 #FAFBFC);
                border-radius: 20px;
                border: none;
                padding: 24px;
            }
        """)
        contact_layout = QVBoxLayout(contact_card)
        contact_layout.setSpacing(10)
        
        contact_title = QLabel("Support")
        contact_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #111827; padding-bottom: 12px; font-family: 'Segoe UI', sans-serif;")
        contact_layout.addWidget(contact_title)
    
        support_text = QLabel(
            "For technical support or questions about this application, "
            "please contact your system administrator or refer to the user manual."
        )
        support_text.setStyleSheet("font-size: 15px; color: #374151; line-height: 1.7; font-family: 'Segoe UI', sans-serif; font-weight: 400;")
        support_text.setWordWrap(True)
        contact_layout.addWidget(support_text)
        
        scroll_layout.addWidget(contact_card)
        
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)
        return page

    def add_log_entry(self, log_type, log_entry, serial_no, index):
        """Add a single log entry to the display with formatted fields"""
        timestamp_full = log_entry.get("timestamp", "")
        data_string = log_entry["string"]
        
        card = QFrame()
        card.setMinimumHeight(80)
        
        bg_color = "#FFFFFF" if (index % 2 == 0) else "#FBFBFD"
        style = "QFrame {{ background: {}; border: 1px solid #eaecef; border-radius: 12px; }} QFrame:hover {{ border-color: #d0d7de; }}".format(bg_color)
        card.setStyleSheet(style)
        card_layout = QHBoxLayout(card)
        card_layout.setSpacing(4)
        card_layout.setContentsMargins(8, 6, 8, 6)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 25))
        card.setGraphicsEffect(shadow)
        
        if timestamp_full:
            try:
                parts_ts = timestamp_full.split(" ")
                if len(parts_ts) >= 2:
                    date_val = parts_ts[0]
                    time_val = parts_ts[1][:5]
                    datetime_val = f"{date_val}\n{time_val}"
            except Exception:
                pass
        
        mode_val = "Unknown"
        raw_parts = data_string.strip().split(",")
        if len(raw_parts) > 4:
            if raw_parts[0] == "*":
                mode_val = raw_parts[4]
            elif raw_parts[0] == "S":
                mode_val = raw_parts[3]
            else:
                mode_val = raw_parts[4]
        
        # Simplify mode display
        mode_val = mode_val.replace("_MODE", "").replace("MODE", "")
        
        datetime_lbl = QLabel(f"{datetime_val}")
        datetime_lbl.setStyleSheet("font-weight: 600; color: #1f2937; font-size: 12px;")
        datetime_lbl.setFixedWidth(100) # Adjusted width
        datetime_lbl.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(datetime_lbl)
        
        mode_lbl = QLabel(f"{mode_val}")
        mode_lbl.setStyleSheet("font-weight: 600; color: #0b69ff; font-size: 12px;")
        mode_lbl.setFixedWidth(60)
        mode_lbl.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(mode_lbl)
        
        comparison_string = None
        if log_type == "sent":
            logs = load_logs(serial_no)
            fetched_logs = logs.get("fetched", [])
            for fetched in sorted(fetched_logs, key=lambda x: x["timestamp"], reverse=True):
                if fetched["timestamp"] <= timestamp_full:
                    comparison_string = fetched["string"]
                    break
        string_label = QLabel()
        # Allow the long data string to wrap within the available width so that
        # no horizontal scrollbar is needed and everything stays on the same page.
        string_label.setWordWrap(True)
        string_label.setTextFormat(Qt.RichText)
        string_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if comparison_string and log_type == "sent":
            highlighted_text = self.highlight_changes(comparison_string, data_string)
            string_label.setText(highlighted_text)
        else:
            string_label.setText(f'<span style="font-family: monospace; font-size: 11px;">{data_string}</span>')
            
        string_label.setStyleSheet("QLabel { background-color: #F6F8FA; border: 1px solid #e5e7eb; border-radius: 6px; padding: 6px 8px; font-family: monospace; font-size: 11px; color: #111827; }")
        string_label.setToolTip(data_string)
        card_layout.addWidget(string_label, 1)
        
        type_text_str = "▲" if log_type == "sent" else "▼"
        if log_type == "fetched":
            type_bg = "#22c55e"
        else:
            type_bg = "#3b82f6"
            
        type_lbl = QLabel(type_text_str)
        type_lbl.setAlignment(Qt.AlignCenter)
        style = "QLabel {{ background-color: {}; color: white; font-weight: 800; border-radius: 8px; padding: 1px 3px; font-size: 12px; min-width: 30px; max-width: 30px; }}".format(type_bg)
        type_lbl.setStyleSheet(style)
        type_lbl.setFixedWidth(30)
        card_layout.addWidget(type_lbl)
        
        self.logs_container.addWidget(card)
    
    def highlight_changes(self, fetched_string, sent_string):
        """Compare fetched and sent strings and highlight changes with circles"""
        # Parse both strings into parts
        fetched_parts = fetched_string.strip("*#").split(",")
        sent_parts = sent_string.strip("*#").split(",")
        
        # Find differences
        highlighted_parts = []
        max_len = max(len(fetched_parts), len(sent_parts))
        
        for i in range(max_len):
            fetched_val = fetched_parts[i].strip() if i < len(fetched_parts) else ""
            sent_val = sent_parts[i].strip() if i < len(sent_parts) else ""
            
            if fetched_val != sent_val:
                # Changed value - highlight with circle effect
                # Using a combination of background circle and border
                highlighted_parts.append(
                    f'<span style="background-color: #fde68a; color: #111827; border: 1px solid #f59e0b; border-radius: 50%; padding: 2px 6px; font-weight: 600; display: inline-block; min-width: 24px; text-align: center; line-height: 1.2; margin: 1px;">{sent_val}</span>'
                )
            else:
                # Unchanged value - escape HTML special characters
                escaped_val = sent_val.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                highlighted_parts.append(escaped_val)
        
        # Reconstruct string with highlighting - add commas between parts
        result = []
        for i, part in enumerate(highlighted_parts):
            
            result.append(part)
            if i < len(highlighted_parts) - 1:  # Add comma after each part except the last
                result.append(",")
        
        highlighted_string = "".join(result)
        return f'<span style="font-family: monospace; font-size: 11px; white-space: nowrap;">*{highlighted_string}#</span>'

    def update_all_from_cloud(self, message):
        # Support both plain strings and dict messages with optional explicit serial override.
        if isinstance(message, dict):
            device_data = message.get("device_data")
            serial_override = (message.get("serial") or "").strip()
        else:
            device_data = message
            serial_override = ""
            
        if not isinstance(device_data, str):
            QMessageBox.warning(self, "Error", f"Invalid device data: expected string, got {type(device_data)}")
            return

        device_data = device_data.strip()
        if not (device_data.startswith("*") and device_data.endswith("#")):
            QMessageBox.warning(self, "Error", "Device data must start with '*' and end with '#'. ")
            return

        parts = [p.strip() for p in device_data[1:-1].split(",")]
        print(f"Parsed parts: {parts[:10]}...")  # Show first 10 parts
        print(f"Machine type: {self.machine_type}")

        # Extract serial number from the data if available, otherwise use current machine_serial.
        serial_from_data = ""
        try:
            # Serial is typically at the end of the F or I section
            if "F" in parts:
                f_idx = parts.index("F")
                if f_idx + 8 < len(parts):
                    serial_from_data = parts[f_idx + 8].rstrip(",")
            elif "I" in parts:
                i_idx = parts.index("I")
                if i_idx + 8 < len(parts):
                    serial_from_data = parts[i_idx + 8].rstrip(",")
        except Exception:
            pass
        
        # Decide which serial to treat as the "active device":
        # 1) explicit override (e.g. Admin's typed serial on Fetch),
        # 2) serial parsed from the data string,
        # 3) existing machine_serial.
        # Always normalize so logs/settings/UI all use the same base serial.
        raw_serial_key = (serial_override or serial_from_data or self.machine_serial or "").strip()
        serial_key = normalize_serial(raw_serial_key)
        if serial_key:
            self.machine_serial = serial_key
            # Keep key UI elements in sync so the whole dashboard treats this as the new device.
            if hasattr(self, "serial_input") and self.serial_input:
                self.serial_input.setText(serial_key)
            if hasattr(self, "logs_serial_input") and self.logs_serial_input:
                self.logs_serial_input.setText(serial_key)
            if hasattr(self, "info_label") and self.info_label:
                self.info_label.setText(f"User: ({self.user_name})    |    Machine S/N: ({serial_key})")
            # Track as recently active
            try:
                self.add_active_serial_to_list(serial_key, self.machine_type)
                self.update_recent_serial(serial_key)
                self.update_active_serial_numbers_display()
            except Exception:
                pass
        # Log the fetched string
        if serial_key:
            save_log(serial_key, "fetched", device_data)
        # Load settings for this specific serial number
        self.all_settings = load_all_settings(serial_key) if serial_key else {}
        mask_map_inv = {"1.0": "Nasal", "2.0": "Pillow", "3.0": "FullFace"}
        gender_map_inv = {"1.0": "Male", "2.0": "Female", "3.0": "Other"}

        try:
            print(f"Entering parsing for machine type: {self.machine_type}")
            if self.machine_type == "CPAP":
                print("Parsing CPAP settings (VT30 format)")

                # G - CPAP Manual Mode
                if "G" in parts:
                    g_idx = parts.index("G")
                    set_p = float(parts[g_idx + 1])
                    mask_type_code = parts[g_idx + 2] if g_idx + 2 < len(parts) else "1.0"
                    key_tube = f"{float(mask_type_code):.1f}"
                    mask_type = mask_map_inv.get(key_tube, "Nasal")
                    self.all_settings["CPAP"] = {"Set Pressure": set_p, "Mask Type": mask_type}

                # H - AutoCPAP Mode  
                if "H" in parts:
                    h_idx = parts.index("H")
                    start_p = float(parts[h_idx + 1])
                    min_p = float(parts[h_idx + 2])
                    max_p = float(parts[h_idx + 3])
                    mask_type_code = parts[h_idx + 4] if h_idx + 4 < len(parts) else "1.0"
                    key_tube = f"{float(mask_type_code):.1f}"
                    mask_type = mask_map_inv.get(key_tube, "Nasal")
                    self.all_settings["AutoCPAP"] = {
                        "Start Pressure": start_p, 
                        "Min Pressure": min_p, 
                        "Max Pressure": max_p,
                        "Mask Type": mask_type
                    }

                # I - Settings
                    i_idx = parts.index("I")
                    ramp = float(parts[i_idx + 1])
                    hum = float(parts[i_idx + 2])
                    tube = parts[i_idx + 3]
                    imode_num = float(parts[i_idx + 4])
                    leak_num = float(parts[i_idx + 5])
                    gender_num = parts[i_idx + 6]
                    sleep_num = float(parts[i_idx + 7])
                    key_tube = f"{float(tube):.1f}"
                    mask_type = mask_map_inv.get(key_tube, "Nasal")
                    imode = "ON" if imode_num == 1.0 else "OFF"
                    leak = "ON" if leak_num == 1.0 else "OFF"
                    key_gender = f"{float(gender_num):.1f}"
                    gender = gender_map_inv.get(key_gender, "Male")
                    sleep = "ON" if sleep_num == 1.0 else "OFF"
                    
                    all_settings = {
                        "Ramp Time": ramp,
                        "Humidifier": hum,
                    "Mask Type": mask_type,
                        "IMODE": imode,
                        "Leak Alert": leak,
                        "Gender": gender,
                        "Sleep Mode": sleep,
                    }
                    self.all_settings["Settings"] = all_settings

            elif self.machine_type == "BIPAP":
                print("Parsing BIPAP settings (VT60 format)")
                
                # A - CPAP Mode
                if "A" in parts:
                    a_idx = parts.index("A")
                    set_p = float(parts[a_idx + 1])
                    mask_type_code = parts[a_idx + 2] if a_idx + 2 < len(parts) else "1.0"
                    key_tube = f"{float(mask_type_code):.1f}"
                    mask_type = mask_map_inv.get(key_tube, "Nasal")
                    self.all_settings["CPAP"] = {"Set Pressure": set_p, "Mask Type": mask_type}

                # B - S Mode
                if "B" in parts:
                    b_idx = parts.index("B")
                    ipap = float(parts[b_idx + 1])
                    epap = float(parts[b_idx + 2])
                    start_epap = float(parts[b_idx + 3])
                    ti_min = float(parts[b_idx + 4]) / 10.0  # Convert back from *10
                    ti_max = float(parts[b_idx + 5]) / 10.0  # Convert back from *10
                    sensitivity = float(parts[b_idx + 6])
                    rise_time = float(parts[b_idx + 7])
                    mask_type_code = parts[b_idx + 8] if b_idx + 8 < len(parts) else "1.0"
                    key_tube = f"{float(mask_type_code):.1f}"
                    mask_type = mask_map_inv.get(key_tube, "Nasal")
                    
                    self.all_settings["S"] = {
                        "IPAP": ipap, "EPAP": epap, "Start EPAP": start_epap,
                        "Ti.Min": ti_min, "Ti.Max": ti_max, "Sensitivity": sensitivity,
                        "Rise Time": rise_time, "Mask Type": mask_type
                    }

                # C - T Mode
                if "C" in parts:
                    c_idx = parts.index("C")
                    ipap = float(parts[c_idx + 1])
                    epap = float(parts[c_idx + 2])
                    start_epap = float(parts[c_idx + 3])
                    resp_rate = float(parts[c_idx + 4])
                    ti_min = float(parts[c_idx + 5]) / 10.0  # Convert back from *10
                    ti_max = float(parts[c_idx + 6]) / 10.0  # Convert back from *10
                    sensitivity = float(parts[c_idx + 7])
                    rise_time = float(parts[c_idx + 8])
                    mask_type_code = parts[c_idx + 9] if c_idx + 9 < len(parts) else "1.0"
                    key_tube = f"{float(mask_type_code):.1f}"
                    mask_type = mask_map_inv.get(key_tube, "Nasal")
                    
                    self.all_settings["T"] = {
                        "IPAP": ipap, "EPAP": epap, "Start EPAP": start_epap,
                        "Respiratory Rate": resp_rate, "Ti.Min": ti_min, "Ti.Max": ti_max,
                        "Sensitivity": sensitivity, "Rise Time": rise_time, "Mask Type": mask_type
                    }

                # D - ST Mode
                if "D" in parts:
                    d_idx = parts.index("D")
                    ipap = float(parts[d_idx + 1])
                    epap = float(parts[d_idx + 2])
                    start_epap = float(parts[d_idx + 3])
                    backup_rate = float(parts[d_idx + 4])
                    ti_min = float(parts[d_idx + 5]) / 10.0  # Convert back from *10
                    ti_max = float(parts[d_idx + 6]) / 10.0  # Convert back from *10
                    sensitivity = float(parts[d_idx + 7])
                    rise_time = float(parts[d_idx + 8])
                    mask_type_code = parts[d_idx + 9] if d_idx + 9 < len(parts) else "1.0"
                    key_tube = f"{float(mask_type_code):.1f}"
                    mask_type = mask_map_inv.get(key_tube, "Nasal")
                    
                    self.all_settings["ST"] = {
                        "IPAP": ipap, "EPAP": epap, "Start EPAP": start_epap,
                        "Backup Rate": backup_rate, "Ti.Min": ti_min, "Ti.Max": ti_max,
                        "Sensitivity": sensitivity, "Rise Time": rise_time, "Mask Type": mask_type
                    }

                # E - VAPS Mode
                if "E" in parts:
                    e_idx = parts.index("E")
                    max_ipap = float(parts[e_idx + 1])
                    min_ipap = float(parts[e_idx + 2])
                    epap = float(parts[e_idx + 3])
                    resp_rate = float(parts[e_idx + 4])
                    ti_min = float(parts[e_idx + 5]) / 10.0  # Convert back from *10
                    ti_max = float(parts[e_idx + 6]) / 10.0  # Convert back from *10
                    sensitivity = float(parts[e_idx + 7])
                    rise_time = float(parts[e_idx + 8])
                    mask_type_code = parts[e_idx + 9] if e_idx + 9 < len(parts) else "1.0"
                    key_tube = f"{float(mask_type_code):.1f}"
                    mask_type = mask_map_inv.get(key_tube, "Nasal")
                    height = float(parts[e_idx + 10]) if e_idx + 10 < len(parts) else 170.0
                    tidal_volume = float(parts[e_idx + 11]) if e_idx + 11 < len(parts) else 500.0
                    
                    self.all_settings["VAPS"] = {
                        "Max IPAP": max_ipap, "Min IPAP": min_ipap, "EPAP": epap,
                        "Respiratory Rate": resp_rate, "Ti.Min": ti_min, "Ti.Max": ti_max,
                        "Sensitivity": sensitivity, "Rise Time": rise_time, "Mask Type": mask_type,
                        "Height": height, "Tidal Volume": tidal_volume
                    }

                # F - Settings (common for all modes)
                if "F" in parts:
                    f_idx = parts.index("F")
                    ramp = float(parts[f_idx + 1])
                    hum = float(parts[f_idx + 2])
                    tube = parts[f_idx + 3]
                    imode_num = float(parts[f_idx + 4])
                    leak_num = float(parts[f_idx + 5])
                    gender_num = parts[f_idx + 6] if f_idx + 6 < len(parts) else "1.0"
                    sleep_num = float(parts[f_idx + 7]) if f_idx + 7 < len(parts) else 1.0
                    
                    # Tubetype mapping
                    tube_map = {"1.0": "Standard", "2.0": "Slimline", "3.0": "Heated"}
                    key_tube = f"{float(tube):.1f}"
                    tubetype = tube_map.get(key_tube, "Standard")
                    
                    imode = "ON" if imode_num == 1.0 else "OFF"
                    leak = "ON" if leak_num == 1.0 else "OFF"
                    key_gender = f"{float(gender_num):.1f}"
                    gender = gender_map_inv.get(key_gender, "Male")
                    sleep = "ON" if sleep_num == 1.0 else "OFF"
                    
                    all_settings = {
                        "Ramp Time": ramp,
                        "Humidifier": hum,
                        "Tubetype": tubetype,
                        "IMode": imode,
                        "Leak Alert": leak,
                        "Gender": gender,
                        "Sleep Mode": sleep,
                    }
                    self.all_settings["Settings"] = all_settings

        except ValueError as ve:
            QMessageBox.warning(self, "Error", f"Invalid data format: {str(ve)}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to parse settings: {str(e)}")

        print(f"Parsed settings for {len(self.all_settings)} modes: {list(self.all_settings.keys())}")
        # Save settings per serial number
        if serial_key:
            try:
                with open(SETTINGS_FILE, "r") as f:
                    all_serials_data = json.load(f)
            except Exception:
                all_serials_data = {}
                
            all_serials_data[serial_key] = self.all_settings
            
            with open(SETTINGS_FILE, "w") as f:
                json.dump(all_serials_data, f, indent=4)
            
            self.load_settings()
            self.update_alerts()
            self.update_button_states()
            
            # Log the fetched string
            if serial_key:
                save_log(serial_key, "fetched", device_data)
            
            QMessageBox.information(self, "Success", "Settings loaded from cloud into UI!")
            
    def update_stats(self):
        elapsed = time.time() - self.start_time
        hours = elapsed / 3600
        therapy_hours = hours if self.therapy_active else 0
        try:
            if hasattr(self, 'therapy_usage_label') and self.therapy_usage_label:
                self.therapy_usage_label.setText(f"({therapy_hours:.1f}) hours")
            if hasattr(self, 'machine_up_time_label') and self.machine_up_time_label:
                self.machine_up_time_label.setText(f"({hours:.1f}) hours")
        except RuntimeError: 
            pass
    def update_recent_serial(self, serial: str):
        """
        Update the 'Recently Searched Serial No' card with serial and timestamp.
        Call this whenever you want the card to reflect a new serial.
        """
        try:
            if not hasattr(self, 'recent_serial_label') or not hasattr(self, 'recent_time_label'):
                # UI may not have been created yet
                return
            display_serial = str(serial) if serial else "(None)"
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.recent_serial_label.setText(f"({display_serial})")
            self.recent_time_label.setText(f"({now})")
        except Exception as e:

            print(f"Failed to update recent serial UI: {e}")

    def update_active_serial_numbers_display(self):
        # Clear existing serial number labels
        # We need to ensure self.active_serials_list is initialized before trying to clear it.
        # It's initialized in create_dashboard_page, so we should only call this after the UI is built.
        if not hasattr(self, 'active_serials_list') or not self.active_serials_list:
            return 

        while self.active_serials_list.count() > 1: # Keep the title label
            item = self.active_serials_list.takeAt(1) # Take from index 1 to preserve title
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # If it's a layout, clear its widgets and then delete it
                while item.layout().count():
                    sub_item = item.layout().takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()
                item.layout().deleteLater()

        # Add new serial number labels
        if self.recently_active_serials:
            for serial_num, machine_type in self.recently_active_serials:
                serial_label = QLabel(f"{serial_num} ({machine_type})")
                serial_label.setStyleSheet("font-size: 14px; font-weight: 500; color: #374151; padding: 2px; font-family: 'Segoe UI', sans-serif;")
                self.active_serials_list.addWidget(serial_label)
        else:
            no_serials_label = QLabel("No active serials yet.")
            no_serials_label.setStyleSheet("font-size: 14px; color: " + THEME_TEXT_SOFT + "; padding: 2px; font-family: 'Segoe UI', sans-serif; font-style: italic;")
            self.active_serials_list.addWidget(no_serials_label)
    
    def add_active_serial_to_list(self, serial: str, machine_type: str):
        if not serial or not serial.strip(): 
            return

        new_entry = (serial, machine_type)

        # Remove if already present to move it to the end (most recent)
        # We need to check only the serial part of the tuple
        self.recently_active_serials = [entry for entry in self.recently_active_serials if entry[0] != serial]
        
        # Add to the end
        self.recently_active_serials.append(new_entry)

        # Keep only the last 3 active serials
        if len(self.recently_active_serials) > 3:
            self.recently_active_serials = self.recently_active_serials[-3:]
        
        self.update_active_serial_numbers_display()

    
    def extract_date_and_update_user_count(self, device_data_str):
        """Extract date from device data string and update user count for that month."""
        try:
            # Device data format: *S,DDMMYY,HHMM,...#
            # Look for date pattern in the string
            import re
            
            # Pattern for date: 2 digits day, 2 digits month, 2 digits year
            date_match = re.search(r'\b(\d{2})(\d{2})(\d{2})\b', device_data_str)
            
            if date_match:
                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3))
                
                # Convert 2-digit year to 4-digit (assuming 2000s)
                full_year = 2000 + year if year < 100 else year
                
                # Get month abbreviation
                month_abbr = calendar.month_abbr[month]
                
                # Load current active users data
                data = load_active_users_file()
            
                
                # Increment count for this month
                current_count = data.get(month_abbr, 0)
                data[month_abbr] = current_count + 1
                
                # Save updated data
                save_active_users_file(data)
                
                # Emit signal to notify about data change
                if hasattr(self, 'active_users_data_changed'):
                    self.active_users_data_changed.emit()
                
                # Update local active_users
                self.active_users = data
                
                # Update pie chart
                # self.update_pie_chart()
                
                print(f"Updated user count for {month_abbr} {full_year}: {current_count + 1}")
                
                return True
            else:
                print("No date found in device data")
                return False
                
        except Exception as e:
            print(f"Error extracting date and updating user count: {e}")
            return False

    def update_total_active_devices_kpi(self):
        """Updates the 'Total Active Devices' KPI card with the latest count."""
        total_devices = get_total_active_devices()
        self.total_active_devices_kpi.value_label.setText(str(total_devices))
        print(f"Updated 'Total Active Devices' KPI to: {total_devices}")
            
    # --- Active users / pie chart helpers ---


    # def update_pie_chart(self):
    #     """Read `self.active_users` (or file) and update the matplotlib pie chart."""
    #     try:
    #         # prefer dashboard canvas, fall back to admin canvas if present
    #         target_ax = None
    #         target_canvas = None
    #         if hasattr(self, 'ax') and hasattr(self, 'canvas'):
    #             target_ax = self.ax
    #             target_canvas = self.canvas
    #         elif hasattr(self, 'admin_ax') and hasattr(self, 'admin_canvas'):
    #             target_ax = self.admin_ax
    #             target_canvas = self.admin_canvas
    #         else:
    #             return

    #         data = getattr(self, 'active_users', None) or load_active_users_file()
    #         # Sort months by calendar order
    #         months = [calendar.month_abbr[i] for i in range(1,13)]
    #         counts = [int(data.get(m, 0)) for m in months]
            
    #         # If all zeros, show sample slice to avoid matplotlib warnings
    #         if sum(counts) == 0:
    #             counts = [1 if i == 0 else 0 for i in range(12)]
            
    #         target_ax.clear()
            
    #         # Create color palette
    #         colors = plt.cm.Set3(np.arange(12) / 12)
            
    #         # Create pie chart with bigger fonts and explode for current month
    #         explode = [0.05 if i == datetime.now().month - 1 else 0 for i in range(12)]
            
    #         wedges, texts, autotexts = target_ax.pie(
    #             counts, 
    #             labels=months, 
    #             autopct='%1.1f%%', 
    #             startangle=90,
    #             colors=colors,
    #             explode=explode,
    #             textprops={'fontsize': 10, 'fontweight': 'bold'}
    #         )
            
    #         target_ax.set_title('Active Users by Month', fontsize=14, fontweight='bold', pad=20)
            
    #         # Make labels bigger
    #         for t in texts:
    #             t.set_fontsize(11)
    #             t.set_fontweight('bold')
            
    #         # Make percentage labels bigger
    #         for at in autotexts:
    #             at.set_fontsize(10)
    #             at.set_fontweight('bold')
    #             at.set_color('darkred')
            
    #         try:
    #             if hasattr(target_ax, 'figure'):
    #                 target_ax.figure.tight_layout()
    #         except Exception:
    #             pass
            
    #         try:
    #             target_canvas.draw_idle()
    #         except Exception:
    #             try:
    #                 target_canvas.draw()
    #             except Exception:
    #                 pass
            
    #         # Print debug info
    #         print(f"Pie chart updated: {dict(zip(months, counts))}")
            
    #     except Exception as e:
    #         print(f"update_pie_chart error: {e}")
    #         import traceback
    #         traceback.print_exc()

    def resizeEvent(self, event):
        """Handle window resize to maintain responsive layout"""
        super().resizeEvent(event)
        width = self.width()
        if width < 1200:
            self.sidebar_frame.setMaximumWidth(200)
        elif width < 1600:
            self.sidebar_frame.setMaximumWidth(280)
        else:
            self.sidebar_frame.setMaximumWidth(350)

    def update_alerts(self):
        self.load_settings()
        if hasattr(self, 'alert_labels'):
            for setting in self.alert_labels:
                value = self.settings.get(setting, self.default_values['Settings'].get(setting, 'OFF'))
                try:
                    fvalue = float(value)
                    disp = f"{fvalue:.1f}"
                except:
                    disp = str(value)
                self.alert_labels[setting].setText(f"{setting}: ({disp})")
                self.alert_labels[setting].setStyleSheet("color: red;" if "Alert" in setting and str(value).upper() == "ON" else "color: green; font-size: calc(12px + 0.02 * 100vw); padding: 2px;")

    def export_pdf(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Save PDF", "", "PDF Files (*.pdf)")
        if file_name:
            QMessageBox.information(self, "Export", "PDF exported to " + file_name)

    def export_csv(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV Files (*.csv)")
        if file_name:
            QMessageBox.information(self, "Export", "CSV exported to " + file_name) 
            
    def do_logout(self):
        if self.login_window:
            self.login_window.show()
        self.close()
    

    def reset_mode(self, mode_name):
        """Reset the specified mode to default values"""
        print(f"DEBUG: reset_mode called for mode: {mode_name}")
        
        # Get default values for the mode
        default_settings = self.default_values.get(mode_name, {})
        
        # Update the settings with defaults
        if mode_name in self.all_settings:
            self.all_settings[mode_name] = default_settings.copy()
        
        # Refresh the current page to show updated values
        current_index = self.stack.currentIndex()
        current_name = self.stack.currentWidget().objectName()
        if current_name == mode_name:
            # Refresh the current mode page
            self.stack.removeWidget(self.stack.currentWidget())
            self.create_mode_page(mode_name)
            self.stack.setCurrentIndex(current_index)
        
        QMessageBox.information(self, "Reset", f"{mode_name} settings reset to defaults")

    def set_mode(self, index, name):
        print(f"DEBUG: set_mode called with index={index}, name='{name}', stack.count()={self.stack.count()}")  # Debug
        if index >= self.stack.count():
            QMessageBox.warning(self, "Error", f"Page index {index} is out of range!")
            return
        # No auto-save on mode switch
        # ...existing code...
        self.stack.setCurrentIndex(index)
        mode_name = name.replace(" Mode", "")
        if mode_name in self.mode_map:
            self.current_mode = mode_name
        self.current_mode_label.setText(f"Current Mode: {name}")
        if name == "Dashboard":
            self.update_alerts()
        elif name == "Logs":
            # Refresh logs when switching to Logs mode
            if hasattr(self, 'logs_serial_input'): 
                self.refresh_logs()
    def create_page(self, text):
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 18px; color: #30A8FF; font-weight: bold; padding: 5px;")
        layout.addWidget(label)
        return page

    def create_mode_page(self, mode_name, params, options_mode=False):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.setContentsMargins(5, 5, 5, 5)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(20)
        self.value_labels[mode_name] = {}
        row, col = 0, 0

        for i, (title, val) in enumerate(params.items()):
            if options_mode:
                options = []
                numerical_options = False
                min_val = 0.0
                max_val = 0.0

                if title in ["i mode", "Leak alert", "Sleep Mode"]:
                    options = ["OFF", "ON"]
                elif title == "Gender":
                    options = ["Male", "Female"]
                elif title == "Mask Type":
                    options = ["Nasal", "Pillow", "full face"]
                elif title == "Tubetype":
                    options = ["Standard", "Slimline", "Heated"]
                elif title == "Ramp Time":
                    numerical_options = True
                    min_val = 5.0
                    max_val = 45.0
                    max_val = 50.0

                if numerical_options:
                    card = self.create_card(title, val, min_val, max_val, mode_name)
                else:
                    card = self.create_option_card(title, val, options)
            else:
                card = self.create_card(title, val, 4.0 if title in ["Min Pressure", "Max Pressure"] else val if val > 0 else 0, 20.0 if title in ["Min Pressure", "Max Pressure"] else val * 10 + 20, mode_name)
            
            grid.addWidget(card, row, col)
            self.value_labels[mode_name][title] = card.findChildren(QLabel)[1]
            col += 1
            if col > 2:
                col = 0
                row += 1
                row += 2
                row += 3
                
        # Set column stretch to ensure proportional scaling
        for c in range(3):
            grid.setColumnStretch(c, 1)

        layout.addLayout(grid)
        layout.addStretch()

        # Save and Reset buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.setAlignment(Qt.AlignCenter)
        btn_save = QPushButton("Save")
        btn_reset = QPushButton("Reset")

        btn_style = """
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                                            stop:0 """ + THEME_PRIMARY + """, stop:1 """ + THEME_PRIMARY_2 + """);
                color: white;
                font-weight: 600;
                font-size: 18px;
                border-radius: 18px;
                border: none;
                padding: 16px 28px;
                font-family: 'Segoe UI', sans-serif;
            }   
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                                            stop:0 """ + THEME_PRIMARY_2 + """, stop:1 """ + THEME_PRIMARY + """);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                                            stop:0 #057D84, stop:1 #046469);
            }
        """
        for btn in [btn_save, btn_reset]:
            btn.setFixedSize(170, 45)    
            btn.setStyleSheet(btn_style)
        @pyqtSlot()
        def on_save_clicked():
            btn_save.setEnabled(False)
            btn_save.setText("Saving...")
            # Save and send only current mode
            self.save_mode(mode_name, send_to_cloud=True)
            QTimer.singleShot(2000, lambda: (btn_save.setEnabled(True), btn_save.setText("Save")))

        btn_save.clicked.connect(on_save_clicked)
        btn_reset.clicked.connect(lambda: self.reset_mode(mode_name))  

        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_reset)
        layout.addLayout(btn_layout)
        
        return page

    def create_card(self, title, value, min_val, max_val, mode_name):
        unit_map = {
            "IPAP":"CmH2O", "EPAP":"CmH2O", "Start EPAP":"CmH2O",
            "Rise Time":"mSec", "Ti.Min":"Sec", "Ti.Max":"Sec",
            "Ti (Insp. Time)":"Sec", "Height":"cm", "Tidal Volume":"ml",
            "Set Pressure": "CmH2O" if mode_name == "CPAP" else "",
            "Sensitivity": "", "Min IPAP":"CmH2O","Max IPAP":"CmH2O",
            "Min Pressure":"CmH2O", "Max Pressure":"CmH2O", "Backup Rate":"/min",
            "Respiratory Rate":"/min"
        }
        unit = unit_map.get(title, "")

        card = QFrame() 
        card.setObjectName("ParamCard") 
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setStyleSheet(f"""
            QFrame#ParamCard {{
                border: 1px solid #06919B;
                border-radius: 10px;
            }}
            QFrame#ParamCard:hover {{
            }}
        """)
        main_layout = QHBoxLayout(card)
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(8, 8, 8, 8)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)

        label_title = QLabel(title)
        label_title.setObjectName("ParamTitle") 
        label_title.setAlignment(Qt.AlignCenter)
        label_title.setStyleSheet("color: #6B7280; font-size: 15px; font-weight: 500;")

        value_label = QLabel(f"{float(value):.1f}") 
        value_label.setObjectName("ParamValue") 
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet("color: #06919B; font-size: 32px; font-weight: 700;")
        text_layout.addWidget(label_title)
        text_layout.addWidget(value_label)
        # Add unit label if available
        if unit:
            unit_label = QLabel(unit)
            unit_label.setObjectName("ParamUnit") 
            unit_label.setAlignment(Qt.AlignCenter)
            unit_label.setStyleSheet("color: #9CA3AF; font-size: 14px;")
            text_layout.addWidget(unit_label)

        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(5)
        btn_layout.setAlignment(Qt.AlignVCenter)

        
        pressure_params = {
            "Set Pressure": 0.2,
            "Min Pressure": 0.2,
            "Max Pressure": 0.2,
            "IPAP": 0.2,
            "EPAP": 0.2,
            "Start EPAP": 0.2,
            "Min IPAP": 0.2,
            "Max IPAP": 0.2
        }
        step = pressure_params.get(title, 0.1 if (max_val - min_val) < 10 else 1)
        step = step if step > 0 else 0.1
        step = step if step < 1 else 1 

        print (f"DEBUG ")
        print (f"DEBUG: max_val = {max_val}")
        print (f"DEBUG: min_val = {min_val}")
        print (f"DEBUG: title = {title}")
        print (f"DEBUG: value = {value}")
        print (f"DEBUG: unit = {unit}")
        print (f"DEBUG: mode_name = {mode_name}")
        print (f"DEBUG: pressure_params = {pressure_params}")
        print (f"DEBUG: step = {step}")

        # Up Arrow Button
        btn_up = QPushButton("▲")
        btn_up.setFixedSize(40, 32) # Adjusted size based on QToolButton spec
        btn_up.setStyleSheet("""
            QPushButton {
                background-color: #E0F7FA; /* Light Cyan */
                color: #00796B; /* Dark Cyan */
                border-radius: 10px;
                width: 40px;
                height: 32px;
                font-size: 20px; /* Slightly larger font for the arrows */
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #B2EBF2; /* Slightly darker cyan on hover */
            }
            QPushButton:pressed {
                background-color: #80DEEA; /* Even darker cyan when pressed */
            }
        """)

        # Down Arrow Button
        btn_down = QPushButton("▼")
        btn_down.setFixedSize(40, 32) # Adjusted size based on QToolButton spec
        btn_down.setStyleSheet("""
            QPushButton {
                background-color: #E0F7FA; /* Light Cyan */
                color: #00796B; /* Dark Cyan */
                border-radius: 10px;
                width: 40px;
                height: 32px;
                font-size: 20px; /* Slightly larger font for the arrows */
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #B2EBF2; /* Slightly darker cyan on hover */
            }
            QPushButton:pressed {
                background-color: #80DEEA; /* Even darker cyan when pressed */
            }
        """)

        def increase():
            try:
                # Get current text from the label
                current_text = value_label.text()
                # Remove parentheses and extract number - handle format like "(4.0 CmH2O)" or "(4.0)"
                text_clean = current_text.strip().lstrip("(").rstrip(")")
                # Extract the first number from the text (handles units after the number)
                num_match = re.search(r'[-+]?\d*\.?\d+', text_clean)
                if num_match:
                    val = float(num_match.group())
                    new_val = val + step
                    # Ensure value doesn't exceed max
                    if new_val <= max_val:
                        val = new_val
                    else:
                        val = max_val
                    # Format with unit
                    value_label.setText(f"({val:.1f})")
                    # Force update
                    value_label.update()
            except Exception as e:
                print(f"Error in increase for {title}: {e}")
                import traceback
                traceback.print_exc()

        def decrease():
            try:
                # Get current text from the label
                current_text = value_label.text()
                # Remove parentheses and extract number - handle format like "(4.0 CmH2O)" or "(4.0)"
                text_clean = current_text.strip().lstrip("(").rstrip(")")
                # Extract the first number from the text (handles units after the number)
                num_match = re.search(r'[-+]?\d*\.?\d+', text_clean)
                if num_match:
                    val = float(num_match.group())
                    new_val = val - step
                    # Ensure value doesn't go below min
                    if new_val >= min_val:
                        val = new_val
                    else:
                        val = min_val
                    # Format with unit
                    value_label.setText(f"({val:.1f})")
                    # Force update
                    value_label.update()
            except Exception as e:
                print(f"Error in decrease for {title}: {e}")
                import traceback
                traceback.print_exc()
        
        # Connect buttons with explicit lambda to ensure proper closure
        btn_up.clicked.connect(lambda checked, lbl=value_label: increase())
        btn_down.clicked.connect(lambda checked, lbl=value_label: decrease())

        btn_layout.addWidget(btn_up)
        btn_layout.addWidget(btn_down)

        main_layout.addLayout(text_layout, 2)
        main_layout.addLayout(btn_layout, 1)
        main_layout.addStretch()
        return card

    def create_option_card(self, title, initial, options):
        card = QFrame()
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setObjectName("ParamCard") # Set object name for QSS targeting
        card.setStyleSheet(f"""
            QFrame#ParamCard {{
                border: 1px solid #06919B;
                border-radius: 10px;
            }}
            QFrame#ParamCard:hover {{
            }}
        """)
        main_layout = QHBoxLayout(card)
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(8, 8, 8, 8)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)

        label_title = QLabel(title)
        label_title.setObjectName("ParamTitle") # Set object name for QSS targeting
        label_title.setAlignment(Qt.AlignCenter)
        label_title.setStyleSheet("color: #6B7280; font-size: 15px; font-weight: 500;")

        try:
            f_init = float(initial)
            value_label = QLabel(f"({f_init:.1f})")
        except:
            value_label = QLabel(f"({initial})")
        value_label.setObjectName("ParamValue") # Set object name for QSS targeting
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet("color: #06919B; font-size: 32px; font-weight: 700;")

        text_layout.addWidget(label_title)
        text_layout.addWidget(value_label)


        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(5)
        btn_layout.setAlignment(Qt.AlignVCenter)

        btn_up = QPushButton("▲")
        btn_up.setFixedSize(40, 32)
        btn_up.setStyleSheet("""
            QPushButton {
                background-color: #E0F7FA; /* Light Cyan */
                color: #00796B; /* Dark Cyan */
                border-radius: 10px;
                width: 40px;
                height: 32px;
                font-size: 20px; /* Slightly larger font for the arrows */
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #B2EBF2; /* Slightly darker cyan on hover */
            }
            QPushButton:pressed {
                background-color: #80DEEA; /* Even darker cyan when pressed */
            }
        """)

        btn_down = QPushButton("▼")
        btn_down.setFixedSize(40, 32)
        btn_down.setStyleSheet("""
            QPushButton {
                background-color: #E0F7FA; /* Light Cyan */
                color: #00796B; /* Dark Cyan */
                border-radius: 10px;
                width: 40px;
                height: 32px;
                font-size: 20px; /* Slightly larger font for the arrows */
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #B2EBF2; /* Slightly darker cyan on hover */
            }
            QPushButton:pressed {
                background-color: #80DEEA; /* Even darker cyan when pressed */
            }
        """)

        def increase():
            try:
                current_val = value_label.text().strip("()").strip()
                if current_val in options:
                    idx = options.index(current_val)
                    idx = (idx + 1) % len(options)
                    value_label.setText(f"({options[idx]})")
            except Exception as e:
                print(f"Error in option increase: {e}")

        def decrease():
            try:
                current_val = value_label.text().strip("()").strip()
                if current_val in options:
                    idx = options.index(current_val)
                    idx = (idx - 1) % len(options)
                    value_label.setText(f"({options[idx]})")
            except Exception as e:
                print(f"Error in option decrease: {e}")
        btn_up.clicked.connect(increase)
        btn_down.clicked.connect(decrease)
        
        btn_layout.addWidget(btn_up)
        btn_layout.addWidget(btn_down)

        main_layout.addLayout(text_layout, 2)
        main_layout.addLayout(btn_layout, 1)
        main_layout.addStretch()

        return card
    
    def save_mode(self, mode_name, send_to_cloud=False):
        print("save_mode called") 
        now_time = time.time()
        payload_placeholder = json.dumps({
            "device_status": 1,
            "device_data": f"{mode_name}_{now_time}"
        })
        payload_hash = hash(payload_placeholder)
        last_sent = self.recent_sends.get(payload_hash)
        if last_sent and now_time - last_sent < 30:
            print("Skipping duplicate send (recent)")
            return
      
        self.recent_sends[payload_hash] = now_time
       
        for h, ts in list(self.recent_sends.items()):
            if now_time - ts > 30:
                del self.recent_sends[h]

        mode_data = {}
        for title, label in self.value_labels[mode_name].items():
            raw = label.text().strip("()").split()[0]
            if title in ["Gender", "Sleep Mode", "Mask Type", "i mode", "Leak alert", "Tubetype"]:
                val = raw
            else:
                try:
                    val = float(raw)
                except ValueError:
                    num_match = re.search(r'[-+]?\d*\.?\d+', raw)
                    if num_match:
                        val = float(num_match.group())
                    else:
                        val = 0.0  # Fallback to default
            if title in self.int_fields:
                val = int(float(val))
            mode_data[title] = val 

        # 2. Save to settings.json (per serial number)
        # Check if machine_serial is empty, and if this is AdminDashboard, try to get from serial_input
        if not self.machine_serial or not self.machine_serial.strip():
            # If this is AdminDashboard, check the serial_input field
            if hasattr(self, 'serial_input') and self.serial_input:
                serial_from_input = self.serial_input.text().strip()
                if serial_from_input:
                    self.machine_serial = serial_from_input
                    # Update info label if it exists
                    if hasattr(self, 'info_label'):
                        self.info_label.setText(f"User: ({self.user_name})    |    Machine S/N: ({self.machine_serial})")
                else:
                    QMessageBox.warning(
                        self, 
                        "Error", 
                        "Machine serial number is required to save settings.\n\n"
                        "Please enter a serial number in the 'Serial No' field on the Dashboard page, "
                        "or use 'Fetch Settings' to load data for a serial number."
                    )
                    return
            else:
                QMessageBox.warning(
                    self, 
                    "Error", 
                    "Machine serial number is required to save settings.\n\n"
                    "Please ensure a serial number is set. You may need to fetch settings first "
                    "or enter a serial number."
                )
                return 
        
        # Use normalized/base serial (without protocol type suffix) as the key
        # so one physical machine always maps to a single entry in settings.
        serial_key = normalize_serial(self.machine_serial)
        self.add_active_serial_to_list(serial_key, self.machine_type)
        # Load all settings (all serials)
        try:
            with open(SETTINGS_FILE, "r") as f:
                all_serials_data = json.load(f)
        except Exception:
            all_serials_data = {}
        
        # Get or create settings for this serial number
        if serial_key not in all_serials_data:
            all_serials_data[serial_key] = {}
        
        all_serials_data[serial_key][mode_name] = mode_data
        
        # Save back to file
        with open(SETTINGS_FILE, "w") as f:
            json.dump(all_serials_data, f, indent=4)
        
        # Also keep a local copy for current operations
        all_settings = all_serials_data[serial_key]

        if mode_name == "Settings":
            self.settings = mode_data
            self.update_alerts()

        # 3. Build CSV line based on machine_type
        now = datetime.now()
        date = now.strftime("%d%m%y")
        time_ = now.strftime("%H%M")
        parts = ["*"]
        parts += ["S", date, time_]

        
        if mode_name in ["CPAP", "AutoCPAP", "S", "T", "ST", "VAPS"]:
            mode_str = self.get_mode_str(mode_name)
            parts.append(mode_str)

        mask_map = {"Nasal": "1", "Pillow": "2", "Full Face": "3"}
        gender_map = {"Male": "1", "Female": "2"}
        settings_vals = all_settings.get("Settings", self.default_values["Settings"])
        mask_num = self.format_for_csv(float(mask_map.get(settings_vals.get("Mask Type", "Nasal"), "1")))
        gender_num = self.format_for_csv(float(gender_map.get(settings_vals.get("Gender", "Male"), "1")))
        

        # Use machine_serial as unique identifier - ensure it's not empty
        # (Th
        serial = (self.machine_serial or "").strip()
        if not serial:
            # This should not happen if the check above worked, but handle it anyway
            if hasattr(self, 'serial_input') and self.serial_input:
                serial_from_input = self.serial_input.text().strip()
                if serial_from_input:
                    self.machine_serial = serial_from_input
                    serial = serial_from_input
                else:
                    QMessageBox.warning(self, "Error", "Machine serial number is required. Please ensure serial number is set.")
                    return
            else:
                QMessageBox.warning(self, "Error", "Machine serial number is required. Please ensure serial number is set.")
                return

        # Prepare serial as last CSV field in the wire format.
        # For BIPAP machines, append "B" (e.g. 12345678B),
        # for CPAP machines, append "C" (e.g. 12345678C).
        serial_for_csv = serial
        if self.machine_type == "BIPAP" and not serial_for_csv.endswith("B"):
            serial_for_csv = serial_for_csv + "B"
        elif self.machine_type == "CPAP" and not serial_for_csv.endswith("C"):
            serial_for_csv = serial_for_csv + "C"

        if self.machine_type == "CPAP":
            # G - CPAP
            cpap_vals = all_settings.get("CPAP", self.default_values.get("CPAP", {}))
            set_p = cpap_vals.get("Set Pressure", 4.0)
            parts += ["G", self.format_for_csv(set_p), mask_num]

            # H - AutoCPAP 
            autocpap_vals = all_settings.get("AutoCPAP", self.default_values.get("AutoCPAP", {}))
            min_p = autocpap_vals.get("Min Pressure", 4.0)
            max_p = autocpap_vals.get("Max Pressure", 20.0)
            parts += ["H", self.format_for_csv(min_p), self.format_for_csv(min_p), self.format_for_csv(max_p), mask_num]

            # I - Settings
            ramp = settings_vals.get("Ramp Time", 5.0)
            hum = settings_vals.get("Humidifier", 1.0)
            
            # Tubetype mapping
            tubetype_map = {"Standard": "1", "Slimline": "2", "Heated": "3"}
            tube_num = tubetype_map.get(settings_vals.get("Tubetype", "Standard"), "1")

            # Helper function to safely convert ON/OFF values
            def safe_on_off(val, default="OFF"):
                if isinstance(val, (int, float)):
                    return 1.0 if val != 0 else 0.0
                val_str = str(val).upper() if val else default.upper()
                return 1.0 if val_str == "ON" else 0.0
            imode_num = safe_on_off(settings_vals.get("I Mode", "OFF"))
            leak_num = safe_on_off(settings_vals.get("Leak alert", "OFF"))
            sleep_num = safe_on_off(settings_vals.get("Sleep Mode", "OFF"))
            parts += ["I", self.format_for_csv(ramp), self.format_for_csv(hum), tube_num, str(imode_num), str(leak_num), gender_num, str(sleep_num), serial_for_csv]

        else:  # BIPAP
            # A - CPAP
            cpap_vals = all_settings.get("CPAP", self.default_values.get("CPAP", {}))
            set_p = cpap_vals.get("Set Pressure", 4.0)
            parts += ["A", self.format_for_csv(set_p), mask_num]

            # Helper function for safe parsing (used in all loops below)
            def safe_parse_val(v):
                if isinstance(v, str):
                    # Regex to extract number (handles "0.3s", "0.3 s", etc.)
                    num_match = re.search(r'[-+]?\d*\.?\d+', v)
                    if num_match:
                        return float(num_match.group())
                    else:
                        return 0.0  # Fallback
                else:
                    return float(v)  # Ensure float

            # B - S Mode
            s_vals = all_settings.get("S", self.default_values.get("S", {}))
            parts.append("B")
            parts.append(self.format_for_csv(safe_parse_val(s_vals.get("IPAP", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(s_vals.get("EPAP", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(s_vals.get("Start EPAP", 0.0))))
            parts.append(self.format_for_csv(int(safe_parse_val(s_vals.get("Ti.Min", 0.0)) * 10)))
            parts.append(self.format_for_csv(int(safe_parse_val(s_vals.get("Ti.Max", 0.0)) * 10)))
            parts.append(self.format_for_csv(safe_parse_val(s_vals.get("Sensitivity", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(s_vals.get("Rise Time", 0.0))))
            parts.append(mask_num)

            # C - T Mode
            t_vals = all_settings.get("T", self.default_values.get("T", {}))
            parts.append("C")
            parts.append(self.format_for_csv(safe_parse_val(t_vals.get("IPAP", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(t_vals.get("EPAP", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(t_vals.get("Start EPAP", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(t_vals.get("Respiratory Rate", 0.0))))
            parts.append(self.format_for_csv(int(safe_parse_val(t_vals.get("Ti.Min", 0.0)) * 10)))
            parts.append(self.format_for_csv(int(safe_parse_val(t_vals.get("Ti.Max", 0.0)) * 10)))
            parts.append(self.format_for_csv(safe_parse_val(t_vals.get("Sensitivity", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(t_vals.get("Rise Time", 0.0))))
            parts.append(mask_num)

            # D - ST Mode
            st_vals = all_settings.get("ST", self.default_values.get("ST", {}))
            parts.append("D")
            parts.append(self.format_for_csv(safe_parse_val(st_vals.get("IPAP", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(st_vals.get("EPAP", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(st_vals.get("Start EPAP", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(st_vals.get("Backup Rate", 0.0))))
            parts.append(self.format_for_csv(int(safe_parse_val(st_vals.get("Ti.Min", 0.0)) * 10)))
            parts.append(self.format_for_csv(int(safe_parse_val(st_vals.get("Ti.Max", 0.0)) * 10)))
            parts.append(self.format_for_csv(safe_parse_val(st_vals.get("Sensitivity", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(st_vals.get("Rise Time", 0.0))))
            parts.append(mask_num)

            # E - VAPS Mode (Assuming VAPS is the equivalent of AUTOCPAP/CPAP for BIPAP in your context)
            # Based on your provided format, this looks like a combination of VAPS and some other mode.
            # I'll map the fields as best as possible to your provided format.
            vaps_vals = all_settings.get("VAPS", self.default_values.get("VAPS", {}))
            parts.append("E")
            parts.append(self.format_for_csv(safe_parse_val(vaps_vals.get("Max IPAP", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(vaps_vals.get("Min IPAP", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(vaps_vals.get("EPAP", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(vaps_vals.get("Respiratory Rate", 0.0))))
            parts.append(self.format_for_csv(int(safe_parse_val(vaps_vals.get("Ti.Min", 0.0)) * 10)))
            parts.append(self.format_for_csv(int(safe_parse_val(vaps_vals.get("Ti.Max", 0.0)) * 10)))
            parts.append(self.format_for_csv(safe_parse_val(vaps_vals.get("Sensitivity", 0.0))))
            parts.append(self.format_for_csv(safe_parse_val(vaps_vals.get("Rise Time", 0.0))))
            parts.append(mask_num)
            parts.append(self.format_for_csv(safe_parse_val(vaps_vals.get("Height", 170.0))))
            parts.append(self.format_for_csv(safe_parse_val(vaps_vals.get("Tidal Volume", 500.0))))

            # F - Settings
            ramp = safe_parse_val(settings_vals.get("Ramp Time", 5.0))
            hum = safe_parse_val(settings_vals.get("Humidifier", 1.0))
            
            # Tubetype mapping
            tubetype_map = {"Standard": "1", "Slimline": "2", "Heated": "3"}
            tube_num = tubetype_map.get(settings_vals.get("Tubetype", "Standard"), "1")

            # Helper function to safely convert ON/OFF values
            def safe_on_off(val, default="OFF"):
                if isinstance(val, (int, float)):
                    return 1.0 if val != 0 else 0.0
                val_str = str(val).upper() if val else default.upper()
                return 1.0 if val_str == "ON" else 0.0
            
            imode_num = safe_on_off(settings_vals.get(" I Mode", "OFF"))
            leak_num = safe_on_off(settings_vals.get("Leak alert", "OFF"))
            sleep_num = safe_on_off(settings_vals.get("Sleep Mode", "OFF"))

            parts += ["F", self.format_for_csv(ramp), self.format_for_csv(hum), tube_num, str(imode_num), str(leak_num), gender_num, str(sleep_num), serial_for_csv]

        # Filter out any empty strings from parts before joining
        filtered_parts = [p for p in parts if p is not None and p != ""]
        csv_line = ",".join(filtered_parts) + "#"

        if send_to_cloud:
            # 4. Send to AWS with serial number as unique identifier in the payload.
            # For the protocol we still append the machine type suffix, but logs and
            # settings use the normalized (base) serial.
            serial_for_payload = (self.machine_serial or "").strip()
            if self.machine_type == "BIPAP" and not serial_for_payload.endswith("B"):
                serial_for_payload = serial_for_payload + "B"
            elif self.machine_type == "CPAP" and not serial_for_payload.endswith("C"):
                serial_for_payload = serial_for_payload + "C"
            payload = {
                "device_status": 1,
                "device_data": csv_line
            }
            self.aws_send_queue.put(json.dumps(payload))
            # 5. Log the sent string against the base serial, so all history for a
            # device is grouped together regardless of type suffix.
            base_serial_for_log = normalize_serial(self.machine_serial)
            if base_serial_for_log:
                save_log(base_serial_for_log, "sent", csv_line)

        # 7. UI feedback
        changed = {k: mode_data[k] for k in mode_data
                   if all_settings.get(mode_name, {}).get(k) != mode_data[k]}
        changed_list = ", ".join(changed.keys()) if changed else "None"

        preview = csv_line[:200] + "..." if len(csv_line) > 200 else csv_line

        if not getattr(self, "_suppress_save_mode_message", False):
            QMessageBox.information(
                self,
                "Settings Saved",
                f"Mode: {mode_name}\n"
                f"Changed fields: {changed_list}\n\n"
                f"Sent CSV line ({self.machine_type} format) to the cloud:\n{preview}"
            )
    
    def load_settings(self):
        try:
            # Load settings for the current machine serial number
            serial_key = (self.machine_serial or "").strip()
            if not serial_key:
                # If no serial, try to load from file (might be old format)
                with open(SETTINGS_FILE, "r") as f:
                    all_data = json.load(f)
                # Check if it's old format (flat) or new format (per serial)
                if any(key in all_data for key in ["CPAP", "Settings", "S", "T", "ST", "VAPS", "AutoCPAP"]):
                    # Old format - use as is
                    all_data_to_use = all_data
                else:
                    # New format but no serial - use empty
                    all_data_to_use = {}
            else:
                # Load settings for this specific serial number
                all_data_to_use = load_all_settings(serial_key)
              
            
            self.settings = all_data_to_use.get("Settings", self.default_values["Settings"])
            for mode, values in all_data_to_use.items():
                if mode in self.value_labels:
                    for title, val in values.items():
                        if title in self.value_labels[mode]:
                            # Only show the raw value in the blue label; units
                            # are already rendered separately in grey below.
                            if isinstance(val, (int, float)):
                                display_val = f"{float(val):.1f}"
                            else:
                                display_val = str(val)
                            self.value_labels[mode][title].setText(display_val)
        except FileNotFoundError:
            self.settings = self.default_values["Settings"]
    
    def aws_iot_loop(self):
        ENDPOINT = "a2jqpfwttlq1yk-ats.iot.us-east-1.amazonaws.com"
        CLIENT_ID = "iotconsole-560333af-04b9-45fb-8cd0-4ef4cd819d92"
        BASE_PATH = os.getcwd()
        PATH_TO_CERTIFICATE = os.path.join(BASE_PATH, "Aws", "6e5d12437ffc7b19a750505da172d382b6e81026243aa254bce059b8bc45796f-certificate.pem.crt")
        PATH_TO_PRIVATE_KEY = os.path.join(BASE_PATH, "Aws", "6e5d12437ffc7b19a750505da172d382b6e81026243aa254bce059b8bc45796f-private.pem.key")
        PATH_TO_AMAZON_ROOT_CA = os.path.join(BASE_PATH, "Aws", "AmazonRootCA1.pem")
        TOPIC = "esp32/data24"
        ACK_TOPIC = "esp32/data24" 
        
        QUEUE_FILE = os.path.join(BASE_PATH, "pendingfiles.json")
        pending_messages = []
        is_connected = False
        self.ack_received = True
        pending_send_hold = 5  
        connection_time = None
        mqtt_connection = None
        
        def load_pending():
            nonlocal pending_messages
            try:
                
                if not os.path.exists(QUEUE_FILE):
                    pending_messages = []
                    save_pending()
                    print(f"No pending data file found; initialized empty at {QUEUE_FILE}")
                    return 
                
                if os.path.getsize(QUEUE_FILE) == 0:
                    pending_messages = []
                    save_pending()
                    print("Pending file was empty; initialized to empty list.")
                    return 
                with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
                    data = f.read().strip()
                    if not data:
                        pending_messages = []
                        save_pending()
                        print("Pending file contained only whitespace; initialized to empty list.")
                        return
                    pending_messages = json.loads(data)
                    if not isinstance(pending_messages,list):
                        pending_messages = [pending_messages]
                        save_pending()
                print(f"Loaded {len(pending_messages)} pending messages from file.")
            except json.JSONDecodeError:
                try:
                    corrupt_path = QUEUE_FILE + ".corrupt"
                    os.replace(QUEUE_FILE, corrupt_path)
                    print(f"Corrupt pending file moved to {corrupt_path}; reinitialized.")
                except Exception:
                    print("Failed to backup corrupt pending file; reinitializing in place.")
                pending_messages = []
                save_pending()
            except Exception as e:
                print(f"Error loading pending messages: {e}")
                pending_messages = []
                
        def save_pending():
            nonlocal pending_messages
            try:
                os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)
                with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(pending_messages, f, indent=3)
                print("Pending messages saved to file.")
            except Exception as e:
                print(f"Error saving pending messages: {e}")

        def is_duplicate_sample(data):
            nonlocal pending_messages
            for msg in pending_messages:
                if data == msg:
                    return True
            return False

        def on_message_received(topic, payload, dup, qos, retain, **kwargs):
            try:
                print(f"\nReceived message from topic '{topic}':")
                text = payload.decode('utf-8', errors='replace')
           
                try:
                    message = json.loads(text)
                except json.JSONDecodeError:
                    
                    stripped = text.strip()
                    if stripped.startswith("*") and stripped.endswith("#"):
                        message = {"device_status": None, "device_data": stripped}
                    else:
                        
                        message = {"raw_payload": stripped}

                print(f"Message content: {json.dumps(message, indent=2)}")
                if topic == ACK_TOPIC and message.get("acknowledgment") == 1:
                    print("Acknowledgment received")
                    self.ack_received = True
                elif "device_data" in message:
                  
                    if isinstance(message.get("device_data"), str):
                        device_data = message["device_data"]
                        
                        # Extract date and update user count for pie chart
                        # self.extract_date_and_update_user_count(device_data)
                        
                        # Also check if this is a serial number search and update recent serial
                        if "S," in device_data:
                            # Try to extract serial number from the data
                            parts = device_data.strip("*#").split(",")
                            if len(parts) > 1:
                                # The first part after "S" might be the date, but we can check for serial
                                # Look for an 8-digit number (typical serial format)
                                for part in parts:
                                    if part.isdigit() and len(part) >= 6:
                                        serial_num = part
                                        self.update_recent_serial(serial_num)
                                        break
                        
                        self.aws_receive_queue.put(message)
                    else: 
                               print("Ignored device_data: not a string")
                else:
                
                    print("Received non-device payload; stored for inspection.")
                print("Message received successfully!")
            except Exception as e:
                print(f"Error processing received message: {e}")

        def on_connection_interrupted(connection, error, **kwargs):
            nonlocal is_connected
            is_connected = False
            self.is_connected = False
            device_status_signal.status_changed.emit(False)  # Emit RED status
            print(f"Connection interrupted. Error: {error}. Device is now DISCONNECTED.")

        def on_connection_resumed(connection, return_code, session_present, **kwargs):
            nonlocal is_connected
            nonlocal connection_time
            is_connected = True
            self.is_connected = True
            device_status_signal.status_changed.emit(True)  # Emit GREEN status
            self.ack_received = True  
            print(f"Connection resumed. Return code: {return_code}, Session present: {session_present}. Device is now CONNECTED.")
            load_pending()
            if not session_present:
                subscribe_to_topics(connection)
            connection_time = time.time()
                
        def send_data(data, connection):
            print(f"Publishing message to topic '{TOPIC}':\n{data}")
            try:
                publish_future, packet_id = connection.publish(
                    topic=TOPIC,
                    payload=data.encode('utf-8'),
                    qos=mqtt.QoS.AT_LEAST_ONCE
                )
                publish_future.result(timeout=10)
                print("Data sent to AWS IoT Core! Waiting for acknowledgment...")
                print(f"Packet ID: {packet_id}")
                self.ack_received = False
                return True
                
            except Exception as e:
                print(f"Publish failed: {e}")
                return False

        def send_pending(connection):
            nonlocal pending_messages
            nonlocal connection_time
            print(f"send_pending: ack_received={self.ack_received}, pending_messages_count={len(pending_messages)}")
            if not is_connected:
                print("Cannot send pending messages: Device is DISCONNECTED.")
                return
       
            if connection_time is None or time.time() - connection_time < pending_send_hold:
                print(f"Deferring pending sends for {pending_send_hold} seconds after connect...")
                return
            if pending_messages and self.ack_received:
                data = pending_messages[0]
                print(f"Attempting to send pending message: {data}")
                if send_data(data, connection):
                    start_time = time.time()
                    while not self.ack_received and time.time() - start_time < 10:
                        time.sleep(0.1)
                    if self.ack_received:
                        print("Message acknowledged, removing from queue")
                        pending_messages.pop(0)
                        
                        save_pending()
                    else:
                        print("No acknowledgment received within timeout. Proceeding to next message (fallback).")
                        pending_messages.pop(0)
                else:
                    print("Failed to send pending message.")

        def subscribe_to_topics(connection):
            nonlocal is_connected
            if not is_connected:
                print("Cannot subscribe: Device is DISCONNECTED.")
                return False
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    print(f"Subscribing to topic '{TOPIC}' (attempt {attempt + 1})...")
                    subscribe_future, packet_id = connection.subscribe(
                        topic=TOPIC,
                        qos=mqtt.QoS.AT_LEAST_ONCE,
                        callback=on_message_received
                    )
                    subscribe_result = subscribe_future.result(timeout=10)
                    print(f"Subscribed to topic '{TOPIC}' with QoS: {subscribe_result['qos']}")
                    print(f"Subscription packet ID: {packet_id}")

                    print(f"Subscribing to acknowledgment topic '{ACK_TOPIC}' (attempt {attempt + 1})...")
                    subscribe_future, packet_id = connection.subscribe(
                        topic=ACK_TOPIC,
                        qos=mqtt.QoS.AT_LEAST_ONCE,
                        callback=on_message_received
                    
                    )
                    subscribe_result = subscribe_future.result(timeout=10)
                    print(f"Subscribed to topic '{ACK_TOPIC}' with QoS: {subscribe_result['qos']}")
                    print(f"Subscription packet ID: {packet_id}")
                    return True
                except Exception as e:
                    print(f"Subscription failed: {e}. Retrying..." if attempt < max_retries - 1 else f"Subscription failed after {max_retries} attempts: {e}")
                    time.sleep(1)
            return False

        io.init_logging(io.LogLevel.Error, 'stderr')
        event_loop_group = io.EventLoopGroup(1)
        host_resolver = io.DefaultHostResolver(event_loop_group)
        client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)
        
        
        missing_files = [p for p in (PATH_TO_CERTIFICATE, PATH_TO_PRIVATE_KEY, PATH_TO_AMAZON_ROOT_CA) if not os.path.isfile(p)]
        if missing_files:
            
            alt_base = os.path.join(os.getcwd(), 'Aws')
            alt_paths = [os.path.join(alt_base, os.path.basename(p)) for p in (PATH_TO_CERTIFICATE, PATH_TO_PRIVATE_KEY, PATH_TO_AMAZON_ROOT_CA)]
            if all(os.path.isfile(p) for p in alt_paths):
                PATH_TO_CERTIFICATE, PATH_TO_PRIVATE_KEY, PATH_TO_AMAZON_ROOT_CA = alt_paths
                print("Found TLS files in local 'Aws' folder; updated paths.")
            else:
                print(f"MQTT TLS files missing: {missing_files}. Aborting AWS IoT connection loop.")
                return
            
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
            keep_alive_secs=1200
        )
        load_pending()
        while not is_connected:
            print(f"Connecting to {ENDPOINT} with client ID '{CLIENT_ID}'...")
            try:
                connect_future: Future = mqtt_connection.connect()
                connect_future.result(timeout=10)
                is_connected = True
                self.is_connected = True
                connection_time = time.time()
                device_status_signal.status_changed.emit(True)  # Emit GREEN status on first connect
                print("Connected successfully to AWS IoT Core! Device is now CONNECTED.")
                subscribe_to_topics(mqtt_connection)
                
            except Exception as e:
                print(f"Connection failed: {e}. Device is DISCONNECTED. Retrying in 1 second...")
                time.sleep(1)

        try:
            print("\nKeeping connection alive to receive messages and check for pending data...")
            while True:
                print(f"Device connection status: {'CONNECTED' if is_connected else 'DISCONNECTED'}")
                if is_connected:
                    if pending_messages and self.ack_received:
                        send_pending(mqtt_connection)
                    try:
                        new_data = self.aws_send_queue.get_nowait()
                        if not is_duplicate_sample(new_data):
                            if not send_data(new_data, mqtt_connection):
                                pending_messages.append(new_data)
                                save_pending()
                    except queue.Empty:
                        pass
                else:
                    print("Connection lost! Attempting immediate reconnection...")
                    try:
                        connect_future: Future = mqtt_connection.connect()
                        connect_future.result(timeout=10)
                        is_connected = True 
                        self.is_connected = True
                        connection_time = time.time()
                        device_status_signal.status_changed.emit(True)  # Emit GREEN status
                        print("Reconnected successfully to AWS IoT Core! Device is now CONNECTED.")
                        subscribe_to_topics(mqtt_connection)
                        send_pending(mqtt_connection)
                    except Exception as e:
                        print(f"Reconnection failed: {e}. Retrying immediately...")
                    try:
                        new_data = self.aws_send_queue.get_nowait()
                        if not is_duplicate_sample(new_data):
                            pending_messages.append(new_data)
                            save_pending()
                        print("New data queued to pending_data.json since device is DISCONNECTED.")
                    except queue.Empty: 
                        pass
                # Minimal sleep to keep connection alive and responsive
                time.sleep(0.5 if is_connected else 1)
        except KeyboardInterrupt:
            print("\nDisconnecting from AWS IoT Core...")
        
class AdminDashboard(Dashboard):
    active_users_data_changed = pyqtSignal()
    def __init__(self, user_name="Admin", machine_serial="", login_window=None, user_data={}):
        self.recently_active_serials = [] # Initialize list for recently active serials
        super().__init__(user_name, machine_serial, login_window, user_data)
        if hasattr(self, 'machine_type_combo') and self.machine_type_combo:
            self.machine_type_combo.currentTextChanged.connect(self.on_type_change)
        self.machine_serial = machine_serial
        self.recently_active_serials = [] # Initialize list for recently active serials
        self.add_active_serial_to_list(self.machine_serial, self.machine_type)
        try: 
            self.update_recent_serial(self.machine_serial)
        except Exception:
            pass
        
        # Connect the signal to the slot for KPI updates
        self.active_users_data_changed.connect(self.update_total_active_devices_kpi)

    def create_dashboard_page(self):
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setSpacing(18)  
        
        main_layout.setContentsMargins(20, 16, 20, 16)
        topbar = QHBoxLayout()
        topbar.setSpacing(10)
        title = QLabel("Admin Dashboard")
        title.setStyleSheet("font-size:18px;font-weight:700;color:#111827;")
        toggle = QPushButton("Toggle Sidebar")
        toggle.setFixedHeight(32)
        toggle.setStyleSheet(f"""
            QPushButton {{
                background: {THEME_PRIMARY};
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 5px 10px;
                font-weight: 600;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {THEME_PRIMARY_2};
            }}
        """)
        toggle.clicked.connect(lambda: self.sidebar_frame.setVisible(not self.sidebar_frame.isVisible()))
        topbar.addWidget(title)
        topbar.addStretch()
        topbar.addWidget(toggle)
        main_layout.addLayout(topbar)
        controls = QFrame()
        controls.setStyleSheet("QFrame { background:#FFFFFF; border:1px solid #E5E7EB; border-radius:12px; }")
        c = QHBoxLayout(controls)
        c.setContentsMargins(12, 10, 12, 10)
        c.setSpacing(10)
        lbl_s = QLabel("Serial No")
        self.serial_input = QLineEdit(self.machine_serial)
        self.serial_input.setPlaceholderText("Enter Serial Number")
        self.serial_input.setFixedHeight(36)
        lbl_t = QLabel("Machine Type")
        self.machine_type_combo = QComboBox()
        self.machine_type_combo.addItems(["CPAP","BIPAP"])
        self.machine_type_combo.setCurrentText("BIPAP")
        self.machine_type_combo.currentTextChanged.connect(self.on_type_change)
        self.machine_type_combo.setStyleSheet(f"""
            QComboBox {{
                border: 2px solid #E5E7EB;
                border-radius: 10px;
                padding: 6px 12px;
                background: #FFFFFF;
                color: #111827;
                font-weight: 600;
            }}
            QComboBox:focus {{
                border: 2px solid {THEME_PRIMARY};
            }}
            QComboBox::drop-down {{
                width: 0px;
                border: none;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0px;
                height: 0px;
            }}
        """)
        arrow_btn = QPushButton("▾")
        arrow_btn.setFixedSize(36, 36)
        arrow_btn.clicked.connect(self.machine_type_combo.showPopup)
        arrow_btn.setStyleSheet(f"""
            QPushButton {{
                background: {THEME_PRIMARY};
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: {THEME_PRIMARY_2};
            }}
            QPushButton:pressed {{
                background: #e55f00;
            }}
        """)
        combo_container = QWidget()
        combo_layout = QHBoxLayout(combo_container)
        combo_layout.setContentsMargins(0, 0, 0, 0)
        combo_layout.setSpacing(6)
        combo_layout.addWidget(self.machine_type_combo, 1)
        combo_layout.addWidget(arrow_btn)
        combo_container.setMinimumHeight(36)
        btn_fetch = QPushButton("Fetch Settings")
        btn_fetch.setFixedHeight(36)
        btn_fetch.clicked.connect(self.fetch_settings)
        btn_fetch.setStyleSheet(f"""
            QPushButton {{
                background: {THEME_PRIMARY};
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {THEME_PRIMARY_2};
            }}
            QPushButton:pressed {{
                background: #e55f00;
            }}
        """)
      
        btn_update_serial = QPushButton("Update Serial No")
        btn_update_serial.setFixedHeight(36)
        btn_update_serial.clicked.connect(self.update_serial_from_input)
        btn_update_serial.setStyleSheet(f"""
        QPushButton {{
            background: #10B981;
            color: #FFFFFF;
            border: none;
            border-radius: 10px;
            padding: 8px 14px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background: #059669;
        }}
        QPushButton:pressed {{
            background: #047857;
        }}
        """)
        c.addWidget(lbl_s)
        c.addWidget(self.serial_input, 1)
        c.addWidget(lbl_t)
        c.addWidget(combo_container)
        c.addStretch()
        c.addWidget(btn_update_serial)
        c.addWidget(btn_fetch)
        main_layout.addWidget(controls)
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(16)
        self.total_active_devices_kpi = HoverKPICard("Total Active Devices", str(get_total_active_devices()), "#2563EB", "#2196F3")
        kpi_row.addWidget(self.total_active_devices_kpi)
        kpi_row.addWidget(HoverKPICard("Device Usage (Recent Device) (hrs/day)","---","#16A34A", "#4CAF50"))
        kpi_row.addWidget(HoverKPICard("Recently Active Devices","3","#2563EB", "#FF9800"))
        kpi_row.addWidget(HoverKPICard("Device Alerts","0","#DC2626", "#F44336"))
        main_layout.addLayout(kpi_row)
        charts = QHBoxLayout()
        charts.setSpacing(16)
        charts.setContentsMargins(0, 8, 0, 0)

        # Monthly Active Bar Chart with Heading
        monthly_chart_container = QVBoxLayout()
        monthly_chart_title = QLabel("Total Modified Devices Per Month 2026")
        monthly_chart_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #FF6A00; margin-bottom: 12px; padding: 4px; font-family: 'Segoe UI', sans-serif;")
        monthly_chart_container.addWidget(monthly_chart_title)
        usage = MonthlyActiveBar()
        monthly_chart_container.addWidget(usage)
        charts.addLayout(monthly_chart_container, 1)

        # Realtime Serial Numbers Box
        serial_numbers_frame = QFrame()
        serial_numbers_frame.setStyleSheet(card_style) 
        serial_numbers_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        active_serials_list = QVBoxLayout(serial_numbers_frame)
        active_serials_list.setContentsMargins(15, 15, 15, 15)
        
        serial_numbers_title = QLabel("Recently Active Devices")
        serial_numbers_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #FF6A00; margin-bottom: 12px; padding: 4px; font-family: 'Segoe UI', sans-serif;")
        active_serials_list.addWidget(serial_numbers_title)
        active_serials_list.addStretch()
        
        charts.addWidget(serial_numbers_frame, 1)
        self.active_serials_list = active_serials_list 
        self.update_active_serial_numbers_display() 
        
        main_layout.addLayout(charts, 2)
        alerts = QTableWidget(0,1)
        alerts.setMaximumHeight(100)
        alerts.setHorizontalHeaderLabels(["Alerts","Status","Time"])
        alerts.horizontalHeader().setStretchLastSection(True)
        alerts.setAlternatingRowColors(True)
        alerts.setStyleSheet(
            "QTableWidget{background:#FFFFFF;border:1px solid #E5E7EB;border-radius:18px;}"
            " QHeaderView::section{background:#F9FAFB;border:1px solid #E5E7EB;font-weight:700;color:#111827;border-radius:18px;}"
        )
        def add_row(n,s,c):
            r = alerts.rowCount()
            alerts.insertRow(r)
            alerts.setItem(r,0,QTableWidgetItem(n))
            w = QWidget()
            b = QLabel(s,w)
            b.setAlignment(Qt.AlignCenter)
            b.setStyleSheet(f"background:{c};color:#FFFFFF;padding:4px 12px;border-radius:14px;font-weight:600;")
            l = QHBoxLayout(w)
            l.setContentsMargins(0,0,0,0)
            l.addWidget(b)
            alerts.setCellWidget(r,1,w)
            alerts.setItem(r,2,QTableWidgetItem(datetime.now().strftime('%H:%M')))
        
        main_layout.addWidget(alerts)
        main_layout.addStretch()
        page.setStyleSheet("QWidget{background-color:#FFFFFF;font-family:'Segoe UI';} QLabel#KPIValue{font-size:20px;font-weight:bold;color:#111827;}")
        s = QScrollArea()
        s.setWidget(page)
        s.setWidgetResizable(True)
        s.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #FFFFFF;
            }
            QScrollBar:vertical {
                border: none;
                background: #FFFFFF;
                width: 10px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #cccccc;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        return s

    def apply_current_mode_to_multiple_devices(self):
        """
        Admin helper: apply the currently selected mode's settings to multiple devices
        by serial number in one action.
        """
        # Ensure a mode is selected
        if not hasattr(self, "current_mode") or not self.current_mode:
            QMessageBox.warning(self, "Error", "Please select a mode before applying settings.")
            return

        # Ensure the multi-serial input exists
        if not hasattr(self, "multi_serials_input") or self.multi_serials_input is None:
            QMessageBox.warning(self, "Error", "Multi-serial input field is not available.")
            return

        raw = self.multi_serials_input.text().strip()
        if not raw:
            QMessageBox.warning(self, "Error", "Please enter at least one serial number (comma-separated).")
            return

        # Allow comma, space or newline separated serials
        serial_candidates = re.split(r"[,\s]+", raw)
        serials = [s.strip() for s in serial_candidates if s.strip()]

        if not serials:
            QMessageBox.warning(self, "Error", "No valid serial numbers were found.")
            return

        # De-duplicate while preserving order
        unique_serials = []
        seen = set()
        for s in serials:
            if s not in seen:
                seen.add(s)
                unique_serials.append(s)

        # Confirm with admin
        listed = ", ".join(unique_serials)
        reply = QMessageBox.question(
            self,
            "Confirm Apply",
            f"Apply current '{self.current_mode}' settings to {len(unique_serials)} device(s):\n{listed}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        original_serial = getattr(self, "machine_serial", "")
        success = 0
        failed = []

        # Suppress the per-device 'Settings Saved' popup inside save_mode
        self._suppress_save_mode_message = True
        try:
            for s in unique_serials:
                try:
                    self.machine_serial = s
                    self.save_mode(self.current_mode)
                    success += 1
                except Exception as e:
                    failed.append((s, str(e)))
        finally:
            # Restore original serial and flag
            self.machine_serial = original_serial
            self._suppress_save_mode_message = False

        # High-level summary for admin
        if success and not failed:
            QMessageBox.information(self, "Success", f"Settings applied to {success} device(s).")
        elif success and failed:
            failed_list = ", ".join(f"{s}" for s, _ in failed)
            QMessageBox.warning(
                self,
                "Partial Success",
                f"Settings applied to {success} device(s).\nFailed for: {failed_list}",
            )
        elif not success and failed:
            failed_list = ", ".join(f"{s}" for s, _ in failed)
            QMessageBox.critical(
                self,
                "Failure",
                f"Failed to apply settings to any device.\nFailed serials: {failed_list}",
            )

        # Admin Controls
        patient_frame = QFrame()
        patient_frame.setStyleSheet(card_style)
        patient_frame.setMinimumSize(150, 100)
        patient_layout = QFormLayout(patient_frame)
        patient_layout.setLabelAlignment(Qt.AlignRight)
        patient_layout.setFormAlignment(Qt.AlignHCenter)
        patient_layout.setSpacing(12)
        patient_layout.setContentsMargins(15, 15, 15, 15)
        
        # === Serial No ==
        serial_label = QLabel("Serial No:")
        serial_label.setStyleSheet("font-size: 17px; font-weight: bold; color: #111827; font-family: 'Segoe UI', sans-serif;")
        
        self.serial_input = QLineEdit(self.machine_serial)
        self.serial_input.setPlaceholderText("Enter Machine Serial Number")
        self.serial_input.setFixedHeight(50)
        self.serial_input.setMinimumWidth(150)
        self.serial_input.setMaxLength(20)
        self.serial_input.setStyleSheet("""
            QLineEdit {
                border: 2px solid rgba(229, 231, 235, 1);
                border-radius: 14px;
                padding: 12px 16px;
                background: #FFFFFF;
                font-size: 15px;
                font-weight: 500;
                font-family: 'Segoe UI', sans-serif;
                color: #111827;
            }
            QLineEdit:focus {
                border: 2px solid #FF6A00;
                background: white;
            }
            QLineEdit:hover {
                border: 2px solid rgba(255, 106, 0, 0.4);
            }
            QLineEdit::placeholder {
                color: #9CA3AF;
            }
        """)
        
        patient_layout.addRow(serial_label, self.serial_input)
        
        # === Multi-serial apply ===
        multi_label = QLabel("Apply To Serials:")
        multi_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #111827; font-family: 'Segoe UI', sans-serif;")

        self.multi_serials_input = QLineEdit()
        self.multi_serials_input.setPlaceholderText("Enter multiple serial numbers (comma, space or newline separated)")
        self.multi_serials_input.setFixedHeight(40)
        self.multi_serials_input.setMinimumWidth(150)
        self.multi_serials_input.setMaxLength(300)
        self.multi_serials_input.setStyleSheet("""
            QLineEdit {
                border: 2px solid rgba(229, 231, 235, 1);
                border-radius: 12px;
                padding: 10px 14px;
                background: #FFFFFF;
                font-size: 14px;
                font-weight: 500;
                font-family: 'Segoe UI', sans-serif;
                color: #111827;
            }
            QLineEdit:focus {
                border: 2px solid #FF6A00;
                background: white;
            }
            QLineEdit:hover {
                border: 2px solid rgba(255, 106, 0, 0.4);
            }
            QLineEdit::placeholder {
                color: #9CA3AF;
            }
        """)

        patient_layout.addRow(multi_label, self.multi_serials_input)

        # === Spacer ===
        spacer = QFrame()
        spacer.setFixedHeight(2)
        patient_layout.addRow("", spacer)
        
        # === Machine Type ===
        type_label = QLabel("Machine Type:")
        type_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #111827; font-family: 'Segoe UI', sans-serif;")
        
        self.machine_type_combo = QComboBox()
        self.machine_type_combo.addItems(["CPAP", "BIPAP"])
        self.machine_type_combo.setCurrentText("BIPAP")
        self.machine_type_combo.setFixedHeight(50)
        self.machine_type_combo.setStyleSheet("""
            QComboBox {
                border: 2px solid rgba(229, 231, 235, 1);
                border-radius: 14px;
                padding: 12px 16px;
                background: white;
                font-size: 15px;
                font-weight: 500;
                font-family: 'Segoe UI', sans-serif;
                color: #111827;
            }   
            QComboBox:focus {
                border: 2px solid #FF6A00;
            }
            QComboBox:hover {
                border: 2px solid rgba(255, 106, 0, 0.4);
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {me
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 8px solid #FF6A00;
                margin-right: 10px;
            }
        """)
        
        patient_layout.addRow(type_label, self.machine_type_combo)
        
        # === Spacer before button ===
        spacer2 = QFrame()
        spacer2.setFixedHeight(2)  
        patient_layout.addRow("", spacer2)
        
        # === Fetch Settings Button ===
        fetch_btn = QPushButton("Fetch Settings")
        fetch_btn.clicked.connect(self.fetch_settings)
        fetch_btn.setFixedHeight(50)
        fetch_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #9b59b6, stop:1 #8e44ad);
                color: white;
                border-radius: 16px;
                padding: 14px 28px;
                font-weight: 600;
                font-size: 15px;
                font- mily: 'Segoe UI', sans-serif;
                border: none;
                min-width: 120px;
                margin-top: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8e44ad, stop:1 #9b59b6);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7d3c98, stop:1 #6c3483);
            }
        """)

        # === Apply To Multiple Devices Button ===
        apply_multi_btn = QPushButton("Apply To Multiple Devices")
        apply_multi_btn.clicked.connect(self.apply_current_mode_to_multiple_devices)
        apply_multi_btn.setFixedHeight(50)
        apply_multi_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1D4ED8);
                color: white;
                border-radius: 16px;
                padding: 14px 28px;
                font-weight: 600;
                font-size: 15px;
                font-family: 'Segoe UI', sans-serif;
                border: none;
                min-width: 160px;
                margin-top: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1D4ED8, stop:1 #2563EB);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1E40AF, stop:1 #1D4ED8);
            }
        """)

        # Create a layout for the buttons to center them
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(fetch_btn)
        button_layout.addSpacing(20)
        button_layout.addWidget(apply_multi_btn)
        button_layout.addStretch()

        patient_layout.addRow("", button_layout)
        
        patient_title = QLabel("Admin Controls")
        patient_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #FF6A00; margin-bottom: 16px; padding: 4px; font-family: 'Segoe UI', sans-serif;")
        patient_title.setStylesheet("font")
        # Stats
        stats_frame = QFrame()
        stats_frame.setStyleSheet(card_style)
        stats_frame.setMinimumSize(150, 100)
        
        stats_layout = QFormLayout(stats_frame)
        stats_layout.setLabelAlignment(Qt.AlignRight)
        stats_layout.setFormAlignment(Qt.AlignHCenter)
        stats_layout.setSpacing(8)
        self.therapy_usage_label = QLabel("(0.0) hours")
        self.machine_up_time_label = QLabel("(0.0) hours")
        stats_layout.addRow("Therapy Usage:", self.therapy_usage_label)
        stats_layout.addRow("Machine Up Time:", self.machine_up_time_label)
        stats_title = QLabel("Usage Stats")
        stats_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #FF6A00; margin-bottom: 12px; padding: 4px; font-family: 'Segoe UI', sans-serif;")

        # --- Pie Chart (Admin) - BIGGER ---
        # pie_admin_frame = QFrame()
        # pie_admin_frame.setStyleSheet(card_style)
        # pie_admin_frame.setMinimumSize(300, 300)  # Bigger minimum size
        # pie_admin_layout = QVBoxLayout(pie_admin_frame)
        # pie_admin_layout.setContentsMargins(8, 8, 8, 8)
        # pie_admin_layout.setSpacing(6)
        # pie_admin_title = QLabel("Active Users (Monthly)")
        # pie_admin_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #1f2937;")
        # pie_admin_layout.addWidget(pie_admin_title)
        # # create admin matplotlib canvas - BIGGER
        # try:
        #     self.admin_fig = Figure(figsize=(7, 5), dpi=80)  # Bigger figure
        #     self.admin_ax = self.admin_fig.add_subplot(111)
        #     self.admin_canvas = FigureCanvas(self.admin_fig)
        #     self.admin_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #     try:
        #         self.admin_fig.tight_layout()
        #     except Exception:
        #         pass
        #     pie_admin_layout.addWidget(self.admin_canvas, 1)  # Stretch factor
        # except Exception as e:
        #     print(f"Failed to create admin pie chart canvas: {e}")

        # Alerts
        alerts_frame = QFrame()
        alerts_frame.setStyleSheet(card_style)
        alerts_frame.setMinimumSize(150, 140)
        alerts_layout = QVBoxLayout(alerts_frame)
        alerts_layout.setSpacing(5)
        self.alert_labels = {}
        for setting in ["IMODE", "Leak Alert", "Sleep Mode", "Mask Type", "Ramp Time", "Humidifier"]:
            label = QLabel(f"{setting}: (OFF)")
            alerts_layout.addWidget(label)
            self.alert_labels[setting] = label
        alerts_title = QLabel("Alerts & Settings")
        alerts_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #FF6A00; margin-bottom: 12px; padding: 4px; font-family: 'Segoe UI', sans-serif;")
        # Report
        report_frame = QFrame()
        report_frame.setStyleSheet(card_style)

        report_layout = QVBoxLayout(report_frame)
        report_layout.setSpacing(8)
        
        # BIGGER Calendar for Admin
        calendar = QCalendarWidget()
        calendar.setGridVisible(True)
        calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        calendar.setMinimumHeight(300)  
        calendar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Enhanced calendar styling for admin
        calendar.setStyleSheet("""
            QCalendarWidget {
                background-color: #FFFFFF;
                font-size: 14px;
                font-family: 'Segoe UI', sans-serif;
                border-radius: 12px;
            }
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F9FAFB, stop:1 #F3F4F6);
                border: none;
                border-radius: 12px 12px 0 0;
                min-height: 45px;
            }
            QCalendarWidget QToolButton {
                color: #111827;
                font-size: 16px;
                font-weight: 600;
                border: none;
                background: none;
                padding: 10px;
                border-radius: 8px;
            }
            QCalendarWidget QToolButton:hover {
                background-color: rgba(255, 106, 0, 0.1);
            }
            QCalendarWidget QToolButton:pressed {
                background-color: rgba(255, 106, 0, 0.2);
            }
            QCalendarWidget QAbstractItemView {
                font-size: 13px;
                background-color: #FFFFFF;
                color: #374151;
                selection-background-color: #FF6A00;
                selection-color: white;
                alternate-background-color: #F9FAFB;
            }
            QCalendarWidget QAbstractItemView::item {
                padding: 10px;
                min-height: 42px;
                min-width: 42px;
                border-radius: 8px;
            }
            QCalendarWidget QAbstractItemView::item:selected {
                background-color: #FF6A00;
                color: white;
                border-radius: 8px;
            }
            QCalendarWidget QAbstractItemView::item:hover {
                background-color: rgba(255, 106, 0, 0.1);
            }
        """)
        
        # Device Status
        status_layout = QHBoxLayout()
        status_layout.setSpacing(10)
        status_layout.setAlignment(Qt.AlignLeft)
        self.status_label = QLabel("●")
        self.status_label.setStyleSheet("QLabel { font-size: 12px; color: #EF4444; font-family: 'Segoe UI', sans-serif; }")
        self.status_text = QLabel("Not Connected")
        self.status_text.setStyleSheet("QLabel { font-size: 13px; color: " + THEME_TEXT_SOFT + "; font-weight: 500; font-family: 'Segoe UI', sans-serif; padding-left: 10px; }")
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.status_text) 
        status_layout.addStretch()

        status_frame = QFrame()
        status_frame.setLayout(status_layout)
        status_frame.setStyleSheet("QFrame { background: transparent; padding: 10px 0; }")

        pdf_btn = QPushButton("Export PDF")
        pdf_btn.clicked.connect(self.export_pdf)
        csv_btn = QPushButton("Export CSV") 
        csv_btn.clicked.connect(self.export_csv)    
        btn_layout = QHBoxLayout()
           
        btn_layout.setSpacing(10)
        btn_layout.addWidget(pdf_btn)
        btn_layout.addWidget(csv_btn)
        

        report_layout.addWidget(calendar, 2)  
        report_layout.addWidget(status_frame)
        report_layout.addLayout(btn_layout)

        report_title = QLabel("Report")
        report_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #FF6A00; margin-bottom: 12px; padding: 4px; font-family: 'Segoe UI', sans-serif;")

        pdf_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10B981, stop:1 #059669);
                color: white;
                border-radius: 14px;
                padding: 12px 24px;
                font-weight: 600;
                font-size: 15px;
                font-family: 'Segoe UI', sans-serif;
                border: none;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #059669, stop:1 #10B981);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #047857, stop:1 #059669);
            }
        """)
        
        csv_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F59E0B, stop:1 #D97706);
                color: white;
                border-radius: 14px;
                padding: 12px 24px;
                font-weight: 600;
                font-size: 15px;
                font-family: 'Segoe UI', sans-serif;
                border: none;
                min-width: 120px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #D97706, stop:1 #F59E0B);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B45309, stop:1 #D97706);
            }
        """)
        
        # Grid layout - 
        grid = QGridLayout()
        grid.setSpacing(15)
        grid.setContentsMargins(0, 0, 0, 0)
        
        # Row 0: Titles
        grid.addWidget(patient_title, 0, 0)
        grid.addWidget(stats_title, 0, 1)
        grid.addWidget(alerts_title, 0, 2)
        grid.addWidget(report_title, 0, 3)
        
        # Row 1: Main cards
        grid.addWidget(patient_frame, 1, 0)
        grid.addWidget(stats_frame, 1, 1)
        grid.addWidget(alerts_frame, 1, 2)
        grid.addWidget(report_frame, 1, 3)
        
        
        
        # Set stretch factors
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 2)
        grid.setColumnStretch(3, 3)  
        
        grid.setRowStretch(1, 2)  
        
        #main_layout.addLayout(grid)
        
        scroll = QScrollArea()
        #scroll.setWidget(page)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { 
                border: none; 
                background: transparent; 
            } 
            QScrollBar:vertical { 
                background: rgba(229, 231, 235, 0.5); 
                border-radius: 8px; 
                width: 12px; 
            } 
            QScrollBar::handle:vertical { 
                background: #FF6A00; 
                border-radius: 6px; 
                min-height: 30px; 
            }
            QScrollBar::handle:vertical:hover { 
                background: #FF8A00; 
            }
        """)
        return scroll

    def fetch_settings(self):
        # --- 1. Read & normalize serial safely ---
        raw_serial = self.serial_input.text()
        serial = raw_serial.strip()

        print("RAW SERIAL:", repr(raw_serial))
        print("NORMALIZED SERIAL:", repr(serial))

        if not serial:
            QMessageBox.warning(self, "Error", "Please enter a serial number.")
            return

        # Prevent placeholder / bad input
        if "{" in serial or "}" in serial:
            QMessageBox.warning(self, "Invalid Serial", "Invalid serial number entered.")
            return

        
        original_serial = serial
        if serial.isdigit():
            serial = serial.zfill(3)
            
        print(f"Original serial: {original_serial}, Normalized serial: {serial}")

        machine_type_selected = self.machine_type_combo.currentText()

        url = f"https://stringfetchbackend-production.up.railway.app/api/devices/{serial}/data?limit=1"
        print("FINAL URL:", url)

        try:
            response = requests.get(url, timeout=10)
            print(f"Response status: {response.status_code}")
            response.raise_for_status()
            api_data = response.json()

            # Debug response
            print("API RESPONSE:", api_data)
            print(f"Success: {api_data.get('success')}")
            print(f"Data keys: {list(api_data.get('data', {}).keys()) if api_data.get('data') else 'No data'}")
            if api_data.get('data') and api_data.get('data').get('records'):
                print(f"Number of records: {len(api_data['data']['records'])}")
            else:
                print("No records found")

            if not api_data.get("success"):
                QMessageBox.warning(
                    self,
                    "Error",
                    f"API request failed: {api_data.get('message', 'Unknown error')}"
                )
                return

            # Check if API returns direct data structure or records array
            api_data_content = api_data.get("data", {})
            
            if "records" in api_data_content:
                # Old format with records array
                records = api_data_content["records"]
                if not records:
                    QMessageBox.warning(self, "No Data", f"No records found for device serial: {serial}")
                    return
                latest_record = records[0]
                device_type_api = latest_record.get("device_type", "BIPAP")
                csv_line = latest_record.get("parsed_data", {}).get("csv_line", "")
            else: 
                # New format with direct dataString
                data_string = api_data_content.get("dataString", "")
                device_type_api = api_data_content.get("deviceType", "BIPAP")
                csv_line = data_string
                
                if not data_string:
                    QMessageBox.warning(self, "No Data", f"No dataString found for device serial: {serial}")
                    return
                print(f"Found direct dataString: {data_string[:50]}...")  

            if device_type_api != machine_type_selected:
                reply = QMessageBox.question(
                    self,
                    "Type Mismatch",
                    f"API reports {device_type_api}, selected {machine_type_selected}. Proceed?"
                )
                if reply != QMessageBox.Yes:
                    return

            # --- 2. Update machine state ---
            self.machine_type = device_type_api
            self.machine_type_combo.setCurrentText(device_type_api)
            self.update_button_states()

            # --- 3. Process CSV line ---
            if not csv_line:
                QMessageBox.warning(self, "Error", "No CSV data received from API.")
                return

            print(f"Sending to update_all_from_cloud: {csv_line}")
            message = {"device_data": csv_line}
            self.update_all_from_cloud(message)

            # --- 4. Update UI ---
            self.machine_serial = serial
            self.serial_input.setText(serial)
            self.info_label.setText(
                f"User: ({self.user_name})    |    Machine S/N: ({serial})"
            )

            QMessageBox.information(
                self,
                "Success",
                "Settings fetched from API and loaded into UI!"
            )

        except requests.exceptions.RequestException as e:
            QMessageBox.warning(self, "Network Error", str(e))

        except Exception as e:
            QMessageBox.warning(self, "Processing Error", str(e))


    def on_type_change(self, machine_type):
        """Handle machine type combo box change"""
        self.machine_type = machine_type
        self.update_button_states()
            
class HoverKPICard(QFrame):
    def __init__(self, text, value, icon_color, border_color, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setObjectName("HoverKPICard")
        self.initial_border_color = border_color
        self.hover_border_color = QColor(border_color).lighter(150).name()

        self.setStyleSheet("""
            QFrame#HoverKPICard {{
                background: transparent;
                border-radius:20px;
                border:3px solid {};
                padding:20px;
            }}
        """.format(self.initial_border_color))

        v = QVBoxLayout(self)
        v.setSpacing(6)
        
        self.label_text = QLabel(text)
        self.label_text.setStyleSheet("font-size:18px;color:" + THEME_TEXT_SOFT + ";")
        
        self.label_value = QLabel(value)
        self.label_value.setObjectName("KPIValue")
        self.label_value.setStyleSheet("font-size:24px;font-weight:700;color:#111827;")
        

        self.label_icon = QLabel("•")
        self.label_icon.setStyleSheet(f"font-size:18px;color:{icon_color};")
        
        v.addWidget(self.label_icon)
        v.addWidget(self.label_text)
        v.addWidget(self.label_value)
        v.addStretch()

    def enterEvent(self, event):
        super().enterEvent(event) 

    def leaveEvent(self, event):
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        QMessageBox.information(self, "Report", f"{self.label_text.text()} details")
        super().mousePressEvent(event)

# Run
if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    app.setApplicationName("CPAP/BIPAP Dashboard")
    app.setStyleSheet("""
        * {
            font-family: 'Segoe UI', 'Arial';
            color: #111827;
        }
        QLabel {
            font-size: 14px;
        }
        QLineEdit, QComboBox, QDateEdit {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: 6px 10px;
            selection-background-color: #1f6feb;
            selection-color: #ffffff;
        }
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
            border: 1px solid """ + THEME_PRIMARY + """;
        }
        QPushButton {
            border-radius: 10px;
            padding: 8px 14px;
            font-weight: 600;
        }
        QPushButton:disabled {
            background: #eef2f7;
            color: #9ca3af;
        }
        QTableWidget {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            gridline-color: #e5e7eb;
        }
        QHeaderView::section {
            background: #F6F8FA;
            border: 1px solid #e5e7eb;
            padding: 6px 8px;
            font-weight: 700;
            color: #374151;
        }
        QScrollBar:vertical {
            width: 8px;
            background: transparent;
            margin: 12px 4px 12px 0px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 """ + THEME_PRIMARY + """, stop:1 """ + THEME_PRIMARY_2 + """);
            border-radius: 4px;
            min-height: 24px;
        }
        QScrollBar::handle:vertical:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #30A8FF, stop:1 #58A6FF);
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            background: none;
            height: 0px;
            width: 0px;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: #e5e7eb;
            border-radius: 4px;
        }
        QScrollBar:horizontal {
            height: 8px;
            background: transparent;
            margin: 0px 12px 0px 12px;
            border-radius: 4px;
        }
        QScrollBar::handle:horizontal {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #58A6FF, stop:1 #30A8FF);
            border-radius: 4px;
            min-width: 24px;
        }
        QScrollBar::handle:horizontal:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #30A8FF, stop:1 #58A6FF);
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            background: none;
            height: 0px;
            width: 0px;
        }
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
            background: #e5e7eb;
            border-radius: 4px;
        }
        QMessageBox {
            background: #ffffff;
        }
        QMessageBox QLabel {
            font-size: 13px;
        }
        QMessageBox QPushButton {
            min-width: 90px;
        }
    """)
    window = LoginWindow()
    window.show()
    sys.exit(app.exec_())
