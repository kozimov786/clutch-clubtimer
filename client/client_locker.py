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
import types
import requests

from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal, QObject, QDate, QByteArray, QBuffer, QIODevice, QPointF
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QPushButton, QFrame, QHBoxLayout, QScrollArea, QGridLayout,
    QLineEdit, QGraphicsDropShadowEffect, QSizePolicy, QStackedWidget,
    QSpacerItem, QMessageBox, QDialog, QSlider, QCheckBox
)
from PyQt6.QtGui import QFont, QColor, QPixmap, QGuiApplication, QIcon, QPainter, QPen

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
            # KeepAspectRatio ("object-fit: contain") — rasm butunlay
            # ko'rinadi, hech qismi kesilmaydi. Oldin
            # KeepAspectRatioByExpanding ishlatilgan edi ("cover"), bu esa
            # nisbati mos kelmagan rasmlarni kuchli kattalashtirib,
            # ko'pini kesib tashlar edi (xira/juda yaqinlashtirilgan
            # ko'rinish sababi shu edi).
            scaled = pixmap.scaled(
                target_w, target_h,
                Qt.AspectRatioMode.KeepAspectRatio,
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

    def customer_login_async(self, phone, password, on_done=None):
        """Mijoz qulf ekranida telefon+parol kiritganda chaqiriladi.
        Birinchi marta kirishda server kiritilgan parolni avtomatik
        shu mijozning paroli sifatida saqlaydi (o'z-o'zini ro'yxatdan
        o'tkazish) — PC holatiga ta'sir qilmaydi, faqat mijoz
        ma'lumotini qaytaradi."""
        def _post():
            try:
                r = requests.post(
                    f"{self.server_url}/api/customers/kiosk_login/",
                    json={"phone": phone, "password": password},
                    headers=self._headers(),
                    timeout=12
                )
                ok = r.status_code == 200
                if on_done:
                    on_done(ok, r.json() if r.content else {})
            except Exception as e:
                print(f"[API] customer_login: {e}")
                if on_done:
                    on_done(False, {"error": "Server bilan aloqa yo'q"})
        threading.Thread(target=_post, daemon=True).start()

    def customer_start_session_async(self, pc_id, session_token, on_done=None):
        """Mijoz qulf ekranida "Kompyuterni ochish" tugmasini bosganda
        chaqiriladi — seans balansdan bosqichma-bosqich yechiladigan
        Open Time rejimida boshlanadi. Muvaffaqiyatli bo'lsa, PC
        odatdagi status-sinxronlash yo'li (heartbeat/WebSocket) orqali
        o'zi ochiladi — bu yerda alohida "unlock" chaqirilmaydi.

        session_token — kiosk_login javobida qaytgan, taxmin qilib
        bo'lmaydigan, muddati cheklangan token (xom customer_id EMAS —
        server endi shu tokenni talab qiladi, aks holda istalgan kiosk
        boshqa mijozning ID raqamini kiritib, uning balansidan pul
        yechib qo'yishi mumkin edi)."""
        def _post():
            try:
                r = requests.post(
                    f"{self.server_url}/api/computers/{pc_id}/customer_start_session/",
                    json={"session_token": session_token},
                    headers=self._headers(),
                    timeout=12
                )
                ok = r.status_code == 200
                if on_done:
                    on_done(ok, r.json() if r.content else {})
            except Exception as e:
                print(f"[API] customer_start_session: {e}")
                if on_done:
                    on_done(False, {"error": "Server bilan aloqa yo'q"})
        threading.Thread(target=_post, daemon=True).start()

    def fetch_my_activity_async(self, session_token, on_done=None):
        """Mijozning "Kabinet" oynasidagi "Jami harakatlar" ro'yxati
        uchun — o'z tranzaksiyalari va seanslar tarixi."""
        def _post():
            try:
                r = requests.post(
                    f"{self.server_url}/api/customers/my_activity/",
                    json={"session_token": session_token},
                    headers=self._headers(),
                    timeout=10
                )
                ok = r.status_code == 200
                if on_done:
                    on_done(ok, r.json() if r.content else {})
            except Exception as e:
                print(f"[API] my_activity: {e}")
                if on_done:
                    on_done(False, {"error": "Server bilan aloqa yo'q"})
        threading.Thread(target=_post, daemon=True).start()

    def change_password_async(self, session_token, old_password, new_password, on_done=None):
        """Mijoz "Kabinet" oynasida o'z parolini o'zgartirganda."""
        def _post():
            try:
                r = requests.post(
                    f"{self.server_url}/api/customers/kiosk_change_password/",
                    json={"session_token": session_token, "old_password": old_password, "new_password": new_password},
                    headers=self._headers(),
                    timeout=10
                )
                ok = r.status_code == 200
                if on_done:
                    on_done(ok, r.json() if r.content else {})
            except Exception as e:
                print(f"[API] change_password: {e}")
                if on_done:
                    on_done(False, {"error": "Server bilan aloqa yo'q"})
        threading.Thread(target=_post, daemon=True).start()

    def customer_stop_session_async(self, pc_id, session_token, on_done=None):
        """Mijoz "Kabinet" oynasidan o'zi balansidan ochgan seansni
        o'zi to'xtatganda. Muvaffaqiyatli bo'lsa, PC odatdagi
        status-sinxronlash orqali o'zi qulflanadi."""
        def _post():
            try:
                r = requests.post(
                    f"{self.server_url}/api/computers/{pc_id}/customer_stop_session/",
                    json={"session_token": session_token},
                    headers=self._headers(),
                    timeout=10
                )
                ok = r.status_code == 200
                if on_done:
                    on_done(ok, r.json() if r.content else {})
            except Exception as e:
                print(f"[API] customer_stop_session: {e}")
                if on_done:
                    on_done(False, {"error": "Server bilan aloqa yo'q"})
        threading.Thread(target=_post, daemon=True).start()


# "FILTER BY" pillslari endi qattiq kodlangan ro'yxatdan EMAS, balki
# config.json'dagi fallback_games (yoki serverdan kelgan o'yinlar)
# ro'yxatida haqiqatda uchraydigan category qiymatlaridan dinamik
# quriladi (GamesPage._rebuild_category_filters) — shu orqali "Settings"
# kabi qo'shimcha kategoriyalar ham avtomatik pill oladi, "Sports"/
# "Action" kabi hech qaysi o'yinda ishlatilmagan bo'sh pillslar esa
# ko'rinmaydi. Bu ro'yxat faqat ma'lum kategoriyalar uchun ikonka
# tanlashda ishlatiladi.
GAME_CATEGORY_ICONS = {
    'fps': '🎯', 'shooter': '🎯',
    'action': '⚔️', 'rpg': '⚔️',
    'sports': '🏎️', 'racing': '🏎️',
    'strategy': '🎮', 'moba': '🎮',
    'settings': '⚙️',
}
GAME_CATEGORY_DEFAULT_ICON = '📁'


def _game_category_icon_for(cat):
    return GAME_CATEGORY_ICONS.get((cat or '').lower(), GAME_CATEGORY_DEFAULT_ICON)


# ──────────────────────────────────────────────────────────────────────────────
#  4b. CORNER-BRACKET FRAME — dizayn tizimining asosiy vizual belgisi
#      (referens dizaynlardagi kartalarning burchaklarida ko'ringan
#      kichik "L" shakldagi chiziqlar). QSS bilan chizib bo'lmagani
#      uchun paintEvent orqali qo'lda chiziladi — shu tufayli har
#      qanday o'lchamdagi widget'da avtomatik moslashadi.
# ──────────────────────────────────────────────────────────────────────────────
# Dizayn tizimi — aniq rang palitrasi (foydalanuvchi bergan
# spetsifikatsiya asosida, "Clutch Zone" referens dizaynlari).
COLOR_BG = "#08090C"
COLOR_PANEL = "#101216"
COLOR_PANEL_BORDER = "rgba(255,255,255,0.07)"
COLOR_INPUT_BG = "#0A0B0E"
COLOR_INPUT_BORDER = "#1F222A"
COLOR_CYAN = "#00F3FF"
COLOR_CYAN_GLOW = "rgba(0,243,255,0.4)"
COLOR_ROSE = "#F0A8B3"
COLOR_VIOLET = "#8B5CF6"
COLOR_CRIMSON_BG = "#231013"
COLOR_CRIMSON_BORDER = "#7A1F28"

GRADIENT_BTN_QSS = f"""
    QPushButton {{
        color: #060911; font-weight: bold;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {COLOR_CYAN}, stop:1 {COLOR_VIOLET});
        border: none; border-radius: 10px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4df6ff, stop:1 #a78bfa);
    }}
    QPushButton:disabled {{ color: #475569; background: rgba(255,255,255,0.08); }}
"""

CRIMSON_BTN_QSS = f"""
    QPushButton {{
        background: {COLOR_CRIMSON_BG}; color: #f87171;
        border: 1px solid {COLOR_CRIMSON_BORDER}; border-radius: 9px;
    }}
    QPushButton:hover {{ background: #2c1418; }}
"""

INPUT_QSS = f"""
    QLineEdit {{
        background: {COLOR_INPUT_BG}; color: #e2e8f0;
        border: 1px solid {COLOR_INPUT_BORDER};
        border-radius: 10px; padding: 0 16px; font-size: 13px;
    }}
    QLineEdit:focus {{ background: #12151c; border: 1px solid {COLOR_CYAN}; }}
"""


def serif_font(size, weight=QFont.Weight.Bold):
    """'Cinzel Decorative'/'Playfair Display' odatiy Windows shriftlari
    EMAS — kiosk PC'larda o'rnatilmagan bo'lishi mumkin. QFont.setFamilies()
    orqali zanjir beriladi: topilmasa avtomatik Georgia'ga (Windows'da
    har doim mavjud) o'tadi."""
    f = QFont()
    f.setFamilies(["Cinzel Decorative", "Playfair Display", "Georgia"])
    f.setPointSize(size)
    f.setWeight(weight)
    return f


class BracketFrame(QFrame):
    """4 burchakli HUD chizig'i. `bracket_color2` berilsa, ikki xil
    rang navbatma-navbat qo'llaniladi (masalan o'yin kartalarida
    referens dizayndagi kabi cyan+pushti aralash burchaklar)."""
    def __init__(self, parent=None, bracket_color=COLOR_CYAN, bracket_color2=None, bracket_len=16, bracket_width=2):
        super().__init__(parent)
        self._bracket_color = QColor(bracket_color)
        self._bracket_color2 = QColor(bracket_color2) if bracket_color2 else self._bracket_color
        self._bracket_len = bracket_len
        self._bracket_w = bracket_width

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._bracket_color)
        pen.setWidth(self._bracket_w)
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        painter.setPen(pen)
        w, h = self.width(), self.height()
        seg = self._bracket_len
        m = 2
        # 4 burchak — HUD uslubidagi "L" shakllar (bosh rang: yuqori-chap, pastki-o'ng)
        painter.drawLine(m, m, m + seg, m)
        painter.drawLine(m, m, m, m + seg)
        painter.drawLine(w - m, h - m, w - m - seg, h - m)
        painter.drawLine(w - m, h - m, w - m, h - m - seg)
        # ikkinchi rang: yuqori-o'ng, pastki-chap
        pen2 = QPen(self._bracket_color2)
        pen2.setWidth(self._bracket_w)
        pen2.setCapStyle(Qt.PenCapStyle.SquareCap)
        painter.setPen(pen2)
        painter.drawLine(w - m, m, w - m - seg, m)
        painter.drawLine(w - m, m, w - m, m + seg)
        painter.drawLine(m, h - m, m + seg, h - m)
        painter.drawLine(m, h - m, m, h - m - seg)
        painter.end()


