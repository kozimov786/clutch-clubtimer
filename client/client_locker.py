import sys
import os
import time
import json
import subprocess
import platform
import threading
import requests
import websocket

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QFrame,
    QHBoxLayout, QScrollArea, QGridLayout
)
from PyQt6.QtGui import QFont, QColor

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

# Signals for UI thread communication
class SyncSignals(QObject):
    status_updated = pyqtSignal(dict)

class LockScreenWindow(QWidget):
    def __init__(self, pc_name="PC-01"):
        super().__init__()
        self.pc_name = pc_name
        self.init_ui()

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.showFullScreen()
        
        # Dark Cyberpunk Glassmorphism Background
        self.setStyleSheet("""
            QWidget {
                background-color: #090d16;
                color: #e2e8f0;
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setFixedSize(550, 420)
        card.setStyleSheet("""
            QFrame {
                background: rgba(18, 25, 41, 0.9);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 24px;
            }
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Lock Icon / Logo
        icon_label = QLabel("🔒")
        icon_label.setFont(QFont("Segoe UI Emoji", 48))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(icon_label)

        # Title PC Name
        title = QLabel(self.pc_name)
        title.setFont(QFont("Consolas", 32, QFont.Weight.Bold))
        title.setStyleSheet("color: #00f0ff; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        # Status text
        status_lbl = QLabel("STATION LOCKED")
        status_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        status_lbl.setStyleSheet("color: #ef4444; letter-spacing: 1px;")
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(status_lbl)

        # Instructions
        desc = QLabel("Please contact administrator at the front desk to start a session.")
        desc.setFont(QFont("Segoe UI", 12))
        desc.setStyleSheet("color: #94a3b8;")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(desc)

        layout.addWidget(card)

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
                background: rgba(10, 14, 23, 0.88);
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
                background: linear-gradient(135deg, rgba(168, 85, 247, 0.3) 0%, rgba(217, 70, 239, 0.3) 100%);
                color: #c084fc;
                border: 1px solid rgba(168, 85, 247, 0.6);
                border-radius: 12px;
            }
            QPushButton:hover {
                background: rgba(168, 85, 247, 0.6);
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

class BarMenuWindow(QWidget):
    def __init__(self, pc_name="PC-01", server_url="http://localhost:8000"):
        super().__init__()
        self.pc_name = pc_name
        self.server_url = server_url
        self.cart = {}
        self.products = []
        self.categories = []
        self.current_category_id = None
        self.init_ui()

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
                background: rgba(15, 23, 42, 0.95);
                border: 1px solid rgba(0, 240, 255, 0.3);
                border-radius: 20px;
            }
        """)
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


class ClientLockerApp:
    def __init__(self, config_path="config.json"):
        self.load_config(config_path)
        self.signals = SyncSignals()
        self.signals.status_updated.connect(self.handle_status_update)
        self.signals.bar_order_updated.connect(self.handle_bar_order_update)

        self.lock_window = LockScreenWindow(self.pc_name)
        self.bar_menu_window = BarMenuWindow(self.pc_name, self.server_url)
        self.overlay_window = TimerOverlayWidget(self.pc_name, on_bar_click=self.toggle_bar_menu)

        self.current_status = 'LOCKED'
        self.time_remaining = 0

        # Qt Timer for local countdown
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.local_tick)
        self.countdown_timer.start(1000)

        # Start lock screen initially
        install_keyboard_hook()
        self.lock_window.show()
        self.overlay_window.hide()
        self.bar_menu_window.hide()

        # Background thread for sync
        self.sync_thread = threading.Thread(target=self.run_sync_loop, daemon=True)
        self.sync_thread.start()

    def toggle_bar_menu(self):
        if self.bar_menu_window.isVisible():
            self.bar_menu_window.hide()
        else:
            self.bar_menu_window.load_data()
            self.bar_menu_window.show()

    def handle_bar_order_update(self, data):
        self.bar_menu_window.update_order_status(data)

    def load_config(self, path):
        default_config = {
            "server_url": "http://localhost:8000",
            "websocket_url": "ws://localhost:8000/ws/pc-status/",
            "pc_name": "PC-01",
            "playnite_path": "C:\\Program Files\\Playnite\\Playnite.FullscreenApp.exe",
            "heartbeat_interval_seconds": 5
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
        self.playnite_path = default_config["playnite_path"]
        self.heartbeat_interval = default_config["heartbeat_interval_seconds"]

    def handle_status_update(self, data):
        new_status = data.get('status', 'LOCKED')
        seconds = data.get('time_remaining', 0)
        self.time_remaining = seconds

        if new_status in ('ACTIVE', 'WARNING') and seconds > 0:
            if self.current_status == 'LOCKED':
                self.unlock_pc()
            self.current_status = new_status
            self.overlay_window.update_timer(self.time_remaining)
        else:
            if self.current_status != 'LOCKED':
                self.lock_pc()

    def unlock_pc(self):
        print("[Locker] Unlocking PC and starting Playnite...")
        uninstall_keyboard_hook()
        self.lock_window.hide()
        self.overlay_window.show()
        self.current_status = 'ACTIVE'

        # Launch Playnite
        if os.path.exists(self.playnite_path):
            try:
                subprocess.Popen([self.playnite_path])
            except Exception as e:
                print(f"Error launching Playnite: {e}")
        else:
            print(f"[Playnite Simulator] Launching Playnite (Path not found: {self.playnite_path})")

    def lock_pc(self):
        print("[Locker] Locking PC and terminating game processes...")
        self.current_status = 'LOCKED'
        self.time_remaining = 0
        self.overlay_window.hide()
        self.bar_menu_window.hide()
        self.lock_window.show()
        install_keyboard_hook()

        # Session cleanup: Taskkill games/Playnite
        if IS_WINDOWS:
            try:
                subprocess.run(["taskkill", "/F", "/IM", "Playnite.FullscreenApp.exe"], capture_output=True)
            except Exception as e:
                print(f"Taskkill error: {e}")
        else:
            print("[Cleanup Simulator] Terminating active game process trees...")

    def local_tick(self):
        if self.current_status in ('ACTIVE', 'WARNING'):
            if self.time_remaining > 0:
                self.time_remaining -= 1
                self.overlay_window.update_timer(self.time_remaining)
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
    app = QApplication(sys.argv)
    locker = ClientLockerApp("config.json")
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
