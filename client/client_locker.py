import sys
import os
import time
import json
import subprocess
import platform
import threading
import requests
import websocket

from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QFrame,
    QHBoxLayout, QScrollArea, QGridLayout, QLineEdit, QGraphicsDropShadowEffect,
    QSizePolicy
)
from PyQt6.QtGui import QFont, QColor, QPixmap, QGuiApplication

# Signals for UI thread communication
class SyncSignals(QObject):
    status_updated = pyqtSignal(dict)
    bar_order_updated = pyqtSignal(dict)

# Low-level Windows hook using ctypes
IS_WINDOWS = platform.system() == 'Windows'

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    WH_KEYBOARD_LL = 13
    WM_KEYDOWN = 0x0100
    WM_SYSKEYDOWN = 0x0104

    VK_TAB = 0x09
    VK_ESCAPE = 0x1B
    VK_LWIN = 0x5B
    VK_RWIN = 0x5C
    VK_F4 = 0x73

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
        ]

    HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT))

    hook_id = None
    is_hook_enabled = False

    def low_level_keyboard_proc(nCode, wParam, lParam):
        global is_hook_enabled
        if nCode >= 0 and is_hook_enabled:
            kb = lParam.contents
            vk = kb.vkCode
            flags = kb.flags
            alt_down = (flags & 0x20) != 0

            # Block Alt+Tab, Win Keys, Alt+F4, Ctrl+Esc
            if (alt_down and vk == VK_TAB) or \
               (vk in (VK_LWIN, VK_RWIN)) or \
               (alt_down and vk == VK_F4) or \
               (vk == VK_ESCAPE and (flags & 0x01)):
                return 1 # Block key event

        return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)

    pointer_proc = HOOKPROC(low_level_keyboard_proc)

    def install_keyboard_hook():
        global hook_id, is_hook_enabled
        is_hook_enabled = True
        if not hook_id:
            hook_id = user32.SetWindowsHookExA(WH_KEYBOARD_LL, pointer_proc, kernel32.GetModuleHandleW(None), 0)

    def uninstall_keyboard_hook():
        global hook_id, is_hook_enabled
        is_hook_enabled = False
        if hook_id:
            user32.UnhookWindowsHookEx(hook_id)
            hook_id = None
else:
    def install_keyboard_hook():
        print("[Hook Simulator] Windows keyboard hook enabled (Simulated on non-Windows)")

    def uninstall_keyboard_hook():
        print("[Hook Simulator] Windows keyboard hook disabled")


