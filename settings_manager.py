import sys, json, os, time, threading
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QStackedWidget, QMessageBox, QFormLayout, QFrame, QHBoxLayout, QDialog,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QSizePolicy, QGridLayout,
    QCalendarWidget, QTableWidget, QTableWidgetItem, QFileDialog, QScrollArea,
    QComboBox
)
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QEventLoop, QTimer

# Import AWS IoT related modules
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder
from concurrent.futures import Future
import queue  
from datetime import datetime

# --- Style Constants for Professional Look (Dark Teal/Emerald Green) ---
PRIMARY_COLOR = "#00A398"      # Teal/Emerald Green (Primary Accent)
ACCENT_COLOR = "#00736C"       # Darker Teal/Emerald (Hover/Active)
BACKGROUND_LIGHT = "#FFFFFF"   # Crisp White Background for Cards/Inputs
BACKGROUND_ALT = "#F0FFEE"     # Very Light, hint-of-green Background for Main Window
TEXT_DARK = "#2C3E50"          # Dark Charcoal Text for high readability
TEXT_ACCENT = "#00A398"        # Teal Text
SUCCESS_COLOR = "#2ECC71"      # Green for Save/Success
DANGER_COLOR = "#E74C3C"       # Red for Logout/Reset

USER_FILE = "users.json"
SETTINGS_FILE = "settings.json"

def compact_csv(*values: str) -> str:
    """Join values with commas, skip any None/empty/whitespace."""
    parts = [v for v in values if v and str(v).strip() and str(v).strip() != ""]
    return ",".join(parts)

def load_all_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

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
 
# ---------- OTP Dialog ----------
class OTPDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OTP Verification")
        self.setFixedSize(400, 250)
        self.setWindowFlags(Qt.Window)

        layout = QVBoxLayout()
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background: rgba({BACKGROUND_LIGHT}, 0.8);
                border-radius: 0px;
                border: 1px solid {PRIMARY_COLOR};
            }}
            QLabel {{ font-size: 14px; color: {TEXT_DARK}; }}
            QLineEdit {{
                border: 2px solid rgba({PRIMARY_COLOR}, 0.5); 
                border-radius: 12px; 
                padding: 8px; 
                font-size: 14px;
                background: rgba({BACKGROUND_LIGHT}, 0.8);
            }}
            QLineEdit:focus {{ border: 2px solid {PRIMARY_COLOR}; }}
            QPushButton {{
                background: {PRIMARY_COLOR};
                color: white; 
                border-radius: 15px; 
                padding: 10px; 
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {ACCENT_COLOR};
            }}
        """)
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
        self.setFixedSize(900, 600)
        self.users = load_users()
        self.setWindowFlags(Qt.Window)

        # ---------- Main Layout ----------
        main_layout = QHBoxLayout()
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Left Panel
        self.left_panel = QFrame()
        self.left_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.left_panel.setStyleSheet(f"QFrame {{ background: rgba(0, 0, 0, 0.2); border: none; }}")

        # Right Panel
        self.right_panel = QFrame()
        self.right_panel.setStyleSheet(f"QFrame {{ background: rgba({BACKGROUND_LIGHT}, 0.8); border-radius: 0px; border: none; }}")
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

        # Shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setXOffset(0)
        shadow.setYOffset(5)
        shadow.setColor(QColor(0, 0, 0, 80))
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
        bg = QPixmap("assets/sign in background.jpg")
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
        container.setStyleSheet(f"""
            QFrame {{
                background: rgba({BACKGROUND_LIGHT}, 0.7);
                border-radius: 0px;
                border: 1px solid {PRIMARY_COLOR};
                padding: 20px;
            }}
        """)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container_layout = QVBoxLayout()
        container_layout.setSpacing(15)

        title = QLabel(f"<h1 style='color:{ACCENT_COLOR}; margin:0; font-size:28px;'>BIPAP Dashboard</h1>"
                       f"<h2 style='color:{ACCENT_COLOR}; margin:0; font-size:20px;'>DeckMount Electronics Ltd.</h2>")
        title.setAlignment(Qt.AlignCenter)

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("Email ID")
        self.user_input.setStyleSheet(self.input_style())
        self.user_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.user_input.setFixedHeight(40)
        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("Password")
        self.pass_input.setEchoMode(QLineEdit.Password)
        self.pass_input.setStyleSheet(self.input_style())
        self.pass_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.pass_input.setFixedHeight(40)
        login_btn = QPushButton("Login")
        login_btn.setStyleSheet(self.button_style())
        login_btn.clicked.connect(self.do_login)
        login_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        login_btn.setFixedHeight(45)
        reg_btn = QPushButton("New User? Register Here")
        reg_btn.setStyleSheet(f"background:none;color:{PRIMARY_COLOR};border:none;font-size:14px;")
        reg_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        reg_btn.setFixedHeight(30)

        container_layout.addWidget(title)
        container_layout.addWidget(self.user_input)
        container_layout.addWidget(self.pass_input)
        container_layout.addWidget(login_btn)
        container_layout.addWidget(reg_btn, alignment=Qt.AlignCenter)
        container_layout.addStretch()
        container.setLayout(container_layout)
        layout.addWidget(container)
        
        page.setLayout(layout)
        return page

    def register_page(self):
        page = QFrame()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.addStretch()

        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background: rgba({BACKGROUND_LIGHT}, 0.8);
                border-radius: 0px; 
                border: 1px solid {PRIMARY_COLOR};
                padding: 20px;
            }}
        """)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(12)
        form_layout.setHorizontalSpacing(20)
        form_layout.setLabelAlignment(Qt.AlignRight)

        title = QLabel(f"<h1 style='color:{ACCENT_COLOR}; margin:5px; font-size:24px;'>New User Registration</h1>")
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
            w.setFixedHeight(40)

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
        reg_btn.setFixedHeight(45)
        back_btn = QPushButton("Back to Login")
        back_btn.setStyleSheet(f"background:none;color:{PRIMARY_COLOR};border:none;font-size:14px;")
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
        return f"""
        QLineEdit {{
            border: 2px solid rgba({PRIMARY_COLOR}, 0.5);
            border-radius: 12px;
            padding: 10px;
            background: rgba({BACKGROUND_LIGHT}, 0.8);
            font-size: 14px;
        }}
        QLineEdit:focus {{ border: 2px solid {ACCENT_COLOR}; }}
        """

    def button_style(self):
        return f"""
        QPushButton {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {SUCCESS_COLOR}, stop:1 {PRIMARY_COLOR});
            color: white; 
            border-radius: 18px; 
            font-weight: bold; 
            padding: 12px;
            font-size: 14px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {PRIMARY_COLOR}, stop:1 {SUCCESS_COLOR});
        }}
        """

    def do_login(self):
        email = self.user_input.text().strip()
        pwd = self.pass_input.text().strip()
        print(f"Login attempt: email={email}, password={pwd}, users={self.users}")
        if email == "mehul@admin" and pwd == "admin":
            QMessageBox.information(self, "Success", "Welcome Admin!")
            self.admin_dashboard = AdminDashboard(user_name="Admin", machine_serial="", login_window=self, user_data={})
            self.admin_dashboard.showMaximized()
            self.user_input.clear()
            self.pass_input.clear()
            self.hide()
        elif email in self.users and self.users[email]["password"] == pwd:
            user_name = self.users[email].get("name", email.split('@')[0] or "User")
            serial_no = self.users[email].get('serial_no', 'Unknown')
            user_data = self.users[email]
            user_data['email'] = email
            QMessageBox.information(self, "Success", f"Welcome {user_name}!")
            self.dashboard = Dashboard(user_name=user_name, machine_serial=serial_no, login_window=self, user_data=user_data)
            self.dashboard.showMaximized()
            self.user_input.clear()
            self.pass_input.clear()
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
        print(f"Register attempt: email={email}, password={password}")
        if not all([name, contact, address, password, email, serial]):
            QMessageBox.warning(self, "Error", "All fields are required!")
            return
        if email in self.users:
            QMessageBox.warning(self, "Error", "User already exists!")
            return
        otp_dialog = OTPDialog(self)
        if otp_dialog.exec_() == QDialog.Accepted:
            try:
                self.users[email] = {
                    "name": name,
                    "contact": contact,
                    "address": address,
                    "password": password,
                    "serial_no": serial
                }
                save_users(self.users)
                self.users = load_users()
                QMessageBox.information(self, "Registered", "User Registered Successfully!")
                self.stack.setCurrentIndex(0)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to register user: {str(e)}")