# ──────────────────────────────────────────────────────────────────────────────
#  5. LOCK SCREEN
# ──────────────────────────────────────────────────────────────────────────────
class LockScreenWidget(QWidget):
    # PC holatiga (qulflanganligiga) hech qanday ta'sir qilmaydi — faqat
    # loglash uchun yuqoriga (ClientLockerApp'gacha) uzatiladi.
    login_succeeded = pyqtSignal(dict)
    # ApiClient.customer_login_async fon oqimida ishlaydi; Qt widget'larini
    # to'g'ridan-to'g'ri fon oqimidan o'zgartirib bo'lmaydi (bu loyihada
    # ilgari xuddi shu xato jiddiy render muammolariga sabab bo'lgan edi),
    # shuning uchun natija signal orqali asosiy (GUI) oqimga uzatiladi.
    _login_result_ready = pyqtSignal(bool, dict)
    # "Kompyuterni ochish" (balansdan): ClientLockerApp'gacha uzatiladi
    # (u pc_id'ni biladi), natija esa xuddi login kabi thread-xavfsiz
    # signal orqali qaytadi. customer_id EMAS, session_token (str)
    # uzatiladi — server endi shuni talab qiladi.
    unlock_requested = pyqtSignal(str)
    unlock_result_ready = pyqtSignal(bool, dict)

    def __init__(self, pc_name="PC-01", api_client=None, parent=None):
        super().__init__(parent)
        self.pc_name = pc_name
        self.api_client = api_client
        self.logged_in_customer = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(f"background-color: {COLOR_BG};")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Referens dizayndagi kabi — BITTA yagona karta: yuqorida logo/
        # brend, keyin (holatga qarab) login forma YOKI profil, pastda
        # stansiya holati qatori. QGraphicsDropShadowEffect() ATAYLAB
        # ishlatilmagan: QGraphicsEffect ba'zi Windows kompyuterlarda
        # (cheklangan/eskirgan GPU-render yo'lida) butun oynani noto'g'ri
        # (bo'sh/shaffof) chizib qo'yishi mumkin bo'lgan ma'lum Qt muammosi.
        card = BracketFrame(bracket_color=COLOR_CYAN, bracket_len=18)
        card.setObjectName("lockCard")
        card.setFixedWidth(440)
        card.setStyleSheet(f"""
            QFrame#lockCard {{
                background: {COLOR_PANEL};
                border: 1px solid {COLOR_PANEL_BORDER};
                border-radius: 18px;
            }}
            QLabel {{ border: none; background: transparent; }}
        """)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(40, 34, 40, 26)
        cl.setSpacing(6)
        cl.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        logo_pix_path = os.path.join(ASSETS_DIR, "clutch_logo_mark.png")
        if os.path.exists(logo_pix_path):
            logo_label = QLabel()
            pix = QPixmap(logo_pix_path)
            if not pix.isNull():
                logo_label.setPixmap(pix.scaled(52, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(logo_label)
            cl.addSpacing(10)

        brand = QLabel("CLUTCH ZONE")
        brand.setFont(serif_font(24))
        brand.setStyleSheet(f"color: {COLOR_ROSE}; letter-spacing: 2px;")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(brand)
        cl.addSpacing(20)

        # ── Login qismi ──
        self.login_widget = QWidget()
        lw = QVBoxLayout(self.login_widget)
        lw.setContentsMargins(0, 0, 0, 0)
        lw.setSpacing(12)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("👤   Telefon raqam")
        self.phone_input.setFixedHeight(42)
        self.phone_input.setStyleSheet(INPUT_QSS)
        self.phone_input.returnPressed.connect(self._on_login_clicked)
        lw.addWidget(self.phone_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("🔒   Parol")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setFixedHeight(42)
        self.password_input.setStyleSheet(INPUT_QSS)
        self.password_input.returnPressed.connect(self._on_login_clicked)
        lw.addWidget(self.password_input)

        self.login_error = QLabel("")
        self.login_error.setStyleSheet("color: #ef4444; font-size: 11px;")
        self.login_error.setWordWrap(True)
        self.login_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.login_error.hide()
        lw.addWidget(self.login_error)

        self.login_btn = QPushButton("KIRISH")
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.setFixedHeight(44)
        self.login_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.login_btn.setStyleSheet(GRADIENT_BTN_QSS)
        self.login_btn.clicked.connect(self._on_login_clicked)
        lw.addWidget(self.login_btn)

        hint = QLabel("Birinchi marta kirsangiz, kiritgan parolingiz saqlanib qoladi.")
        hint.setFont(QFont("Segoe UI", 9))
        hint.setStyleSheet("color: #475569;")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lw.addWidget(hint)

        cl.addWidget(self.login_widget)

        # ── Profil qismi (login qilingandan keyin) ──
        self.profile_widget = QWidget()
        pw = QVBoxLayout(self.profile_widget)
        pw.setContentsMargins(0, 0, 0, 0)
        pw.setSpacing(8)

        self.profile_name = QLabel("")
        self.profile_name.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self.profile_name.setStyleSheet("color: #ffffff;")
        self.profile_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pw.addWidget(self.profile_name)

        self.profile_balance = QLabel("")
        self.profile_balance.setFont(QFont("Consolas", 22, QFont.Weight.Bold))
        self.profile_balance.setStyleSheet(f"color: {COLOR_CYAN};")
        self.profile_balance.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pw.addWidget(self.profile_balance)

        self.profile_bonus = QLabel("")
        self.profile_bonus.setFont(QFont("Segoe UI", 11))
        self.profile_bonus.setStyleSheet("color: #94a3b8;")
        self.profile_bonus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pw.addWidget(self.profile_bonus)
        pw.addSpacing(6)

        self.unlock_error = QLabel("")
        self.unlock_error.setStyleSheet("color: #ef4444; font-size: 11px;")
        self.unlock_error.setWordWrap(True)
        self.unlock_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unlock_error.hide()
        pw.addWidget(self.unlock_error)

        self.unlock_btn = QPushButton("🔓  KOMPYUTERNI OCHISH")
        self.unlock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unlock_btn.setFixedHeight(44)
        self.unlock_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.unlock_btn.setStyleSheet(GRADIENT_BTN_QSS)
        self.unlock_btn.clicked.connect(self._on_unlock_clicked)
        pw.addWidget(self.unlock_btn)

        logout_btn = QPushButton("Chiqish")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setFixedHeight(34)
        logout_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.05); color: #94a3b8;
                border: 1px solid rgba(255,255,255,0.12); border-radius: 8px;
            }
            QPushButton:hover { color: #e2e8f0; }
        """)
        logout_btn.clicked.connect(self._on_logout_clicked)
        pw.addWidget(logout_btn)

        cl.addWidget(self.profile_widget)
        self.profile_widget.hide()

        # ── Pastki qator: stansiya holati ──
        cl.addSpacing(18)
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: rgba(255,255,255,0.08); border: none;")
        cl.addWidget(divider)
        cl.addSpacing(12)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #ef4444; font-size: 10px;")
        bottom_row.addWidget(self.status_dot)
        self.pc_label = QLabel(f"STATION {self.pc_name}")
        self.pc_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.pc_label.setStyleSheet("color: #64748b; letter-spacing: 1px;")
        bottom_row.addWidget(self.pc_label)
        bottom_row.addStretch(1)
        self.lock_status_label = QLabel("QULFLANGAN")
        self.lock_status_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.lock_status_label.setStyleSheet("color: #ef4444; letter-spacing: 1px;")
        bottom_row.addWidget(self.lock_status_label)
        cl.addLayout(bottom_row)

        main_layout.addWidget(card)

        self._login_result_ready.connect(self._apply_login_result)
        self.unlock_result_ready.connect(self._apply_unlock_result)

    def set_pc_name(self, pc_name):
        self.pc_name = pc_name
        self.pc_label.setText(f"STATION {pc_name}")

    def _on_login_clicked(self):
        phone = self.phone_input.text().strip()
        password = self.password_input.text()
        if not phone or not password:
            self._show_login_error("Telefon raqam va parolni kiriting")
            return
        if not self.api_client:
            return
        self.login_btn.setEnabled(False)
        self.login_btn.setText("Tekshirilmoqda...")
        self.api_client.customer_login_async(
            phone, password,
            on_done=lambda ok, data: self._login_result_ready.emit(ok, data)
        )

    def _apply_login_result(self, ok, data):
        self.login_btn.setEnabled(True)
        self.login_btn.setText("KIRISH")
        if not ok:
            self._show_login_error(data.get('error', "Xatolik yuz berdi"))
            return
        self.logged_in_customer = data
        self.login_error.hide()
        self.password_input.clear()
        self._show_profile(data)
        self.login_succeeded.emit(data)

    def _show_login_error(self, msg):
        self.login_error.setText(msg)
        self.login_error.show()

    def _show_profile(self, data):
        self.profile_name.setText(data.get('full_name', ''))
        try:
            balance = float(data.get('balance', 0))
        except (TypeError, ValueError):
            balance = 0
        self.profile_balance.setText(f"{balance:,.0f} UZS")
        self.profile_bonus.setText(f"🎁 {data.get('bonus_points', 0)} bonus ball")
        self.unlock_error.hide()
        self.unlock_btn.setEnabled(True)
        self.unlock_btn.setText("🔓  KOMPYUTERNI OCHISH")
        self.login_widget.hide()
        self.profile_widget.show()

    def _on_logout_clicked(self):
        self.reset_login_state()

    def reset_login_state(self):
        """Mijoz "Chiqish"ni bossa YOKI seans (masalan balans tugab)
        tugab, PC qayta qulflansa chaqiriladi — aks holda keyingi
        mijoz oldingi mijozning profilini ko'rib qolishi mumkin edi."""
        self.logged_in_customer = None
        self.phone_input.clear()
        self.password_input.clear()
        self.login_error.hide()
        self.profile_widget.hide()
        self.login_widget.show()

    def _on_unlock_clicked(self):
        if not self.logged_in_customer:
            return
        self.unlock_error.hide()
        self.unlock_btn.setEnabled(False)
        self.unlock_btn.setText("Ochilmoqda...")
        self.unlock_requested.emit(self.logged_in_customer.get('session_token', ''))

    def _apply_unlock_result(self, ok, data):
        if ok:
            # PC odatdagi status-sinxronlash orqali (heartbeat/WebSocket)
            # o'zi ACTIVE holatga o'tadi — bu yerda qo'shimcha hech
            # narsa qilish shart emas, tugma holati ham muhim emas
            # (butun LockScreenWidget hozir yashirinib, launcher
            # ko'rsatiladi).
            return
        self.unlock_btn.setEnabled(True)
        self.unlock_btn.setText("🔓  KOMPYUTERNI OCHISH")
        self.unlock_error.setText(data.get('error', "Xatolik yuz berdi"))
        self.unlock_error.show()


# ──────────────────────────────────────────────────────────────────────────────
#  5b. DIZAYN TIZIMI — TopBar/sahifa sarlavhalarida qayta ishlatiladigan
#      kichik widget'lar (referens dizayn: profil kapsulasi, qiya/oval
#      tab almashtirgichlar, taktik radar bezagi).
# ──────────────────────────────────────────────────────────────────────────────
class ProfileCapsule(QFrame):
    """TopBar'ning o'ng tarafidagi "ALEX_GAMER / STATION #042" ovalsimon
    kapsulasi — doiraviy avatar + ism/stansiya matni. Bosilganda Kabinet
    ochiladi."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(48)
        self.setStyleSheet(f"""
            QFrame {{
                background: {COLOR_PANEL};
                border: 1px solid {COLOR_PANEL_BORDER};
                border-radius: 24px;
            }}
        """)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(6, 6, 16, 6)
        lo.setSpacing(10)

        self.avatar = QLabel("?")
        self.avatar.setFixedSize(36, 36)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.avatar.setStyleSheet(f"""
            color: {COLOR_BG}; border: none;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {COLOR_CYAN}, stop:1 {COLOR_VIOLET});
            border-radius: 18px;
        """)
        lo.addWidget(self.avatar)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        self.name_label = QLabel("")
        self.name_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.name_label.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        text_col.addWidget(self.name_label)
        self.station_label = QLabel("")
        self.station_label.setFont(QFont("Segoe UI", 8))
        self.station_label.setStyleSheet("color: #64748b; background: transparent; border: none;")
        text_col.addWidget(self.station_label)
        lo.addLayout(text_col)

    def set_data(self, name, station):
        self.avatar.setText((name or '?')[:1].upper())
        self.name_label.setText((name or '').upper())
        self.station_label.setText(station)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ParallelogramTabBar(QWidget):
    """GamesPage sarlavhasidagi "GAMES LIBRARY / BAR & SNACKS" qiya
    (konsol-uslubidagi) tab almashtirgichi. `active_key` shu widget
    joylashgan sahifaga mos ravishda qat'iy beriladi (masalan
    GamesPage doim "games"ni faol ko'rsatadi) — bosilganda esa
    LauncherPage.inner_stack boshqa sahifaga o'tkaziladi."""
    tab_clicked = pyqtSignal(str)
    TABS = [("games", "🎮  GAMES LIBRARY"), ("bar", "🍔  BAR & SNACKS")]

    def __init__(self, active_key="games", parent=None):
        super().__init__(parent)
        self._active = active_key
        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(2)
        self._buttons = {}
        for key, label in self.TABS:
            btn = QPushButton(label)
            btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(38)
            btn.setMinimumWidth(160)
            btn.clicked.connect(lambda _, k=key: self._on_click(k))
            lo.addWidget(btn)
            self._buttons[key] = btn
        self._apply_styles()

    def _on_click(self, key):
        if key != self._active:
            self.tab_clicked.emit(key)

    def _apply_styles(self):
        for key, btn in self._buttons.items():
            if key == self._active:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {COLOR_PANEL}; color: {COLOR_CYAN};
                        border: 1px solid {COLOR_CYAN}; border-radius: 6px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #0d0f13; color: #64748b;
                        border: 1px solid {COLOR_PANEL_BORDER}; border-radius: 6px;
                    }}
                    QPushButton:hover {{ color: #94a3b8; }}
                """)


class RadarGraphic(QWidget):
    """"COMMAND CENTER"/"Provisions" sarlavhalari ortidagi taktik radar
    dekoratsiyasi — sof bezak, hech qanday funksiyaga ega emas."""
    def __init__(self, size=90, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(255, 255, 255, 28))
        pen.setWidth(1)
        painter.setPen(pen)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        for ratio in (0.32, 0.6, 0.9):
            radius = min(w, h) / 2 * ratio
            painter.drawEllipse(QPointF(cx, cy), radius, radius)
        painter.drawLine(0, int(cy), w, int(cy))
        painter.drawLine(int(cx), 0, int(cx), h)
        painter.end()


class MouseSettingsDialog(QDialog):
    """Sichqoncha sezgirligi — Windows darajasida (SystemParametersInfo
    orqali), shuning uchun har qanday sichqoncha bilan ishlaydi, alohida
    drayver kerak emas. Login talab qilinmaydi — istalgan o'yinchi
    (naqd/karta bilan boshlangan seansda ham) sozlashi mumkin. PC
    qulflanganda standart holatga avtomatik qaytariladi (ClientLockerApp
    tomonidan) — bir mijozning sezgirligi keyingisiga o'tib qolmasligi
    uchun."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sichqoncha sozlamalari")
        self.setModal(True)
        self.setFixedSize(380, 300)
        self.setStyleSheet(f"QDialog {{ background: {COLOR_BG}; }} QLabel {{ color: #e2e8f0; border: none; background: transparent; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        title = QLabel("🖱️  SICHQONCHA SOZLAMALARI")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        root.addWidget(title)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Sezgirlik (sensitivity)"))
        row1.addStretch(1)
        self.speed_val_label = QLabel("10")
        self.speed_val_label.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        self.speed_val_label.setStyleSheet(f"color: {COLOR_CYAN};")
        row1.addWidget(self.speed_val_label)
        root.addLayout(row1)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setMinimum(1)
        self.speed_slider.setMaximum(20)
        self.speed_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 6px; background: {COLOR_INPUT_BG}; border-radius: 3px; }}
            QSlider::handle:horizontal {{
                width: 18px; margin: -6px 0; border-radius: 9px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {COLOR_CYAN}, stop:1 {COLOR_VIOLET});
            }}
            QSlider::sub-page:horizontal {{ background: {COLOR_CYAN}; border-radius: 3px; }}
        """)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        root.addWidget(self.speed_slider)

        low_high_row = QHBoxLayout()
        low = QLabel("Past")
        low.setStyleSheet("color: #64748b; font-size: 10px;")
        low_high_row.addWidget(low)
        low_high_row.addStretch(1)
        high = QLabel("Yuqori")
        high.setStyleSheet("color: #64748b; font-size: 10px;")
        low_high_row.addWidget(high)
        root.addLayout(low_high_row)

        root.addSpacing(6)

        self.accel_checkbox = QCheckBox("Sichqoncha tezlashishi (Enhance pointer precision)")
        self.accel_checkbox.setStyleSheet("color: #e2e8f0;")
        self.accel_checkbox.toggled.connect(self._on_accel_toggled)
        root.addWidget(self.accel_checkbox)
        accel_hint = QLabel("FPS o'yinlarda ko'pchilik o'yinchilar buni o'chirib qo'yadi (aim uchun barqaror sezgirlik).")
        accel_hint.setWordWrap(True)
        accel_hint.setStyleSheet("color: #475569; font-size: 10px;")
        root.addWidget(accel_hint)

        root.addStretch(1)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("Standartga qaytarish")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setFixedHeight(36)
        reset_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06); color: #94a3b8;
                border: 1px solid rgba(255,255,255,0.12); border-radius: 8px;
            }
            QPushButton:hover { color: #e2e8f0; }
        """)
        reset_btn.clicked.connect(self._on_reset_clicked)
        btn_row.addWidget(reset_btn)

        close_btn = QPushButton("Yopish")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedHeight(36)
        close_btn.setStyleSheet(GRADIENT_BTN_QSS)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        # Joriy qiymatlar bilan boshlanadi (oldingi mijoz o'zgartirgan
        # bo'lsa ham, hozirgi haqiqiy holat ko'rsatiladi).
        self.speed_slider.blockSignals(True)
        self.speed_slider.setValue(get_mouse_speed())
        self.speed_slider.blockSignals(False)
        self.speed_val_label.setText(str(get_mouse_speed()))
        self.accel_checkbox.blockSignals(True)
        self.accel_checkbox.setChecked(get_mouse_acceleration())
        self.accel_checkbox.blockSignals(False)

    def _on_speed_changed(self, value):
        self.speed_val_label.setText(str(value))
        set_mouse_speed(value)

    def _on_accel_toggled(self, checked):
        set_mouse_acceleration(checked)

    def _on_reset_clicked(self):
        self.speed_slider.setValue(MOUSE_DEFAULT_SPEED)  # valueChanged -> set_mouse_speed
        self.accel_checkbox.setChecked(True)              # toggled -> set_mouse_acceleration