class LockScreenWindow(QWidget):
    """STATION LOCKED — Fullscreen qulf oynasi.

    Windows'da ishonchli fullscreen yechim:
      - FramelessWindowHint + WindowStaysOnTopHint + Window
      - showFullScreen() emas, manual setGeometry(screen_geo) + show()
        bu taskbarsiz butun ekranni ishonchli qoplaydi.
    """

    def __init__(self, pc_name="PC-01"):
        super().__init__()
        self.pc_name = pc_name
        self._force_fullscreen_enabled = False
        self._showing = False  # rekursiyadan himoya

        # ----------------------------------------------------------------
        # WINDOW FLAGS — __init__ ichida, widget yaratilishidan darhol
        # Tool flag ishlatilmaydi — Windows'da showFullScreen() bilan
        # mos kelmaydi va oyna kichik qoladi.
        # ----------------------------------------------------------------
        flags = (
            Qt.WindowType.FramelessWindowHint |   # Sarlavha paneli yo'q
            Qt.WindowType.WindowStaysOnTopHint |  # Har doim eng tepada
            Qt.WindowType.Window                  # Oddiy top-level oyna
        )
        if IS_WINDOWS:
            # Taskbar'da Alt+Tab ro'yxatidan yashirish
            flags |= Qt.WindowType.WindowDoesNotAcceptFocus
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self.init_ui()

    def init_ui(self):
        # ----------------------------------------------------------------
        # FULLSCREEN BACKGROUND — butun ekranni qoplaydigan to'q fon
        # ----------------------------------------------------------------
        self.setStyleSheet("background-color: #060911;")

        # ----------------------------------------------------------------
        # ROOT LAYOUT — margin 0, spacing 0, fon 100% ekranni egallaydi
        # ----------------------------------------------------------------
        # Expanding sizePolicy — layout butun oyna maydonini egallaydi
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ----------------------------------------------------------------
        # LOCK CARD — faqat kartaning o'ziga fixed width, fon emas
        # ----------------------------------------------------------------
        self.lock_card = QFrame()
        self.lock_card.setFixedWidth(500)
        self.lock_card.setStyleSheet("""
            QFrame {
                background: rgba(12, 18, 32, 0.94);
                border: 2px solid rgba(0, 240, 255, 0.35);
                border-radius: 28px;
            }
        """)

        card_shadow = QGraphicsDropShadowEffect(self.lock_card)
        card_shadow.setBlurRadius(40)
        card_shadow.setColor(QColor(0, 240, 255, 110))
        card_shadow.setOffset(0, 0)
        self.lock_card.setGraphicsEffect(card_shadow)

        card_layout = QVBoxLayout(self.lock_card)
        card_layout.setContentsMargins(40, 36, 40, 36)
        card_layout.setSpacing(14)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Official Clutch Zone Logo
        logo_lbl = QLabel()
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "clutch_logo_full.png")
        if not os.path.exists(logo_path):
            logo_path = os.path.join(os.getcwd(), "client", "assets", "clutch_logo_full.png")

        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            scaled_pixmap = pixmap.scaled(320, 170, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(scaled_pixmap)
        else:
            logo_lbl.setText("CLUTCH ZONE")
            logo_lbl.setFont(QFont("Impact", 36, QFont.Weight.Bold))
            logo_lbl.setStyleSheet("color: #00f0ff; letter-spacing: 4px;")

        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_glow = QGraphicsDropShadowEffect(logo_lbl)
        logo_glow.setBlurRadius(30)
        logo_glow.setColor(QColor(0, 240, 255, 180))
        logo_glow.setOffset(0, 0)
        logo_lbl.setGraphicsEffect(logo_glow)
        card_layout.addWidget(logo_lbl)

        # Status text
        status_lbl = QLabel("STATION LOCKED")
        status_lbl.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        status_lbl.setStyleSheet("color: #ef4444; letter-spacing: 3px;")
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(status_lbl)

        # Title PC Name
        title = QLabel(self.pc_name)
        title.setFont(QFont("Consolas", 34, QFont.Weight.Bold))
        title.setStyleSheet("color: #00f0ff; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        # Instructions
        desc = QLabel("Seansni boshlash uchun administratorga murojaat qiling.")
        desc.setFont(QFont("Segoe UI", 12))
        desc.setStyleSheet("color: #94a3b8;")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(desc)

        layout.addWidget(self.lock_card)
        self._force_fullscreen_enabled = True

    # ----------------------------------------------------------------
    # FORCE FULLSCREEN — hide/show siklida ham ishlaydigan yechim.
    # WindowFlags qayta o'rnatish + primaryScreen geometry + showFullScreen
    # kombinatsiyasi Windows'da taskbar va desktop'ni 100% ishonchli yopadi.
    # _showing guard — showEvent rekursiyasidan himoya qiladi.
    # ----------------------------------------------------------------
    def _apply_fullscreen(self):
        """Ekranni to'liq qoplaydigan asosiy metod."""
        if self._showing:
            return
        self._showing = True
        try:
            flags = (
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Window
            )
            if IS_WINDOWS:
                flags |= Qt.WindowType.WindowDoesNotAcceptFocus
            self.setWindowFlags(flags)
            screen = QGuiApplication.primaryScreen().geometry()
            self.setGeometry(screen)
            self.showFullScreen()
            self.raise_()
            self.activateWindow()
        finally:
            self._showing = False

    def show_locker(self):
        """Qulf oynasini majburan to'liq ekranda ko'rsatadi.
        lock_pc() / WebSocket tomonidan chaqiriladi."""
        self._apply_fullscreen()

    def showEvent(self, event):
        """Oyna har safar ko'rsatilganda (show/hide sikl) fullscreen
        holatni avtomatik tiklaydi. _showing guard rekursiyadan himoya qiladi.
        WindowFlags qayta o'rnatiladi va primaryScreen geometry majburan qo'llanadi."""
        super().showEvent(event)
        if self._showing:
            return
        self._showing = True
        try:
            flags = (
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Window
            )
            if IS_WINDOWS:
                flags |= Qt.WindowType.WindowDoesNotAcceptFocus
            self.setWindowFlags(flags)
            screen = QGuiApplication.primaryScreen().geometry()
            self.setGeometry(screen)
            self.showFullScreen()
            self.raise_()
            self.activateWindow()
        finally:
            self._showing = False

    # ----------------------------------------------------------------
    # MINIMIZE BLOKIROVKA — singleShot orqali xavfsiz
    # ----------------------------------------------------------------
    def changeEvent(self, event):
        """Minimize yoki boshqa holat o'zgarishida ekranni qayta qoplaydi."""
        super().changeEvent(event)
        if (
            self._force_fullscreen_enabled
            and not self._showing
            and self.isVisible()
            and event.type() == QEvent.Type.WindowStateChange
        ):
            if self.windowState() & Qt.WindowState.WindowMinimized:
                QTimer.singleShot(100, self._apply_fullscreen)

    def closeEvent(self, event):
        """Qulf oynasini yopishga yo'l bermaymiz."""
        event.ignore()

    def keyPressEvent(self, event):
        """Barcha klaviatura kirishlarini bloklash."""
        event.accept()


class TimerOverlayWidget(QWidget):
    def __init__(self, pc_name="PC-01", on_bar_click=None):
        super().__init__()
        self.pc_name = pc_name
        self.on_bar_click = on_bar_click
        self.init_ui()

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(350, 75)
        
        # Position top-right corner
        screen_geo = QApplication.primaryScreen().geometry()
        self.move(screen_geo.width() - 370, 20)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame {
                background: rgba(10, 14, 23, 0.92);
                border: 1px solid rgba(0, 240, 255, 0.4);
                border-radius: 16px;
            }
        """)

        cont_layout = QHBoxLayout(self.container)
        cont_layout.setContentsMargins(14, 8, 14, 8)

        timer_box = QVBoxLayout()
        timer_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.timer_label = QLabel("00:00:00")
        self.timer_label.setFont(QFont("Consolas", 18, QFont.Weight.Bold))
        self.timer_label.setStyleSheet("color: #00f0ff;")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        timer_box.addWidget(self.timer_label)

        sub_label = QLabel(f"{self.pc_name} - ACTIVE SESSION")
        sub_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        sub_label.setStyleSheet("color: #10b981; letter-spacing: 1px;")
        sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        timer_box.addWidget(sub_label)

        cont_layout.addLayout(timer_box)

        self.bar_btn = QPushButton("🍸 BAR")
        self.bar_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.bar_btn.setFixedSize(85, 45)
        self.bar_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #a855f7, stop:0.5 #d946ef, stop:1 #ec4899);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.4);
                border-radius: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #c084fc, stop:1 #f472b6);
                border: 1px solid #00f0ff;
                color: #ffffff;
            }
        """)
        if self.on_bar_click:
            self.bar_btn.clicked.connect(self.on_bar_click)
        cont_layout.addWidget(self.bar_btn)

        layout.addWidget(self.container)

    def update_timer(self, seconds):
        if seconds <= 0:
            self.timer_label.setText("00:00:00")
            return
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        self.timer_label.setText(f"{h:02d}:{m:02d}:{s:02d}")


class BackdropOverlayWidget(QWidget):
    def __init__(self, on_click=None):
        super().__init__()
        self.on_click = on_click
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setStyleSheet("background-color: rgba(5, 8, 15, 0.85);")

    def mousePressEvent(self, event):
        if self.on_click:
            self.on_click()
        super().mousePressEvent(event)


class BarMenuWindow(QWidget):
    closed_signal = pyqtSignal()

    def __init__(self, pc_name="PC-01", server_url="http://localhost:8000"):
        super().__init__()
        self.pc_name = pc_name
        self.server_url = server_url
        self.cart = {}
        self.products = []
        self.categories = []
        self.current_category_id = None
        self.init_ui()

    def hideEvent(self, event):
        self.closed_signal.emit()
        super().hideEvent(event)

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setFixedSize(850, 560)

        screen_geo = QApplication.primaryScreen().geometry()
        self.move((screen_geo.width() - 850) // 2, (screen_geo.height() - 560) // 2)

        self.setStyleSheet("""
            QWidget {
                background-color: #090d16;
                color: #e2e8f0;
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #0f172a;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                border-radius: 3px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background: rgba(15, 23, 42, 0.98);
                border: 2px solid rgba(0, 240, 255, 0.4);
                border-radius: 22px;
            }
        """)

        container_shadow = QGraphicsDropShadowEffect(container)
        container_shadow.setBlurRadius(30)
        container_shadow.setColor(QColor(0, 240, 255, 120))
        container_shadow.setOffset(0, 0)
        container.setGraphicsEffect(container_shadow)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(20, 16, 20, 20)

        # Header Bar
        header = QHBoxLayout()
        header_title = QLabel("🍸 CLUTCH ZONE BAR & REFRESHMENTS")
        header_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_title.setStyleSheet("color: #00f0ff; letter-spacing: 1px;")

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(32, 32)
        close_btn.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.2);
                color: #ef4444;
                border: 1px solid rgba(239, 68, 68, 0.4);
                border-radius: 16px;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.4);
                color: #ffffff;
            }
        """)
        close_btn.clicked.connect(self.hide)

        header.addWidget(header_title)
        header.addStretch()
        header.addWidget(close_btn)
        container_layout.addLayout(header)

        # Body Layout (Catalog Left, Cart Right)
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 10, 0, 0)

        # Catalog Section
        catalog_panel = QVBoxLayout()

        # Category buttons container
        self.cat_widget = QWidget()
        self.cat_layout = QHBoxLayout(self.cat_widget)
        self.cat_layout.setContentsMargins(0, 0, 0, 0)
        self.cat_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        catalog_panel.addWidget(self.cat_widget)

        # Products scroll area
        self.product_scroll = QScrollArea()
        self.product_scroll.setWidgetResizable(True)
        self.product_grid_widget = QWidget()
        self.product_grid_layout = QGridLayout(self.product_grid_widget)
        self.product_grid_layout.setSpacing(12)
        self.product_grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.product_scroll.setWidget(self.product_grid_widget)

        catalog_panel.addWidget(self.product_scroll)
        body_layout.addLayout(catalog_panel, stretch=2)

        # Cart Section
        cart_frame = QFrame()
        cart_frame.setFixedWidth(290)
        cart_frame.setStyleSheet("""
            QFrame {
                background: rgba(10, 15, 29, 0.9);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
            }
        """)
        cart_layout = QVBoxLayout(cart_frame)
        cart_layout.setContentsMargins(14, 14, 14, 14)

        cart_title = QLabel("🛒 BUYURTMA SAVATI")
        cart_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        cart_title.setStyleSheet("color: #c084fc;")
        cart_layout.addWidget(cart_title)

        # Cart scroll
        self.cart_scroll = QScrollArea()
        self.cart_scroll.setWidgetResizable(True)
        self.cart_container = QWidget()
        self.cart_items_layout = QVBoxLayout(self.cart_container)
        self.cart_items_layout.setContentsMargins(0, 0, 0, 0)
        self.cart_items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.cart_scroll.setWidget(self.cart_container)
        cart_layout.addWidget(self.cart_scroll)

        # Order Status Banner
        self.status_banner = QLabel("")
        self.status_banner.setWordWrap(True)
        self.status_banner.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.status_banner.setStyleSheet("color: #f59e0b; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px; padding: 6px;")
        self.status_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_banner.hide()
        cart_layout.addWidget(self.status_banner)

        # Total Price
        self.total_label = QLabel("Jami: 0 UZS")
        self.total_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.total_label.setStyleSheet("color: #10b981;")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        cart_layout.addWidget(self.total_label)

        # Submit Button
        self.send_order_btn = QPushButton("🛍️ BUYURTMA YUBORISH")
        self.send_order_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.send_order_btn.setStyleSheet("""
            QPushButton {
                background: linear-gradient(135deg, #00f0ff 0%, #0284c7 100%);
                color: #030712;
                border: none;
                border-radius: 12px;
                padding: 12px;
            }
            QPushButton:hover {
                background: #00f0ff;
            }
        """)
        self.send_order_btn.clicked.connect(self.submit_order)
        cart_layout.addWidget(self.send_order_btn)

        body_layout.addWidget(cart_frame, stretch=1)
        container_layout.addLayout(body_layout)
        main_layout.addWidget(container)

    def load_data(self):
        try:
            r_cat = requests.get(f"{self.server_url}/api/categories/", timeout=4)
            if r_cat.status_code == 200:
                self.categories = r_cat.json()

            r_prod = requests.get(f"{self.server_url}/api/products/", timeout=4)
            if r_prod.status_code == 200:
                self.products = r_prod.json()

            self.render_categories()
            self.render_products()
        except Exception as e:
            print(f"[BarMenu] Error loading products: {e}")

    def render_categories(self):
        for i in reversed(range(self.cat_layout.count())):
            w = self.cat_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        all_btn = QPushButton("Barchasi")
        all_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        all_btn.setStyleSheet("background: rgba(0, 240, 255, 0.2); color: #00f0ff; border: 1px solid #00f0ff; border-radius: 10px; padding: 6px 12px;")
        all_btn.clicked.connect(lambda: self.set_category(None))
        self.cat_layout.addWidget(all_btn)

        for cat in self.categories:
            btn = QPushButton(f"{cat.get('icon', '🍿')} {cat['name']}")
            btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            btn.setStyleSheet("background: rgba(30, 41, 59, 0.6); color: #94a3b8; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 10px; padding: 6px 12px;")
            cid = cat['id']
            btn.clicked.connect(lambda checked, c=cid: self.set_category(c))
            self.cat_layout.addWidget(btn)

    def set_category(self, cat_id):
        self.current_category_id = cat_id
        self.render_products()

    def render_products(self):
        for i in reversed(range(self.product_grid_layout.count())):
            w = self.product_grid_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        filtered = [p for p in self.products if self.current_category_id is None or p.get('category') == self.current_category_id]

        col_count = 2
        for idx, p in enumerate(filtered):
            card = QFrame()
            card.setFixedSize(240, 130)
            card.setStyleSheet("""
                QFrame {
                    background: rgba(18, 27, 46, 0.85);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 14px;
                }
            """)
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(12, 10, 12, 10)

            name_lbl = QLabel(p['name'])
            name_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            name_lbl.setStyleSheet("color: #ffffff;")
            name_lbl.setWordWrap(True)
            c_layout.addWidget(name_lbl)

            price_val = float(p['price'])
            info_lbl = QLabel(f"{price_val:,.0f} UZS | Stock: {p['stock']}")
            info_lbl.setFont(QFont("Consolas", 9))
            info_lbl.setStyleSheet("color: #38bdf8;")
            c_layout.addWidget(info_lbl)

            add_btn = QPushButton("➕ Savatga Qo'shish")
            add_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            add_btn.setEnabled(p['stock'] > 0)
            add_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(16, 185, 129, 0.2);
                    color: #10b981;
                    border: 1px solid rgba(16, 185, 129, 0.4);
                    border-radius: 8px;
                    padding: 5px;
                }
                QPushButton:hover {
                    background: rgba(16, 185, 129, 0.4);
                    color: #ffffff;
                }
                QPushButton:disabled {
                    background: rgba(100, 116, 139, 0.2);
                    color: #64748b;
                    border: none;
                }
            """)
            add_btn.clicked.connect(lambda checked, prod=p: self.add_to_cart(prod))
            c_layout.addWidget(add_btn)

            row = idx // col_count
            col = idx % col_count
            self.product_grid_layout.addWidget(card, row, col)

    def add_to_cart(self, prod):
        pid = prod['id']
        if pid in self.cart:
            if self.cart[pid]['quantity'] < prod['stock']:
                self.cart[pid]['quantity'] += 1
        else:
            self.cart[pid] = {
                'id': pid,
                'name': prod['name'],
                'price': float(prod['price']),
                'quantity': 1
            }
        self.render_cart()

    def render_cart(self):
        for i in reversed(range(self.cart_items_layout.count())):
            w = self.cart_items_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        total_sum = 0
        for pid, item in self.cart.items():
            subtotal = item['price'] * item['quantity']
            total_sum += subtotal

            item_widget = QWidget()
            i_layout = QHBoxLayout(item_widget)
            i_layout.setContentsMargins(0, 4, 0, 4)

            lbl = QLabel(f"{item['name']}\n{subtotal:,.0f} UZS")
            lbl.setFont(QFont("Segoe UI", 9))
            lbl.setStyleSheet("color: #e2e8f0;")
            i_layout.addWidget(lbl, stretch=2)

            btn_minus = QPushButton("-")
            btn_minus.setFixedSize(22, 22)
            btn_minus.setStyleSheet("background: #1e293b; color: #ffffff; border-radius: 4px;")
            btn_minus.clicked.connect(lambda checked, p=pid: self.update_cart_qty(p, -1))
            i_layout.addWidget(btn_minus)

            qty_lbl = QLabel(str(item['quantity']))
            qty_lbl.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            qty_lbl.setStyleSheet("color: #00f0ff;")
            i_layout.addWidget(qty_lbl)

            btn_plus = QPushButton("+")
            btn_plus.setFixedSize(22, 22)
            btn_plus.setStyleSheet("background: #1e293b; color: #ffffff; border-radius: 4px;")
            btn_plus.clicked.connect(lambda checked, p=pid: self.update_cart_qty(p, 1))
            i_layout.addWidget(btn_plus)

            self.cart_items_layout.addWidget(item_widget)

        self.total_label.setText(f"Jami: {total_sum:,.0f} UZS")

    def update_cart_qty(self, pid, change):
        if pid in self.cart:
            self.cart[pid]['quantity'] += change
            if self.cart[pid]['quantity'] <= 0:
                del self.cart[pid]
            self.render_cart()

    def submit_order(self):
        if not self.cart:
            return

        items = [{"product_id": pid, "quantity": item['quantity']} for pid, item in self.cart.items()]
        payload = {
            "pc_name": self.pc_name,
            "items": items
        }

        try:
            res = requests.post(f"{self.server_url}/api/orders/", json=payload, timeout=5)
            if res.status_code == 201:
                self.cart = {}
                self.render_cart()
                self.status_banner.setText("⏳ Buyurtmangiz yuborildi! Admin tasdiqlashini kuting.")
                self.status_banner.setStyleSheet("color: #f59e0b; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px; padding: 6px;")
                self.status_banner.show()
            else:
                err_msg = res.json().get('error', 'Buyurtma berishda xatolik!')
                self.status_banner.setText(f"❌ {err_msg}")
                self.status_banner.setStyleSheet("color: #ef4444; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 6px;")
                self.status_banner.show()
        except Exception as e:
            self.status_banner.setText("❌ Serverga ulanib bo'lmadi!")
            self.status_banner.show()

    def update_order_status(self, order_data):
        status = order_data.get('status')
        if status == 'PENDING':
            self.status_banner.setText(f"⏳ Buyurtma #{order_data.get('id')} kutilmoqda...")
            self.status_banner.setStyleSheet("color: #f59e0b; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px; padding: 6px;")
            self.status_banner.show()
        elif status == 'APPROVED':
            self.status_banner.setText(f"👍 Buyurtma #{order_data.get('id')} tasdiqlandi! Operator yetkazmoqda.")
            self.status_banner.setStyleSheet("color: #00f0ff; background: rgba(0, 240, 255, 0.15); border: 1px solid rgba(0, 240, 255, 0.3); border-radius: 8px; padding: 6px;")
            self.status_banner.show()
        elif status == 'DELIVERED':
            self.status_banner.setText(f"🚚 Buyurtma #{order_data.get('id')} topshirildi! Yoqimli ishtaha.")
            self.status_banner.setStyleSheet("color: #10b981; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 6px;")
            self.status_banner.show()
        elif status == 'CANCELLED':
            self.status_banner.setText(f"❌ Buyurtma #{order_data.get('id')} bekor qilindi.")
            self.status_banner.setStyleSheet("color: #ef4444; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 6px;")
            self.status_banner.show()