# ---------------- Dashboard ----------------
class Dashboard(QWidget):
    def __init__(self, user_name="Sample User", machine_serial="SN123456", login_window=None, user_data=None):
        super().__init__()
        self.login_window = login_window
        self.user_data = user_data or {}
        self.setWindowTitle("BIPAP Dashboard")
        self.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {BACKGROUND_ALT}, stop:1 {BACKGROUND_LIGHT}
                );
            }}
        """)

        self.user_name = user_name
        self.machine_serial = machine_serial
        self.machine_type = "BIPAP"  
        self.start_time = time.time()
        self.therapy_active = True
        self.current_mode = None

        # Default values - Added Ti.Max for ST
        self.default_values = {
            "CPAP": {"Set Pressure": 4.0},
            "AutoCPAP": {"Min Pressure": 4.0, "Max Pressure": 20.0},
            "S": {"IPAP": 6, "EPAP": 4, "Start EPAP": 4,
                  "Ti.Min": 0.2, "Ti.Max": 3,
                  "Sensitivity": 1, "Rise Time": 50},
            "T": {"IPAP": 6, "EPAP": 4, "Start EPAP": 4,
                  "Respiratory Rate": 10, "Ti.Min": 1, "Ti.Max": 2, "Rise Time": 200},
            "VAPS": {"Height": 170, "Tidal Volume": 500, "Max IPAP": 20,
                     "Min IPAP": 10, "EPAP": 5, "Respiratory Rate": 10,
                     "Ti.Min": 1, "Ti.Max": 2, "Rise Time": 200, "Sensitivity": 1},
            "ST": {"IPAP": 6, "EPAP": 4, "Start EPAP": 4, "Backup Rate": 10,
                   "Ti.Min": 1, "Ti.Max": 2, "Rise Time": 200, "Sensitivity": 3},
            "Settings": {"IMODE": "OFF", "Leak Alert": "OFF", "Gender": "Male",
                         "Sleep Mode": "OFF", "Mask Type": "Nasal", "Ramp Time": "5",
                         "Humidifier": 1, "Flex": "OFF", "Flex Level": 1}
        }

        self.mode_map = {
            "CPAP": (0, 0),
            "AutoCPAP": (0, 1),
            "S": (1, 2),
            "T": (1, 3),
            "ST": (1, 4),
            "VAPS": (1, 5),
        }

        self.card_color = "#A8D8FF"
        self.value_labels = {}
        self.info_label = None  # To update serial
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # ---------------- Sidebar ----------------
        sidebar = QVBoxLayout()
        sidebar.setSpacing(25)
        sidebar.setContentsMargins(5, 5, 5, 5)
        self.sidebar_buttons = []

        sidebar_color = (f"{ACCENT_COLOR}", f"{PRIMARY_COLOR}")
        for text in ["Dashboard", "CPAP Mode", "AutoCPAP Mode", "S Mode", "T Mode", "VAPS Mode", "ST Mode", "Report", "Settings"]:
            btn = QPushButton(text)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setFixedHeight(55)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                                                stop:0 {sidebar_color[0]}, stop:1 {sidebar_color[1]});
                    color: #000000;
                    font-weight: bold;
                    font-size: 16px;
                    border-radius: 10px;
                    padding: 10px;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                                                stop:0 {sidebar_color[1]}, stop:1 {sidebar_color[0]});
                }}
            """)
            sidebar.addWidget(btn)
            self.sidebar_buttons.append(btn)

        # Add Logout button
        logout_btn = QPushButton("Logout")
        logout_btn.setFixedSize(120, 50)
        logout_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        logout_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                                            stop:0 {DANGER_COLOR}, stop:1 #C82333);
                color: #FFFFFF;
                font-weight: bold;
                font-size: 14px;
                border-radius: 12px;
                padding: 10px;
                border: none;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                                            stop:0 #C82333, stop:1 {DANGER_COLOR});
            }}
        """)
        logout_btn.clicked.connect(self.do_logout)
        sidebar.addStretch()
        sidebar.addWidget(logout_btn, alignment=Qt.AlignCenter)

        # ---------------- Content ----------------
        content_layout = QVBoxLayout()
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(5, 5, 5, 5)

        self.info_label = QLabel(f"User: {self.user_name}    |    Machine S/N: {self.machine_serial}")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {TEXT_DARK}; padding: 5px;")
        content_layout.addWidget(self.info_label)

        self.current_mode_label = QLabel("Current Mode: Dashboard")
        self.current_mode_label.setAlignment(Qt.AlignCenter)
        self.current_mode_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {PRIMARY_COLOR}; padding: 5px;")
        content_layout.addWidget(self.current_mode_label)

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout.addWidget(self.stack)

        # Mode pages
        self.pages = []
        for mode_name in ["Dashboard", "CPAP", "AutoCPAP", "S", "T", "VAPS", "ST", "Report", "Settings"]:
            if mode_name == "Dashboard":
                page = self.create_dashboard_page()
            elif mode_name in self.default_values:
                page = self.create_mode_page(mode_name, self.default_values[mode_name], options_mode=(mode_name == "Settings"))
            else:
                page = self.create_page(f"{mode_name} Page")
            self.pages.append(page)
            self.stack.addWidget(page)

        main_layout.addLayout(sidebar, 1)
        main_layout.addLayout(content_layout, 4)  

        # Button actions
        for i, btn in enumerate(self.sidebar_buttons):
            btn.clicked.connect(lambda _, idx=i, name=btn.text(): self.set_mode(idx, name))

        self.load_settings()
        self.set_mode(0, "Dashboard")

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

    def apply_cloud_csv(self, csv_line: str, serial: str, machine_type: str):
        """Parse the raw CSV line (e.g. "*S,101124,1430,A,8.0,1,…#") and fill UI."""
        if not (csv_line.startswith("*") and csv_line.endswith("#")):
            QMessageBox.warning(self, "Error", "Invalid CSV line – missing * / #")
            return

        parts = [p.strip() for p in csv_line[1:-1].split(",")]
        all_settings = load_all_settings()
        mask_map_inv = {"1": "Nasal", "2": "Pillow", "3": "FullFace"}
        gender_map_inv = {"1": "Male", "2": "Female"}

        try:
            if machine_type == "CPAP":
                if len(parts) != 20:
                    raise ValueError(f"CPAP expects 20 fields, got {len(parts)}")
                # G – CPAP
                g_idx = parts.index("G")
                all_settings["CPAP"] = {"Set Pressure": float(parts[g_idx + 1])}

                # H – AutoCPAP
                h_idx = parts.index("H")
                all_settings["AutoCPAP"] = {
                    "Min Pressure": float(parts[h_idx + 1]),
                    "Max Pressure": float(parts[h_idx + 3])
                }

                # I – Settings
                i_idx = parts.index("I")
                all_settings["Settings"] = {
                    "Ramp Time": int(parts[i_idx + 1]),
                    "Humidifier": int(parts[i_idx + 2]),
                    "Mask Type": mask_map_inv.get(parts[i_idx + 3], "Nasal"),
                    "IMODE": "ON" if parts[i_idx + 4] == "1" else "OFF",
                    "Leak Alert": "ON" if parts[i_idx + 5] == "1" else "OFF",
                    "Gender": gender_map_inv.get(parts[i_idx + 6], "Male"),
                    "Sleep Mode": "ON" if parts[i_idx + 7] == "1" else "OFF"
                }

            else:  # BIPAP (default)
                if len(parts) != 56:
                    raise ValueError(f"BIPAP expects 56 fields, got {len(parts)}")

                # A – CPAP
                a_idx = parts.index("A")
                all_settings["CPAP"] = {"Set Pressure": float(parts[a_idx + 1])}

                # B – S Mode (9 fields: IPAP, EPAP, Start EPAP, Ti.Min*10, Ti.Max*10, Sensitivity, Rise Time, Mask, ?)
                b_idx = parts.index("B")
                all_settings["S"] = {
                    "IPAP": int(parts[b_idx + 1]),
                    "EPAP": int(parts[b_idx + 2]),
                    "Start EPAP": int(parts[b_idx + 3]),
                    "Ti.Min": float(parts[b_idx + 4]) / 10,
                    "Ti.Max": float(parts[b_idx + 5]) / 10,
                    "Sensitivity": int(parts[b_idx + 6]),
                    "Rise Time": int(parts[b_idx + 7])
                }

                # C – T Mode (10 fields: IPAP, EPAP, Start EPAP, RR, Ti.Min*10, Ti.Max*10, Sensitivity, Rise Time, Mask, ?)
                c_idx = parts.index("C")
                all_settings["T"] = {
                    "IPAP": int(parts[c_idx + 1]),
                    "EPAP": int(parts[c_idx + 2]),
                    "Start EPAP": int(parts[c_idx + 3]),
                    "Respiratory Rate": int(parts[c_idx + 4]),
                    "Ti.Min": float(parts[c_idx + 5]) / 10,
                    "Ti.Max": float(parts[c_idx + 6]) / 10,
                    "Sensitivity": int(parts[c_idx + 7]),
                    "Rise Time": int(parts[c_idx + 8])
                }

                # D – ST Mode (10 fields: IPAP, EPAP, Start EPAP, Backup Rate, Ti.Min*10, Ti.Max*10, Sensitivity, Rise Time, Mask, ?)
                d_idx = parts.index("D")
                all_settings["ST"] = {
                    "IPAP": int(parts[d_idx + 1]),
                    "EPAP": int(parts[d_idx + 2]),
                    "Start EPAP": int(parts[d_idx + 3]),
                    "Backup Rate": int(parts[d_idx + 4]),
                    "Ti.Min": float(parts[d_idx + 5]) / 10,
                    "Ti.Max": float(parts[d_idx + 6]) / 10,
                    "Sensitivity": int(parts[d_idx + 7]),
                    "Rise Time": int(parts[d_idx + 8])
                }

                # E – VAPS Mode (13 fields: Max IPAP, Min IPAP, EPAP, RR, Ti.Min*10, Ti.Max*10, Sensitivity, Rise Time, Mask, Height, Tidal Volume, ?, ?)
                e_idx = parts.index("E")
                all_settings["VAPS"] = {
                    "Max IPAP": int(parts[e_idx + 1]),
                    "Min IPAP": int(parts[e_idx + 2]),
                    "EPAP": int(parts[e_idx + 3]),
                    "Respiratory Rate": int(parts[e_idx + 4]),
                    "Ti.Min": float(parts[e_idx + 5]) / 10,
                    "Ti.Max": float(parts[e_idx + 6]) / 10,
                    "Sensitivity": int(parts[e_idx + 7]),
                    "Rise Time": int(parts[e_idx + 8]),
                    "Height": int(parts[e_idx + 10]),  # Skip mask at +9
                    "Tidal Volume": int(parts[e_idx + 11])
                }

                # F – Settings (9 fields: Ramp, Humidifier, Mask, IMODE, Leak, Gender, Sleep, Serial, ?)
                f_idx = parts.index("F")
                all_settings["Settings"] = {
                    "Ramp Time": int(parts[f_idx + 1]),
                    "Humidifier": int(parts[f_idx + 2]),
                    "Mask Type": mask_map_inv.get(parts[f_idx + 3], "Nasal"),
                    "IMODE": "ON" if parts[f_idx + 4] == "1" else "OFF",
                    "Leak Alert": "ON" if parts[f_idx + 5] == "1" else "OFF",
                    "Gender": gender_map_inv.get(parts[f_idx + 6], "Male"),
                    "Sleep Mode": "ON" if parts[f_idx + 7] == "1" else "OFF"
                }

                # Note: AutoCPAP (H) not in BIPAP CSV; fall back to defaults
                if "AutoCPAP" not in all_settings:
                    all_settings["AutoCPAP"] = self.default_values["AutoCPAP"]

            # Save updated settings to file
            with open(SETTINGS_FILE, "w") as f:
                json.dump(all_settings, f, indent=4)

            # Reload settings to update UI labels
            self.load_settings()

            # Update machine serial if provided and different
            if serial and serial != self.machine_serial:
                self.machine_serial = serial
                self.info_label.setText(f"User: {self.user_name}    |    Machine S/N: {self.machine_serial}")

            # Update alerts if settings changed
            self.update_alerts()

            QMessageBox.information(self, "Success", f"Settings for {machine_type} updated from cloud data!")

        except ValueError as ve:
            QMessageBox.warning(self, "Parse Error", f"Invalid CSV format: {str(ve)}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to apply cloud settings: {str(e)}")

    def reset_mode(self, mode_name):
        defaults = self.default_values[mode_name]
        for title, label in self.value_labels[mode_name].items():
            val = defaults[title]
            unit_map = {
                "IPAP": "CmH2O", "EPAP": "CmH2O", "Start EPAP": "CmH2O",
                "Rise Time": " mSec", "Ti.Min": "Sec", "Ti.Max": "Sec",
                "Ti (Insp. Time)": "Sec", "Height": "cm", "Tidal Volume": "ml",
                "Set Pressure": "CmH2O" if mode_name == "CPAP" else "",
                "Sensitivity": "", "Min IPAP": "CmH2O", "Max IPAP": "CmH2O",
                "Min Pressure": "CmH2O", "Max Pressure": "CmH2O", "Backup Rate": "/min"
            }
            unit = unit_map.get(title, "")
            if isinstance(val, float):
                label.setText(f"{val:.2f} {unit}".strip())
            else:
                label.setText(f"{val} {unit}".strip())

    def load_settings(self):
        try:
            with open(SETTINGS_FILE, "r") as f:
                all_data = json.load(f)
            self.settings = all_data.get("Settings", self.default_values["Settings"])
            for mode, values in all_data.items():
                if mode in self.value_labels:
                    for title, val in values.items():
                        if title in self.value_labels[mode]:
                            unit_map = {
                                "IPAP": "CmH2O", "EPAP": "CmH2O", "Start EPAP": "CmH2O",
                                "Rise Time": " mSec", "Ti.Min": "Sec", "Ti.Max": "Sec",
                                "Ti (Insp. Time)": "Sec", "Height": "cm", "Tidal Volume": "ml",
                                "Set Pressure": "CmH2O" if mode == "CPAP" else "",
                                "Sensitivity": "", "Min IPAP": "CmH2O", "Max IPAP": "CmH2O",
                                "Min Pressure": "CmH2O", "Max Pressure": "CmH2O", "Backup Rate": "/min"
                            }
                            unit = unit_map.get(title, "")
                            self.value_labels[mode][title].setText(f"{val:.2f} {unit}".strip() if isinstance(val, float) else f"{val} {unit}".strip())
        except FileNotFoundError:
            self.settings = self.default_values["Settings"]

    def aws_iot_loop(self):
        ENDPOINT = "a2jqpfwttlq1yk-ats.iot.us-east-1.amazonaws.com"
        CLIENT_ID = "iotconsole-560333af-04b9-45fb-8cd0-4ef4cd819d92"

        BASE_PATH = r"C:\Users\tanya\OneDrive\Desktop\CPAP\AWS"
        PATH_TO_CERTIFICATE = os.path.join(BASE_PATH, "6e5d12437ffc7b19a750505da172d382b6e81026243aa254bce059b8bc45796f-certificate.pem.crt")
        PATH_TO_PRIVATE_KEY = os.path.join(BASE_PATH, "6e5d12437ffc7b19a750505da172d382b6e81026243aa254bce059b8bc45796f-private.pem.key")
        PATH_TO_AMAZON_ROOT_CA = os.path.join(BASE_PATH, "AmazonRootCA1.pem")
        
        TOPIC = "esp32/data1"
        ACK_TOPIC = "esp32/data" 

        QUEUE_FILE = os.path.join(BASE_PATH, "pendingfiles.json")

        pending_messages = []
        is_connected = False
        self.ack_received = True
        mqtt_connection = None

        def load_pending():
            nonlocal pending_messages
            if os.path.exists(QUEUE_FILE):
                try:
                    with open(QUEUE_FILE, 'r') as f:
                        pending_messages = json.load(f)
                    print(f"Loaded {len(pending_messages)} pending messages from file: {pending_messages}")
                except Exception as e:
                    print(f"Error loading pending messages: {e}")
                    pending_messages = []
            else:
                print(f"No pending data file found at {QUEUE_FILE}")
                pending_messages = []

        def save_pending():
            nonlocal pending_messages
            try:
                with open(QUEUE_FILE, 'w') as f:
                    json.dump(pending_messages, f)
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
                message = json.loads(payload.decode('utf-8'))
                print(f"Message content: {json.dumps(message, indent=2)}")
                if topic == ACK_TOPIC and message.get("acknowledgment") == 1:
                    print("Acknowledgment received")
                    self.ack_received = True
                elif "device_data" in message:
                    self.aws_receive_queue.put(message)
                print("Message received successfully!")
            except Exception as e:
                print(f"Error processing received message: {e}")

        def on_connection_interrupted(connection, error, **kwargs):
            nonlocal is_connected
            is_connected = False
            print(f"Connection interrupted. Error: {error}. Device is now DISCONNECTED.")

        def on_connection_resumed(connection, return_code, session_present, **kwargs):
            nonlocal is_connected
            is_connected = True
            self.ack_received = True  
            print(f"Connection resumed. Return code: {return_code}, Session present: {session_present}. Device is now CONNECTED.")
            load_pending()
            if not session_present:
                subscribe_to_topics(connection)
            if pending_messages:
                send_pending(connection)

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
            print(f"send_pending: ack_received={self.ack_received}, pending_messages_count={len(pending_messages)}")
            if not is_connected:
                print("Cannot send pending messages: Device is DISCONNECTED.")
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
                        save_pending()
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
        load_pending()
        while not is_connected:
          
            print(f"Connecting to {ENDPOINT} with client ID '{CLIENT_ID}'...")
            try:
                connect_future: Future = mqtt_connection.connect()
                connect_future.result(timeout=10)
                is_connected = True
                print("Connected successfully to AWS IoT Core! Device is now CONNECTED.")
                subscribe_to_topics(mqtt_connection)
                send_pending(mqtt_connection)
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
                    print("Attempting to reconnect...")
                    try:
                        connect_future: Future = mqtt_connection.connect()
                        connect_future.result(timeout=10)
                        is_connected = True 
                        print("Reconnected successfully to AWS IoT Core! Device is now CONNECTED.")
                        subscribe_to_topics(mqtt_connection)
                        send_pending(mqtt_connection)
                    except Exception as e:
                        print(f"Reconnection failed: {e}. Retrying in 1 second...")
                    try:
                        new_data = self.aws_send_queue.get_nowait()
                        if not is_duplicate_sample(new_data):
                            pending_messages.append(new_data)
                            save_pending()
                        print("New data queued to pending_data.json since device is DISCONNECTED.")
                    except queue.Empty: 
                        pass
                time.sleep(2 if not is_connected else 1)
        except KeyboardInterrupt:
            print("\nDisconnecting from AWS IoT Core...")

# AdminDashboard – dashboard page + fetch-settings
class AdminDashboard(Dashboard):
    def __init__(self, user_name="Admin", machine_serial="", login_window=None, user_data={}):
        super().__init__(user_name, machine_serial, login_window, user_data)
        self.machine_serial = machine_serial
        # combo will be filled in create_dashboard_page()
        self.machine_type_combo = None

    def create_dashboard_page(self):
        """Admin version of the dashboard – adds serial + type + Fetch button."""
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        card_style = f"""
            QFrame {{
                background-color: {BACKGROUND_LIGHT};
                border-radius: 10px;
                border: none;
                padding: 8px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            }}
            QLabel {{
                font-size: 12px;
                color: {TEXT_DARK};
                font-family: 'Arial';
                padding: 2px;
            }}
        """

        responsive_card_style = f"""
            QFrame {{
                background-color: {BACKGROUND_LIGHT};
                border-radius: 10px;
                border: none;
                padding: 8px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            }}
            QLabel {{
                font-size: calc(12px + 0.02 * 100vw);
                color: {TEXT_DARK};
                font-family: 'Arial';
                padding: 2px;
            }}
        """

        # ---------- Admin Controls ----------
        admin_frame = QFrame()
        admin_frame.setStyleSheet(responsive_card_style)
        admin_layout = QFormLayout(admin_frame)
        admin_layout.setLabelAlignment(Qt.AlignRight)
        admin_layout.setFormAlignment(Qt.AlignHCenter)
        admin_layout.setSpacing(5)

        # Serial number (editable)
        self.serial_input = QLineEdit(self.machine_serial)
        self.serial_input.setStyleSheet(self.input_style())
        admin_layout.addRow("Serial No:", self.serial_input)

        # Machine type combo
        self.machine_type_combo = QComboBox()
        self.machine_type_combo.addItems(["CPAP", "BIPAP"])
        self.machine_type_combo.setCurrentText("BIPAP")
        self.machine_type_combo.currentTextChanged.connect(self.on_type_change)
        self.machine_type_combo.setStyleSheet(f"""
            QComboBox {{
                border: 1px solid #AAAAAA;
                border-radius: 6px;
                padding: 8px;
                background: {BACKGROUND_LIGHT};
                color: {TEXT_DARK};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: darkgray;
                border-left-style: solid; 
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }}
        """)
        admin_layout.addRow("Machine Type:", self.machine_type_combo)

        # Fetch button
        fetch_btn = QPushButton("Fetch Settings from Cloud")
        fetch_btn.setStyleSheet(f"""
            QPushButton {{
                background: {PRIMARY_COLOR};
                color: {BACKGROUND_LIGHT}; 
                border-radius: 6px; 
                font-weight: bold; 
                padding: 8px 15px;
                font-size: 14px;
                border: none;
            }}
            QPushButton:hover {{
                background: {ACCENT_COLOR};
            }}
        """)
        fetch_btn.clicked.connect(self.fetch_settings)
        admin_layout.addRow(fetch_btn)
       
        admin_title = QLabel("Admin Controls")
        admin_title.setStyleSheet(
            f"font-size: calc(16px + 0.02 * 100vw); "
            f"font-weight: bold; color: {ACCENT_COLOR}; margin-bottom: 8px; padding: 2px;"
        )
        # ---------- Usage Stats ----------
        stats_frame = QFrame()
        stats_frame.setStyleSheet(card_style)
        stats_layout = QFormLayout(stats_frame)
        stats_layout.setLabelAlignment(Qt.AlignRight)
        stats_layout.setFormAlignment(Qt.AlignHCenter)
        stats_layout.setSpacing(5)
        self.therapy_usage_label = QLabel("0 hours")
        self.machine_up_time_label = QLabel("0 hours")
        stats_layout.addRow("Therapy Usage:", self.therapy_usage_label)
        stats_layout.addRow("Machine Up Time:", self.machine_up_time_label)
        stats_title = QLabel("Usage Stats")
        stats_title.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {ACCENT_COLOR}; margin-bottom: 8px; padding: 2px;"
        )
        # ---------- Alerts ----------
        alerts_frame = QFrame()
        alerts_frame.setStyleSheet(responsive_card_style)
        alerts_layout = QVBoxLayout(alerts_frame)
        alerts_layout.setSpacing(5)
        self.alert_labels = {}
        for setting in ["IMODE", "Leak Alert", "Sleep Mode", "Mask Type",
                        "Ramp Time", "Humidifier"]:
            lbl = QLabel(f"{setting}: OFF")
            alerts_layout.addWidget(lbl)
            self.alert_labels[setting] = lbl
        alerts_title = QLabel("Alerts & Settings")
        alerts_title.setStyleSheet(
            f"font-size: calc(16px + 0.02 * 100vw); "
            f"font-weight: bold; color: {ACCENT_COLOR}; margin-bottom: 8px; padding: 2px;"
        )
        # ---------- Report ----------
        report_frame = QFrame()
        report_frame.setStyleSheet(card_style)
        report_layout = QVBoxLayout(report_frame)
        report_layout.setSpacing(5)
        calendar = QCalendarWidget()
        calendar.setGridVisible(True)
        calendar.setStyleSheet(f"""
            QCalendarWidget QWidget {{ alternate-background-color: {BACKGROUND_ALT}; }}
            QCalendarWidget QToolButton {{ color: {ACCENT_COLOR}; font-size: 14px; }}
            QCalendarWidget QAbstractItemView {{ selection-background-color: {PRIMARY_COLOR}; }}
        """)
        table = QTableWidget(5, 5)
        table.setHorizontalHeaderLabels(["Date", "Usage", "AHI", "Leaks", "Pressure"])
        table.setStyleSheet(f"""
            QTableWidget {{ 
                border: 1px solid #DDDDDD; 
                selection-background-color: #E6F0FF; 
                gridline-color: #EEEEEE; 
            }}
            QHeaderView::section {{ 
                background-color: {BACKGROUND_ALT}; 
                color: {TEXT_DARK}; 
                padding: 4px; 
                border: 1px solid #DDDDDD; 
                font-weight: bold;
            }}
        """)
        for i in range(5):
            for j in range(5):
                table.setItem(i, j, QTableWidgetItem(f"Data {i+1}-{j+1}"))
        pdf_btn = QPushButton("Export PDF")
        pdf_btn.setStyleSheet(f"""
            QPushButton {{
                background: {SUCCESS_COLOR};
                color: {BACKGROUND_LIGHT}; 
                border-radius: 6px; 
                font-weight: bold; 
                padding: 8px 15px;
                font-size: 14px;
                border: none;
            }}
            QPushButton:hover {{
                background: #27AE60;
            }}
        """)
        pdf_btn.clicked.connect(self.export_pdf)
        csv_btn = QPushButton("Export CSV")
        csv_btn.setStyleSheet(f"""
            QPushButton {{
                background: {SUCCESS_COLOR};
                color: {BACKGROUND_LIGHT}; 
                border-radius: 6px; 
                font-weight: bold; 
                padding: 8px 15px;
                font-size: 14px;
                border: none;
            }}
            QPushButton:hover {{
                background: #27AE60;
            }}
        """)
        csv_btn.clicked.connect(self.export_csv)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(pdf_btn)
        btn_layout.addWidget(csv_btn)
        report_layout.addWidget(calendar)
        report_layout.addWidget(table)
        report_layout.addLayout(btn_layout)
        report_title = QLabel("Report")
        report_title.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {TEXT_DARK}; margin-bottom: 8px; padding: 2px;"
        )
        # ---------- Grid ----------
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.addWidget(admin_title, 0, 0)
        grid.addWidget(admin_frame, 1, 0, 2, 1)
        grid.addWidget(stats_title, 0, 1)
        grid.addWidget(stats_frame, 1, 1, 2, 1)
        grid.addWidget(alerts_title, 0, 2)
        grid.addWidget(alerts_frame, 1, 2, 2, 1)
        grid.addWidget(report_title, 3, 0)
        grid.addWidget(report_frame, 4, 0, 1, 3)

        grid.setRowStretch(1, 1)
        grid.setRowStretch(4, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        main_layout.addLayout(grid)
        # Wrap in scroll area (same as user dashboard)
        scroll = QScrollArea()
        scroll.setWidget(page)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        return scroll
    
    # Helper: when the admin changes the machine type we just store it
    
    def on_type_change(self, text: str):
        self.machine_type = text  
    # fetch_settings – request data from the device via AWS
    
    def fetch_settings(self):
        """Ask the device (via AWS) for its current CSV line."""
        serial = self.serial_input.text().strip()
        if not serial:
            QMessageBox.warning(self, "Input error", "Please enter a Serial No.")
            return
        
        if self.machine_type_combo is None:
           
            machine_type = "BIPAP"  
            self.machine_type = machine_type
            QMessageBox.information(self, "Fallback", f"Combo not ready – using default '{machine_type}' for testing.")
        else:
            machine_type = self.machine_type_combo.currentText()
            self.machine_type = machine_type

        # FOR TESTING: Mock sample data (set if True: to enable; False to use real AWS)
        if True:  
            csv_line = self._generate_sample_csv(machine_type, serial)
            self.apply_cloud_csv(csv_line, serial, machine_type)
            return

        request = {
            "request_settings": 1,
            "serial_no": serial,
            "machine_type": machine_type
        }
        self.aws_send_queue.put(json.dumps(request))

        # Wait up to 10 s for the answer
        start = time.time()
        while time.time() - start < 10:
            try:
                payload = self.aws_receive_queue.get_nowait()
                data = json.loads(payload) if isinstance(payload, str) else payload
                if data.get("serial_no") == serial and data.get("machine_type") == machine_type:
                    csv_line = data.get("device_data", "")
                    self.apply_cloud_csv(csv_line, serial, machine_type)
                    return
            except queue.Empty:
                time.sleep(0.1)

        QMessageBox.warning(self, "Timeout", "No response from the device within 10 s.")

    def _generate_sample_csv(self, machine_type: str, serial: str) -> str:
        """Generate a sample CSV line for testing (simulates device response)."""
        if machine_type == "CPAP":  
            
            parts = [
                "G", "8.0",                    
                "H", "4.0", "0", "20.0",       
                "I", "5", "1", "1", "1", "0", "1", "1",  
                "serial", "0", "0", "0", "0", "0"   
            ]
            return "*" + ",".join(parts) + "#"
        elif machine_type == "BIPAP":
            
            parts = [
                
                "A", "4.0", "1",
                "B", "6", "4", "4", "2", "30", "1", "50", "1",
                "C", "6", "4", "4", "10", "10", "20", "1", "200", "1",
                "D", "6", "4", "4", "10", "10", "20", "3", "200", "1",
                "E", "20", "10", "5", "10", "10", "20", "1", "200", "1", "170", "500",
                "F", "5", "1", "1", "1", "0", "1", "1", serial,
                "0", "0", "0"
            ]
            return "*" + ",".join(parts) + "#"
        else:
            return "*SAMPLE,DATA,#"

    def export_pdf(self):
      
        QMessageBox.information(self, "Export", "PDF export not implemented yet.")

    def export_csv(self):
 
        QMessageBox.information(self, "Export", "CSV export not implemented yet.")

    def input_style(self):
        # --- NEW STYLES (Inherited from Login for consistency) ---
        return f"""
        QLineEdit {{
            border: 2px solid rgba(0, 163, 152, 0.5);
            border-radius: 12px;
            padding: 10px;
            background: {BACKGROUND_LIGHT}; 
            font-size: 14px;
            color: {TEXT_DARK};
        }}
        QLineEdit:focus {{ 
            border: 2px solid {PRIMARY_COLOR}; 
        }}
        """
        # --- END NEW STYLES ---

    def do_logout(self):
        if self.login_window:
            self.login_window.show()
        self.close()

    def create_mode_page(self, mode_name, fields, options_mode=False):
        page = QFrame()
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel(f"{mode_name} Mode Settings")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {PRIMARY_COLOR};")
        layout.addWidget(title)

        # Form
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(20)
        form.setLabelAlignment(Qt.AlignRight)

        self.value_labels[mode_name] = {}
        for title, default in fields.items():
            label = QLabel()
            unit_map = {
                "IPAP": "CmH2O", "EPAP": "CmH2O", "Start EPAP": "CmH2O",
                "Rise Time": " mSec", "Ti.Min": "Sec", "Ti.Max": "Sec",
                "Ti (Insp. Time)": "Sec", "Height": "cm", "Tidal Volume": "ml",
                "Set Pressure": "CmH2O" if mode_name == "CPAP" else "",
                "Sensitivity": "", "Min IPAP": "CmH2O", "Max IPAP": "CmH2O",
                "Min Pressure": "CmH2O", "Max Pressure": "CmH2O", "Backup Rate": "/min"
            }
            unit = unit_map.get(title, "")
            if isinstance(default, float):
                label.setText(f"{default:.2f} {unit}".strip())
            else:
                label.setText(f"{default} {unit}".strip())
            label.setStyleSheet(f"font-size: 14px; color: {TEXT_DARK}; padding: 5px; background: {BACKGROUND_LIGHT}; border-radius: 4px;")
            self.value_labels[mode_name][title] = label
            form.addRow(title + ":", label)

        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save Settings")
        save_btn.setStyleSheet(self.button_style())
        save_btn.clicked.connect(lambda: self.save_settings(mode_name, fields))
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: {DANGER_COLOR};
                color: white; 
                border-radius: 6px; 
                font-weight: bold; 
                padding: 12px;
                font-size: 15px;
                border: none;
            }}
            QPushButton:hover {{
                background: #C82333;
            }}
        """)
        reset_btn.clicked.connect(lambda: self.reset_mode(mode_name))
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(reset_btn)
        form.addRow(btn_layout)

        layout.addLayout(form)
        layout.addStretch()
        page.setLayout(layout)
        return page

    def create_page(self, title_text):
        page = QFrame()
        layout = QVBoxLayout()
        label = QLabel(title_text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(f"font-size: 20px; color: {TEXT_DARK};")
        layout.addWidget(label)
        layout.addStretch()
        page.setLayout(layout)
        return page

    def create_dashboard_page(self):
        page = QFrame()
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)

        # Patient Info
        info_frame = QFrame()
        info_frame.setStyleSheet(f"""
            QFrame {{
                background: {BACKGROUND_LIGHT};
                border-radius: 0px;
                border: 1px solid {ACCENT_COLOR};
                padding: 15px;
            }}
        """)
        info_layout = QFormLayout(info_frame)
        info_layout.setLabelAlignment(Qt.AlignRight)
        self.patient_name_label = QLabel(self.user_name)
        self.serial_label = QLabel(self.machine_serial)
        info_layout.addRow("Patient Name:", self.patient_name_label)
        info_layout.addRow("Machine Serial:", self.serial_label)

        # Stats Cards
        stats_layout = QGridLayout()
        cards = [
            ("Therapy Usage", "0 hours", 0, 0),
            ("Machine Up Time", "0 hours", 0, 1),
            ("AHI", "0 events/hr", 1, 0),
            ("Leak Rate", "0 L/min", 1, 1)
        ]
        self.stat_labels = {}
        for text, value, row, col in cards:
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {BACKGROUND_LIGHT};
                    border-radius: 0px;
                    border: 1px solid {ACCENT_COLOR};
                    padding: 10px;
                }}
                QLabel {{
                    color: {TEXT_DARK};
                }}
            """)
            card_layout = QVBoxLayout(card)
            title_label = QLabel(text)
            title_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {TEXT_DARK};")
            value_label = QLabel(value)
            value_label.setStyleSheet(f"font-size: 18px; color: {PRIMARY_COLOR};")
            card_layout.addWidget(title_label)
            card_layout.addWidget(value_label)
            self.stat_labels[text] = value_label
            stats_layout.addWidget(card, row, col)

        # Alerts
        alerts_frame = QFrame()
        alerts_frame.setStyleSheet(f"""
            QFrame {{
                background: {BACKGROUND_LIGHT};
                border-radius: 0px;
                border: 1px solid {ACCENT_COLOR};
                padding: 15px;
            }}
        """)
        alerts_layout = QVBoxLayout(alerts_frame)
        alerts_title = QLabel("Alerts")
        alerts_title.setStyleSheet(f"font-weight: bold; font-size: 16px; color: {PRIMARY_COLOR};")
        alerts_layout.addWidget(alerts_title)
        self.alert_list = QLabel("No alerts active.")
        self.alert_list.setStyleSheet(f"color: {SUCCESS_COLOR};")
        alerts_layout.addWidget(self.alert_list)

        layout.addWidget(info_frame)
        layout.addLayout(stats_layout)
        layout.addWidget(alerts_frame)
        layout.addStretch()
        page.setLayout(layout)
        return page

    def update_stats(self):
        elapsed = time.time() - self.start_time
        hours = elapsed / 3600
        self.stat_labels["Therapy Usage"].setText(f"{hours:.1f} hours")
        self.stat_labels["Machine Up Time"].setText(f"{hours:.1f} hours")

    def set_mode(self, index, mode_name):
        self.stack.setCurrentIndex(index)
        self.current_mode_label.setText(f"Current Mode: {mode_name}")
        for btn in self.sidebar_buttons:
            btn.setChecked(btn.text() == mode_name)

    def save_settings(self, mode_name, fields):
        all_settings = load_all_settings()
        mode_data = {}
        for title, widget in self.value_labels[mode_name].items():
            text = widget.text().split()[0]  # Extract value before unit
            try:
                if title in ["IPAP", "EPAP", "Start EPAP", "Rise Time", "Ti.Min", "Ti.Max", "Sensitivity", "Min IPAP", "Max IPAP", "Min Pressure", "Max Pressure", "Set Pressure"]:
                    val = float(text)
                else:
                    val = int(text)
                mode_data[title] = val
            except ValueError:
                QMessageBox.warning(self, "Error", f"Invalid value for {title}")
                return
        all_settings[mode_name] = mode_data

        # Update settings if mode_name == "Settings"
        if mode_name == "Settings":
            self.settings = mode_data
            self.update_alerts()

        # Save to file
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(all_settings, f, indent=4)
            # Generate CSV and send to AWS
            self.generate_and_send_csv(mode_name, mode_data)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save: {e}")

    def update_alerts(self):
        alerts = []
        for key, val in self.settings.items():
            if val == "ON" or val > 0:
                alerts.append(f"{key}: Active")
        self.alert_list.setText("\n".join(alerts) if alerts else "No alerts active.")

    def generate_and_send_csv(self, mode_name, mode_data):
        all_settings = load_all_settings()
        mask_map = {"Nasal": "1", "Pillow": "2", "FullFace": "3"}
        gender_map = {"Male": "1", "Female": "2"}
        settings_vals = all_settings.get("Settings", self.default_values["Settings"])
        mask_num = mask_map.get(settings_vals.get("Mask Type", "Nasal"), "1")
        gender_num = gender_map.get(settings_vals.get("Gender", "Male"), "1")

        now = datetime.now()
        date = now.strftime("%d%m%y")
        time_ = now.strftime("%H%M")
        parts = [f"S", date, time_]

        # A - CPAP Mode
        cpap_vals = all_settings.get("CPAP", self.default_values.get("CPAP", {}))
        parts += ["A", str(cpap_vals.get("Set Pressure", 4.0)), mask_num]

        # B - S Mode
        s_vals = all_settings.get("S", self.default_values.get("S", {}))
        b_fields = ["IPAP", "EPAP", "Start EPAP", "Ti.Min", "Ti.Max", "Sensitivity", "Rise Time"]
        parts.append("B")
        for f in b_fields: 
            v = s_vals.get(f, 0)
            if f in ("Ti.Min", "Ti.Max"):
                v = int(v * 10)
            parts.append(str(v))
        parts.append(mask_num)

        # C - T Mode
        t_vals = all_settings.get("T", self.default_values.get("T", {}))
        c_fields = ["IPAP", "EPAP", "Start EPAP", "Respiratory Rate", "Ti.Min", "Ti.Max", "Sensitivity", "Rise Time"]
        parts.append("C")
        for f in c_fields: 
            v = t_vals.get(f, 0)
            if f in ("Ti.Min", "Ti.Max"):
                v = int(v * 10)
            parts.append(str(v))
        parts.append(mask_num)

        # D - ST Mode
        st_vals = all_settings.get("ST", self.default_values.get("ST", {}))
        d_fields = ["IPAP", "EPAP", "Start EPAP", "Backup Rate", "Ti.Min", "Ti.Max", "Sensitivity", "Rise Time"]
        parts.append("D")
        for f in d_fields: 
            v = st_vals.get(f, 0)
            if f in ("Ti.Min", "Ti.Max"):
                v = int(v * 10)
            parts.append(str(v))
        parts.append(mask_num)

        # E - VAPS Mode
        vaps_vals = all_settings.get("VAPS", self.default_values.get("VAPS", {}))
        e_fields = ["Max IPAP", "Min IPAP", "EPAP", "Respiratory Rate", "Ti.Min", "Ti.Max", "Sensitivity", "Rise Time"]
        parts.append("E")
        for f in e_fields:
            v = vaps_vals.get(f, 0)
            if f in ("Ti.Min", "Ti.Max"):
                v = int(v * 10)
            parts.append(str(v))
        parts.append(mask_num)
        parts.append(str(vaps_vals.get("Height", 170)))
        parts.append(str(vaps_vals.get("Tidal Volume", 500)))

        # F - Settings
        ramp = settings_vals.get("Ramp Time", 5)
        hum = settings_vals.get("Humidifier", 1)
        tube = mask_num
        imode_num = 1 if settings_vals.get("IMODE", "OFF").upper() == "ON" else 0
        leak_num = 1 if settings_vals.get("Leak Alert", "OFF").upper() == "ON" else 0
        sleep_num = 1 if settings_vals.get("Sleep Mode", "OFF").upper() == "ON" else 0
        serial = self.machine_serial or ""
        parts += ["F", str(ramp), str(hum), tube, str(imode_num), str(leak_num), gender_num, str(sleep_num), serial]

        csv_line = "*" + ",".join(parts) + "#"

        # 4. Send to AWS
        payload = {
            "device_status": 1,
            "device_data": csv_line
        }
        self.aws_send_queue.put(json.dumps(payload))

        # 5. UI feedback
        changed = {k: mode_data[k] for k in mode_data
                   if all_settings.get(mode_name, {}).get(k) != mode_data[k]}
        changed_list = ", ".join(changed.keys()) if changed else "None"

        preview = csv_line[:200] + "..." if len(csv_line) > 200 else csv_line

        QMessageBox.information(
            self,
            "Settings Saved",
            f"Mode: {mode_name}\n"
            f"Changed fields: {changed_list}\n\n"
            f"Sent CSV line ({self.machine_type} format) to the cloud:\n{preview}"
        )

    def button_style(self):
        # --- NEW STYLES (Solid professional button) ---
        return f"""
        QPushButton {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {PRIMARY_COLOR}, stop:1 {ACCENT_COLOR});
            color: white; 
            border-radius: 18px; 
            font-weight: bold; 
            padding: 12px;
            font-size: 14px;
            border: none;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {ACCENT_COLOR}, stop:1 {PRIMARY_COLOR});
        }}
        """
     

# Run
if __name__ == "__main__":
    print(f"Current working directory: {os.getcwd()}")
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    app.setApplicationName("BIPAP Dashboard")
    
    # Global Style (Optional, but adds a global font/clean look)
    app.setStyleSheet(f"""
        * {{
            font-family: 'Segoe UI', 'Arial';
            color: {TEXT_DARK};
        }}
        QPushButton {{
            font-family: 'Segoe UI', 'Arial';
            transition: all 0.2s;
        }}
        QMessageBox QPushButton {{
            min-width: 80px;
        }}
    """)

    # Main window initialization
    login_window = LoginWindow()
    login_window.show()
    sys.exit(app.exec_())