"""
client_locker.py — Clutch Zone Client PC Locker (Native PyQt6, WebEngine-siz)
===================================================================================
Bu versiya WebEngine/Chromium'ni umuman ishlatmaydi — barcha UI (qulf ekrani,
o'yinlar menyusi, bar) sof PyQt6 widgetlari bilan qurilgan, ma'lumotlar esa
Django REST API'dan JSON orqali olinadi. Sabab: ayrim Windows kompyuterlarda
QWebEngineView butun oynani "shaffof" qilib qo'yadigan, aniq ildizi topilmagan
render xatosi bor edi; sof Qt widgetlar esa har doim to'g'ri ishlagan.
"""

import sys
import os
import ctypes

# ──────────────────────────────────────────────────────────────────────────────
#  1. DPI AWARENESS (QApplication yaratilishidan OLDIN)
# ──────────────────────────────────────────────────────────────────────────────
if sys.platform == 'win32':
    try:
        DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
        ctypes.windll.user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = "1"

import time
import json
import socket
import subprocess
import platform
import threading
import zipfile
import shutil
import tempfile
import requests

from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal, QObject, QDate, QByteArray, QBuffer, QIODevice
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QPushButton, QFrame, QHBoxLayout, QScrollArea, QGridLayout,
    QLineEdit, QGraphicsDropShadowEffect, QSizePolicy, QStackedWidget,
    QSpacerItem
)
from PyQt6.QtGui import QFont, QColor, QPixmap, QGuiApplication, QIcon

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
CLIENT_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(CLIENT_DIR, "VERSION")


def get_local_client_version():
    try:
        with open(VERSION_FILE, 'r') as f:
            return f.read().strip()
    except Exception:
        return "0.0.0"