# ──────────────────────────────────────────────────────────────────────────────
#  6. TOP BAR
# ──────────────────────────────────────────────────────────────────────────────
class TopBar(QFrame):
    """Referens dizayn bo'yicha: chapda logo + balans + qolgan vaqt,
    o'ngda Yutuqlar havolasi + profil kapsulasi. O'yinlar/Bar orasidagi
    navigatsiya endi bu yerda EMAS — har bir sahifaning o'z sarlavhasida
    (ParallelogramTabBar) joylashgan."""
    achievements_requested = pyqtSignal()
    mouse_settings_requested = pyqtSignal()
    cabinet_requested = pyqtSignal()

    def __init__(self, pc_name="PC-01", parent=None):
        super().__init__(parent)
        self.pc_name = pc_name
        self.setFixedHeight(84)
        self.setStyleSheet(f"""
            QFrame#topBar {{
                background-color: {COLOR_BG};
                border-bottom: 1px solid {COLOR_PANEL_BORDER};
            }}
        """)
        self.setObjectName("topBar")

        lo = QHBoxLayout(self)
        lo.setContentsMargins(28, 0, 28, 0)
        lo.setSpacing(20)

        # Logo
        logo_row = QHBoxLayout()
        logo_row.setSpacing(10)
        logo_pix_path = os.path.join(ASSETS_DIR, "clutch_logo_mark.png")
        logo_label = QLabel()
        if os.path.exists(logo_pix_path):
            pix = QPixmap(logo_pix_path)
            if not pix.isNull():
                logo_label.setPixmap(pix.scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo_row.addWidget(logo_label)
        title = QLabel("CLUTCH ZONE")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff; letter-spacing: 1px;")
        logo_row.addWidget(title)
        logo_widget = QWidget()
        logo_widget.setLayout(logo_row)
        lo.addWidget(logo_widget)

        lo.addSpacing(20)

        # Balans (faqat mijoz tizimga kirgan bo'lsa ko'rinadi)
        self.balance_badge = QLabel("")
        self.balance_badge.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.balance_badge.setStyleSheet(f"color: {COLOR_CYAN};")
        self.balance_badge.hide()
        lo.addWidget(self.balance_badge)

        # Qolgan vaqt
        self.time_badge = QLabel("")
        self.time_badge.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.time_badge.setStyleSheet("color: #94a3b8;")
        lo.addWidget(self.time_badge)

        lo.addStretch(1)

        # Yutuqlar — referens dizaynda alohida ko'rsatilmagan, lekin
        # mavjud funksiyani yo'qotmaslik uchun kichik ikonka-tugma
        # sifatida saqlab qolinadi.
        self.achievements_btn = QPushButton("🏆")
        self.achievements_btn.setFont(QFont("Segoe UI", 13))
        self.achievements_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.achievements_btn.setFixedSize(38, 38)
        self.achievements_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLOR_INPUT_BG}; border: 1px solid {COLOR_INPUT_BORDER};
                border-radius: 19px;
            }}
            QPushButton:hover {{ border: 1px solid {COLOR_CYAN}; }}
        """)
        self.achievements_btn.clicked.connect(self.achievements_requested.emit)
        lo.addWidget(self.achievements_btn)

        # Sichqoncha sozlamalari — login shart emas, istalgan o'yinchi
        # (naqd/karta seansida ham) sezgirlikni o'zgartira olishi kerak.
        self.mouse_settings_btn = QPushButton("🖱️")
        self.mouse_settings_btn.setFont(QFont("Segoe UI", 13))
        self.mouse_settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mouse_settings_btn.setFixedSize(38, 38)
        self.mouse_settings_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLOR_INPUT_BG}; border: 1px solid {COLOR_INPUT_BORDER};
                border-radius: 19px;
            }}
            QPushButton:hover {{ border: 1px solid {COLOR_CYAN}; }}
        """)
        self.mouse_settings_btn.clicked.connect(self.mouse_settings_requested.emit)
        lo.addWidget(self.mouse_settings_btn)

        # Mijoz kabineti — faqat kimdir qulf ekranida tizimga kirgan
        # bo'lsa ko'rinadi (odatiy holatda yashirin).
        self.cabinet_capsule = ProfileCapsule()
        self.cabinet_capsule.clicked.connect(self.cabinet_requested.emit)
        self.cabinet_capsule.hide()
        lo.addWidget(self.cabinet_capsule)

        # PC status pill
        self.status_pill = QLabel(f"{self.pc_name} · ACTIVE")
        self.status_pill.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.status_pill.setStyleSheet(f"""
            color: {COLOR_CYAN};
            background: rgba(0,243,255,0.08);
            border: 1px solid rgba(0,243,255,0.35);
            border-radius: 14px;
            padding: 8px 16px;
        """)
        lo.addWidget(self.status_pill)

    def set_status(self, pc_name, status_text):
        self.status_pill.setText(f"{pc_name} · {status_text}")

    def set_time_remaining(self, text):
        self.time_badge.setText(f"⏱  {text}" if text else "")

    def set_logged_in_customer(self, data):
        if data:
            try:
                balance = float(data.get('balance', 0))
            except (TypeError, ValueError):
                balance = 0
            self.balance_badge.setText(f"💳  {balance:,.0f} UZS")
            self.balance_badge.show()
            self.cabinet_capsule.set_data(data.get('full_name', ''), f"STATION {self.pc_name}")
            self.cabinet_capsule.show()
        else:
            self.balance_badge.hide()
            self.cabinet_capsule.hide()


