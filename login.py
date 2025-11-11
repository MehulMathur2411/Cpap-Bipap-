
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFrame, QStackedWidget,
    QLabel, QLineEdit, QPushButton, QMessageBox
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint
from PyQt5.QtGui import QPixmap, QPainter
from core.user_manager import validate_login, register_user

import os

class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BIPAP Dashboard")
        self.setFixedSize(900, 600)
        self._setup_ui()
        self._setup_animations()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Left: Background
        self.left = QFrame()
        self.left.setStyleSheet("background: rgba(0,0,0,0.2);")

        # Right: Form
        self.right = QFrame()
        self.right.setStyleSheet("background: rgba(255,255,255,0.8); border-radius: 0px;")
        right_layout = QVBoxLayout(self.right)
        right_layout.setContentsMargins(40, 40, 40, 40)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._login_page())
        self.stack.addWidget(self._register_page())
        right_layout.addWidget(self.stack)

        main_layout.addWidget(self.left, 1)
        main_layout.addWidget(self.right, 1)

    def _login_page(self):
        page = QFrame()
        layout = QVBoxLayout(page)
        container = QFrame()
        container.setStyleSheet("background: rgba(255,255,255,0.7); border: 1px solid #3498db; border-radius: 0px; padding: 20px;")
        form = QVBoxLayout(container)

        form.addWidget(QLabel("<h1 style='color:#2980b9;'>BIPAP Dashboard</h1><h2>DeckMount Electronics Ltd.</h2>").setAlignment(Qt.AlignCenter))

        self.email_in = QLineEdit(); self.email_in.setPlaceholderText("Email ID"); self.email_in.setStyleSheet(self._input_style())
        self.pass_in = QLineEdit(); self.pass_in.setPlaceholderText("Password"); self.pass_in.setEchoMode(QLineEdit.Password); self.pass_in.setStyleSheet(self._input_style())

        login_btn = QPushButton("Login"); login_btn.setStyleSheet(self._button_style()); login_btn.clicked.connect(self._do_login)
        reg_link = QPushButton("New User? Register Here"); reg_link.setStyleSheet("background:none; color:#2980b9; border:none;"); reg_link.clicked.connect(lambda: self.stack.setCurrentIndex(1))

        for w in [self.email_in, self.pass_in, login_btn]: form.addWidget(w)
        form.addWidget(reg_link, alignment=Qt.AlignCenter)
        layout.addWidget(container)
        return page

    def _register_page(self):
        page = QFrame()
        layout = QVBoxLayout(page)
        container = QFrame()
        container.setStyleSheet("background: rgba(255,255,255,0.8); border: 1px solid #3498db; padding: 20px;")
        form = QVBoxLayout(container)

        inputs = {}
        fields = ["Name", "Contact", "Address", "Password", "Email", "Serial No"]
        for field in fields:
            inp = QLineEdit(); inp.setStyleSheet(self._input_style())
            form.addWidget(QLabel(field + ":")); form.addWidget(inp)
            inputs[field.lower().replace(" ", "_")] = inp

        reg_btn = QPushButton("Register"); reg_btn.setStyleSheet(self._button_style()); reg_btn.clicked.connect(lambda: self._do_register(inputs))
        back_btn = QPushButton("Back to Login"); back_btn.setStyleSheet("background:none; color:#2980b9; border:none;"); back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))

        form.addWidget(reg_btn); form.addWidget(back_btn)
        layout.addWidget(container, alignment=Qt.AlignCenter)
        return page

    def _do_login(self):
        email, pwd = self.email_in.text().strip(), self.pass_in.text().strip()
        success, result = validate_login(email, pwd)
        if success:
            self.hide()
            #DashboardWindow(user_data=result, login_window=self).showMaximized()
        else:
            QMessageBox.warning(self, "Error", result)

    def _do_register(self, inputs):
        data = {k: v.text().strip() for k, v in inputs.items()}
        if not all(data.values()):
            QMessageBox.warning(self, "Error", "All fields required!")
            return
        #dialog = OTPDialog(self)
        #if dialog.exec_() == dialog.Accepted:
            success, msg = register_user(data["email"], {
                "name": data["name"], "contact": data["contact"], "address": data["address"],
                "password": data["password"], "serial_no": data["serial_no"]
            })
            QMessageBox.information(self, "Result", msg)
            if success:
                self.stack.setCurrentIndex(0)

    def _input_style(self):
        return "border: 2px solid #3498db; border-radius: 12px; padding: 10px; background: rgba(255,255,255,0.8);"

    def _button_style(self):
        return "background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #5dade2, stop:1 #2980b9); color: white; border-radius: 18px; padding: 12px; font-weight: bold;"

    def _setup_animations(self):
        # Fade + Slide (same as original)
        pass

    def paintEvent(self, event):
        painter = QPainter(self)
        bg = QPixmap("assets/sign in background.jpg").scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        painter.drawPixmap((self.width() - bg.width()) // 2, (self.height() - bg.height()) // 2, bg)