class ImageCache(QObject):
    cache = {}
    image_downloaded_signal = pyqtSignal(str, QPixmap)

    def fetch_image(self, url, width, height):
        if not url or url in self.cache:
            return

        def fetch():
            try:
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    pix = QPixmap()
                    pix.loadFromData(r.content)
                    if not pix.isNull():
                        scaled = pix.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                        ImageCache.cache[url] = scaled
                        self.image_downloaded_signal.emit(url, scaled)
            except Exception as e:
                print(f"[ImageCache] Remote fetch error for {url}: {e}")

        threading.Thread(target=fetch, daemon=True).start()

    @classmethod
    def get_cached(cls, path_or_url, width, height):
        if not path_or_url:
            return None
        if path_or_url in cls.cache:
            return cls.cache[path_or_url]

        resolved_path = path_or_url
        if not os.path.exists(resolved_path):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            alt_path = os.path.join(script_dir, path_or_url)
            if os.path.exists(alt_path):
                resolved_path = alt_path
            else:
                rel_name = os.path.basename(path_or_url)
                alt_asset = os.path.join(script_dir, "assets", "games", rel_name)
                if os.path.exists(alt_asset):
                    resolved_path = alt_asset

        if os.path.exists(resolved_path):
            pix = QPixmap(resolved_path)
            if not pix.isNull():
                scaled = pix.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                cls.cache[path_or_url] = scaled
                return scaled
        return None