# ──────────────────────────────────────────────────────────────────────────────
#  6b. CUSTOMER CABINET (mijozning shaxsiy kabineti — parol, tarix)
# ──────────────────────────────────────────────────────────────────────────────
class CustomerCabinetPage(QWidget):
    """Mijozning "Kabinet" bo'limi — endi modal QDialog EMAS, balki
    Games/Bar sahifalari singari LauncherPage.inner_stack ichidagi
    to'liq huquqli sahifa (foydalanuvchi talabi: "u modal emas bar,
    oyin menusi singari sahifa bolishi kere")."""
    # API so'rovlar fon oqimida ishlaydi; natijalar Qt widget'larini
    # xavfsiz yangilash uchun signal orqali asosiy oqimga uzatiladi.
    _pw_result_ready = pyqtSignal(bool, dict)
    _activity_result_ready = pyqtSignal(bool, dict)
    # "Vaqtni to'xtatish" — bu sahifa o'zi pc_id'ni bilmaydi (uni faqat
    # ClientLockerApp biladi), shuning uchun so'rov yuqoriga
    # (LauncherPage -> MainWindow -> ClientLockerApp) uzatiladi.
    stop_session_requested = pyqtSignal(str)
    back_requested = pyqtSignal()

    CARD_STYLE = f"""
        QFrame#cabinetCard {{
            background: {COLOR_PANEL};
            border: 1px solid {COLOR_PANEL_BORDER};
            border-radius: 14px;
        }}
        QLabel {{ border: none; background: transparent; }}
    """

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.customer_data = {}
        self.setStyleSheet(f"background-color: {COLOR_BG};")

        self._pw_result_ready.connect(self._apply_password_result)
        self._activity_result_ready.connect(self._apply_activity_result)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(28, 20, 28, 24)
        root.setSpacing(16)

        back_btn = QPushButton("←  ORQAGA")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setFixedHeight(30)
        back_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        back_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #94a3b8;
                border: none; text-align: left;
            }
            QPushButton:hover { color: #e2e8f0; }
        """)
        back_btn.clicked.connect(self.back_requested.emit)
        back_row = QHBoxLayout()
        back_row.addWidget(back_btn)
        back_row.addStretch(1)
        root.addLayout(back_row)

        root.addWidget(self._build_header_card())

        columns = QHBoxLayout()
        columns.setSpacing(16)
        columns.addWidget(self._build_identity_card(), 1)
        columns.addWidget(self._build_security_card(), 1)
        columns.addWidget(self._build_stats_card(), 1)
        root.addLayout(columns, 1)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def set_customer(self, data):
        """Sahifa bir marta yaratiladi va qayta ishlatiladi — har safar
        "Kabinet" ochilganda shu metod chaqirilib, ko'rsatilayotgan
        ma'lumotlar joriy tizimga kirgan mijozga mos yangilanadi."""
        self.customer_data = data or {}
        full_name = self.customer_data.get('full_name', '')
        phone = self.customer_data.get('phone', '')

        self.avatar_label.setText((full_name or '?')[:1].upper())
        self.name_label.setText(full_name)
        self.phone_label.setText(f"📞  {phone}")
        try:
            bal = float(self.customer_data.get('balance', 0))
        except (TypeError, ValueError):
            bal = 0
        self.header_balance_label.setText(f"{bal:,.0f} UZS")
        self.identity_name_val.setText(full_name)
        self.identity_phone_val.setText(phone)

        self.old_pw_input.clear()
        self.new_pw_input.clear()
        self.pw_status.hide()
        self.playtime_val.setText("—")
        self.station_val.setText("—")
        self._load_activity()

    def _build_header_card(self):
        card = BracketFrame(bracket_color=COLOR_CYAN, bracket_len=14)
        card.setObjectName("cabinetCard")
        card.setFixedHeight(150)
        card.setStyleSheet(self.CARD_STYLE)

        row = QHBoxLayout(card)
        row.setContentsMargins(24, 20, 24, 20)
        row.setSpacing(20)

        # Avatar — haqiqiy rasm yo'q, shuning uchun ismning bosh
        # harfi bilan gradient "belgi" ko'rsatiladi.
        self.avatar_label = QLabel("?")
        self.avatar_label.setFixedSize(84, 84)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setFont(serif_font(30))
        self.avatar_label.setStyleSheet(f"""
            color: {COLOR_BG};
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {COLOR_CYAN}, stop:1 {COLOR_VIOLET});
            border-radius: 16px;
        """)
        row.addWidget(self.avatar_label)

        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        status_row = QLabel("🟢  ONLINE")
        status_row.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        status_row.setStyleSheet("color: #22c55e; letter-spacing: 1px;")
        info_col.addWidget(status_row)

        self.name_label = QLabel("")
        self.name_label.setFont(serif_font(22))
        self.name_label.setStyleSheet("color: #ffffff;")
        info_col.addWidget(self.name_label)

        self.phone_label = QLabel("")
        self.phone_label.setStyleSheet("color: #64748b; font-size: 12px;")
        info_col.addWidget(self.phone_label)
        info_col.addStretch(1)
        row.addLayout(info_col, 1)

        balance_box = QFrame()
        balance_box.setStyleSheet(f"""
            background: rgba(0,243,255,0.05);
            border: 1px solid {COLOR_CYAN};
            border-radius: 10px;
        """)
        bb = QVBoxLayout(balance_box)
        bb.setContentsMargins(18, 10, 18, 10)
        bb.setSpacing(2)
        balance_tag = QLabel("JORIY BALANS")
        balance_tag.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        balance_tag.setStyleSheet("color: #64748b; letter-spacing: 1px;")
        balance_tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bb.addWidget(balance_tag)
        self.header_balance_label = QLabel("0 UZS")
        self.header_balance_label.setFont(QFont("Consolas", 20, QFont.Weight.Bold))
        self.header_balance_label.setStyleSheet(f"color: {COLOR_CYAN};")
        self.header_balance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bb.addWidget(self.header_balance_label)

        topup_btn = QPushButton("+  BALANSNI TO'LDIRISH")
        topup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        topup_btn.setFixedHeight(32)
        topup_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        topup_btn.setStyleSheet(GRADIENT_BTN_QSS)
        topup_btn.clicked.connect(self._on_topup_info_clicked)

        right_col = QVBoxLayout()
        right_col.setSpacing(8)
        right_col.addWidget(balance_box)
        right_col.addWidget(topup_btn)
        row.addLayout(right_col)

        return card

    def _on_topup_info_clicked(self):
        QMessageBox.information(
            self, "Balansni to'ldirish",
            "Balansni to'ldirish uchun klub administratoriga (kassaga) murojaat qiling."
        )

    def _build_identity_card(self):
        card = BracketFrame(bracket_color=COLOR_CYAN, bracket_len=12)
        card.setObjectName("cabinetCard")
        card.setStyleSheet(self.CARD_STYLE)
        lo = QVBoxLayout(card)
        lo.setContentsMargins(18, 16, 18, 16)
        lo.setSpacing(10)

        title = QLabel("🪪  IDENTITY")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title.setStyleSheet("color: #e2e8f0;")
        lo.addWidget(title)

        name_tag = QLabel("ISM")
        name_tag.setStyleSheet("color: #64748b; font-size: 9px; letter-spacing: 1px;")
        lo.addWidget(name_tag)
        self.identity_name_val = QLabel("")
        self.identity_name_val.setStyleSheet("color: #e2e8f0; font-size: 13px; font-weight: bold;")
        lo.addWidget(self.identity_name_val)

        phone_tag = QLabel("TELEFON RAQAM")
        phone_tag.setStyleSheet("color: #64748b; font-size: 9px; letter-spacing: 1px;")
        lo.addWidget(phone_tag)
        self.identity_phone_val = QLabel("")
        self.identity_phone_val.setStyleSheet("color: #e2e8f0; font-size: 13px; font-weight: bold;")
        lo.addWidget(self.identity_phone_val)

        hint = QLabel("Ma'lumotlarni o'zgartirish uchun administratorga murojaat qiling.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #475569; font-size: 10px;")
        lo.addWidget(hint)
        lo.addStretch(1)
        return card

    def _build_security_card(self):
        card = BracketFrame(bracket_color=COLOR_CYAN, bracket_len=12)
        card.setObjectName("cabinetCard")
        card.setStyleSheet(self.CARD_STYLE)
        lo = QVBoxLayout(card)
        lo.setContentsMargins(18, 16, 18, 16)
        lo.setSpacing(10)

        title = QLabel("🔐  SECURITY")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title.setStyleSheet("color: #e2e8f0;")
        lo.addWidget(title)

        self.old_pw_input = QLineEdit()
        self.old_pw_input.setPlaceholderText("Joriy parol")
        self.old_pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.old_pw_input.setFixedHeight(36)
        self.old_pw_input.setStyleSheet(INPUT_QSS)
        lo.addWidget(self.old_pw_input)

        self.new_pw_input = QLineEdit()
        self.new_pw_input.setPlaceholderText("Yangi parol")
        self.new_pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_pw_input.setFixedHeight(36)
        self.new_pw_input.setStyleSheet(INPUT_QSS)
        lo.addWidget(self.new_pw_input)

        self.pw_status = QLabel("")
        self.pw_status.setWordWrap(True)
        self.pw_status.setStyleSheet("color: #ef4444; font-size: 10px;")
        self.pw_status.hide()
        lo.addWidget(self.pw_status)

        self.pw_submit_btn = QPushButton("UPDATE PASSWORD")
        self.pw_submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pw_submit_btn.setFixedHeight(36)
        self.pw_submit_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.pw_submit_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06); color: #e2e8f0;
                border: 1px solid rgba(255,255,255,0.15); border-radius: 9px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); }
            QPushButton:disabled { color: #475569; }
        """)
        self.pw_submit_btn.clicked.connect(self._on_change_password_clicked)
        lo.addWidget(self.pw_submit_btn)

        lo.addSpacing(6)

        stop_btn = QPushButton("⏻  VAQTNI TO'XTATISH")
        stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        stop_btn.setFixedHeight(36)
        stop_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        stop_btn.setStyleSheet(CRIMSON_BTN_QSS)
        stop_btn.clicked.connect(self._on_stop_session_clicked)
        lo.addWidget(stop_btn)

        lo.addStretch(1)
        return card

    def _build_stats_card(self):
        w = QWidget()
        lo = QVBoxLayout(w)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(12)

        def _stat_box(tag_text):
            box = BracketFrame(bracket_color=COLOR_CYAN, bracket_len=10)
            box.setObjectName("cabinetCard")
            box.setStyleSheet(self.CARD_STYLE)
            bl = QVBoxLayout(box)
            bl.setContentsMargins(16, 10, 16, 10)
            bl.setSpacing(2)
            tag = QLabel(tag_text)
            tag.setStyleSheet("color: #64748b; font-size: 9px; letter-spacing: 1px;")
            bl.addWidget(tag)
            val = QLabel("—")
            val.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
            val.setStyleSheet("color: #e2e8f0;")
            bl.addWidget(val)
            return box, val

        playtime_box, self.playtime_val = _stat_box("TOTAL PLAYTIME")
        lo.addWidget(playtime_box)

        station_box, self.station_val = _stat_box("FAV STATION")
        lo.addWidget(station_box)

        history_card = BracketFrame(bracket_color=COLOR_CYAN, bracket_len=12)
        history_card.setObjectName("cabinetCard")
        history_card.setStyleSheet(self.CARD_STYLE)
        hl = QVBoxLayout(history_card)
        hl.setContentsMargins(16, 14, 16, 14)
        hl.setSpacing(8)
        history_title = QLabel("🕐  HISTORY")
        history_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        hl.addWidget(history_title)

        self.activity_area = QScrollArea()
        self.activity_area.setWidgetResizable(True)
        self.activity_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.activity_container = QWidget()
        self.activity_layout = QVBoxLayout(self.activity_container)
        self.activity_layout.setSpacing(6)
        self.activity_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.activity_loading = QLabel("Yuklanmoqda...")
        self.activity_loading.setStyleSheet("color: #64748b; font-size: 11px;")
        self.activity_layout.addWidget(self.activity_loading)
        self.activity_area.setWidget(self.activity_container)
        hl.addWidget(self.activity_area, 1)

        lo.addWidget(history_card, 1)
        return w

    def _on_change_password_clicked(self):
        old_pw = self.old_pw_input.text()
        new_pw = self.new_pw_input.text()
        if not old_pw or not new_pw:
            self._show_pw_status("Ikkala maydonni ham to'ldiring", error=True)
            return
        self.pw_submit_btn.setEnabled(False)
        self.pw_submit_btn.setText("Yangilanmoqda...")
        self.api_client.change_password_async(
            self.customer_data.get('session_token', ''), old_pw, new_pw,
            on_done=lambda ok, data: self._pw_result_ready.emit(ok, data)
        )

    def _apply_password_result(self, ok, data):
        self.pw_submit_btn.setEnabled(True)
        self.pw_submit_btn.setText("Parolni yangilash")
        if not ok:
            self._show_pw_status(data.get('error', "Xatolik yuz berdi"), error=True)
            return
        self.old_pw_input.clear()
        self.new_pw_input.clear()
        self._show_pw_status("Parol muvaffaqiyatli yangilandi ✓", error=False)

    def _show_pw_status(self, msg, error=True):
        self.pw_status.setStyleSheet(f"color: {'#ef4444' if error else '#22c55e'}; font-size: 11px;")
        self.pw_status.setText(msg)
        self.pw_status.show()

    def _load_activity(self):
        token = self.customer_data.get('session_token', '')
        self.api_client.fetch_my_activity_async(
            token, on_done=lambda ok, data: self._activity_result_ready.emit(ok, data)
        )

    def _on_stop_session_clicked(self):
        reply = QMessageBox.question(
            self, "Tasdiqlash",
            "Haqiqatan ham vaqtni to'xtatmoqchimisiz? Kompyuter darhol qulflanadi.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.stop_session_requested.emit(self.customer_data.get('session_token', ''))
        self.back_requested.emit()

    def _apply_activity_result(self, ok, data):
        while self.activity_layout.count():
            item = self.activity_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        if not ok:
            err = QLabel(data.get('error', "Yuklab bo'lmadi"))
            err.setStyleSheet("color: #ef4444;")
            self.activity_layout.addWidget(err)
            return

        sessions = data.get('sessions', [])
        total_minutes = 0
        station_counts = {}
        for s in sessions:
            try:
                total_minutes += int(s.get('duration_minutes') or 0)
            except (TypeError, ValueError):
                pass
            cname = s.get('computer_name')
            if cname:
                station_counts[cname] = station_counts.get(cname, 0) + 1
        if hasattr(self, 'playtime_val'):
            hours, mins = divmod(total_minutes, 60)
            self.playtime_val.setText(f"{hours} soat {mins} daq" if total_minutes else "—")
        if hasattr(self, 'station_val'):
            fav = max(station_counts, key=station_counts.get) if station_counts else None
            self.station_val.setText(fav or "—")

        rows = []
        for t in data.get('transactions', []):
            sign = '+' if t.get('type') == 'TOPUP' else '−'
            color = '#22c55e' if t.get('type') == 'TOPUP' else '#ef4444'
            try:
                amount = float(t.get('amount', 0))
            except (TypeError, ValueError):
                amount = 0
            rows.append((t.get('created_at', ''), t.get('type_display', ''), f"{sign}{amount:,.0f} UZS", color))
        for s in sessions:
            try:
                price = float(s.get('total_price', 0))
            except (TypeError, ValueError):
                price = 0
            rows.append((s.get('start_time', ''), f"🎮 {s.get('computer_name', '')}", f"−{price:,.0f} UZS", '#ef4444'))

        rows.sort(key=lambda r: r[0] or '', reverse=True)

        if not rows:
            empty = QLabel("Hali harakatlar yo'q")
            empty.setStyleSheet("color: #64748b;")
            self.activity_layout.addWidget(empty)
            return

        for created_at, label, amount_text, color in rows[:60]:
            row = QHBoxLayout()
            date_label = QLabel(str(created_at)[:16].replace('T', ' '))
            date_label.setStyleSheet("color: #64748b; font-size: 10px;")
            row.addWidget(date_label)
            type_label = QLabel(label)
            type_label.setStyleSheet("color: #e2e8f0; font-size: 11px;")
            row.addWidget(type_label, 1)
            amount_label = QLabel(amount_text)
            amount_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
            amount_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(amount_label)
            row_widget = QWidget()
            row_widget.setLayout(row)
            self.activity_layout.addWidget(row_widget)


# ──────────────────────────────────────────────────────────────────────────────
#  7. RESPONSIVE FLOW GRID (o'yin/mahsulot kartalari uchun)
# ──────────────────────────────────────────────────────────────────────────────
class FlowGrid(QWidget):
    """ResponsiveGrid bilan bir xil moslashuvchan panjara mantig'i,
    lekin o'zining QScrollArea'siz — BarPage'da bir nechta kategoriya
    bo'limini (har biri o'z sarlavhasi bilan) BITTA umumiy scroll
    ichiga ketma-ket joylash uchun ishlatiladi."""
    def __init__(self, card_min_width=220, spacing=18, margins=(0, 0, 0, 0), parent=None):
        super().__init__(parent)
        self.card_min_width = card_min_width
        self.spacing = spacing
        self._items = []
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(spacing)
        self.grid_layout.setContentsMargins(*margins)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

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
        cols = self._columns_for_width(self.width())
        for index, widget in enumerate(self._items):
            row, col = divmod(index, cols)
            self.grid_layout.addWidget(widget, row, col)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._items:
            self._relayout()


class ResponsiveGrid(QScrollArea):
    def __init__(self, card_min_width=260, spacing=20, parent=None):
        super().__init__(parent)
        self.card_min_width = card_min_width
        self.spacing = spacing
        self._items = []
        self.setWidgetResizable(True)
        self.setStyleSheet(f"QScrollArea {{ border: none; background-color: {COLOR_BG}; }}")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # QScrollArea'ning ichki viewport widget'i alohida bo'lib, yuqoridagi
        # stylesheet uni har doim ham to'liq qamrab olavermaydi (ayniqsa
        # panjara bo'sh bo'lganda, tizim palitrasidagi och rang ko'rinib
        # qolishi mumkin edi) — shuning uchun uni ham aniq belgilaymiz.
        self.viewport().setStyleSheet(f"background-color: {COLOR_BG};")

        self.container = QWidget()
        self.container.setStyleSheet(f"background-color: {COLOR_BG};")
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
class GameCard(BracketFrame):
    launch_requested = pyqtSignal(dict)

    def __init__(self, game, parent=None):
        super().__init__(bracket_color=COLOR_CYAN, bracket_color2=COLOR_ROSE, bracket_len=12)
        self.game = game
        self.setFixedWidth(260)
        self.setObjectName("gameCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame#gameCard {{
                background: {COLOR_PANEL};
                border: 1px solid {COLOR_PANEL_BORDER};
                border-radius: 14px;
            }}
            QFrame#gameCard:hover {{
                border: 1px solid {COLOR_CYAN_GLOW};
            }}
        """)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        self.cover = QLabel()
        self.cover.setFixedSize(258, 150)
        self.cover.setStyleSheet("background-color: #16181d; border-top-left-radius: 14px; border-top-right-radius: 14px;")
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setText("🎮")
        self.cover.setFont(QFont("Segoe UI", 32))
        lo.addWidget(self.cover)

        cover_path = game.get('cover_path')
        if cover_path:
            load_image_async(cover_path, self.cover)

        cat_key = game.get('category', '')
        badge = QLabel(cat_key.upper() if cat_key else '', self.cover)
        badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        badge.setStyleSheet(f"""
            color: {COLOR_CYAN}; background: rgba(0,243,255,0.12);
            border: 1px solid rgba(0,243,255,0.3);
            border-radius: 8px; padding: 3px 8px;
        """)
        if cat_key:
            badge.adjustSize()
            badge.move(10, 10)

        self._name_text = game.get('name', 'Unknown')
        self.name_label = QLabel(self._name_text)
        self.name_label.setFont(serif_font(13))
        self.name_label.setStyleSheet("color: #ffffff; padding: 14px 10px;")
        self.name_label.setWordWrap(True)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(self.name_label)

        # Ba'zi o'yinlar ochilishi bir necha soniya cho'zilishi mumkin —
        # shu orada sabrsizlanib qayta-qayta bosilsa, o'yinning o'zi
        # "faqat bitta nusxa ishlashi mumkin" xatosi bilan qulashiga
        # sabab bo'lardi. Bosilgandan keyin karta vaqtincha bloklanadi
        # va holatini ko'rsatadi.
        self._launching = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._launching:
            self._launching = True
            self.name_label.setText("⏳  ISHGA TUSHIRILMOQDA...")
            self.setCursor(Qt.CursorShape.WaitCursor)
            self.launch_requested.emit(self.game)
            QTimer.singleShot(6000, self._reset_launch_state)
        super().mousePressEvent(event)

    def _reset_launch_state(self):
        self._launching = False
        try:
            self.name_label.setText(self._name_text)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        except RuntimeError:
            pass  # karta panjara qayta yuklanganda allaqachon o'chirilgan bo'lishi mumkin


# ──────────────────────────────────────────────────────────────────────────────
#  9. GAMES PAGE (kategoriya, qidiruv, panjara)
# ──────────────────────────────────────────────────────────────────────────────
class GamesPage(QWidget):
    game_launch_requested = pyqtSignal(dict)
    tab_switch_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {COLOR_BG};")
        self._all_games = []
        self._active_category = "all"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sahifa sarlavhasi + taktik radar bezagi + SYS.ONLINE teg
        header_row = QHBoxLayout()
        header_row.setContentsMargins(28, 20, 28, 4)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        dash = QLabel("—")
        dash.setStyleSheet(f"color: {COLOR_CYAN}; font-size: 20px;")
        title_row.addWidget(dash)
        page_title = QLabel("CLUTCH ZONE")
        page_title.setFont(serif_font(26))
        page_title.setStyleSheet("color: #ffffff; letter-spacing: 1px;")
        title_row.addWidget(page_title)
        header_row.addLayout(title_row)
        header_row.addStretch(1)
        header_row.addWidget(RadarGraphic(size=70))
        online_tag = QLabel("SYS.ONLINE")
        online_tag.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        online_tag.setStyleSheet("""
            color: #22c55e; background: rgba(34,197,94,0.10);
            border: 1px solid rgba(34,197,94,0.3);
            border-radius: 8px; padding: 4px 10px; letter-spacing: 1px;
        """)
        header_row.addWidget(online_tag, 0, Qt.AlignmentFlag.AlignTop)
        header_widget0 = QWidget()
        header_widget0.setLayout(header_row)
        # Games/Bar sahifalari o'rtasida almashishda tarkib "sakramasligi"
        # uchun — ikkala sahifaning sarlavha bloki bir xil balandlikda
        # bo'lishi shart (BarPage'da xuddi shu qiymatlar ishlatiladi).
        header_widget0.setFixedHeight(94)
        root.addWidget(header_widget0)

        # Sahifa almashtirgichi (GAMES LIBRARY / BAR & SNACKS)
        switcher_row = QHBoxLayout()
        switcher_row.setContentsMargins(28, 8, 28, 0)
        self.page_tabs = ParallelogramTabBar(active_key="games")
        self.page_tabs.tab_clicked.connect(self.tab_switch_requested.emit)
        switcher_row.addWidget(self.page_tabs)
        switcher_row.addStretch(1)
        switcher_widget = QWidget()
        switcher_widget.setLayout(switcher_row)
        switcher_widget.setFixedHeight(46)
        root.addWidget(switcher_widget)

        # Category filter row — pillslar set_games()'da, config.json'dagi
        # o'yinlarda haqiqatda uchraydigan category qiymatlaridan dinamik
        # quriladi (pastdagi _rebuild_category_filters).
        self.cat_row = QHBoxLayout()
        self.cat_row.setContentsMargins(28, 14, 28, 10)
        self.cat_row.setSpacing(10)
        self.filter_label = QLabel("FILTER BY:")
        self.filter_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.filter_label.setStyleSheet("color: #64748b; letter-spacing: 1px;")
        self.cat_row.addWidget(self.filter_label)
        self.cat_buttons = {}
        self._rebuild_category_filters([])
        cat_row_widget = QWidget()
        cat_row_widget.setLayout(self.cat_row)
        cat_row_widget.setFixedHeight(58)
        root.addWidget(cat_row_widget)

        # Error banner
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(28, 0, 28, 14)
        toolbar.setSpacing(14)

        self.error_banner = QLabel("")
        self.error_banner.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.error_banner.setStyleSheet("color: #ef4444; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.3); border-radius: 10px; padding: 10px 16px;")
        self.error_banner.hide()
        toolbar.addWidget(self.error_banner, 1)

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
        # O'yinlarda haqiqatda uchraydigan kategoriyalarni (birinchi
        # ko'rinish tartibida, takrorlanmasdan) yig'ib, filter
        # pillslarini shularga moslab qayta quramiz.
        seen = set()
        categories = []
        for g in games:
            cat = (g.get('category') or '').strip()
            if cat and cat.lower() not in seen:
                seen.add(cat.lower())
                categories.append(cat)
        self._rebuild_category_filters(categories)
        if self._active_category != "all" and self._active_category.lower() not in seen:
            self._active_category = "all"
        self._refresh_grid()

    def _rebuild_category_filters(self, categories):
        while self.cat_row.count() > 1:  # 0-indeks — "FILTER BY:" yorlig'i
            item = self.cat_row.takeAt(1)
            if item.widget():
                item.widget().setParent(None)
        self.cat_buttons = {}

        all_btn = QPushButton("🌐  BARCHASI")
        all_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        all_btn.setFixedHeight(34)
        all_btn.clicked.connect(lambda: self._select_category("all"))
        self.cat_row.addWidget(all_btn)
        self.cat_buttons["all"] = all_btn

        for cat in categories:
            btn = QPushButton(f"{_game_category_icon_for(cat)}  {cat.upper()}")
            btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(34)
            btn.clicked.connect(lambda _, k=cat: self._select_category(k))
            self.cat_row.addWidget(btn)
            self.cat_buttons[cat] = btn

        self.cat_row.addStretch(1)
        self._apply_category_styles()

    def _select_category(self, key):
        self._active_category = key
        self._apply_category_styles()
        self._refresh_grid()

    def _apply_category_styles(self):
        for key, btn in self.cat_buttons.items():
            if key == self._active_category:
                btn.setStyleSheet(f"""
                    QPushButton {{ background: {COLOR_VIOLET}; color: #ffffff; border: none; border-radius: 17px; padding: 0 16px; }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{ background: {COLOR_PANEL}; color: #94a3b8; border: 1px solid {COLOR_PANEL_BORDER}; border-radius: 17px; padding: 0 16px; }}
                    QPushButton:hover {{ border: 1px solid {COLOR_CYAN_GLOW}; color: #e2e8f0; }}
                """)

    def _refresh_grid(self):
        games = self._all_games
        if self._active_category != "all":
            games = [g for g in games if (g.get('category') or '').lower() == self._active_category.lower()]

        cards = []
        for g in games:
            card = GameCard(g)
            card.launch_requested.connect(self.game_launch_requested.emit)
            cards.append(card)
        self.grid.set_items(cards)