def check_and_apply_update(server_url, api_key):
    """Serverdan (ClientBuild) eng so'nggi versiyani tekshiradi; agar
    yangisi bo'lsa, zip arxivini yuklab olib client/ papkasi ustiga
    yozadi (config.json'ga tegmaydi) va True qaytaradi — chaqiruvchi
    True kelganda dasturni yopishi kerak (watchdog.bat uni yangi kod
    bilan qayta ishga tushiradi). Har qanday xatoda jim False qaytaradi —
    yangilanish bilan bog'liq muammo hech qachon kiosk ishga tushishiga
    to'sqinlik qilmasligi kerak."""
    try:
        local_version = get_local_client_version()
        headers = {"X-API-Key": api_key} if api_key else {}
        resp = requests.get(f"{server_url}/api/client/latest/", headers=headers, timeout=6)
        if resp.status_code != 200:
            return False
        server_version = resp.json().get('version')
        if not server_version or server_version == local_version:
            return False

        print(f"[Update] Yangi versiya topildi: {server_version} (joriy: {local_version}) — yuklab olinmoqda...")
        dl = requests.get(f"{server_url}/api/client/download/", headers=headers, timeout=60)
        if dl.status_code != 200:
            print(f"[Update] Yuklab bo'lmadi: HTTP {dl.status_code}")
            return False

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "update.zip")
            with open(zip_path, 'wb') as f:
                f.write(dl.content)

            extract_dir = os.path.join(tmpdir, "extracted")
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_dir)

            for root, _dirs, files in os.walk(extract_dir):
                for fname in files:
                    if fname == "config.json":
                        continue
                    src = os.path.join(root, fname)
                    rel = os.path.relpath(src, extract_dir)
                    dest = os.path.join(CLIENT_DIR, rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(src, dest)

        with open(VERSION_FILE, 'w') as f:
            f.write(server_version)

        print(f"[Update] {server_version} versiyasi o'rnatildi, dastur qayta ishga tushirilmoqda...")
        return True
    except Exception as e:
        print(f"[Update] Tekshirishda xato (e'tiborsiz qoldirildi): {e}")
        return False


def get_screen_resolution():
    if sys.platform == 'win32':
        try:
            width = ctypes.windll.user32.GetSystemMetrics(0)
            height = ctypes.windll.user32.GetSystemMetrics(1)
            if width > 0 and height > 0:
                return width, height
        except Exception as e:
            print(f"[user32 API Error] {e}")
    screen = QGuiApplication.primaryScreen().geometry()
    return screen.width(), screen.height()


# ──────────────────────────────────────────────────────────────────────────────
#  2. FORCE FULLSCREEN & SHOW EVENT OVERRIDE
# ──────────────────────────────────────────────────────────────────────────────
class FullscreenMixin:
    def force_native_fullscreen(self):
        w, h = get_screen_resolution()

        # MUHIM: Qt.WindowType.Window shu yerda ATAYLAB qo'shilgan. Ota-
        # widget'siz (top-level) oyna uchun Qt buni windowFlags()'ga
        # avtomatik qo'shib qo'yadi — agar biz uni desired_flags'da hisobga
        # olmasak, solishtiruv HECH QACHON to'g'ri kelmaydi va
        # setWindowFlags() har safar (hatto hech narsa o'zgarmagan bo'lsa
        # ham) qayta chaqiriladi. Bu esa allaqachon ko'rsatilgan oynani
        # yashiradi (Qt'ning hujjatlashtirilgan xatti-harakati), va agar
        # shu payt isFullScreen() "eski" holatni True deb ko'rsatsa,
        # showFullScreen() qayta chaqirilmaydi — oyna abadiy yashirin
        # qolib ketadi. Aynan shu xato butun "shaffof oyna" muammosining
        # haqiqiy ildizi edi.
        desired_flags = (
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        if self.windowFlags() != desired_flags:
            self.setWindowFlags(desired_flags)

        geo = self.geometry()
        if geo.x() != 0 or geo.y() != 0 or geo.width() != w or geo.height() != h:
            self.setGeometry(0, 0, w, h)
            self.setFixedSize(w, h)

        # isVisible() ham tekshiriladi — faqat isFullScreen()ga ishonish
        # xavfli, chunki setWindowFlags() oynani yashirgandan keyin ham bu
        # bayroq "eski" (True) holatda qolib ketishi mumkin.
        if not self.isFullScreen() or not self.isVisible():
            self.showFullScreen()

        self.raise_()
        self.activateWindow()

    def showEvent(self, event):
        super().showEvent(event)
        self.force_native_fullscreen()


# ──────────────────────────────────────────────────────────────────────────────
#  3. ASYNC IMAGE LOADING (rasm URL/faylni UI oqimini bloklamasdan yuklaydi)
# ──────────────────────────────────────────────────────────────────────────────
class _ImageLoadSignal(QObject):
    loaded = pyqtSignal(object, bytes)


_image_signal = _ImageLoadSignal()
_image_cache = {}


def _on_image_loaded(label, data):
    try:
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            target_w = label.width() if label.width() > 0 else 280
            target_h = label.height() if label.height() > 0 else 150
            scaled = pixmap.scaled(
                target_w, target_h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            label.setPixmap(scaled)
    except RuntimeError:
        pass  # widget o'chirilgan bo'lishi mumkin (grid qayta yuklanganda)


_image_signal.loaded.connect(_on_image_loaded)


def load_image_async(url_or_path, label):
    """Rasmni fon oqimida yuklaydi; tayyor bo'lgach label'ga UI-thread'da o'rnatadi."""
    if not url_or_path:
        return
    if url_or_path in _image_cache:
        _image_signal.loaded.emit(label, _image_cache[url_or_path])
        return

    def _fetch():
        try:
            if url_or_path.startswith('http://') or url_or_path.startswith('https://'):
                r = requests.get(url_or_path, timeout=6)
                if r.status_code == 200:
                    data = r.content
                    _image_cache[url_or_path] = data
                    _image_signal.loaded.emit(label, data)
                else:
                    print(f"[Image] {url_or_path}: HTTP {r.status_code}")
            else:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                # config.json'dagi fallback_games "client/assets/..." kabi
                # repo-ildizga nisbatan yo'l beradi, lekin dastur odatda
                # client/ papkasining o'zidan ishga tushiriladi — shuning
                # uchun boshidagi "client/" qismini olib tashlab ham sinaymiz.
                stripped = url_or_path
                for prefix in ("client/", "client\\"):
                    if stripped.startswith(prefix):
                        stripped = stripped[len(prefix):]
                        break
                candidates = [
                    url_or_path,
                    os.path.join(script_dir, url_or_path),
                    os.path.join(script_dir, stripped),
                    os.path.join(script_dir, os.path.basename(url_or_path)),
                ]
                for path in candidates:
                    if os.path.exists(path):
                        with open(path, 'rb') as f:
                            data = f.read()
                        _image_cache[url_or_path] = data
                        _image_signal.loaded.emit(label, data)
                        return
                print(f"[Image] {url_or_path}: fayl topilmadi (sinovlar: {candidates})")
        except Exception as e:
            print(f"[Image] {url_or_path}: {e}")

    threading.Thread(target=_fetch, daemon=True).start()


# ──────────────────────────────────────────────────────────────────────────────
#  4. DJANGO REST API CLIENT
# ──────────────────────────────────────────────────────────────────────────────
class ApiClient:
    def __init__(self, server_url, api_key=None):
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key

    def _headers(self):
        return {"X-API-Key": self.api_key} if self.api_key else {}

    def _get(self, path):
        try:
            r = requests.get(f"{self.server_url}{path}", headers=self._headers(), timeout=6)
            if r.status_code == 200:
                return r.json()
            elif r.status_code in (401, 403):
                print(f"[API] GET {path}: ruxsat rad etildi ({r.status_code}) — "
                      f"config.json'dagi api_key server bilan mos kelmayapti.")
        except Exception as e:
            print(f"[API] GET {path}: {e}")
        return None

    def get_games(self):
        data = self._get("/api/games/")
        return data if isinstance(data, list) else []

    def get_categories(self):
        data = self._get("/api/categories/")
        return data if isinstance(data, list) else []

    def get_products(self):
        data = self._get("/api/products/")
        return data if isinstance(data, list) else []

    def create_order_async(self, pc_name, items, on_done=None):
        def _post():
            try:
                r = requests.post(
                    f"{self.server_url}/api/orders/",
                    json={"pc_name": pc_name, "items": items, "payment_method": "CASH"},
                    headers=self._headers(),
                    timeout=6
                )
                ok = r.status_code == 201
                if on_done:
                    on_done(ok, r.json() if r.content else {})
            except Exception as e:
                print(f"[API] create_order: {e}")
                if on_done:
                    on_done(False, {"error": str(e)})
        threading.Thread(target=_post, daemon=True).start()


GAME_CATEGORIES = [
    ("all", "BARCHASI", "🌐"),
    ("FPS", "FPS / SHOOTER", "🎯"),
    ("Action", "ACTION / RPG", "⚔️"),
    ("Sports", "SPORTS / RACING", "🏎️"),
    ("Strategy", "STRATEGY / MOBA", "🎮"),
]

CATEGORY_LABELS = {key: label for key, label, _ in GAME_CATEGORIES}


# ──────────────────────────────────────────────────────────────────────────────
#  5. LOCK SCREEN
# ──────────────────────────────────────────────────────────────────────────────
class LockScreenWidget(QWidget):
    def __init__(self, pc_name="PC-01", parent=None):
        super().__init__(parent)
        self.pc_name = pc_name
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background-color: #060911;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("lockCard")
        card.setFixedSize(460, 300)
        card.setStyleSheet("""
            QFrame#lockCard {
                background: #0a0e17;
                border: 2px solid rgba(0,240,255,0.35);
                border-radius: 20px;
            }
            QLabel { border: none; background: transparent; }
        """)
        # QGraphicsDropShadowEffect() ATAYLAB ishlatilmagan: QGraphicsEffect
        # ba'zi Windows kompyuterlarda (cheklangan/eskirgan GPU-render
        # yo'lida) butun oynani noto'g'ri (bo'sh/shaffof) chizib qo'yishi
        # mumkin bo'lgan ma'lum Qt muammosi.

        cl = QVBoxLayout(card)
        cl.setContentsMargins(40, 36, 40, 36)
        cl.setSpacing(16)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        s = QLabel("🔒 STATION LOCKED")
        s.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        s.setStyleSheet("color: #ef4444; letter-spacing: 3px;")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(s)

        self.pc_label = QLabel(self.pc_name)
        self.pc_label.setFont(QFont("Consolas", 44, QFont.Weight.Bold))
        self.pc_label.setStyleSheet("color: #00f0ff; letter-spacing: 2px;")
        self.pc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.pc_label)

        desc = QLabel("Seansni boshlash uchun administratorga murojaat qiling.")
        desc.setFont(QFont("Segoe UI", 13))
        desc.setStyleSheet("color: #94a3b8;")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(desc)

        main_layout.addWidget(card)

    def set_pc_name(self, pc_name):
        self.pc_name = pc_name
        self.pc_label.setText(pc_name)

    def keyPressEvent(self, event): event.accept()


# ──────────────────────────────────────────────────────────────────────────────
#  6. TOP BAR
# ──────────────────────────────────────────────────────────────────────────────
class TopBar(QFrame):
    tab_changed = pyqtSignal(str)  # "games" | "bar" | "achievements"

    def __init__(self, pc_name="PC-01", parent=None):
        super().__init__(parent)
        self.pc_name = pc_name
        self._active_tab = "games"
        self.setFixedHeight(84)
        self.setStyleSheet("""
            QFrame#topBar {
                background-color: #0a0e17;
                border-bottom: 1px solid rgba(255,255,255,0.06);
            }
        """)
        self.setObjectName("topBar")

        lo = QHBoxLayout(self)
        lo.setContentsMargins(28, 0, 28, 0)
        lo.setSpacing(24)

        # Logo
        logo_row = QHBoxLayout()
        logo_row.setSpacing(10)
        logo_pix_path = os.path.join(ASSETS_DIR, "clutch_logo_mark.png")
        logo_label = QLabel()
        if os.path.exists(logo_pix_path):
            pix = QPixmap(logo_pix_path)
            if not pix.isNull():
                logo_label.setPixmap(pix.scaled(38, 38, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo_row.addWidget(logo_label)
        title = QLabel("CLUTCH ZONE")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff; letter-spacing: 1px;")
        logo_row.addWidget(title)
        logo_widget = QWidget()
        logo_widget.setLayout(logo_row)
        lo.addWidget(logo_widget)

        lo.addSpacing(30)

        # Nav tabs
        self.nav_buttons = {}
        for key, label in [("games", "O'YINLAR"), ("bar", "BAR MENYUSI"), ("achievements", "YUTUQLAR")]:
            btn = QPushButton(label)
            btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFlat(True)
            btn.clicked.connect(lambda _, k=key: self._on_tab_clicked(k))
            lo.addWidget(btn)
            self.nav_buttons[key] = btn

        lo.addStretch(1)

        # Clock
        clock_box = QVBoxLayout()
        clock_box.setSpacing(0)
        self.clock_label = QLabel("00:00")
        self.clock_label.setFont(QFont("Consolas", 16, QFont.Weight.Bold))
        self.clock_label.setStyleSheet("color: #00f0ff;")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        clock_box.addWidget(self.clock_label)
        loc = QLabel("TASHKENT, UZ")
        loc.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        loc.setStyleSheet("color: #00f0ff; letter-spacing: 1px;")
        loc.setAlignment(Qt.AlignmentFlag.AlignRight)
        clock_box.addWidget(loc)
        clock_widget = QWidget()
        clock_widget.setLayout(clock_box)
        lo.addWidget(clock_widget)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        # PC status pill
        self.status_pill = QLabel(f"{self.pc_name} · ACTIVE")
        self.status_pill.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.status_pill.setStyleSheet("""
            color: #00f0ff;
            background: rgba(0,240,255,0.08);
            border: 1px solid rgba(0,240,255,0.35);
            border-radius: 14px;
            padding: 8px 16px;
        """)
        lo.addWidget(self.status_pill)

        self._apply_tab_styles()

    def _update_clock(self):
        self.clock_label.setText(time.strftime("%H:%M"))

    def set_status(self, pc_name, status_text):
        self.status_pill.setText(f"{pc_name} · {status_text}")

    def _on_tab_clicked(self, key):
        self._active_tab = key
        self._apply_tab_styles()
        self.tab_changed.emit(key)

    def _apply_tab_styles(self):
        for key, btn in self.nav_buttons.items():
            if key == self._active_tab:
                btn.setStyleSheet("QPushButton { color: #ffffff; border: none; } QPushButton:hover { color: #00f0ff; }")
            else:
                btn.setStyleSheet("QPushButton { color: #64748b; border: none; } QPushButton:hover { color: #94a3b8; }")


# ──────────────────────────────────────────────────────────────────────────────
#  7. RESPONSIVE FLOW GRID (o'yin/mahsulot kartalari uchun)
# ──────────────────────────────────────────────────────────────────────────────
class ResponsiveGrid(QScrollArea):
    def __init__(self, card_min_width=260, spacing=20, parent=None):
        super().__init__(parent)
        self.card_min_width = card_min_width
        self.spacing = spacing
        self._items = []
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { border: none; background-color: #060911; }")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # QScrollArea'ning ichki viewport widget'i alohida bo'lib, yuqoridagi
        # stylesheet uni har doim ham to'liq qamrab olavermaydi (ayniqsa
        # panjara bo'sh bo'lganda, tizim palitrasidagi och rang ko'rinib
        # qolishi mumkin edi) — shuning uchun uni ham aniq belgilaymiz.
        self.viewport().setStyleSheet("background-color: #060911;")

        self.container = QWidget()
        self.container.setStyleSheet("background-color: #060911;")
        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setSpacing(spacing)
        self.grid_layout.setContentsMargins(28, 20, 28, 28)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(self.container)

    def set_items(self, widgets):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)
        self._items = widgets
        self._relayout()

    def _columns_for_width(self, width):
        col_width = self.card_min_width + self.spacing
        return max(1, width // col_width)

    def _relayout(self):
        cols = self._columns_for_width(self.viewport().width())
        # clear positions only (widgets stay alive)
        for index, widget in enumerate(self._items):
            row, col = divmod(index, cols)
            self.grid_layout.addWidget(widget, row, col)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._items:
            self._relayout()


# ──────────────────────────────────────────────────────────────────────────────
#  8. GAME CARD
# ──────────────────────────────────────────────────────────────────────────────
class GameCard(QFrame):
    launch_requested = pyqtSignal(dict)

    def __init__(self, game, parent=None):
        super().__init__(parent)
        self.game = game
        self.setFixedWidth(260)
        self.setObjectName("gameCard")
        self.setStyleSheet("""
            QFrame#gameCard {
                background: #0a0e17;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
            }
            QFrame#gameCard:hover {
                border: 1px solid rgba(0,240,255,0.45);
            }
        """)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        self.cover = QLabel()
        self.cover.setFixedSize(258, 150)
        self.cover.setStyleSheet("background-color: #12172a; border-top-left-radius: 14px; border-top-right-radius: 14px;")
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setText("🎮")
        self.cover.setFont(QFont("Segoe UI", 32))
        lo.addWidget(self.cover)

        cover_path = game.get('cover_path')
        if cover_path:
            load_image_async(cover_path, self.cover)

        info = QHBoxLayout()
        info.setContentsMargins(14, 12, 14, 10)
        name = QLabel(game.get('name', 'Unknown'))
        name.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        name.setStyleSheet("color: #ffffff;")
        name.setWordWrap(True)
        info.addWidget(name, 1)

        cat_key = game.get('category', '')
        badge = QLabel(cat_key.upper() if cat_key else '')
        badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        badge.setStyleSheet("""
            color: #94a3b8; background: rgba(255,255,255,0.06);
            border-radius: 8px; padding: 3px 8px;
        """)
        info.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        lo.addLayout(info)

        self.launch_btn = QPushButton("▶  ISHGA TUSHIRISH")
        self.launch_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.launch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.launch_btn.setFixedHeight(42)
        self.launch_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0,240,255,0.10);
                color: #00f0ff;
                border: none;
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
            }
            QPushButton:hover { background: rgba(0,240,255,0.22); }
        """)
        self.launch_btn.clicked.connect(lambda: self.launch_requested.emit(self.game))
        lo.addWidget(self.launch_btn)


# ──────────────────────────────────────────────────────────────────────────────
#  9. GAMES PAGE (kategoriya, qidiruv, panjara)
# ──────────────────────────────────────────────────────────────────────────────
class GamesPage(QWidget):
    game_launch_requested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #060911;")
        self._all_games = []
        self._active_category = "all"
        self._search_text = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Category filter row
        cat_row = QHBoxLayout()
        cat_row.setContentsMargins(28, 18, 28, 10)
        cat_row.setSpacing(10)
        self.cat_buttons = {}
        for key, label, icon in GAME_CATEGORIES:
            btn = QPushButton(f"{icon}  {label}")
            btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(38)
            btn.clicked.connect(lambda _, k=key: self._select_category(k))
            cat_row.addWidget(btn)
            self.cat_buttons[key] = btn
        cat_row.addStretch(1)
        cat_row_widget = QWidget()
        cat_row_widget.setLayout(cat_row)
        root.addWidget(cat_row_widget)

        # Error banner + search
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(28, 0, 28, 14)
        toolbar.setSpacing(14)

        self.error_banner = QLabel("")
        self.error_banner.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.error_banner.setStyleSheet("color: #ef4444; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.3); border-radius: 10px; padding: 10px 16px;")
        self.error_banner.hide()
        toolbar.addWidget(self.error_banner, 1)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍  O'yin nomini qidirish...")
        self.search_box.setFixedWidth(280)
        self.search_box.setFixedHeight(38)
        self.search_box.setStyleSheet("""
            QLineEdit {
                background: #0a0e17; color: #e2e8f0;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 10px; padding: 0 12px;
            }
        """)
        self.search_box.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_box)

        toolbar_widget = QWidget()
        toolbar_widget.setLayout(toolbar)
        root.addWidget(toolbar_widget)

        self.grid = ResponsiveGrid(card_min_width=260, spacing=20)
        root.addWidget(self.grid, 1)

        self._apply_category_styles()

    def show_error(self, msg):
        self.error_banner.setText(f"❌  {msg}")
        self.error_banner.show()

    def clear_error(self):
        self.error_banner.hide()

    def set_games(self, games):
        self._all_games = games
        self._refresh_grid()

    def _select_category(self, key):
        self._active_category = key
        self._apply_category_styles()
        self._refresh_grid()

    def _apply_category_styles(self):
        for key, btn in self.cat_buttons.items():
            if key == self._active_category:
                btn.setStyleSheet("""
                    QPushButton { background: #00f0ff; color: #06131a; border: none; border-radius: 10px; padding: 0 16px; }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton { background: #0a0e17; color: #94a3b8; border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 0 16px; }
                    QPushButton:hover { border: 1px solid rgba(0,240,255,0.35); color: #e2e8f0; }
                """)

    def _on_search_changed(self, text):
        self._search_text = text.strip().lower()
        self._refresh_grid()

    def _refresh_grid(self):
        games = self._all_games
        if self._active_category != "all":
            games = [g for g in games if g.get('category') == self._active_category]
        if self._search_text:
            games = [g for g in games if self._search_text in g.get('name', '').lower()]

        cards = []
        for g in games:
            card = GameCard(g)
            card.launch_requested.connect(self.game_launch_requested.emit)
            cards.append(card)
        self.grid.set_items(cards)


# ──────────────────────────────────────────────────────────────────────────────
#  10. BAR MENU PAGE
# ──────────────────────────────────────────────────────────────────────────────
class ProductCard(QFrame):
    qty_changed = pyqtSignal(dict, int)

    def __init__(self, product, parent=None):
        super().__init__(parent)
        self.product = product
        self.qty = 0
        self.setFixedWidth(220)
        self.setObjectName("productCard")
        self.setStyleSheet("""
            QFrame#productCard { background: #0a0e17; border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; }
        """)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        self.cover = QLabel()
        self.cover.setFixedSize(218, 120)
        self.cover.setStyleSheet("background-color: #12172a; border-top-left-radius: 14px; border-top-right-radius: 14px;")
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setText("🍿")
        self.cover.setFont(QFont("Segoe UI", 26))
        lo.addWidget(self.cover)
        img = product.get('image')
        if img:
            load_image_async(img, self.cover)

        name = QLabel(product.get('name', ''))
        name.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        name.setStyleSheet("color: #ffffff; padding: 10px 12px 2px 12px;")
        name.setWordWrap(True)
        lo.addWidget(name)

        try:
            price = float(product.get('price', 0))
        except (TypeError, ValueError):
            price = 0.0
        price_label = QLabel(f"{price:,.0f} so'm".replace(',', ' '))
        price_label.setFont(QFont("Segoe UI", 10))
        price_label.setStyleSheet("color: #00f0ff; padding: 0 12px 8px 12px;")
        lo.addWidget(price_label)

        stepper = QHBoxLayout()
        stepper.setContentsMargins(12, 0, 12, 12)
        minus = QPushButton("−")
        plus = QPushButton("+")
        for b in (minus, plus):
            b.setFixedSize(34, 34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("QPushButton { background: rgba(255,255,255,0.06); color: #e2e8f0; border-radius: 8px; font-weight: bold; } QPushButton:hover { background: rgba(0,240,255,0.15); }")
        self.qty_label = QLabel("0")
        self.qty_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.qty_label.setStyleSheet("color: #ffffff;")
        self.qty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qty_label.setFixedWidth(30)
        minus.clicked.connect(lambda: self._change_qty(-1))
        plus.clicked.connect(lambda: self._change_qty(1))
        stepper.addWidget(minus)
        stepper.addWidget(self.qty_label, 1)
        stepper.addWidget(plus)
        lo.addLayout(stepper)

    def _change_qty(self, delta):
        self.qty = max(0, self.qty + delta)
        self.qty_label.setText(str(self.qty))
        self.qty_changed.emit(self.product, self.qty)


class BarPage(QWidget):
    # create_order_async'ning on_done callback'i fon oqimidan chaqiriladi —
    # shu signal orqali natija xavfsiz tarzda GUI oqimiga uzatiladi.
    _order_result = pyqtSignal(bool, dict)

    def __init__(self, api_client, pc_name, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.pc_name = pc_name
        self.cart = {}  # product_id -> (product, qty)
        self.setStyleSheet("background-color: #060911;")
        self._order_result.connect(self._on_order_done)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(28, 18, 28, 10)
        title = QLabel("🍸 BAR MENYUSI")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff;")
        header.addWidget(title)
        header.addStretch(1)

        self.total_label = QLabel("Jami: 0 so'm")
        self.total_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.total_label.setStyleSheet("color: #00f0ff;")
        header.addWidget(self.total_label)

        self.order_btn = QPushButton("✅  BUYURTMA BERISH")
        self.order_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.order_btn.setFixedHeight(40)
        self.order_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.order_btn.setStyleSheet("""
            QPushButton { background: #00f0ff; color: #06131a; border: none; border-radius: 10px; padding: 0 18px; }
            QPushButton:disabled { background: rgba(255,255,255,0.06); color: #64748b; }
        """)
        self.order_btn.clicked.connect(self._place_order)
        self.order_btn.setEnabled(False)
        header.addWidget(self.order_btn)

        header_widget = QWidget()
        header_widget.setLayout(header)
        root.addWidget(header_widget)

        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.status_label.setContentsMargins(28, 0, 28, 8)
        self.status_label.hide()
        root.addWidget(self.status_label)

        self.grid = ResponsiveGrid(card_min_width=220, spacing=18)
        root.addWidget(self.grid, 1)

    def set_products(self, products):
        self.cart = {}
        self._update_total()
        cards = []
        for p in products:
            card = ProductCard(p)
            card.qty_changed.connect(self._on_qty_changed)
            cards.append(card)
        self.grid.set_items(cards)

    def _on_qty_changed(self, product, qty):
        pid = product.get('id')
        if qty > 0:
            self.cart[pid] = (product, qty)
        else:
            self.cart.pop(pid, None)
        self._update_total()

    def _update_total(self):
        total = 0.0
        for product, qty in self.cart.values():
            try:
                total += float(product.get('price', 0)) * qty
            except (TypeError, ValueError):
                pass
        self.total_label.setText(f"Jami: {total:,.0f} so'm".replace(',', ' '))
        self.order_btn.setEnabled(len(self.cart) > 0)

    def _place_order(self):
        items = [{"product_id": pid, "quantity": qty} for pid, (_, qty) in self.cart.items()]
        if not items:
            return
        self.order_btn.setEnabled(False)
        self.order_btn.setText("YUBORILMOQDA...")
        self.api_client.create_order_async(
            self.pc_name, items,
            on_done=lambda ok, data: self._order_result.emit(ok, data)
        )

    def _on_order_done(self, ok, data):
        self.order_btn.setText("✅  BUYURTMA BERISH")
        self.status_label.show()
        if ok:
            self.status_label.setStyleSheet("color: #10b981;")
            self.status_label.setText("✅ Buyurtma qabul qilindi! Bar xodimi tez orada olib keladi.")
            self.cart = {}
            self._update_total()
            self.grid.set_items([])
        else:
            self.status_label.setStyleSheet("color: #ef4444;")
            self.status_label.setText("❌ Buyurtma yuborilmadi, qaytadan urinib ko'ring yoki administratorga murojaat qiling.")
            self.order_btn.setEnabled(len(self.cart) > 0)
        QTimer.singleShot(6000, self.status_label.hide)


# ──────────────────────────────────────────────────────────────────────────────
#  11. ACHIEVEMENTS PAGE (placeholder)
# ──────────────────────────────────────────────────────────────────────────────
class AchievementsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #060911;")
        lo = QVBoxLayout(self)
        lo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel("🏆")
        icon.setFont(QFont("Segoe UI", 54))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(icon)
        text = QLabel("YUTUQLAR — tez orada")
        text.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        text.setStyleSheet("color: #94a3b8;")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(text)


# ──────────────────────────────────────────────────────────────────────────────
#  12. LAUNCHER PAGE (TopBar + ichki sahifalar)
# ──────────────────────────────────────────────────────────────────────────────
class LauncherPage(QWidget):
    game_launch_requested = pyqtSignal(dict)
    # Fon oqimidan (threading.Thread) kelgan natijalarni asosiy GUI oqimiga
    # xavfsiz uzatish uchun — Qt signal/slot mexanizmi thread'lar orasida
    # avtomatik ravishda queued-connection ishlatadi, shuning uchun
    # QTimer.singleShot()'ni fon oqimidan chaqirishdan farqli o'laroq,
    # bu widget'larni to'g'ridan-to'g'ri noto'g'ri oqimdan o'zgartirmaydi.
    _games_loaded = pyqtSignal(list)
    _products_loaded = pyqtSignal(list)

    def __init__(self, pc_name, server_url, api_client, fallback_games=None, parent=None):
        super().__init__(parent)
        self.pc_name = pc_name
        self.api_client = api_client
        self.fallback_games = fallback_games or []
        self.setStyleSheet("background-color: #060911;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.top_bar = TopBar(pc_name=pc_name)
        self.top_bar.tab_changed.connect(self._switch_tab)
        root.addWidget(self.top_bar)

        self.inner_stack = QStackedWidget()
        self.games_page = GamesPage()
        self.games_page.game_launch_requested.connect(self.game_launch_requested.emit)
        self.bar_page = BarPage(api_client=api_client, pc_name=pc_name)
        self.achievements_page = AchievementsPage()
        self.inner_stack.addWidget(self.games_page)          # 0
        self.inner_stack.addWidget(self.bar_page)             # 1
        self.inner_stack.addWidget(self.achievements_page)    # 2
        root.addWidget(self.inner_stack, 1)

        self._games_loaded.connect(self.games_page.set_games)
        self._products_loaded.connect(self.bar_page.set_products)

        footer = QHBoxLayout()
        footer.setContentsMargins(28, 8, 28, 10)
        rules = QLabel("Qoidalar   Yordam")
        rules.setStyleSheet("color: #475569; font-size: 10px;")
        footer.addWidget(rules)
        footer.addStretch(1)
        copyright_label = QLabel("© 2026 Clutch Zone. Barcha huquqlar himoyalangan.")
        copyright_label.setStyleSheet("color: #475569; font-size: 10px;")
        footer.addWidget(copyright_label)
        footer_widget = QWidget()
        footer_widget.setLayout(footer)
        root.addWidget(footer_widget)

    def _switch_tab(self, key):
        index = {"games": 0, "bar": 1, "achievements": 2}.get(key, 0)
        self.inner_stack.setCurrentIndex(index)
        if key == "bar":
            self.reload_products()

    def set_pc_status(self, pc_name, status_text):
        self.top_bar.set_status(pc_name, status_text)

    def reload_games(self):
        def _fetch():
            api_games = self.api_client.get_games()
            games = api_games or list(self.fallback_games)
            print(f"[Launcher] games: api={len(api_games) if api_games else 0} "
                  f"fallback_used={not api_games} total={len(games)}")
            self._games_loaded.emit(games)
        threading.Thread(target=_fetch, daemon=True).start()

    def reload_products(self):
        def _fetch():
            products = self.api_client.get_products()
            print(f"[Launcher] products: {len(products)}")
            self._products_loaded.emit(products)
        threading.Thread(target=_fetch, daemon=True).start()

    def show_launch_error(self, msg):
        self.games_page.show_error(msg)
        QTimer.singleShot(6000, self.games_page.clear_error)

    def show_launch_success(self, name):
        print(f"[Launcher] Game launched: {name}")


# ──────────────────────────────────────────────────────────────────────────────
#  13. MAIN WINDOW
# ──────────────────────────────────────────────────────────────────────────────
class MainWindow(FullscreenMixin, QMainWindow):
    game_launched_signal = pyqtSignal(dict)

    PAGE_LOCK = 0
    PAGE_LAUNCHER = 1

    def __init__(self, pc_name="PC-01", server_url="http://localhost:8001", fallback_games=None, api_key=None):
        super().__init__()
        self.pc_name = pc_name
        self.server_url = server_url.rstrip('/')
        self.fallback_games = fallback_games or []
        self.api_client = ApiClient(self.server_url, api_key=api_key)

        self.setWindowTitle(f"Clutch Zone Client Locker - {pc_name}")
        self.setStyleSheet("QMainWindow, QWidget { background-color: #060911; }")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.stacked = QStackedWidget()
        self.stacked.setStyleSheet("QStackedWidget { background-color: #060911; }")
        self.stacked.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.lock_page = LockScreenWidget(pc_name=pc_name)
        self.launcher_page = LauncherPage(
            pc_name=pc_name, server_url=self.server_url, api_client=self.api_client,
            fallback_games=self.fallback_games
        )
        self.launcher_page.game_launch_requested.connect(self.game_launched_signal.emit)

        self.stacked.addWidget(self.lock_page)       # PAGE_LOCK
        self.stacked.addWidget(self.launcher_page)    # PAGE_LAUNCHER
        self.stacked.setCurrentIndex(self.PAGE_LOCK)
        self.setCentralWidget(self.stacked)
        self.force_native_fullscreen()

    def switch_to_lock(self):
        self.stacked.setCurrentIndex(self.PAGE_LOCK)
        self.force_native_fullscreen()

    def switch_to_launcher(self):
        self.stacked.setCurrentIndex(self.PAGE_LAUNCHER)
        self.force_native_fullscreen()

    def yield_to_app(self):
        """O'yin/dastur ishga tushganda chaqiriladi: launcher minimize
        BO'LMAYDI (bu Windows ish stolini ochib qo'yardi) — u faqat
        "har doim tepada" xususiyatini vaqtincha yo'qotib, orqa qatlamga
        o'tadi. Shu tarzda: o'yin ustida, launcher o'rtada (butun ekranni
        hamon egallab turibdi), Windows ish stoli esa hech qachon
        ko'rinmaydi. force_native_fullscreen() (F9/BAR yoki keyingi
        lock-unlock o'tishida) uni yana eng tepaga qaytaradi.

        Qt'ning setWindowFlags()/lower() orqali emas — to'g'ridan-to'g'ri
        Windows'ning o'z SetWindowPos() API'si orqali amalga oshiriladi,
        chunki bu ancha ishonchli ekani aniqlandi (avval Qt darajasidagi
        yondashuv ishlamay qoldi)."""
        if sys.platform == 'win32':
            try:
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOACTIVATE = 0x0010
                HWND_NOTOPMOST = -2
                HWND_BOTTOM = 1
                set_pos = ctypes.windll.user32.SetWindowPos
                set_pos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
                set_pos.restype = ctypes.c_bool
                hwnd = int(self.winId())
                flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
                ok1 = set_pos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
                ok2 = set_pos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, flags)
                print(f"[Window] yield_to_app: NOTOPMOST={ok1} BOTTOM={ok2}")
            except Exception as e:
                print(f"[Window] yield_to_app native SetWindowPos xatosi: {e}")
        else:
            flags = self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint
            self.setWindowFlags(flags)
            self.show()
            self.lower()

    def load_games(self):
        self.launcher_page.reload_games()

    def update_timer(self, seconds):
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        status = f"ACTIVE · {h:02d}:{m:02d}:{s:02d}"
        self.launcher_page.set_pc_status(self.pc_name, status)

    def show_launch_error(self, msg="O'yin fayli topilmadi"):
        self.launcher_page.show_launch_error(msg)

    def show_launch_success(self, name):
        self.launcher_page.show_launch_success(name)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                QTimer.singleShot(80, self.force_native_fullscreen)

    def closeEvent(self, event): event.ignore()


# ──────────────────────────────────────────────────────────────────────────────
#  KEYBOARD HOOK (Windows) — LOCKED holatda Alt+Tab/Win/Alt+F4/Alt+Esc bloklaydi.
#  Global hotkeylar (favqulodda chiqish, F9) ESA endi past darajali hook orqali
#  emas, balki Windows'ning shu maqsad uchun MO'LJALLANGAN RegisterHotKey()
#  API'si orqali aniqlanadi — GetAsyncKeyState + 250ms polling'ga qaraganda
#  ancha ishonchli va kechikishsiz (WM_HOTKEY xabari darhol yetkaziladi).
# ──────────────────────────────────────────────────────────────────────────────
IS_WINDOWS = platform.system() == 'Windows'

EMERGENCY_UNLOCK_REQUESTED = False
SHOW_LAUNCHER_REQUESTED = False

if IS_WINDOWS:
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    WH_KEYBOARD_LL = 13
    VK_TAB = 0x09; VK_LWIN = 0x5B; VK_RWIN = 0x5C; VK_F4 = 0x73; VK_ESCAPE = 0x1B
    VK_U = 0x55; VK_F9 = 0x78; VK_P = 0x50

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
        ]
    HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT))

    # MUHIM: to'g'ri argtypes/restype (ayniqsa c_void_p qaytish qiymati)
    # aniq belgilanmasa, ctypes SetWindowsHookExA'ning 64-bit HHOOK
    # qaytish qiymatini standart bo'yicha 32-bit c_int sifatida talqin
    # qilib, uni KESIB TASHLASHI mumkin — bu haqiqatda hook muvaffaqiyatli
    # o'rnatilgan bo'lsa ham, natija 0 (xato) bo'lib ko'rinishiga olib
    # kelishi mumkin.
    user32.SetWindowsHookExA.restype = ctypes.c_void_p
    user32.SetWindowsHookExA.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
    user32.CallNextHookEx.restype = ctypes.c_long
    user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT)]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]

    hook_id = None; is_hook_enabled = False

    def low_level_keyboard_proc(nCode, wParam, lParam):
        global is_hook_enabled
        if nCode >= 0 and is_hook_enabled:
            kb = lParam.contents; vk = kb.vkCode; alt = (kb.flags & 0x20) != 0
            if (alt and vk == VK_TAB) or (vk in (VK_LWIN, VK_RWIN)) or \
               (alt and vk == VK_F4) or (alt and vk == VK_ESCAPE):
                return 1
        return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)
    pointer_proc = HOOKPROC(low_level_keyboard_proc)

    def install_keyboard_hook():
        global hook_id, is_hook_enabled
        is_hook_enabled = True
        if not hook_id:
            hook_id = user32.SetWindowsHookExA(WH_KEYBOARD_LL, pointer_proc, kernel32.GetModuleHandleW(None), 0)
            if not hook_id:
                print(f"[Hook] OGOHLANTIRISH: SetWindowsHookExA muvaffaqiyatsiz! GetLastError={ctypes.get_last_error()}")
            else:
                print(f"[Hook] Klaviatura hook muvaffaqiyatli o'rnatildi (id={hook_id})")

    def uninstall_keyboard_hook():
        global is_hook_enabled
        is_hook_enabled = False

    # ── Global hotkeylar: RegisterHotKey + native event filter ──
    from PyQt6.QtCore import QAbstractNativeEventFilter

    WM_HOTKEY = 0x0312
    MOD_ALT = 0x0001; MOD_CONTROL = 0x0002; MOD_SHIFT = 0x0004
    HOTKEY_EMERGENCY_1 = 1   # Ctrl+Alt+Shift+U
    HOTKEY_EMERGENCY_2 = 2   # Ctrl+Shift+P
    HOTKEY_SHOW_LAUNCHER = 3  # F9

    class HotkeyEventFilter(QAbstractNativeEventFilter):
        def nativeEventFilter(self, eventType, message):
            global EMERGENCY_UNLOCK_REQUESTED, SHOW_LAUNCHER_REQUESTED
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                if msg.wParam in (HOTKEY_EMERGENCY_1, HOTKEY_EMERGENCY_2):
                    print(f"[Hotkey] Favqulodda chiqish kombinatsiyasi aniqlandi (id={msg.wParam})")
                    EMERGENCY_UNLOCK_REQUESTED = True
                elif msg.wParam == HOTKEY_SHOW_LAUNCHER:
                    print("[Hotkey] F9 aniqlandi")
                    SHOW_LAUNCHER_REQUESTED = True
            return False, 0

    _hotkey_filter = None  # GC bo'lib ketmasligi uchun global reference saqlanadi

    def register_global_hotkeys(app):
        global _hotkey_filter
        _hotkey_filter = HotkeyEventFilter()
        app.installNativeEventFilter(_hotkey_filter)
        results = [
            user32.RegisterHotKey(None, HOTKEY_EMERGENCY_1, MOD_CONTROL | MOD_ALT | MOD_SHIFT, VK_U),
            user32.RegisterHotKey(None, HOTKEY_EMERGENCY_2, MOD_CONTROL | MOD_SHIFT, VK_P),
            user32.RegisterHotKey(None, HOTKEY_SHOW_LAUNCHER, 0, VK_F9),
        ]
        if all(results):
            print("[Hotkey] Barcha global hotkeylar muvaffaqiyatli ro'yxatdan o'tkazildi "
                  "(Ctrl+Alt+Shift+U, Ctrl+Shift+P, F9)")
        else:
            print(f"[Hotkey] OGOHLANTIRISH: ba'zi hotkeylar ro'yxatdan o'tmadi: {results} "
                  f"GetLastError={ctypes.get_last_error()}")

    # ── Ishga tushirilgan o'yin/dastur oynasini majburan old planga
    #    chiqarish. yield_to_app() bizning oynamizni orqaga o'tkazadi,
    #    lekin bu yangi ishga tushgan dastur AVTOMATIK old planga
    #    chiqishini kafolatlamaydi — Windows fon jarayonining fokusni
    #    o'g'irlashini standart ravishda cheklaydi. SetForegroundWindow'ni
    #    shu cheklovni chetlab o'tib ishlatish uchun AttachThreadInput
    #    triki qo'llaniladi (rasmiy, keng qo'llaniladigan Win32 usuli).
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindow.restype = ctypes.c_void_p

    def _find_window_for_pid(pid, timeout=10.0):
        result = []

        def _enum_proc(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            GW_OWNER = 4
            if user32.GetWindow(hwnd, GW_OWNER):
                return True  # faqat mustaqil (owner'siz) top-level oynalar
            proc_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            if proc_id.value == pid:
                result.append(hwnd)
                return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        enum_cb = WNDENUMPROC(_enum_proc)
        start = time.time()
        while time.time() - start < timeout and not result:
            user32.EnumWindows(enum_cb, 0)
            if result:
                break
            time.sleep(0.3)
        return result[0] if result else None

    def bring_process_window_to_front(pid, timeout=10.0):
        hwnd = _find_window_for_pid(pid, timeout=timeout)
        if not hwnd:
            print(f"[Launcher] PID {pid} uchun oyna {timeout}s ichida topilmadi — "
                  f"old planga chiqarib bo'lmadi.")
            return
        SW_RESTORE = 9
        current_thread = kernel32.GetCurrentThreadId()
        fg_hwnd = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
        attached = False
        if fg_thread and fg_thread != current_thread:
            attached = bool(user32.AttachThreadInput(fg_thread, current_thread, True))
        try:
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(fg_thread, current_thread, False)
        print(f"[Launcher] O'yin oynasi (hwnd={hwnd}, pid={pid}) old planga chiqarildi")

    # ── Windows taskbar'ni yashirish/qaytarish ──
    # To'liq ekranli, "har doim tepada" oyna bo'lsa ham, sichqonchani
    # ekranning eng pastki chetiga olib borilsa, Windows taskbar'ni
    # avtomatik "chiqarib yuboradi" — bu hatto topmost oynalar ustidan
    # ham ko'rinadi. Kiosk-rejim uchun standart yechim: taskbar oynasini
    # (Shell_TrayWnd) dastur ishlab turgan davrda butunlay yashirish.
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    SW_HIDE = 0
    SW_SHOW = 5

    def _taskbar_hwnds():
        hwnds = []
        primary = user32.FindWindowW("Shell_TrayWnd", None)
        if primary:
            hwnds.append(primary)
        secondary = user32.FindWindowW("Shell_SecondaryTrayWnd", None)
        if secondary:
            hwnds.append(secondary)
        return hwnds

    def hide_taskbar():
        hwnds = _taskbar_hwnds()
        for hwnd in hwnds:
            user32.ShowWindow(hwnd, SW_HIDE)
        print(f"[Taskbar] Yashirildi ({len(hwnds)} ta oyna)")

    def show_taskbar():
        hwnds = _taskbar_hwnds()
        for hwnd in hwnds:
            user32.ShowWindow(hwnd, SW_SHOW)
        print(f"[Taskbar] Qaytarildi ({len(hwnds)} ta oyna)")
else:
    def install_keyboard_hook():   print("[Hook] enabled (sim)")
    def uninstall_keyboard_hook(): print("[Hook] disabled (sim)")
    def register_global_hotkeys(app): pass
    def bring_process_window_to_front(pid, timeout=10.0): pass
    def hide_taskbar(): pass
    def show_taskbar(): pass


# ──────────────────────────────────────────────────────────────────────────────
#  APPLICATION CONTROLLER
# ──────────────────────────────────────────────────────────────────────────────
class SyncSignals(QObject):
    status_updated = pyqtSignal(dict)
    bar_order_updated = pyqtSignal(dict)


class ClientLockerApp:
    def __init__(self, config_path="config.json"):
        self._load_config(config_path)
        self.signals = SyncSignals()
        self.signals.status_updated.connect(self._handle_status)
        self.signals.bar_order_updated.connect(self._handle_bar_order)
        self.launched_processes = []
        self.current_status = 'LOCKED'
        self.time_remaining = 0
        self.pc_id = None
        # WebSocket ulangan bo'lsa, u real-vaqtli va aniq tartibda keladi —
        # shu payt heartbeat javobini e'tiborsiz qoldiramiz, aks holda
        # kechikkan heartbeat javobi WebSocket orqali kelgan yangi holatni
        # eskisi bilan qayta yozib, ekranda qisqa "miltillash" (masalan
        # ACTIVE -> LOCKED -> ACTIVE) keltirib chiqarishi mumkin edi.
        self.ws_connected = False

        self.main_window = MainWindow(
            pc_name=self.pc_name, server_url=self.server_url,
            fallback_games=self.fallback_games, api_key=self.api_key
        )
        self.main_window.game_launched_signal.connect(self._handle_game_launch)

        self.countdown = QTimer()
        self.countdown.timeout.connect(self._tick)
        self.countdown.start(1000)

        self.hotkey_timer = QTimer()
        self.hotkey_timer.timeout.connect(self._check_global_hotkeys)
        self.hotkey_timer.start(250)

        # Masofadan monitoring uchun: admin panelidan har bir PC ekranini
        # ko'rish imkoniyati (bugungidek uzoq debug jarayonlarini oldini
        # olish uchun). Har 20 soniyada bir marta ekran rasmi serverga
        # yuklanadi.
        self.screenshot_timer = QTimer()
        self.screenshot_timer.timeout.connect(self._capture_and_upload_screenshot)
        self.screenshot_timer.start(20000)

        # Markazlashgan yangilanish: har 30 daqiqada serverda yangi klient
        # versiyasi bor-yo'qligini tekshiradi. Faqat PC LOCKED holatda
        # bo'lganda o'rnatadi (mijoz o'ynayotganda uzilish bo'lmasin uchun).
        self.update_check_timer = QTimer()
        self.update_check_timer.timeout.connect(self._check_for_update)
        self.update_check_timer.start(30 * 60 * 1000)

        install_keyboard_hook()
        if IS_WINDOWS:
            hide_taskbar()
        self.main_window.switch_to_lock()

        threading.Thread(target=self._run_sync, daemon=True).start()

    def _check_global_hotkeys(self):
        global EMERGENCY_UNLOCK_REQUESTED, SHOW_LAUNCHER_REQUESTED
        if EMERGENCY_UNLOCK_REQUESTED:
            print("[Emergency] Ctrl+Alt+Shift+U yoki Ctrl+Shift+P aniqlandi — kiosk rejimi o'chirilmoqda")
            uninstall_keyboard_hook()
            if IS_WINDOWS:
                show_taskbar()
            os._exit(0)
        if SHOW_LAUNCHER_REQUESTED:
            SHOW_LAUNCHER_REQUESTED = False
            self._show_launcher_over_game()

    def _show_launcher_over_game(self):
        if self.current_status in ('ACTIVE', 'WARNING'):
            self.main_window.force_native_fullscreen()

    def _capture_and_upload_screenshot(self):
        if not self.pc_id:
            return
        # MUHIM: screen.grabWindow() — Qt/GUI operatsiyasi, faqat asosiy
        # oqimda (shu QTimer callback'ining o'zida) chaqirilishi shart.
        # Faqat tarmoq so'rovi (requests.post) fon oqimiga o'tkaziladi —
        # shu farqni chalkashtirish ilgari butun oynani "shaffof"
        # qilib qo'yadigan jiddiy xatoga sabab bo'lgan edi.
        try:
            screen = QGuiApplication.primaryScreen()
            if not screen:
                return
            pixmap = screen.grabWindow(0)
            byte_array = QByteArray()
            buffer = QBuffer(byte_array)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            pixmap.save(buffer, "PNG")
            data = bytes(byte_array)
            buffer.close()
        except Exception as e:
            print(f"[Screenshot] Olishda xato: {e}")
            return

        def _upload():
            try:
                requests.post(
                    f"{self.server_url}/api/computers/{self.pc_id}/upload_screenshot/",
                    data=data,
                    headers={"X-API-Key": self.api_key, "Content-Type": "image/png"},
                    timeout=8
                )
            except Exception as e:
                print(f"[Screenshot] Yuklashda xato: {e}")
        threading.Thread(target=_upload, daemon=True).start()

    def _check_for_update(self):
        if self.current_status != 'LOCKED':
            return  # mijoz o'ynayotganda yangilanish o'rnatilmaydi
        def _bg():
            if check_and_apply_update(self.server_url, self.api_key):
                print("[Update] Yangilanish o'rnatildi — dastur qayta ishga tushirilmoqda...")
                os._exit(17)
        threading.Thread(target=_bg, daemon=True).start()

    def _load_config(self, path):
        cfg = {"server_url": "http://localhost:8001", "websocket_url": "ws://localhost:8001/ws/pc-status/",
               "pc_name": "PC-01", "heartbeat_interval_seconds": 5, "fallback_games": [], "api_key": ""}
        if os.path.exists(path):
            try:
                with open(path, 'r') as f: cfg.update(json.load(f))
            except json.JSONDecodeError as e:
                print("=" * 70)
                print(f"[Config] XATO: '{path}' JSON sifatida noto'g'ri yozilgan!")
                print(f"[Config] {e.msg} — {e.lineno}-qator, {e.colno}-ustun atrofida.")
                print("[Config] Standart qiymatlarga (server_url=localhost, pc_name=PC-01) "
                      "qaytilmoqda — bu PC noto'g'ri nom bilan LOCKED holatda qolishiga sabab bo'ladi!")
                print("[Config] config.json faylini tuzatib, dasturni qayta ishga tushiring.")
                print("=" * 70)
            except Exception as e:
                print(f"[Config] {path}ni o'qishda xato: {e}")
        self.server_url = cfg["server_url"]
        self.ws_url = cfg["websocket_url"]
        self.pc_name = cfg["pc_name"]
        self.heartbeat_interval = cfg["heartbeat_interval_seconds"]
        self.fallback_games = cfg.get("fallback_games", [])
        self.api_key = cfg.get("api_key", "")
        if not self.api_key:
            print("[Config] OGOHLANTIRISH: 'api_key' config.json'da yo'q yoki bo'sh — "
                  "server endi API kalitini talab qiladi, heartbeat/o'yinlar/buyurtmalar "
                  "so'rovlari 401/403 xatosi bilan rad etilishi mumkin.")

    def _handle_status(self, data):
        new_status = data.get('status', 'LOCKED')
        seconds = data.get('time_remaining', 0)
        self.time_remaining = seconds
        # EMERGENCY_LOCK_ALL kabi ba'zi xabarlarda 'id' bo'lmaydi —
        # shunday holatda self.pc_id'ni None bilan ustidan yozmaslik kerak,
        # aks holda skrinshot yuklash keyingi haqiqiy status kelgunicha
        # to'xtab qoladi.
        if data.get('id'):
            self.pc_id = data.get('id')
        if new_status in ('ACTIVE', 'WARNING'):
            if self.current_status == 'LOCKED':
                self._unlock()
            self.current_status = new_status
            self.main_window.update_timer(self.time_remaining)
        else:
            if self.current_status != 'LOCKED':
                self._lock()

    def _handle_bar_order(self, data): pass

    def _unlock(self):
        # Alt+Tab/Win/Alt+F4/Alt+Esc bloklash ENDI ACTIVE holatda ham
        # o'chirilmaydi — F9/Ctrl+Shift+P global hotkeylar orqali
        # menyuga/Windows'ga qaytish allaqachon ishlaydi, shuning uchun
        # Alt+Tab'ga hojat yo'q va mijoz undan ish stoliga chiqish uchun
        # foydalana olmasligi kerak.
        print("[Locker] UNLOCK -> Launcher")
        self.main_window.load_games()
        self.main_window.switch_to_launcher()
        self.main_window.force_native_fullscreen()
        self.current_status = 'ACTIVE'

    def _lock(self):
        print("[Locker] LOCK -> LockScreen")
        self.current_status = 'LOCKED'
        self.time_remaining = 0
        self.main_window.switch_to_lock()
        self.main_window.force_native_fullscreen()
        self._kill_games()

    def _kill_games(self):
        for proc in self.launched_processes:
            try:
                proc.terminate()
                proc.kill()
            except Exception as e:
                print(f"[Cleanup] {e}")
        self.launched_processes.clear()
        if IS_WINDOWS:
            for exe in ["cs2.exe", "VALORANT.exe", "TslGame.exe", "GTA5.exe", "Cyberpunk2077.exe",
                        "RDR2.exe", "FC24.exe", "NFSUnbound.exe", "NBA2K24.exe", "dota2.exe", "LeagueClient.exe"]:
                try:
                    subprocess.run(["taskkill", "/F", "/IM", exe], capture_output=True)
                except Exception:
                    pass

    def _handle_game_launch(self, game):
        exe = game.get('executable_path')
        cwd_ = game.get('working_directory')
        name = game.get('name', 'Game')
        print(f"[Launcher] '{name}' -> {exe}")
        if exe and os.path.exists(exe):
            try:
                cwd = None
                if cwd_ and os.path.exists(cwd_):
                    cwd = cwd_
                elif exe and os.path.dirname(exe):
                    cwd = os.path.dirname(exe)
                proc = subprocess.Popen([exe], cwd=cwd)
                self.launched_processes.append(proc)
                print(f"[Launcher] PID: {proc.pid}")
                self.main_window.show_launch_success(name)
                # Launcher minimize qilinmaydi (bu Windows ish stolini
                # ochib qo'yardi) — faqat orqa qatlamga o'tadi, shunda
                # o'yin uning ustida ochiladi, lekin o'yin yopilsa
                # mijoz baribir launcherni ko'radi, ish stolini emas.
                self.main_window.yield_to_app()
                # Bu ikkitasi birga ishlaydi: launcherni orqaga
                # o'tkazish + yangi ishga tushgan o'yin oynasini
                # (topilgan zahoti) majburan old planga chiqarish —
                # Windows fon jarayonining fokus o'g'irlashini
                # cheklashini chetlab o'tish uchun. Oyna paydo bo'lishi
                # bir necha soniya cho'zilishi mumkin, shuning uchun
                # fon oqimida amalga oshiriladi.
                if IS_WINDOWS:
                    threading.Thread(
                        target=bring_process_window_to_front,
                        args=(proc.pid,), daemon=True
                    ).start()
            except Exception as e:
                print(f"[Launcher] Error: {e}")
                self.main_window.show_launch_error(f"Xatolik: {e}")
        else:
            print(f"[Launcher] Not found: {exe}")
            self.main_window.show_launch_error("O'yin fayli topilmadi, iltimos admonga murojaat qiling")

    def _tick(self):
        if self.current_status in ('ACTIVE', 'WARNING'):
            if self.time_remaining > 0:
                self.time_remaining -= 1
                self.main_window.update_timer(self.time_remaining)
            else:
                self._lock()

    @staticmethod
    def _get_local_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
        except Exception:
            return '127.0.0.1'
        finally:
            s.close()

    def _run_sync(self):
        threading.Thread(target=self._run_ws, daemon=True).start()
        local_ip = self._get_local_ip()
        while True:
            try:
                headers = {"X-API-Key": self.api_key} if self.api_key else {}
                r = requests.post(
                    f"{self.server_url}/api/computers/heartbeat/",
                    json={"pc_name": self.pc_name, "ip_address": local_ip},
                    headers=headers, timeout=4
                )
                if r.status_code == 200:
                    # WebSocket ulangan bo'lsa, holat yangilanishlari shu
                    # yerdan emas, real-vaqtli push orqali keladi — aks
                    # holda kechikkan heartbeat javobi eski holatni qayta
                    # tiklab, ekranda miltillashga sabab bo'lishi mumkin edi.
                    if not self.ws_connected:
                        self.signals.status_updated.emit(r.json())
                elif r.status_code in (401, 403):
                    print(f"[Heartbeat] Ruxsat rad etildi ({r.status_code}) — "
                          f"config.json'dagi api_key server bilan mos kelmayapti.")
            except Exception as e:
                print(f"[Heartbeat] {e}")
            time.sleep(self.heartbeat_interval)

    def _run_ws(self):
        try:
            import websocket
        except ImportError:
            print("[WS] websocket-client o'rnatilmagan, faqat heartbeat orqali sinxronlanadi")
            return

        def on_message(ws, msg):
            try:
                d = json.loads(msg)
                if d.get('type') == 'BAR_ORDER_UPDATE':
                    o = d.get('order', {})
                    obj = o.get('order', o)
                    if obj.get('computer_name') == self.pc_name:
                        self.signals.bar_order_updated.emit(obj)
                else:
                    pc = d.get('pc', {})
                    if pc.get('name') == self.pc_name:
                        self.signals.status_updated.emit(pc)
                    elif d.get('action') == 'EMERGENCY_LOCK_ALL':
                        self.signals.status_updated.emit({'status': 'LOCKED', 'time_remaining': 0})
            except Exception as e:
                print(f"[WS] {e}")
        def on_open(ws):
            self.ws_connected = True
            print("[WS] Connected")
        def on_error(ws, e):
            self.ws_connected = False
            print(f"[WS] Error: {e}")
        def on_close(ws, code, msg):
            self.ws_connected = False
            print(f"[WS] Closed ({code})")
        separator = '&' if '?' in self.ws_url else '?'
        ws_url_with_key = f"{self.ws_url}{separator}api_key={self.api_key}" if self.api_key else self.ws_url
        while True:
            try:
                ws = websocket.WebSocketApp(ws_url_with_key, on_message=on_message, on_error=on_error, on_close=on_close)
                ws.run_forever()
            except Exception as e:
                print(f"[WS] Failed: {e}")
            self.ws_connected = False
            time.sleep(3)


# ──────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────
def main():
    # Production kiosk rejimida hech qanday qora konsol oynasi
    # ko'rinmasligi kerak (u locker oynasi ustiga chiqib, mijozga
    # ko'rinib qolishi mumkin edi). Shuning uchun: (1) barcha
    # print()/xato chiqishini konsol o'rniga log faylga yo'naltiramiz,
    # (2) konsol oynasining o'zini yashiramiz. Log fayl keyinroq
    # muammoni tekshirish uchun kerak bo'ladi (client_locker.log).
    if IS_WINDOWS:
        try:
            log_path = os.path.join(CLIENT_DIR, "client_locker.log")
            log_file = open(log_path, "a", buffering=1, encoding="utf-8")
            sys.stdout = log_file
            sys.stderr = log_file
            print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} — ishga tushdi =====")
        except Exception:
            pass
        try:
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
        except Exception:
            pass

    # PyQt6 ba'zan Qt slot/callback ichidagi Python xatosini konsolga chiqarmasdan
    # yutib yuborishi mumkin — bu esa "sababsiz" shaffof/qotgan oyna kabi
    # tashxis qo'yish qiyin bo'lgan holatlarga olib kelishi mumkin. Har qanday
    # ushlanmagan xato albatta konsolga (endi — log faylga) to'liq traceback
    # bilan chiqishini kafolatlaymiz.
    def _excepthook(exc_type, exc_value, exc_tb):
        import traceback
        print("[UNHANDLED EXCEPTION]")
        traceback.print_exception(exc_type, exc_value, exc_tb)
    sys.excepthook = _excepthook

    # Dastur ishga tushishidan oldin: serverda yangi klient versiyasi
    # bo'lsa, uni o'rnatib, nolmas kod bilan chiqamiz — watchdog.bat
    # buni "kutilmagan to'xtash" deb hisoblab, yangi kod bilan qayta
    # ishga tushiradi (kod 0 bo'lganda esa qayta ishga tushirmas edi).
    try:
        with open("config.json", 'r') as f:
            _cfg = json.load(f)
        _server_url = _cfg.get("server_url", "").rstrip('/')
        _api_key = _cfg.get("api_key", "")
        if _server_url and check_and_apply_update(_server_url, _api_key):
            sys.exit(17)
    except SystemExit:
        raise
    except Exception as e:
        print(f"[Update] Ishga tushishda yangilanishni tekshirib bo'lmadi: {e}")

    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QWidget {
            background-color: #060911;
            color: #e2e8f0;
            font-family: 'Segoe UI', 'Inter', 'SF Pro', -apple-system, sans-serif;
        }
    """)
    if IS_WINDOWS:
        register_global_hotkeys(app)

    _locker = ClientLockerApp("config.json")
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