class GameLauncherWindow(QWidget):
    game_launched_signal = pyqtSignal(dict)

    def __init__(self, pc_name="PC-01", server_url="http://localhost:8000", fallback_games=None, on_bar_click=None):
        super().__init__()
        self.pc_name = pc_name
        self.server_url = server_url
        self.fallback_games = fallback_games or []
        self.on_bar_click = on_bar_click
        self.games = []
        self.current_category = None
        self.search_query = ""
        self.pixmap_labels = {}
        self._force_fullscreen_enabled = False
        self._showing = False

        self.image_downloader = ImageCache()
        self.image_downloader.image_downloaded_signal.connect(self.on_image_downloaded)

        flags = (
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Window
        )
        if IS_WINDOWS:
            flags |= Qt.WindowType.WindowDoesNotAcceptFocus
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        # Expanding sizePolicy — oyna dinamik ravishda monitor rezolyutsiyasiga moslashadi
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.init_ui()

    def init_ui(self):
        # Oyna geometriyasi showEvent / show_launcher orqali boshqariladi,
        # init_ui da setGeometry ishlatilmaydi — kichik oyna muammosidan saqlanish uchun.
        self.setStyleSheet("""
            QWidget {
                background-color: #0a0e17;
                color: #e2e8f0;
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #0f172a;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #00f0ff;
            }
            QLineEdit {
                background: rgba(15, 23, 42, 0.9);
                color: #f8fafc;
                border: 1px solid rgba(0, 240, 255, 0.3);
                border-radius: 12px;
                padding: 8px 16px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #00f0ff;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(36, 28, 36, 28)
        main_layout.setSpacing(20)

        header = QHBoxLayout()

        title_box = QVBoxLayout()
        title_lbl = QLabel("🎮 CLUTCH ZONE")
        title_lbl.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #00f0ff; letter-spacing: 2px;")

        sub_title = QLabel(f"GAME CATALOG LAUNCHER • {self.pc_name}")
        sub_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        sub_title.setStyleSheet("color: #94a3b8; letter-spacing: 1px;")

        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_title)
        header.addLayout(title_box)

        header.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 O'yin nomini qidirish...")
        self.search_input.setFixedWidth(290)
        self.search_input.textChanged.connect(self.on_search_changed)
        header.addWidget(self.search_input)

        self.timer_label = QLabel("00:00:00")
        self.timer_label.setFont(QFont("Consolas", 16, QFont.Weight.Bold))
        self.timer_label.setStyleSheet("color: #10b981; background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 12px; padding: 8px 16px;")
        header.addWidget(self.timer_label)

        bar_btn = QPushButton("🍸 BAR MENU")
        bar_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        bar_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #a855f7, stop:0.5 #d946ef, stop:1 #ec4899);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.4);
                border-radius: 12px;
                padding: 10px 20px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #c084fc, stop:1 #f472b6);
                border: 1px solid #00f0ff;
                color: #ffffff;
            }
        """)
        if self.on_bar_click:
            bar_btn.clicked.connect(self.on_bar_click)
        header.addWidget(bar_btn)

        main_layout.addLayout(header)

        cat_bar = QHBoxLayout()
        cat_bar.setSpacing(12)

        categories = [
            ("ALL", "🌐 Barchasi"),
            ("FPS", "🎯 FPS / Shooter"),
            ("Action", "⚔️ Action / RPG"),
            ("Sports", "⚽ Sports / Racing"),
            ("Strategy", "🧠 Strategy / MOBA")
        ]

        self.cat_buttons = {}
        for cat_code, cat_label in categories:
            btn = QPushButton(cat_label)
            btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            btn.setStyleSheet(self.get_cat_btn_style(cat_code == "ALL"))
            code = cat_code
            btn.clicked.connect(lambda checked, c=code: self.set_category_filter(c))
            cat_bar.addWidget(btn)
            self.cat_buttons[cat_code] = btn

        cat_bar.addStretch()
        main_layout.addLayout(cat_bar)

        self.status_msg = QLabel("O'yin tanlang va 'Ishga tushirish' tugmasini bosing")
        self.status_msg.setFont(QFont("Segoe UI", 10))
        self.status_msg.setStyleSheet("color: #94a3b8; background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 8px; padding: 8px 14px;")
        main_layout.addWidget(self.status_msg)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(24)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.grid_widget)

        main_layout.addWidget(self.scroll_area, stretch=1)

        self._force_fullscreen_enabled = True

    # ----------------------------------------------------------------
    # FORCE FULLSCREEN — hide/show siklida ham ishlaydigan yechim.
    # WindowFlags qayta o'rnatish + primaryScreen geometry + showFullScreen
    # kombinatsiyasi Windows'da taskbar va desktop'ni 100% ishonchli yopadi.
    # _showing guard — showEvent rekursiyasidan himoya qiladi.
    # ----------------------------------------------------------------
    def _apply_fullscreen(self):
        """Ekranni to'liq qoplaydigan asosiy metod."""
        if self._showing:
            return
        self._showing = True
        try:
            flags = (
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Window
            )
            if IS_WINDOWS:
                flags |= Qt.WindowType.WindowDoesNotAcceptFocus
            self.setWindowFlags(flags)
            screen = QGuiApplication.primaryScreen().geometry()
            self.setGeometry(screen)
            self.showFullScreen()
            self.raise_()
            self.activateWindow()
        finally:
            self._showing = False

    def show_launcher(self):
        """Launcher oynasini majburan to'liq ekranda ko'rsatadi.
        unlock_pc() / WebSocket tomonidan chaqiriladi."""
        self._apply_fullscreen()

    def showEvent(self, event):
        """Oyna har safar ko'rsatilganda (show/hide sikl) fullscreen
        holatni avtomatik tiklaydi. _showing guard rekursiyadan himoya qiladi.
        WindowFlags qayta o'rnatiladi va primaryScreen geometry majburan qo'llanadi."""
        super().showEvent(event)
        if self._showing:
            return
        self._showing = True
        try:
            flags = (
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Window
            )
            if IS_WINDOWS:
                flags |= Qt.WindowType.WindowDoesNotAcceptFocus
            self.setWindowFlags(flags)
            screen = QGuiApplication.primaryScreen().geometry()
            self.setGeometry(screen)
            self.showFullScreen()
            self.raise_()
            self.activateWindow()
        finally:
            self._showing = False

    # ----------------------------------------------------------------
    # MINIMIZE BLOKIROVKA — singleShot orqali xavfsiz
    # ----------------------------------------------------------------
    def changeEvent(self, event):
        """Minimize yoki boshqa holat o'zgarishida ekranni qayta qoplaydi."""
        super().changeEvent(event)
        if (
            self._force_fullscreen_enabled
            and not self._showing
            and self.isVisible()
            and event.type() == QEvent.Type.WindowStateChange
        ):
            if self.windowState() & Qt.WindowState.WindowMinimized:
                QTimer.singleShot(100, self._apply_fullscreen)

    def closeEvent(self, event):
        event.ignore()

    def get_cat_btn_style(self, is_active):
        if is_active:
            return """
                QPushButton {
                    background: rgba(0, 240, 255, 0.25);
                    color: #00f0ff;
                    border: 1px solid #00f0ff;
                    border-radius: 12px;
                    padding: 8px 18px;
                }
            """
        else:
            return """
                QPushButton {
                    background: rgba(30, 41, 59, 0.5);
                    color: #94a3b8;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    padding: 8px 18px;
                }
                QPushButton:hover {
                    background: rgba(51, 65, 85, 0.8);
                    color: #e2e8f0;
                }
            """

    def set_category_filter(self, cat_code):
        self.current_category = None if cat_code == "ALL" else cat_code
        for code, btn in self.cat_buttons.items():
            btn.setStyleSheet(self.get_cat_btn_style(code == (cat_code if cat_code else "ALL")))
        self.render_games()

    def on_search_changed(self, text):
        self.search_query = text.strip().lower()
        self.render_games()

    def update_timer(self, seconds):
        if seconds <= 0:
            self.timer_label.setText("00:00:00")
            return
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        self.timer_label.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def load_games(self):
        try:
            res = requests.get(f"{self.server_url}/api/games/", timeout=4)
            if res.status_code == 200:
                self.games = res.json()
            else:
                self.games = self.fallback_games
        except Exception as e:
            print(f"[GameLauncher] Error loading games from server: {e}, using fallback.")
            self.games = self.fallback_games

        self.render_games()

    def on_image_downloaded(self, url, pixmap):
        if url in self.pixmap_labels:
            for lbl in self.pixmap_labels[url]:
                lbl.setPixmap(pixmap)

    def render_games(self):
        for i in reversed(range(self.grid_layout.count())):
            w = self.grid_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        self.pixmap_labels.clear()

        filtered = []
        for g in self.games:
            if self.current_category and g.get('category') != self.current_category:
                continue
            if self.search_query and self.search_query not in g.get('name', '').lower():
                continue
            filtered.append(g)

        col_count = 4
        for c in range(col_count):
            self.grid_layout.setColumnStretch(c, 1)

        for idx, game in enumerate(filtered):
            card = QFrame()
            card.setFixedHeight(290)
            card.setStyleSheet("""
                QFrame {
                    background: rgba(14, 21, 36, 0.92);
                    border: 1.5px solid rgba(0, 240, 255, 0.25);
                    border-radius: 18px;
                }
                QFrame:hover {
                    border: 1.5px solid #00f0ff;
                    background: rgba(20, 32, 56, 0.96);
                }
            """)

            shadow = QGraphicsDropShadowEffect(card)
            shadow.setBlurRadius(20)
            shadow.setColor(QColor(0, 240, 255, 75))
            shadow.setOffset(0, 0)
            card.setGraphicsEffect(shadow)

            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(12, 12, 12, 12)
            c_layout.setSpacing(10)

            cover_lbl = QLabel()
            cover_lbl.setFixedHeight(158) # 16:9 ratio
            cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cover_lbl.setStyleSheet("""
                background: linear-gradient(135deg, #0d1527 0%, #1e293b 100%);
                border-radius: 12px;
            """)

            cover_url = game.get('cover_path', '')
            pix = ImageCache.get_cached(cover_url, 300, 158)
            if pix:
                cover_lbl.setPixmap(pix)
            else:
                fallback_logo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "clutch_logo_full.png")
                if not os.path.exists(fallback_logo):
                    fallback_logo = os.path.join(os.getcwd(), "client", "assets", "clutch_logo_full.png")

                if os.path.exists(fallback_logo):
                    fpix = QPixmap(fallback_logo).scaled(240, 130, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    cover_lbl.setPixmap(fpix)
                else:
                    cover_lbl.setText(f"🎮\n{game.get('name')}")
                    cover_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
                    cover_lbl.setStyleSheet("color: #00f0ff; background: rgba(0, 240, 255, 0.1); border-radius: 12px;")

                if cover_url and (cover_url.startswith("http://") or cover_url.startswith("https://")):
                    if cover_url not in self.pixmap_labels:
                        self.pixmap_labels[cover_url] = []
                    self.pixmap_labels[cover_url].append(cover_lbl)
                    self.image_downloader.fetch_image(cover_url, 300, 158)

            c_layout.addWidget(cover_lbl)

            info_row = QHBoxLayout()
            g_name = QLabel(game.get('name', 'Unknown Game'))
            g_name.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            g_name.setStyleSheet("color: #ffffff;")
            g_name.setWordWrap(True)
            info_row.addWidget(g_name, stretch=1)

            cat_pill = QLabel(game.get('category', 'FPS'))
            cat_pill.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            cat_pill.setStyleSheet("color: #38bdf8; background: rgba(56, 189, 248, 0.15); border-radius: 6px; padding: 3px 8px;")
            info_row.addWidget(cat_pill)

            c_layout.addLayout(info_row)

            play_btn = QPushButton("▶ ISHGA TUSHIRISH")
            play_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            play_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00f0ff, stop:1 #10b981);
                    color: #030712;
                    border: none;
                    border-radius: 10px;
                    padding: 9px;
                    font-weight: bold;
                    letter-spacing: 1px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #00f0ff);
                    color: #ffffff;
                    border: 1px solid #00f0ff;
                }
            """)
            g_obj = game
            play_btn.clicked.connect(lambda checked, g=g_obj: self.launch_game(g))
            c_layout.addWidget(play_btn)

            row = idx // col_count
            col = idx % col_count
            self.grid_layout.addWidget(card, row, col)

    def show_launch_error(self, message="O'yin fayli topilmadi, iltimos admonga murojaat qiling"):
        self.status_msg.setText(f"❌ {message}")
        self.status_msg.setStyleSheet("color: #ef4444; background: rgba(239, 68, 68, 0.18); border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 8px; padding: 8px 14px; font-weight: bold;")

    def show_launch_success(self, game_name):
        self.status_msg.setText(f"🚀 {game_name} ishga tushirildi!")
        self.status_msg.setStyleSheet("color: #10b981; background: rgba(16, 185, 129, 0.18); border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 8px; padding: 8px 14px; font-weight: bold;")

    def launch_game(self, game):
        g_name = game.get('name', 'Game')
        self.status_msg.setText(f"⏳ {g_name} tekshirilmoqda...")
        self.status_msg.setStyleSheet("color: #00f0ff; background: rgba(0, 240, 255, 0.15); border: 1px solid rgba(0, 240, 255, 0.3); border-radius: 8px; padding: 8px 14px;")
        self.game_launched_signal.emit(game)


class ClientLockerApp:
    def __init__(self, config_path="config.json"):
        self.load_config(config_path)
        self.signals = SyncSignals()
        self.signals.status_updated.connect(self.handle_status_update)
        self.signals.bar_order_updated.connect(self.handle_bar_order_update)

        self.launched_processes = []

        self.lock_window = LockScreenWindow(self.pc_name)
        self.bar_menu_window = BarMenuWindow(self.pc_name, self.server_url)
        self.backdrop_overlay = BackdropOverlayWidget(on_click=self.bar_menu_window.hide)
        self.bar_menu_window.closed_signal.connect(self.backdrop_overlay.hide)

        self.overlay_window = TimerOverlayWidget(self.pc_name, on_bar_click=self.toggle_bar_menu)
        self.launcher_window = GameLauncherWindow(
            pc_name=self.pc_name,
            server_url=self.server_url,
            fallback_games=self.fallback_games,
            on_bar_click=self.toggle_bar_menu
        )
        self.launcher_window.game_launched_signal.connect(self.handle_game_launch)

        self.current_status = 'LOCKED'
        self.time_remaining = 0

        # Qt Timer for local countdown
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.local_tick)
        self.countdown_timer.start(1000)

        # Start lock screen initially — majburan fullscreen qulf oynasi
        install_keyboard_hook()
        self.backdrop_overlay.hide()
        self.lock_window.show_locker()
        self.overlay_window.hide()
        self.bar_menu_window.hide()
        self.launcher_window.hide()

        # Background thread for sync
        self.sync_thread = threading.Thread(target=self.run_sync_loop, daemon=True)
        self.sync_thread.start()

    def toggle_bar_menu(self):
        if self.bar_menu_window.isVisible():
            self.bar_menu_window.hide()
            self.backdrop_overlay.hide()
        else:
            self.backdrop_overlay.showFullScreen()
            self.bar_menu_window.load_data()
            self.bar_menu_window.show()
            self.bar_menu_window.raise_()
            self.bar_menu_window.activateWindow()

    def handle_bar_order_update(self, data):
        self.bar_menu_window.update_order_status(data)

    def load_config(self, path):
        default_config = {
            "server_url": "http://localhost:8000",
            "websocket_url": "ws://localhost:8000/ws/pc-status/",
            "pc_name": "PC-01",
            "heartbeat_interval_seconds": 5,
            "fallback_games": []
        }
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    cfg = json.load(f)
                    default_config.update(cfg)
            except Exception as e:
                print(f"Error loading config: {e}")

        self.server_url = default_config["server_url"]
        self.ws_url = default_config["websocket_url"]
        self.pc_name = default_config["pc_name"]
        self.heartbeat_interval = default_config["heartbeat_interval_seconds"]
        self.fallback_games = default_config.get("fallback_games", [])

    def handle_status_update(self, data):
        new_status = data.get('status', 'LOCKED')
        seconds = data.get('time_remaining', 0)
        self.time_remaining = seconds

        if new_status in ('ACTIVE', 'WARNING') and seconds > 0:
            if self.current_status == 'LOCKED':
                self.unlock_pc()
            self.current_status = new_status
            self.overlay_window.update_timer(self.time_remaining)
            self.launcher_window.update_timer(self.time_remaining)
        else:
            if self.current_status != 'LOCKED':
                self.lock_pc()

    def unlock_pc(self):
        """Seans boshlanganda chaqiriladi.
        Qulf oynasi yashiriladi, Launcher fullscreen ko'rsatiladi."""
        print("[Locker] Unlocking PC and opening Clutch Zone Game Launcher...")
        uninstall_keyboard_hook()
        self.lock_window.hide()
        self.overlay_window.show()
        self.launcher_window.load_games()
        # Launcher majburan fullscreen
        self.launcher_window.show_launcher()
        self.current_status = 'ACTIVE'

    def handle_game_launch(self, game):
        exe_path = game.get('executable_path')
        working_dir = game.get('working_directory')
        g_name = game.get('name', 'Game')
        print(f"[Launcher] Launching game: '{g_name}' -> exe: '{exe_path}', cwd: '{working_dir}'")

        if exe_path and os.path.exists(exe_path):
            try:
                cwd = None
                if working_dir and os.path.exists(working_dir):
                    cwd = working_dir
                elif exe_path and os.path.dirname(exe_path) and os.path.exists(os.path.dirname(exe_path)):
                    cwd = os.path.dirname(exe_path)

                proc = subprocess.Popen([exe_path], cwd=cwd)
                self.launched_processes.append(proc)
                print(f"[Launcher] Successfully started PID: {proc.pid}")
                self.launcher_window.show_launch_success(g_name)
            except Exception as e:
                print(f"[Launcher] Execution error for {exe_path}: {e}")
                self.launcher_window.show_launch_error(f"Xatolik: {e}")
        else:
            print(f"[Launcher Error] Executable not found at path: {exe_path}")
            self.launcher_window.show_launch_error("O'yin fayli topilmadi, iltimos admonga murojaat qiling")

    def lock_pc(self):
        """Seans tugaganda chaqiriladi.
        Launcher yashiriladi, Qulf oynasi fullscreen ko'rsatiladi."""
        print("[Locker] Locking PC and terminating game processes...")
        self.current_status = 'LOCKED'
        self.time_remaining = 0
        self.overlay_window.hide()
        self.bar_menu_window.hide()
        self.backdrop_overlay.hide()
        self.launcher_window.hide()
        # Qulf oynasini majburan fullscreen ko'rsatish
        self.lock_window.show_locker()
        install_keyboard_hook()

        # Terminate launched processes
        for proc in self.launched_processes:
            try:
                print(f"[Cleanup] Terminating PID: {proc.pid}")
                proc.terminate()
                proc.kill()
            except Exception as e:
                print(f"[Cleanup] Error terminating process: {e}")
        self.launched_processes.clear()

        # Taskkill on Windows
        if IS_WINDOWS:
            exe_names = ["cs2.exe", "VALORANT.exe", "TslGame.exe", "GTA5.exe", "Cyberpunk2077.exe", "RDR2.exe", "FC24.exe", "NFSUnbound.exe", "NBA2K24.exe", "dota2.exe", "LeagueClient.exe"]
            for exe in exe_names:
                try:
                    subprocess.run(["taskkill", "/F", "/IM", exe], capture_output=True)
                except Exception as e:
                    print(f"Taskkill error for {exe}: {e}")
        else:
            print("[Cleanup Simulator] All active game process trees terminated.")

    def local_tick(self):
        if self.current_status in ('ACTIVE', 'WARNING'):
            if self.time_remaining > 0:
                self.time_remaining -= 1
                self.overlay_window.update_timer(self.time_remaining)
                self.launcher_window.update_timer(self.time_remaining)
            else:
                self.lock_pc()

    def run_sync_loop(self):
        ws_thread = threading.Thread(target=self.run_ws_client, daemon=True)
        ws_thread.start()

        while True:
            try:
                resp = requests.post(
                    f"{self.server_url}/api/computers/heartbeat/",
                    json={"pc_name": self.pc_name},
                    timeout=4
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self.signals.status_updated.emit(data)
            except Exception as e:
                print(f"[Heartbeat] Error connecting to server: {e}")
            time.sleep(self.heartbeat_interval)

    def run_ws_client(self):
        def on_message(ws, message):
            try:
                msg_data = json.loads(message)
                if msg_data.get('type') == 'BAR_ORDER_UPDATE':
                    order_info = msg_data.get('order', {})
                    order_obj = order_info.get('order', order_info)
                    if order_obj.get('computer_name') == self.pc_name:
                        self.signals.bar_order_updated.emit(order_obj)
                else:
                    pc_data = msg_data.get('pc', {})
                    if pc_data.get('name') == self.pc_name:
                        self.signals.status_updated.emit(pc_data)
                    elif msg_data.get('action') == 'EMERGENCY_LOCK_ALL':
                        self.signals.status_updated.emit({'status': 'LOCKED', 'time_remaining': 0})
            except Exception as e:
                print(f"[WS] Message parse error: {e}")

        def on_open(ws):
            print("[WS] Client locker connected to WebSocket")

        def on_error(ws, error):
            print(f"[WS] Client locker WebSocket error: {error}")

        while True:
            try:
                ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_message=on_message,
                    on_open=on_open,
                    on_error=on_error
                )
                ws.run_forever()
            except Exception as e:
                print(f"[WS] Connection failed: {e}")
            time.sleep(3)


def main():
    # ----------------------------------------------------------------
    # HIGH-DPI & SCALING FIX — QApplication yaratilishidan OLDIN
    # ----------------------------------------------------------------
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    locker = ClientLockerApp("config.json")
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