# ──────────────────────────────────────────────────────────────────────────────
#  10. BAR MENU PAGE
# ──────────────────────────────────────────────────────────────────────────────
def _category_icon_for(name):
    n = (name or '').lower()
    if any(k in n for k in ('drink', 'ichim', 'energy', 'sok', 'suv', 'napitok')):
        return '⚡'
    if any(k in n for k in ('snack', 'ovqat', 'burger', 'fast', 'taom', 'food')):
        return '🍔'
    return '🛒'


class ProductCard(BracketFrame):
    qty_changed = pyqtSignal(dict, int)

    def __init__(self, product, parent=None):
        super().__init__(bracket_color=COLOR_CYAN, bracket_len=10)
        self.product = product
        self.qty = 0
        try:
            self.stock = max(0, int(product.get('stock', 0)))
        except (TypeError, ValueError):
            self.stock = 0
        self.setFixedWidth(220)
        self.setObjectName("productCard")
        self.setStyleSheet(f"""
            QFrame#productCard {{ background: {COLOR_PANEL}; border: 1px solid {COLOR_PANEL_BORDER}; border-radius: 14px; }}
        """)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        self.cover = QLabel()
        self.cover.setFixedSize(218, 120)
        self.cover.setStyleSheet("background-color: #16181d; border-top-left-radius: 14px; border-top-right-radius: 14px;")
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setText("🍿")
        self.cover.setFont(QFont("Segoe UI", 26))
        lo.addWidget(self.cover)
        img = product.get('image')
        if img:
            load_image_async(img, self.cover)

        try:
            price = float(product.get('price', 0))
        except (TypeError, ValueError):
            price = 0.0
        price_badge = QLabel(f"{price:,.0f} UZS".replace(',', ' '), self.cover)
        price_badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        price_badge.setStyleSheet(f"""
            color: {COLOR_CYAN}; background: rgba(0,243,255,0.12);
            border: 1px solid rgba(0,243,255,0.3);
            border-radius: 8px; padding: 3px 8px;
        """)
        price_badge.adjustSize()
        price_badge.move(218 - price_badge.width() - 8, 8)

        name = QLabel(product.get('name', ''))
        name.setFont(serif_font(12))
        name.setStyleSheet("color: #ffffff; padding: 10px 12px 8px 12px;")
        name.setWordWrap(True)
        lo.addWidget(name)

        self.stock_label = QLabel(self._stock_hint_text())
        self.stock_label.setFont(QFont("Segoe UI", 9))
        self.stock_label.setStyleSheet("color: #64748b; padding: 0 12px 6px 12px;")
        lo.addWidget(self.stock_label)

        stepper = QHBoxLayout()
        stepper.setContentsMargins(12, 0, 12, 12)
        self.minus_btn = QPushButton("−")
        self.plus_btn = QPushButton("+")
        for b in (self.minus_btn, self.plus_btn):
            b.setFixedSize(34, 34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{ background: {COLOR_INPUT_BG}; color: #e2e8f0; border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 8px; font-weight: bold; }}
                QPushButton:hover {{ border: 1px solid {COLOR_CYAN}; color: {COLOR_CYAN}; }}
                QPushButton:disabled {{ color: #334155; border: 1px solid {COLOR_INPUT_BORDER}; }}
            """)
        self.qty_label = QLabel("0")
        self.qty_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.qty_label.setStyleSheet("color: #ffffff;")
        self.qty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qty_label.setFixedWidth(30)
        self.minus_btn.clicked.connect(lambda: self._change_qty(-1))
        self.plus_btn.clicked.connect(lambda: self._change_qty(1))
        stepper.addWidget(self.minus_btn)
        stepper.addWidget(self.qty_label, 1)
        stepper.addWidget(self.plus_btn)
        lo.addLayout(stepper)

        self._update_stepper_state()

    def _stock_hint_text(self):
        if self.stock <= 0:
            return "Omborda yo'q"
        return f"Omborda: {self.stock}"

    def _update_stepper_state(self):
        remaining = self.stock - self.qty
        self.stock_label.setText(f"Omborda: {remaining}" if self.stock > 0 else "Omborda yo'q")
        self.minus_btn.setEnabled(self.qty > 0)
        self.plus_btn.setEnabled(self.qty < self.stock)

    def _change_qty(self, delta):
        # Dashboarddagi (server) mavjud stock miqdoridan oshirib
        # buyurtma qilib bo'lmaydi — "+" tugmasi oxirgi qoldiqqa
        # yetganda o'zi to'xtaydi.
        self.qty = max(0, min(self.stock, self.qty + delta))
        self.qty_label.setText(str(self.qty))
        self._update_stepper_state()
        self.qty_changed.emit(self.product, self.qty)


class BarPage(QWidget):
    # create_order_async'ning on_done callback'i fon oqimidan chaqiriladi —
    # shu signal orqali natija xavfsiz tarzda GUI oqimiga uzatiladi.
    _order_result = pyqtSignal(bool, dict)
    tab_switch_requested = pyqtSignal(str)

    def __init__(self, api_client, pc_name, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.pc_name = pc_name
        self.cart = {}  # product_id -> (product, qty)
        self.setStyleSheet(f"background-color: {COLOR_BG};")
        self._order_result.connect(self._on_order_done)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(28, 20, 28, 4)
        header.setSpacing(10)
        title = QLabel("CLUTCH ZONE BAR")
        title.setFont(serif_font(26))
        title.setStyleSheet("color: #ffffff; letter-spacing: 1px;")
        header.addWidget(title)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {COLOR_ROSE}; font-size: 12px;")
        header.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        header.addStretch(1)

        self.total_label = QLabel("Jami: 0 so'm")
        self.total_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.total_label.setStyleSheet(f"color: {COLOR_CYAN};")
        header.addWidget(self.total_label)

        self.order_btn = QPushButton("✅  BUYURTMA BERISH")
        self.order_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.order_btn.setFixedHeight(40)
        self.order_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.order_btn.setStyleSheet(f"""
            {GRADIENT_BTN_QSS}
            QPushButton {{ padding: 0 18px; }}
        """)
        self.order_btn.clicked.connect(self._place_order)
        self.order_btn.setEnabled(False)
        header.addWidget(self.order_btn)

        header_widget = QWidget()
        header_widget.setLayout(header)
        # GamesPage bilan bir xil balandlik — sahifalar orasida almashishda
        # tarkib "sakramasligi" uchun (GamesPage'dagi header_widget0 bilan
        # bir xil qiymat).
        header_widget.setFixedHeight(94)
        root.addWidget(header_widget)

        # Sahifa almashtirgichi — GamesPage bilan bir xil joylashuv/dizayn
        # (chapda, qiya-tab uslubida).
        switcher_row = QHBoxLayout()
        switcher_row.setContentsMargins(28, 8, 28, 0)
        self.page_tabs = ParallelogramTabBar(active_key="bar")
        self.page_tabs.tab_clicked.connect(self.tab_switch_requested.emit)
        switcher_row.addWidget(self.page_tabs)
        switcher_row.addStretch(1)
        switcher_widget = QWidget()
        switcher_widget.setLayout(switcher_row)
        switcher_widget.setFixedHeight(46)
        root.addWidget(switcher_widget)

        # GamesPage'da shu joyda "FILTER BY" kategoriya qatori bor (58px) —
        # Bar sahifasida unga mos funksiya yo'q, lekin bo'sh joy sahifalar
        # orasida almashishda tarkib bir xil balandlikdan boshlanishi
        # uchun saqlanadi.
        root.addSpacing(58)

        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.status_label.setContentsMargins(28, 0, 28, 8)
        self.status_label.hide()
        root.addWidget(self.status_label)

        self.sections_scroll = QScrollArea()
        self.sections_scroll.setWidgetResizable(True)
        self.sections_scroll.setStyleSheet(f"QScrollArea {{ border: none; background-color: {COLOR_BG}; }}")
        self.sections_scroll.viewport().setStyleSheet(f"background-color: {COLOR_BG};")
        self.sections_container = QWidget()
        self.sections_container.setStyleSheet(f"background-color: {COLOR_BG};")
        self.sections_layout = QVBoxLayout(self.sections_container)
        self.sections_layout.setContentsMargins(28, 10, 28, 28)
        self.sections_layout.setSpacing(22)
        self.sections_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.sections_scroll.setWidget(self.sections_container)
        root.addWidget(self.sections_scroll, 1)

    def set_products(self, products):
        self.cart = {}
        self._update_total()

        while self.sections_layout.count():
            item = self.sections_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)

        groups = {}
        order = []
        for p in products:
            cat = p.get('category_name') or "Boshqa"
            if cat not in groups:
                groups[cat] = []
                order.append(cat)
            groups[cat].append(p)

        for cat in order:
            section_title = QLabel(f"{_category_icon_for(cat)}  {cat}")
            section_title.setFont(serif_font(15))
            section_title.setStyleSheet("color: #ffffff;")
            self.sections_layout.addWidget(section_title)

            flow = FlowGrid(card_min_width=220, spacing=18)
            cards = []
            for p in groups[cat]:
                card = ProductCard(p)
                card.qty_changed.connect(self._on_qty_changed)
                cards.append(card)
            flow.set_items(cards)
            self.sections_layout.addWidget(flow)

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
            self.set_products([])
        else:
            self.status_label.setStyleSheet("color: #ef4444;")
            server_error = data.get('error') if isinstance(data, dict) else None
            self.status_label.setText(f"❌ {server_error}" if server_error else "❌ Buyurtma yuborilmadi, qaytadan urinib ko'ring yoki administratorga murojaat qiling.")
            self.order_btn.setEnabled(len(self.cart) > 0)
        QTimer.singleShot(6000, self.status_label.hide)


# ──────────────────────────────────────────────────────────────────────────────
#  11. ACHIEVEMENTS PAGE (placeholder)
# ──────────────────────────────────────────────────────────────────────────────
class AchievementsPage(QWidget):
    # Bu sahifa TopBar'dagi 🏆 ikonkasi orqali ochiladi (page-local
    # tab almashtirgichlari ichida "Yutuqlar" yo'q) — shuning uchun
    # o'zining "orqaga" tugmasi kerak, aks holda foydalanuvchi
    # Games/Bar'ga qaytish imkoniyatisiz qolib ketadi.
    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {COLOR_BG};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 20, 28, 20)

        back_btn = QPushButton("←  ORQAGA")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setFixedHeight(30)
        back_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        back_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #94a3b8; border: none; text-align: left; }
            QPushButton:hover { color: #e2e8f0; }
        """)
        back_btn.clicked.connect(self.back_requested.emit)
        back_row = QHBoxLayout()
        back_row.addWidget(back_btn)
        back_row.addStretch(1)
        outer.addLayout(back_row)

        lo = QVBoxLayout()
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
        outer.addLayout(lo, 1)


# ──────────────────────────────────────────────────────────────────────────────
#  11b. RUNNING APPS BAR (Windows taskbar'ga o'xshash, lekin locker ichida)
# ──────────────────────────────────────────────────────────────────────────────
class RunningAppsBar(QFrame):
    """Hozir ochiq turgan barcha dasturlarni (Steam, undan ichida ochilgan
    CS2, boshqa ishga tushirilgan o'yin va h.k.) ko'rsatadi. F9 orqali
    launcherga qaytilganda ham bu ro'yxat saqlanib qoladi — har qanday
    dasturga qaytish uchun shu yerdan bosiladi. Hech narsa ishlamayotgan
    bo'lsa butunlay yashirin turadi."""
    app_clicked = pyqtSignal(str)  # exe_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet("""
            QFrame#runningAppsBar {
                background-color: #0a0e17;
                border-top: 1px solid rgba(255,255,255,0.06);
            }
        """)
        self.setObjectName("runningAppsBar")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(28, 6, 28, 6)
        self._layout.setSpacing(10)
        self._apps = {}
        self.hide()

    def set_apps(self, apps):
        """apps: [{'exe': 'steam.exe', 'label': 'Steam'}, ...]"""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._apps = {a['exe']: a for a in apps}

        if not apps:
            self.hide()
            return

        tag = QLabel("ISHLAB TURGAN DASTURLAR:")
        tag.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        tag.setStyleSheet("color: #64748b; letter-spacing: 1px;")
        self._layout.addWidget(tag)

        for a in apps:
            icon_pixmap = a.get('icon')
            btn = QPushButton()
            btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if icon_pixmap:
                btn.setIcon(QIcon(icon_pixmap))
                btn.setIconSize(icon_pixmap.rect().size())
                btn.setText(f"  {a['label']}")
            else:
                btn.setText(f"🎮  {a['label']}")
            btn.setStyleSheet("""
                QPushButton {
                    color: #e2e8f0;
                    background: rgba(0,240,255,0.10);
                    border: 1px solid rgba(0,240,255,0.35);
                    border-radius: 10px;
                    padding: 6px 16px;
                }
                QPushButton:hover { background: rgba(0,240,255,0.22); }
            """)
            exe_key = a['exe']
            btn.clicked.connect(lambda _, e=exe_key: self.app_clicked.emit(e))
            self._layout.addWidget(btn)

        self._layout.addStretch(1)
        self.show()


# ──────────────────────────────────────────────────────────────────────────────
#  12. LAUNCHER PAGE (TopBar + ichki sahifalar)
# ──────────────────────────────────────────────────────────────────────────────
class LauncherPage(QWidget):
    game_launch_requested = pyqtSignal(dict)
    app_switch_requested = pyqtSignal(str)
    cabinet_stop_requested = pyqtSignal(str)
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
        self.logged_in_customer = None
        self.setStyleSheet("background-color: #060911;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.top_bar = TopBar(pc_name=pc_name)
        self.top_bar.achievements_requested.connect(lambda: self._switch_tab("achievements"))
        self.top_bar.mouse_settings_requested.connect(self._open_mouse_settings)
        self.top_bar.cabinet_requested.connect(self._open_cabinet)
        root.addWidget(self.top_bar)

        self.inner_stack = QStackedWidget()
        self.games_page = GamesPage()
        self.games_page.game_launch_requested.connect(self.game_launch_requested.emit)
        self.games_page.tab_switch_requested.connect(self._switch_tab)
        self.bar_page = BarPage(api_client=api_client, pc_name=pc_name)
        self.bar_page.tab_switch_requested.connect(self._switch_tab)
        self.achievements_page = AchievementsPage()
        self.achievements_page.back_requested.connect(lambda: self._switch_tab("games"))
        self.cabinet_page = CustomerCabinetPage(api_client=api_client)
        self.cabinet_page.stop_session_requested.connect(self.cabinet_stop_requested.emit)
        self.cabinet_page.back_requested.connect(self._close_cabinet)
        self.inner_stack.addWidget(self.games_page)          # 0
        self.inner_stack.addWidget(self.bar_page)             # 1
        self.inner_stack.addWidget(self.achievements_page)    # 2
        self.inner_stack.addWidget(self.cabinet_page)         # 3
        root.addWidget(self.inner_stack, 1)
        self._pre_cabinet_index = 0

        self._games_loaded.connect(self.games_page.set_games)
        self._products_loaded.connect(self.bar_page.set_products)

        self.apps_bar = RunningAppsBar()
        self.apps_bar.app_clicked.connect(self.app_switch_requested.emit)
        root.addWidget(self.apps_bar)

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

    def set_time_remaining(self, text):
        self.top_bar.set_time_remaining(text)

    def set_running_apps(self, apps):
        self.apps_bar.set_apps(apps)

    def set_logged_in_customer(self, data):
        self.logged_in_customer = data
        self.top_bar.set_logged_in_customer(data)
        if not data and self.inner_stack.currentWidget() is self.cabinet_page:
            self._close_cabinet()

    def _open_cabinet(self):
        if not self.logged_in_customer:
            return
        current = self.inner_stack.currentIndex()
        if current != self.inner_stack.indexOf(self.cabinet_page):
            self._pre_cabinet_index = current
        self.cabinet_page.set_customer(self.logged_in_customer)
        self.inner_stack.setCurrentWidget(self.cabinet_page)

    def _close_cabinet(self):
        self.inner_stack.setCurrentIndex(self._pre_cabinet_index)

    def _open_mouse_settings(self):
        dialog = MouseSettingsDialog(parent=self)
        dialog.exec()

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
    app_switch_requested_signal = pyqtSignal(str)
    customer_login_signal = pyqtSignal(dict)
    customer_unlock_signal = pyqtSignal(str)
    customer_stop_signal = pyqtSignal(str)

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

        self.lock_page = LockScreenWidget(pc_name=pc_name, api_client=self.api_client)
        self.lock_page.login_succeeded.connect(self.customer_login_signal.emit)
        self.lock_page.unlock_requested.connect(self.customer_unlock_signal.emit)
        self.launcher_page = LauncherPage(
            pc_name=pc_name, server_url=self.server_url, api_client=self.api_client,
            fallback_games=self.fallback_games
        )
        # Mijoz qulf ekranida tizimga kirsa, launcher'ning yuqori
        # panelida ham (o'yinlar menyusiga o'tgandan keyin ham)
        # "Kabinet" ko'rinib turishi kerak.
        self.lock_page.login_succeeded.connect(self.launcher_page.set_logged_in_customer)
        self.launcher_page.game_launch_requested.connect(self.game_launched_signal.emit)
        self.launcher_page.app_switch_requested.connect(self.app_switch_requested_signal.emit)
        self.launcher_page.cabinet_stop_requested.connect(self.customer_stop_signal.emit)

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

    def set_running_apps(self, apps):
        self.launcher_page.set_running_apps(apps)

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
        self.launcher_page.set_time_remaining(f"{h:02d}h {m:02d}m")

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
    # ctypes.windll.* orqali yuklangan DLL'larda ctypes.get_last_error()
    # haqiqiy Windows GetLastError() qiymatini KO'RSATMAYDI — buning
    # uchun DLL use_last_error=True bilan aniq yuklanishi shart, aks
    # holda xato kodlari doim 0 (yolg'on "muvaffaqiyatli") ko'rinadi.
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
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
    # XUDDI SHU 64-bit kesilib qolish xatosi GetModuleHandleW'da ham bor
    # edi — u SetWindowsHookExA'ga hMod sifatida uzatiladigan HMODULE
    # qiymatini qaytaradi. restype aniq belgilanmagani uchun bu qiymat
    # 32-bitga kesilib, SetWindowsHookExA'ga yaroqsiz hMod uzatilar edi
    # (natijada ERROR_MOD_NOT_FOUND / kod 126 bilan muvaffaqiyatsiz
    # tugar edi) — aynan shuning uchun klaviatura hook'i (va shu bilan
    # Alt+Tab bloklash) hech qachon o'rnatilmagan edi.
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]

    hook_id = None; is_hook_enabled = False
    WM_KEYDOWN = 0x0100; WM_SYSKEYDOWN = 0x0104

    def low_level_keyboard_proc(nCode, wParam, lParam):
        global is_hook_enabled, SHOW_LAUNCHER_REQUESTED
        if nCode >= 0 and is_hook_enabled:
            kb = lParam.contents; vk = kb.vkCode; alt = (kb.flags & 0x20) != 0
            if (alt and vk == VK_TAB) or (vk in (VK_LWIN, VK_RWIN)) or \
               (alt and vk == VK_F4) or (alt and vk == VK_ESCAPE):
                return 1
            # F9 uchun IKKINCHI, mustaqil aniqlash yo'li — pastdagi
            # RegisterHotKey (WM_HOTKEY) ba'zi eski, eksklyuziv
            # to'liq ekran (DirectInput) o'yinlarda (masalan Prince of
            # Persia, Pro Evolution Soccer) klaviaturani o'zi
            # "yutib" yuborib, WM_HOTKEY xabarini hech qachon
            # yetkazmasligi mumkin edi — shu sababli F9 vaqti-vaqti
            # bilan ishlamay qolar edi. Past darajali hook esa
            # o'yindan OLDINROQ, xom (raw) darajada ishlaydi, shuning
            # uchun ancha ishonchli. Bu yerda F9 ONCHA Ctrl bosilgan-
            # bosilmaganidan qat'iy nazar aniqlanadi (pastdagi
            # RegisterHotKey esa alohida "faqat F9" va "Ctrl+F9"
            # kombinatsiyalarini ro'yxatdan o'tkazadi — ikkalasi ham
            # shu yerga, xuddi shu natijaga olib keladi).
            if vk == VK_F9 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                SHOW_LAUNCHER_REQUESTED = True
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
    # Ctrl+F9 — F9'ga qo'shimcha (zaxira) kombinatsiya. Scroll Lock EMAS:
    # ko'p (ayniqsa noutbuk) klaviaturalarda bu tugma umuman yo'q. Ctrl
    # va F9 esa HAR QANDAY klaviaturada kafolatlangan mavjud.
    HOTKEY_SHOW_LAUNCHER_2 = 4  # Ctrl+F9

    class HotkeyEventFilter(QAbstractNativeEventFilter):
        def nativeEventFilter(self, eventType, message):
            global EMERGENCY_UNLOCK_REQUESTED, SHOW_LAUNCHER_REQUESTED
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                if msg.wParam in (HOTKEY_EMERGENCY_1, HOTKEY_EMERGENCY_2):
                    print(f"[Hotkey] Favqulodda chiqish kombinatsiyasi aniqlandi (id={msg.wParam})")
                    EMERGENCY_UNLOCK_REQUESTED = True
                elif msg.wParam in (HOTKEY_SHOW_LAUNCHER, HOTKEY_SHOW_LAUNCHER_2):
                    print(f"[Hotkey] F9/Ctrl+F9 aniqlandi (id={msg.wParam})")
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
            user32.RegisterHotKey(None, HOTKEY_SHOW_LAUNCHER_2, MOD_CONTROL, VK_F9),
        ]
        if all(results):
            print("[Hotkey] Barcha global hotkeylar muvaffaqiyatli ro'yxatdan o'tkazildi "
                  "(Ctrl+Alt+Shift+U, Ctrl+Shift+P, F9, Ctrl+F9)")
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

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, ctypes.c_wchar_p, ctypes.POINTER(wintypes.DWORD)
    ]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    def _get_process_full_path(pid):
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return None
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(260)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value
        except Exception:
            pass
        finally:
            kernel32.CloseHandle(h)
        return None

    def _get_process_exe_name(pid):
        """PID'ga tegishli .exe faylining nomini qaytaradi (masalan
        'steam.exe') — Steam kabi ilovalar ko'pincha yangi ishga
        tushirilgan jarayonni allaqachon ochiq turgan asosiy nusxaga
        signal berib, o'zi darhol chiqib ketadi (shuning uchun asl PID
        bo'yicha oyna qidirish natija bermaydi) — bunday holatda exe
        nomi bo'yicha qidirish kerak bo'ladi."""
        path = _get_process_full_path(pid)
        return os.path.basename(path) if path else None

    _WINDIR = os.environ.get('WINDIR', r'C:\Windows').lower()

    def _is_windows_system_process(pid):
        """C:\\Windows ostidan ishga tushirilgan jarayonlar (Sozlamalar,
        ApplicationFrameHost, qidiruv va h.k.) — foydalanuvchi hech
        qachon "o'yin/dastur" deb o'ylamaydigan, "ishlab turgan
        dasturlar" panjarasida ko'rinmasligi kerak bo'lgan tizim
        jarayonlari. Bu — qattiq kodlangan nom ro'yxatidan ko'ra
        umumiyroq va kelajakda paydo bo'ladigan shunga o'xshash
        jarayonlarni ham avtomatik qamrab oladi."""
        path = _get_process_full_path(pid)
        return bool(path) and path.lower().startswith(_WINDIR)

    _IGNORED_FALLBACK_EXES = {
        'explorer.exe', 'clutch-zone', 'python.exe', 'pythonw.exe',
        'searchhost.exe', 'shellexperiencehost.exe', 'textinputhost.exe',
        # Steam/GPU-drayver fon yordamchi jarayonlari — mijoz "dastur"
        # deb o'ylamaydigan, alohida oynasi bo'lmasligi kerak bo'lgan
        # jarayonlar (ba'zan yashirin/nolinchi oynasi ko'rinib qolishi
        # mumkin edi).
        'steamwebhelper.exe', 'steamservice.exe', 'gameoverlayui.exe',
        'windowsterminal.exe', 'openconsole.exe',
        'nvcontainer.exe', 'nvidia share.exe', 'nvsphelper64.exe',
        'nvbackend.exe', 'nvdisplay.container.exe',
    }

    def _find_window_for_pid(pid, exe_name=None, own_hwnd=None, timeout=10.0):
        """PID yoki exe nomi bo'yicha qidiradi. Ikkisi ham topilmasa (masalan
        Steam admin huquqida ishlab, OpenProcess() rad etilsa), oxirgi
        chora sifatida — EnumWindows Z-tartibda (eng oldindagidan
        boshlab) sanaganidan foydalanib, bizning oynamiz va ma'lum
        tizim jarayonlaridan boshqa birinchi ko'rinadigan sarlavhali
        oynani qaytaradi."""
        result = []
        fallback = []

        def _enum_proc(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            GW_OWNER = 4
            if user32.GetWindow(hwnd, GW_OWNER):
                return True  # faqat mustaqil (owner'siz) top-level oynalar
            if user32.GetWindowTextLengthW(hwnd) == 0:
                return True  # sarlavhasiz (odatda ko'rinmas yordamchi) oynalar
            if own_hwnd and hwnd == own_hwnd:
                return True
            proc_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            if proc_id.value == pid:
                result.append(hwnd)
                return False
            win_exe = _get_process_exe_name(proc_id.value)
            if exe_name and win_exe == exe_name:
                result.append(hwnd)
                return False
            if (not fallback and (win_exe or '').lower() not in _IGNORED_FALLBACK_EXES
                    and not _is_windows_system_process(proc_id.value)):
                fallback.append(hwnd)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        enum_cb = WNDENUMPROC(_enum_proc)
        start = time.time()
        while time.time() - start < timeout and not result:
            user32.EnumWindows(enum_cb, 0)
            if result:
                break
            time.sleep(0.3)
        if result:
            return result[0]
        if fallback:
            print(f"[Launcher] PID/exe bo'yicha topilmadi, zaxira sifatida "
                  f"boshqa ko'rinadigan oyna ishlatilmoqda (hwnd={fallback[0]})")
            return fallback[0]
        return None

    def bring_process_window_to_front(pid, exe_name=None, own_hwnd=None, timeout=10.0):
        hwnd = _find_window_for_pid(pid, exe_name=exe_name, own_hwnd=own_hwnd, timeout=timeout)
        if not hwnd:
            print(f"[Launcher] PID {pid} (exe={exe_name}) uchun oyna {timeout}s ichida "
                  f"topilmadi — old planga chiqarib bo'lmadi.")
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

    FRIENDLY_APP_NAMES = {
        'steam.exe': 'Steam', 'cs2.exe': 'CS2', 'valorant.exe': 'Valorant',
        'gta5.exe': 'GTA 5', 'dota2.exe': 'Dota 2', 'leagueclient.exe': 'League',
        'tslgame.exe': 'PUBG', 'rdr2.exe': 'RDR 2', 'fc24.exe': 'FC 24',
        'nfsunbound.exe': 'NFS Unbound', 'nba2k24.exe': 'NBA 2K24',
        'cyberpunk2077.exe': 'Cyberpunk 2077',
    }

    def _friendly_app_label(exe_name):
        name = FRIENDLY_APP_NAMES.get(exe_name.lower())
        if name:
            return name
        base = os.path.splitext(exe_name)[0]
        return base[:16].upper()

    # ── .exe faylidan ikonka olib, "ishlab turgan dasturlar" panjarasida
    #    matn o'rniga haqiqiy dastur belgisini ko'rsatish uchun ──
    shell32 = ctypes.WinDLL('shell32', use_last_error=True)
    gdiplus = ctypes.WinDLL('gdiplus', use_last_error=True)
    shell32.ExtractIconExW.restype = wintypes.UINT
    shell32.ExtractIconExW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p), wintypes.UINT
    ]
    user32.DestroyIcon.restype = wintypes.BOOL
    user32.DestroyIcon.argtypes = [ctypes.c_void_p]

    class _GdiplusStartupInput(ctypes.Structure):
        _fields_ = [
            ("GdiplusVersion", ctypes.c_uint32),
            ("DebugEventCallback", ctypes.c_void_p),
            ("SuppressBackgroundThread", ctypes.c_int),
            ("SuppressExternalCodecs", ctypes.c_int),
        ]

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8),
        ]

    _PNG_CLSID = _GUID(0x557cf406, 0x1a04, 0x11d3,
                        (ctypes.c_ubyte * 8)(0x9a, 0x73, 0x00, 0x00, 0xf8, 0x1e, 0xf3, 0x2e))
    _gdiplus_token = ctypes.c_ulong(0)
    _gdiplus_ready = False
    try:
        _gdi_startup_input = _GdiplusStartupInput(1, None, 0, 0)
        _gdi_status = gdiplus.GdiplusStartup(ctypes.byref(_gdiplus_token), ctypes.byref(_gdi_startup_input), None)
        _gdiplus_ready = (_gdi_status == 0)
    except Exception as e:
        print(f"[Icon] GDI+ ishga tushmadi (ikonkalar matn bilan almashtiriladi): {e}")

    _icon_pixmap_cache = {}

    def _get_app_icon_pixmap(exe_path):
        """.exe fayldan kichik ikonkani QPixmap sifatida qaytaradi.
        Har qanday xatoda (kutilmagan format, GDI+ muammosi va h.k.)
        jim ravishda None qaytaradi — chaqiruvchi bunday holda emoji/
        matn bilan almashtiradi, hech qachon dasturni yiqitmaydi."""
        if not exe_path or not _gdiplus_ready:
            return None
        if exe_path in _icon_pixmap_cache:
            return _icon_pixmap_cache[exe_path]
        pixmap = None
        large = (ctypes.c_void_p * 1)()
        small = (ctypes.c_void_p * 1)()
        hicon = None
        try:
            n = shell32.ExtractIconExW(ctypes.c_wchar_p(exe_path), 0, large, small, 1)
            hicon = small[0] or large[0]
            if n and hicon:
                tmp_path = os.path.join(
                    tempfile.gettempdir(), f"cz_icon_{abs(hash(exe_path))}.png"
                )
                bitmap_ptr = ctypes.c_void_p()
                status = gdiplus.GdipCreateBitmapFromHICON(hicon, ctypes.byref(bitmap_ptr))
                if status == 0 and bitmap_ptr:
                    try:
                        status2 = gdiplus.GdipSaveImageToFile(
                            bitmap_ptr, ctypes.c_wchar_p(tmp_path), ctypes.byref(_PNG_CLSID), None
                        )
                        if status2 == 0 and os.path.exists(tmp_path):
                            pix = QPixmap(tmp_path)
                            if not pix.isNull():
                                pixmap = pix
                    finally:
                        gdiplus.GdipDisposeImage(bitmap_ptr)
        except Exception as e:
            print(f"[Icon] {exe_path}: {e}")
        finally:
            try:
                if small[0]:
                    user32.DestroyIcon(small[0])
                if large[0] and large[0] != small[0]:
                    user32.DestroyIcon(large[0])
            except Exception:
                pass
        _icon_pixmap_cache[exe_path] = pixmap
        return pixmap

    def enumerate_running_apps(own_hwnd=None):
        """Ekranda hozir ko'rinadigan barcha top-level oynalarni (bizniki
        va ma'lum tizim jarayonlaridan tashqari) exe nomi bo'yicha
        guruhlab qaytaradi — pastki "ishlab turgan dasturlar" panjarasi
        uchun. Har bir dasturdan faqat bittadan (birinchi topilgan)
        oyna olinadi."""
        apps = {}

        def _enum_proc(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            GW_OWNER = 4
            if user32.GetWindow(hwnd, GW_OWNER):
                return True
            if user32.GetWindowTextLengthW(hwnd) == 0:
                return True
            if own_hwnd and hwnd == own_hwnd:
                return True
            proc_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            full_path = _get_process_full_path(proc_id.value)
            exe = os.path.basename(full_path) if full_path else None
            if not exe or exe.lower() in _IGNORED_FALLBACK_EXES:
                return True
            if full_path and full_path.lower().startswith(_WINDIR):
                return True
            if exe not in apps:
                apps[exe] = {
                    'hwnd': hwnd, 'pid': proc_id.value,
                    'label': _friendly_app_label(exe),
                    'icon': _get_app_icon_pixmap(full_path),
                }
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        try:
            user32.EnumWindows(WNDENUMPROC(_enum_proc), 0)
        except Exception as e:
            print(f"[Launcher] enumerate_running_apps: {e}")
        return apps

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

    # ── Sichqoncha sezgirligi (Windows OS darajasida — har qanday
    # sichqoncha bilan ishlaydi, alohida drayver/dastur kerak emas) ──
    SPI_GETMOUSE = 0x0003
    SPI_SETMOUSE = 0x0004
    SPI_GETMOUSESPEED = 0x0070
    SPI_SETMOUSESPEED = 0x0071
    SPIF_UPDATEINIFILE = 0x01
    SPIF_SENDCHANGE = 0x02
    MOUSE_DEFAULT_SPEED = 10
    _Int3 = ctypes.c_int * 3

    def get_mouse_speed():
        """1-20 oralig'ida, standart qiymat 10."""
        val = wintypes.UINT()
        user32.SystemParametersInfoW(SPI_GETMOUSESPEED, 0, ctypes.byref(val), 0)
        return val.value

    def set_mouse_speed(value):
        value = max(1, min(20, int(value)))
        user32.SystemParametersInfoW(SPI_SETMOUSESPEED, 0, ctypes.c_void_p(value),
                                      SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)

    def get_mouse_acceleration():
        arr = _Int3()
        user32.SystemParametersInfoW(SPI_GETMOUSE, 0, ctypes.byref(arr), 0)
        return arr[2] != 0

    def set_mouse_acceleration(enabled):
        # Windows standart qiymatlari: [6, 10, 1] (yoqilgan). O'chirilganda
        # uchchalasi ham 0 — bu "Enhance pointer precision"ni
        # o'chirishga teng, ko'p FPS o'yinchilar "xom" (1:1) sezgirlikni
        # afzal ko'radi.
        arr = _Int3(6, 10, 1) if enabled else _Int3(0, 0, 0)
        user32.SystemParametersInfoW(SPI_SETMOUSE, 0, ctypes.byref(arr),
                                      SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)

    def reset_mouse_settings():
        """Har bir seans tugab, PC qulflanganda chaqiriladi — keyingi
        mijoz oldingi o'yinchining sezgirligi bilan qolib ketmasligi
        uchun standart holatga qaytaradi."""
        try:
            set_mouse_speed(MOUSE_DEFAULT_SPEED)
            set_mouse_acceleration(True)
        except Exception as e:
            print(f"[Mouse] Standart holatga qaytarishda xato: {e}")

    # ── Administrator huquqi talab qiladigan o'yinlar (masalan ICCup
    # Launcher) uchun — oddiy CreateProcess (subprocess.Popen) ularni
    # ISHGA TUSHIRA OLMAYDI, "WinError 740: The requested operation
    # requires elevation" bilan darhol muvaffaqiyatsiz tugaydi (Windows
    # UAC oynasini o'zi ko'rsatmaydi, chunki bu jarayon o'zi elevatsiya
    # so'ramagan). ShellExecuteEx "runas" fe'li bilan xuddi foydalanuvchi
    # faylni qo'lda ikki marta bosib, "Ha"ni tanlagandagidek UAC
    # so'rovini chiqaradi.
    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SW_SHOWNORMAL = 1

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", ctypes.c_ulong),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hKeyClass", wintypes.HANDLE),
            ("dwHotKey", wintypes.DWORD),
            ("hIcon", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    shell32 = ctypes.WinDLL('shell32', use_last_error=True)
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    kernel32.GetProcessId.restype = wintypes.DWORD
    kernel32.GetProcessId.argtypes = [wintypes.HANDLE]

    def launch_elevated(exe, cwd=None):
        """UAC "Ha/Yo'q" so'rovini chiqarib, dasturni administrator
        huquqida ishga tushiradi. Muvaffaqiyatli bo'lsa (pid, hProcess)
        qaytaradi — mijoz "Ha"ni bosmasa yoki xato bo'lsa, None."""
        sei = SHELLEXECUTEINFOW()
        sei.cbSize = ctypes.sizeof(sei)
        sei.fMask = SEE_MASK_NOCLOSEPROCESS
        sei.hwnd = None
        sei.lpVerb = "runas"
        sei.lpFile = exe
        sei.lpParameters = None
        sei.lpDirectory = cwd
        sei.nShow = SW_SHOWNORMAL
        ok = shell32.ShellExecuteExW(ctypes.byref(sei))
        if not ok or not sei.hProcess:
            return None
        pid = kernel32.GetProcessId(sei.hProcess)
        return pid, sei.hProcess
else:
    def install_keyboard_hook():   print("[Hook] enabled (sim)")
    def uninstall_keyboard_hook(): print("[Hook] disabled (sim)")
    def register_global_hotkeys(app): pass
    def bring_process_window_to_front(pid, exe_name=None, own_hwnd=None, timeout=10.0): pass
    def enumerate_running_apps(own_hwnd=None): return {}
    def hide_taskbar(): pass
    def show_taskbar(): pass
    MOUSE_DEFAULT_SPEED = 10
    def get_mouse_speed(): return MOUSE_DEFAULT_SPEED
    def set_mouse_speed(value): pass
    def get_mouse_acceleration(): return True
    def set_mouse_acceleration(enabled): pass
    def reset_mouse_settings(): pass
    def launch_elevated(exe, cwd=None): return None


# ──────────────────────────────────────────────────────────────────────────────
#  APPLICATION CONTROLLER
# ──────────────────────────────────────────────────────────────────────────────
class SyncSignals(QObject):
    status_updated = pyqtSignal(dict)
    status_resync = pyqtSignal(dict)
    bar_order_updated = pyqtSignal(dict)
    remote_command = pyqtSignal(str)


class ClientLockerApp:
    def __init__(self, config_path="config.json"):
        self._load_config(config_path)
        self.signals = SyncSignals()
        self.signals.status_updated.connect(self._handle_status)
        self.signals.status_resync.connect(self._handle_status_resync)
        self.signals.bar_order_updated.connect(self._handle_bar_order)
        self.signals.remote_command.connect(self._handle_remote_command)
        self.launched_processes = []
        self.current_status = 'LOCKED'
        self.time_remaining = 0
        self.is_open_time = False
        self.pc_id = None
        # F9 orqali launcherga qaytilganda "O'yinga qaytish" tugmasi
        # bilan hozir ishlab turgan o'yinni qayta old planga chiqarish
        # uchun kuzatiladi.
        self.current_game_name = None
        self.current_game_pid = None
        self.current_game_exe = None
        # GameCard'ning o'zi ham ketma-ket bosishni bloklaydi, lekin
        # bu ikkinchi, mustaqil himoya qatlami — qaysi manbadan kelishidan
        # qat'iy nazar, tezkor ketma-ket ishga tushirish so'rovlarini
        # to'xtatadi.
        self._last_launch_at = 0.0
        # WebSocket ulangan bo'lsa, u real-vaqtli va aniq tartibda keladi —
        # shu payt heartbeat javobini e'tiborsiz qoldiramiz, aks holda
        # kechikkan heartbeat javobi WebSocket orqali kelgan yangi holatni
        # eskisi bilan qayta yozib, ekranda qisqa "miltillash" (masalan
        # ACTIVE -> LOCKED -> ACTIVE) keltirib chiqarishi mumkin edi.
        self.ws_connected = False
        # Dastur yangi ishga tushganda, WebSocket ulanishi heartbeat'ning
        # birinchi javobidan OLDIN ulgurib qolsa (LAN'da tez bo'lishi
        # mumkin), o'sha birinchi heartbeat javobi "e'tiborsiz
        # qoldiriladi" (yuqoridagi izoh) — lekin bu paytgacha WebSocket
        # orqali hali HECH QANDAY xabar kelmagan bo'ladi (chunki xabar
        # faqat admin biror amal bajarganda yuboriladi), shuning uchun
        # dastur "haqiqatda ACTIVE bo'lgan seansni ko'rmasdan" LOCKED
        # holatda abadiy qolib ketishi mumkin edi. Shu bayroq — hech
        # bo'lmasa BITTA haqiqiy sinxronlash sodir bo'lishini kafolatlaydi.
        self._got_initial_sync = False

        self.main_window = MainWindow(
            pc_name=self.pc_name, server_url=self.server_url,
            fallback_games=self.fallback_games, api_key=self.api_key
        )
        self.main_window.game_launched_signal.connect(self._handle_game_launch)
        self.main_window.app_switch_requested_signal.connect(self._handle_app_switch)
        self.main_window.customer_login_signal.connect(self._handle_customer_login)
        self.main_window.customer_unlock_signal.connect(self._handle_customer_unlock_request)
        self.main_window.customer_stop_signal.connect(self._handle_customer_stop_request)

        self.countdown = QTimer()
        self.countdown.timeout.connect(self._tick)
        self.countdown.start(1000)

        self.hotkey_timer = QTimer()
        self.hotkey_timer.timeout.connect(self._check_global_hotkeys)
        self.hotkey_timer.start(250)

        # "Ishlab turgan dasturlar" panjarasi: har 3 soniyada ekrandagi
        # ochiq oynalarni qayta tekshiradi — shu bilan Steam ichidan
        # ochilgan CS2 kabi biz to'g'ridan-to'g'ri ishga tushirmagan
        # dasturlar ham avtomatik ro'yxatga qo'shiladi.
        self.running_apps = {}
        self.apps_scan_timer = QTimer()
        self.apps_scan_timer.timeout.connect(self._scan_running_apps)
        self.apps_scan_timer.start(3000)

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
            # CS2 kabi o'yinlar to'liq ekranli eksklyuziv rejimda odatda
            # ekran o'lchamini (masalan 1920x1080'dan pastroqqa)
            # o'zgartiradi. F9 bosilgan zahoti Windows hali eski
            # o'lchamdan asl monitorga QAYTIB ULGURMAGAN bo'lishi mumkin
            # — shu daqiqada GetSystemMetrics() hali eski (kichikroq)
            # qiymatni qaytarib, oyna "kichrayib qolgandek" ko'rinishiga
            # sabab bo'lardi. Shuning uchun bir necha yuz millisoniyadan
            # keyin qayta tekshirib, haqiqiy monitor o'lchamiga moslab
            # qo'yamiz.
            # Eski, DirectX EKSKLYUZIV to'liq ekran rejimidagi o'yinlar
            # (masalan Prince of Persia, Pro Evolution Soccer) ekranni
            # ancha sekinroq "bo'shatishi" mumkin — shuning uchun
            # qo'shimcha, uzoqroq muddatli qayta urinishlar ham
            # qo'shilgan (2.5s/4s gacha).
            for delay_ms in (400, 1200, 2500, 4000):
                QTimer.singleShot(delay_ms, self.main_window.force_native_fullscreen)

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
        self.is_open_time = data.get('is_open_time', False)
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

    def _handle_status_resync(self, data):
        """WebSocket ulangan paytda heartbeat shu yerga yo'naltiriladi
        (_run_sync'ga qarang) — LOCK/UNLOCK holatini ATAYLAB
        o'ZGARTIRMAYDI (buni faqat WebSocket qiladi, aks holda eski
        miltillash muammosi qaytadi). Lekin time_remaining'ni serverdagi
        haqiqiy qiymat bilan davriy moslab turadi — aks holda mahalliy
        soniyalik hisoblagich (_tick) hech kim tomonidan tuzatilmay,
        asta-sekin haqiqiy vaqtdan chalg'ib ketib, seans hali server
        tomonda faol bo'lsa ham muddatidan oldin o'zi qulflab qo'yishi
        mumkin edi."""
        new_status = data.get('status', 'LOCKED')
        if self.current_status not in ('ACTIVE', 'WARNING') or new_status not in ('ACTIVE', 'WARNING'):
            return
        self.is_open_time = data.get('is_open_time', self.is_open_time)
        server_seconds = data.get('time_remaining', self.time_remaining)
        # Har heartbeat siklida (5s) tarmoq kechikishi/millisekund farqi
        # tufayli server qiymati mahalliy hisoblagichdan deyarli doim
        # 1-2 soniyaga farq qiladi — buni SO'ZSIZ qabul qilaversak,
        # ekranda vaqt sekundlari "sakrab" turgandek ko'rinar edi.
        # Faqat sezilarli (haqiqiy) farq bo'lsa tuzatiladi, mayda
        # tebranishlar esa mahalliy soniyalik hisoblagichga (_tick)
        # qoldiriladi — u baribir har heartbeat'da qayta tekshirilib
        # turadi.
        if abs(server_seconds - self.time_remaining) > 2:
            self.time_remaining = server_seconds
        self.main_window.update_timer(self.time_remaining)
        if data.get('id'):
            self.pc_id = data.get('id')

    def _handle_bar_order(self, data): pass

    def _handle_remote_command(self, command):
        """Dashboarddan WebSocket orqali kelgan masofaviy buyruq
        (ComputerViewSet.remote_shutdown/shutdown_all_pcs/force_close_app).
        MUHIM: bu faqat mijoz/o'yin dasturi muzlab qolganda ishlaydi —
        agar butun Windows qotib qolgan bo'lsa, shu kod ham
        ishlamayotgan bo'lardi (chunki u ham o'sha qotib qolgan
        kompyuterda ishlaydi)."""
        print(f"[Remote] Buyruq qabul qilindi: {command}")
        if command == 'SHUTDOWN':
            if IS_WINDOWS:
                subprocess.run(["shutdown", "/s", "/t", "3"], capture_output=True)
            else:
                print("[Remote] SHUTDOWN — faqat Windows'da ishlaydi (sim)")
        elif command == 'FORCE_CLOSE_APP':
            self._kill_games()

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
        self.running_apps = {}
        self.main_window.set_running_apps([])
        # Oldingi mijozning login holati (profil/kabinet) keyingi
        # mijozga ko'rinib qolmasligi uchun tozalanadi.
        self.main_window.lock_page.reset_login_state()
        self.main_window.launcher_page.set_logged_in_customer(None)
        # Oldingi o'yinchi sozlagan sichqoncha sezgirligi keyingisiga
        # o'tib qolmasligi uchun standart holatga qaytariladi.
        reset_mouse_settings()

    def _kill_games(self):
        for proc in self.launched_processes:
            try:
                if IS_WINDOWS:
                    # /T — butun jarayon DARAXTINI o'chiradi. .bat fayl
                    # orqali ishga tushirilgan o'yinlarda (masalan CS 1.6)
                    # bizga ma'lum bo'lgan PID aslida cmd.exe'niki bo'ladi,
                    # haqiqiy o'yin jarayoni esa uning FARZANDI — oddiy
                    # proc.kill() faqat cmd.exe'ni o'chiradi, o'yin esa
                    # orqa fonda ishlab qolib ketadi va keyingi safar
                    # "faqat bitta nusxa ishlashi mumkin" xatosi bilan
                    # ochilmay qoladi.
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
                else:
                    proc.terminate()
                    proc.kill()
            except Exception as e:
                print(f"[Cleanup] {e}")
        self.launched_processes.clear()
        self.current_game_name = None
        self.current_game_pid = None
        self.current_game_exe = None
        if IS_WINDOWS:
            # Qo'shimcha xavfsizlik to'ri — Steam kabi ba'zi ilovalar
            # yangi jarayonni butunlay mustaqil (bizning jarayon
            # daraxtimizdan tashqarida) ochib, o'zi darhol chiqib
            # ketishi mumkin, bunday holda yuqoridagi /T ham yordam
            # bermaydi, shuning uchun nom bo'yicha ham o'chiriladi.
            for exe in ["cs2.exe", "VALORANT.exe", "TslGame.exe", "GTA5.exe", "Cyberpunk2077.exe",
                        "RDR2.exe", "FC24.exe", "NFSUnbound.exe", "NBA2K24.exe", "dota2.exe", "LeagueClient.exe",
                        "hl.exe"]:
                try:
                    subprocess.run(["taskkill", "/F", "/IM", exe], capture_output=True)
                except Exception:
                    pass

    def _handle_game_launch(self, game):
        exe = game.get('executable_path')
        cwd_ = game.get('working_directory')
        name = game.get('name', 'Game')
        now = time.time()
        if now - self._last_launch_at < 5.0:
            print(f"[Launcher] '{name}' -> e'tiborsiz qoldirildi (yaqinda boshqa o'yin ishga tushirilgan)")
            return
        self._last_launch_at = now
        print(f"[Launcher] '{name}' -> {exe}")
        if exe and os.path.exists(exe):
            try:
                cwd = None
                if cwd_ and os.path.exists(cwd_):
                    cwd = cwd_
                elif exe and os.path.dirname(exe):
                    cwd = os.path.dirname(exe)
                if os.path.splitext(exe)[1].lower() in ('.bat', '.cmd'):
                    # .bat/.cmd fayllar CreateProcess orqali to'g'ridan-
                    # to'g'ri ishga tushmaydi ("WinError 193: %1 is not a
                    # valid Win32 application") — Windows ularni faqat
                    # cmd.exe orqali bajaradi.
                    proc = subprocess.Popen(["cmd.exe", "/c", exe], cwd=cwd)
                else:
                    try:
                        proc = subprocess.Popen([exe], cwd=cwd)
                    except OSError as e:
                        # WinError 740 = ERROR_ELEVATION_REQUIRED — bu exe
                        # (masalan ICCup Launcher) administrator huquqini
                        # talab qiladi. Oddiy CreateProcess (Popen) buni
                        # umuman boshqara olmaydi va UAC oynasini
                        # ko'rsatmasdan darhol shu xato bilan tugaydi —
                        # ShellExecuteEx "runas" fe'li bilan qayta
                        # urinamiz, bu esa qo'lda ikki marta bosilganda
                        # chiqadigan xuddi shu UAC "Ha/Yo'q" so'rovini
                        # chiqaradi.
                        if IS_WINDOWS and getattr(e, 'winerror', None) == 740:
                            result = launch_elevated(exe, cwd)
                            if not result:
                                self.main_window.show_launch_error(
                                    "Administrator ruxsati berilmadi (UAC oynasida 'Ha' bosilmadi), qayta urinib ko'ring."
                                )
                                return
                            pid, _hproc = result
                            proc = types.SimpleNamespace(pid=pid)
                        else:
                            raise
                self.launched_processes.append(proc)
                print(f"[Launcher] PID: {proc.pid}")
                self.main_window.show_launch_success(name)

                # Yangi ishga tushirilgan o'yin oynasini old planga
                # chiqarish uchun kuzatiladi (pastdagi thread'da
                # ishlatiladi).
                self.current_game_name = name
                self.current_game_pid = proc.pid
                self.current_game_exe = os.path.basename(exe)

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
                # fon oqimida amalga oshiriladi. exe_name ham uzatiladi —
                # Steam kabi ilovalar yangi jarayonni allaqachon ochiq
                # nusxaga signal berib, o'zi darhol chiqib ketishi
                # mumkin, bunday holda faqat PID emas, exe nomi bo'yicha
                # qidirish kerak bo'ladi.
                if IS_WINDOWS:
                    threading.Thread(
                        target=bring_process_window_to_front,
                        args=(proc.pid,),
                        kwargs={'exe_name': self.current_game_exe, 'own_hwnd': int(self.main_window.winId())},
                        daemon=True
                    ).start()
            except Exception as e:
                print(f"[Launcher] Error: {e}")
                self.main_window.show_launch_error(f"Xatolik: {e}")
        else:
            print(f"[Launcher] Not found: {exe}")
            self.main_window.show_launch_error("O'yin fayli topilmadi, iltimos admonga murojaat qiling")

    def _scan_running_apps(self):
        """Har 3 soniyada ekrandagi ochiq dasturlarni qayta tekshiradi
        va pastki panjarani yangilaydi — Steam ichidan ochilgan CS2
        kabi biz to'g'ridan-to'g'ri ishga tushirmagan dasturlar ham
        shu orqali avtomatik ro'yxatga qo'shiladi."""
        if not IS_WINDOWS or self.current_status not in ('ACTIVE', 'WARNING'):
            if self.running_apps:
                self.running_apps = {}
                self.main_window.set_running_apps([])
            return
        try:
            own_hwnd = int(self.main_window.winId())
        except Exception:
            return
        found = enumerate_running_apps(own_hwnd=own_hwnd)
        if set(found.keys()) != set(self.running_apps.keys()):
            self.running_apps = found
            apps_list = [{'exe': exe, 'label': info['label'], 'icon': info.get('icon')} for exe, info in found.items()]
            self.main_window.set_running_apps(apps_list)
        else:
            self.running_apps = found  # hwnd/pid yangilanishi mumkin

    def _handle_app_switch(self, exe_name):
        """Pastki 'ishlab turgan dasturlar' panjarasidan bosilgan
        dasturni old planga chiqaradi."""
        info = self.running_apps.get(exe_name)
        if not info:
            return
        print(f"[Launcher] Dasturga o'tish so'ralmoqda: {exe_name} (pid={info['pid']})")
        self.main_window.yield_to_app()
        if IS_WINDOWS:
            threading.Thread(
                target=bring_process_window_to_front,
                args=(info['pid'],),
                kwargs={'exe_name': exe_name, 'own_hwnd': int(self.main_window.winId()), 'timeout': 3.0},
                daemon=True
            ).start()

    def _handle_customer_login(self, data):
        """Mijoz qulf ekranida o'z telefon/paroli bilan kirganda —
        faqat loglash uchun, PC holatiga (qulflanganligiga) hech
        qanday ta'sir qilmaydi."""
        print(f"[Customer] {data.get('full_name')} ({data.get('phone')}) tizimga kirdi")

    def _handle_customer_unlock_request(self, session_token):
        """Mijoz "Kompyuterni ochish" tugmasini bosganda — balansdan
        bosqichma-bosqich yechiladigan seansni boshlashni so'raydi.
        Muvaffaqiyatli bo'lsa, PC odatdagi status-sinxronlash orqali
        o'zi ACTIVE holatga o'tadi (bu yerda alohida unlock chaqirilmaydi)."""
        if not self.pc_id:
            print("[Customer] pc_id hali noma'lum, birozdan keyin qayta urinib ko'ring")
            self.main_window.lock_page.unlock_result_ready.emit(
                False, {"error": "Server bilan hali sinxronlanmoqda, biroz kuting va qayta urinib ko'ring."}
            )
            return
        self.main_window.api_client.customer_start_session_async(
            self.pc_id, session_token,
            on_done=lambda ok, data: self.main_window.lock_page.unlock_result_ready.emit(ok, data)
        )

    def _handle_customer_stop_request(self, session_token):
        """Mijoz "Kabinet"dan "Vaqtni to'xtatish"ni bosganda — o'zi
        balansidan ochgan seansni to'xtatishni so'raydi. Muvaffaqiyatli
        bo'lsa, PC odatdagi status-sinxronlash orqali o'zi qulflanadi."""
        if not self.pc_id:
            return
        self.main_window.api_client.customer_stop_session_async(self.pc_id, session_token)

    def _tick(self):
        if self.current_status in ('ACTIVE', 'WARNING'):
            if self.is_open_time:
                # Open Time seansda vaqt cheklovi yo'q — bu yerda faqat
                # ko'rsatish uchun soniyani oshirib boramiz (elapsed),
                # hech qachon o'zi qulflamaydi. Faqat administrator
                # "Tugatish" bosganda, server orqali haqiqiy LOCK keladi.
                self.time_remaining += 1
                self.main_window.update_timer(self.time_remaining)
            elif self.time_remaining > 0:
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
                    # WebSocket ulangan bo'lsa, LOCK/UNLOCK holat
                    # o'tishlari shu yerdan emas, real-vaqtli push orqali
                    # keladi — aks holda kechikkan heartbeat javobi eski
                    # holatni qayta tiklab, ekranda miltillashga sabab
                    # bo'lishi mumkin edi. Lekin BIRINCHI marta
                    # sinxronlash — bundan mustasno: WebSocket ulangan
                    # bo'lsa ham, agar hali birorta ham haqiqiy holat
                    # kelmagan bo'lsa (masalan dastur endigina ishga
                    # tushdi, seans esa undan OLDIN faol bo'lgan), baribir
                    # shu javobni qabul qilamiz — aks holda dastur
                    # haqiqatda ACTIVE bo'lgan seansni hech qachon
                    # bilmasdan, doimiy LOCKED holatda qolib ketishi mumkin.
                    if not self.ws_connected or not self._got_initial_sync:
                        self.signals.status_updated.emit(r.json())
                        self._got_initial_sync = True
                    else:
                        # LOCK/UNLOCK'ga tegmasdan, faqat time_remaining'ni
                        # serverdagi haqiqiy qiymat bilan moslab turadi —
                        # aks holda mahalliy soniyalik hisoblagich
                        # tuzatilmay, seans hali faol bo'lsa ham
                        # muddatidan oldin o'zi qulflab qo'yishi mumkin edi.
                        self.signals.status_resync.emit(r.json())
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
                elif d.get('action') == 'REMOTE_COMMAND':
                    target = d.get('target')
                    if target == 'ALL' or target == self.pc_name:
                        self.signals.remote_command.emit(d.get('command', ''))
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
                ws = websocket.WebSocketApp(ws_url_with_key, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
                ws.run_forever()
                print("[WS] run_forever() qaytdi (ulanish yopildi)")
            except Exception as e:
                import traceback
                print(f"[WS] Failed: {e}")
                traceback.print_exc()
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

        /* Zamonaviy, yupqa scrollbar — standart Windows'ning "qalin,
           tugmali" ko'rinishi o'rniga (butun dastur bo'ylab, barcha
           QScrollArea'lar uchun amal qiladi). */
        QScrollBar:vertical {
            background: transparent;
            width: 10px;
            margin: 2px 0;
        }
        QScrollBar::handle:vertical {
            background: rgba(255, 255, 255, 0.15);
            border-radius: 5px;
            min-height: 32px;
        }
        QScrollBar::handle:vertical:hover {
            background: rgba(0, 240, 255, 0.45);
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
            border: none;
            background: none;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }
        QScrollBar:horizontal {
            background: transparent;
            height: 10px;
            margin: 0 2px;
        }
        QScrollBar::handle:horizontal {
            background: rgba(255, 255, 255, 0.15);
            border-radius: 5px;
            min-width: 32px;
        }
        QScrollBar::handle:horizontal:hover {
            background: rgba(0, 240, 255, 0.45);
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
            border: none;
            background: none;
        }
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
            background: none;
        }
    """)
    if IS_WINDOWS:
        register_global_hotkeys(app)

    _locker = ClientLockerApp("config.json")
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
