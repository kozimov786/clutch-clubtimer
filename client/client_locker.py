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
import uuid
from datetime import datetime
from urllib.parse import quote

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

from PyQt6.QtCore import (
    Qt, QTimer, QEvent, pyqtSignal, QObject, QDate, QByteArray, QBuffer,
    QIODevice, QPointF, QPropertyAnimation, QVariantAnimation, QEasingCurve, QRect, QSize
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QPushButton, QFrame, QHBoxLayout, QScrollArea, QGridLayout,
    QLineEdit, QGraphicsDropShadowEffect, QSizePolicy, QStackedWidget,
    QSpacerItem, QMessageBox, QDialog, QSlider, QCheckBox, QProgressBar
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

        # MUHIM (CS2'da g'ijirlash sababi topildi): _show_launcher_over_game()
        # bu funksiyani F9 bosilganda 5 marta — darhol, keyin 400/1200/
        # 2500/4000ms'dan keyin — ATAYLAB qayta-qayta chaqiradi (eski,
        # sekin yopiladigan o'yinlar uchun kerak edi). Lekin oldin
        # raise_()/activateWindow()/force_foreground_window() HAR SAFAR
        # SHARTSIZ qayta bajarilardi — hatto oyna ALLAQACHON faol bo'lsa
        # ham. Zamonaviy o'yinlarda (CS2 kabi) birinchi urinishning o'zi
        # yetarli bo'ladi, shu sababli qolgan 4 ta keyingi "kuchlab
        # oldinga chiqarish" chaqiruvi haqiqatda HECH NARSA qilmasdan,
        # shunchaki Windows kompozitorini/oyna fokusini keraksiz qayta-
        # qayta bezovta qilib, sezilarli "qoqilish" (stutter) yaratardi.
        # Endi bu qimmat/bezovta qiluvchi qadam FAQAT oyna hali haqiqatda
        # faol bo'lmagan holatdagina bajariladi — eski, qiynchiluk
        # o'yinlar uchun bir xil ishonchlilik saqlanadi, zamonaviy
        # o'yinlarda esa keyingi urinishlar haqiqiy no-op bo'lib qoladi.
        if not self.isActiveWindow():
            self.raise_()
            self.activateWindow()
            # Qt'ning activateWindow()'i Windows'ning "focus-stealing
            # prevention" siyosati tufayli eksklyuziv to'liq ekranli o'yin
            # ustidan doim ishlayvermaydi (F9 "ba'zida ishlamaydi" muammosi
            # aynan shundan) — shuning uchun ishonchliroq Win32 usuli bilan
            # ham qo'shimcha kuchaytiriladi.
            if IS_WINDOWS:
                try:
                    force_foreground_window(int(self.winId()))
                except Exception as e:
                    print(f"[Fullscreen] force_foreground_window xato: {e}")

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

    def get_games(self, pc_name=None):
        path = f"/api/games/?pc={quote(pc_name)}" if pc_name else "/api/games/"
        data = self._get(path)
        return data if isinstance(data, list) else []

    def get_categories(self):
        data = self._get("/api/categories/")
        return data if isinstance(data, list) else []

    def get_products(self):
        data = self._get("/api/products/")
        return data if isinstance(data, list) else []

    def create_order_async(self, pc_name, items, client_order_id=None, on_done=None):
        def _post():
            try:
                payload = {"pc_name": pc_name, "items": items, "payment_method": "CASH"}
                if client_order_id:
                    payload["client_order_id"] = client_order_id
                r = requests.post(
                    f"{self.server_url}/api/orders/",
                    json=payload,
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

    def whoami_async(self, session_token, pc_name, on_done=None):
        """Dastur qayta ishga tushganda (masalan xatolik/yangilanishdan
        keyin) — bu PC'da hali ham BALANCE seansi ochib turgan mijozning
        "Kabinet" holatini tiklash uchun."""
        def _post():
            try:
                r = requests.post(
                    f"{self.server_url}/api/customers/whoami/",
                    json={"session_token": session_token, "pc_name": pc_name},
                    headers=self._headers(),
                    timeout=8
                )
                ok = r.status_code == 200
                if on_done:
                    on_done(ok, r.json() if r.content else {})
            except Exception as e:
                print(f"[API] whoami: {e}")
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

    def update_profile_async(self, session_token, full_name, on_done=None):
        """Mijoz "Kabinet" oynasida "Pilot Tag" (ism) ni o'zgartirib
        SAVE CHANGES bosganda."""
        def _post():
            try:
                r = requests.post(
                    f"{self.server_url}/api/customers/update_profile/",
                    json={"session_token": session_token, "full_name": full_name},
                    headers=self._headers(),
                    timeout=10
                )
                ok = r.status_code == 200
                if on_done:
                    on_done(ok, r.json() if r.content else {})
            except Exception as e:
                print(f"[API] update_profile: {e}")
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
# ──────────────────────────────────────────────────────────────────────────────
#  4b. CYBER-ESPORTS DESIGN SYSTEM TOKENS & STYLES
# ──────────────────────────────────────────────────────────────────────────────
COLOR_BG = "#0B0E14"
COLOR_SURFACE = "#10131A"
COLOR_SURFACE_DIM = "#10131A"
COLOR_SURFACE_BRIGHT = "#363940"
COLOR_SURFACE_CONTAINER_LOWEST = "#0B0E14"
COLOR_SURFACE_CONTAINER_LOW = "#191C22"
COLOR_SURFACE_CONTAINER = "#1D2026"
COLOR_SURFACE_CONTAINER_HIGH = "#272A31"
COLOR_SURFACE_CONTAINER_HIGHEST = "#32353C"
COLOR_ON_SURFACE = "#E1E2EB"
COLOR_ON_SURFACE_VARIANT = "#BAC9CC"
COLOR_OUTLINE = "#849396"
COLOR_OUTLINE_VARIANT = "#3B494C"
COLOR_SURFACE_VARIANT = "#32353C"
COLOR_PRIMARY_FIXED = "#9CF0FF"

# Accents
COLOR_CYAN = "#00DAF3"
COLOR_CYAN_RGB = "0, 218, 243"
COLOR_CYAN_GLOW = "rgba(0, 218, 243, 0.4)"
COLOR_PRIMARY_CONTAINER = "#00E5FF"
COLOR_PRIMARY = "#C3F5FF"
COLOR_ON_PRIMARY = "#00363D"

COLOR_GREEN = "#52FFAC"
COLOR_GREEN_BG = "rgba(82, 255, 172, 0.10)"
COLOR_SECONDARY = "#F5FFF5"
COLOR_SECONDARY_CONTAINER = "#00FFA3"

COLOR_PURPLE = "#D9C8FF"
COLOR_PURPLE_DARK = "#6C00F7"
COLOR_TERTIARY_CONTAINER = "#D9C8FF"

COLOR_ROSE = "#F0A8B3"
COLOR_VIOLET = "#8B5CF6"
COLOR_CRIMSON_BG = "#231013"
COLOR_CRIMSON_BORDER = "#7A1F28"

# Legacy aliases
COLOR_PANEL = COLOR_SURFACE_CONTAINER_LOW
COLOR_PANEL_BORDER = "rgba(255, 255, 255, 0.08)"
COLOR_INPUT_BG = "#0B0E14"
COLOR_INPUT_BORDER = "#3B494C"

# ── Button & Input Styles ──
CYBER_PRIMARY_BTN_QSS = f"""
    QPushButton {{
        background: {COLOR_PRIMARY_CONTAINER};
        color: #001F24;
        font-family: 'Sora', 'Segoe UI', sans-serif;
        font-weight: 700;
        font-size: 13px;
        letter-spacing: 0.5px;
        border: none;
        border-radius: 4px;
        padding: 0 24px;
    }}
    QPushButton:hover {{
        background: #4de3ff;
    }}
    QPushButton:pressed {{
        background: #00b8cc;
    }}
    QPushButton:disabled {{
        background: rgba(255, 255, 255, 0.08);
        color: #475569;
    }}
"""

GRADIENT_BTN_QSS = f"""
    QPushButton {{
        color: #001F24;
        font-weight: bold;
        background: {COLOR_PRIMARY_CONTAINER};
        border: none;
        border-radius: 4px;
    }}
    QPushButton:hover {{
        background: #4de3ff;
    }}
    QPushButton:disabled {{
        color: #475569;
        background: rgba(255, 255, 255, 0.08);
    }}
"""

CRIMSON_BTN_QSS = f"""
    QPushButton {{
        background: {COLOR_CRIMSON_BG};
        color: #f87171;
        border: 1px solid {COLOR_CRIMSON_BORDER};
        border-radius: 4px;
    }}
    QPushButton:hover {{ background: #2c1418; }}
"""

INPUT_QSS = f"""
    QLineEdit {{
        background: rgba(11, 14, 20, 0.7);
        color: #e1e2eb;
        font-family: 'Hanken Grotesk', 'Segoe UI', sans-serif;
        font-size: 14px;
        border: 1px solid rgba(59, 73, 76, 0.6);
        border-radius: 4px;
        padding: 0 14px;
    }}
    QLineEdit:focus {{
        background: #0b0e14;
        border: 1px solid {COLOR_PRIMARY_CONTAINER};
    }}
"""


def cyber_font(size, weight=QFont.Weight.Normal, family="Sora"):
    f = QFont()
    if family == "Sora":
        f.setFamilies(["Sora", "Segoe UI", "Arial", "sans-serif"])
    elif family == "Mono":
        f.setFamilies(["JetBrains Mono", "Consolas", "Courier New", "monospace"])
    else:
        f.setFamilies(["Hanken Grotesk", "Segoe UI", "sans-serif"])
    f.setPointSize(size)
    f.setWeight(weight)
    return f


def serif_font(size, weight=QFont.Weight.Bold):
    f = QFont()
    f.setFamilies(["Sora", "Cinzel Decorative", "Segoe UI", "Georgia"])
    f.setPointSize(size)
    f.setWeight(weight)
    return f


class BracketFrame(QFrame):
    """4 burchakli HUD chizig'i."""
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
        painter.drawLine(m, m, m + seg, m)
        painter.drawLine(m, m, m, m + seg)
        painter.drawLine(w - m, h - m, w - m - seg, h - m)
        painter.drawLine(w - m, h - m, w - m, h - m - seg)

        pen2 = QPen(self._bracket_color2)
        pen2.setWidth(self._bracket_w)
        pen2.setCapStyle(Qt.PenCapStyle.SquareCap)
        painter.setPen(pen2)
        painter.drawLine(w - m, m, w - m - seg, m)
        painter.drawLine(w - m, m, w - m, m + seg)
        painter.drawLine(m, h - m, m + seg, h - m)
        painter.drawLine(m, h - m, m, h - m - seg)
        painter.end()


class IconLineEdit(QLineEdit):
    """QLineEdit'ning o'ng chekkasida ikonka ko'rsatadi."""
    def __init__(self, icon_char, parent=None):
        super().__init__(parent)
        self._icon_label = QLabel(icon_char, self)
        self._icon_label.setStyleSheet("color: #849396; background: transparent; border: none; font-size: 14px;")
        self._icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._position_icon()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_icon()

    def _position_icon(self):
        self._icon_label.adjustSize()
        x = self.width() - self._icon_label.width() - 14
        y = (self.height() - self._icon_label.height()) // 2
        self._icon_label.move(max(0, x), max(0, y))


class CyberQRWidget(QWidget):
    """Futuristik kiber QR kod vizualini chizuvchi widget."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(148, 148)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Oq fon
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 6, 6)
        
        # Qora QR elementlari
        painter.setBrush(QColor("#0B0E14"))
        
        # 3 ta burchak kvadrati
        def draw_finder(x, y):
            painter.fillRect(x, y, 34, 34, QColor("#0B0E14"))
            painter.fillRect(x + 5, y + 5, 24, 24, QColor("#FFFFFF"))
            painter.fillRect(x + 10, y + 10, 14, 14, QColor("#0B0E14"))
            
        draw_finder(10, 10)
        draw_finder(104, 10)
        draw_finder(10, 104)
        
        # Ichki sinxronlash chiziqlari va ma'lumot matritsasi
        for i in range(10, 138, 8):
            for j in range(10, 138, 8):
                if (i < 50 and j < 50) or (i > 95 and j < 50) or (i < 50 and j > 95):
                    continue
                if ((i * 7 + j * 13) % 11) < 5:
                    painter.fillRect(i, j, 5, 5, QColor("#0B0E14"))
                    
        painter.end()


class AdminOverrideDialog(QDialog):
    """Admin Override / Favqulodda ochish dialogi."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Admin Override")
        self.setFixedSize(360, 240)
        self.setStyleSheet(f"""
            QDialog {{
                background: {COLOR_SURFACE_CONTAINER_LOW};
                border: 1px solid {COLOR_PRIMARY_CONTAINER};
                border-radius: 8px;
            }}
            QLabel {{ color: {COLOR_ON_SURFACE}; border: none; background: transparent; }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        
        title = QLabel("ADMIN OVERRIDE")
        title.setFont(cyber_font(12, QFont.Weight.Bold, "Sora"))
        title.setStyleSheet(f"color: {COLOR_PRIMARY_CONTAINER}; letter-spacing: 1.5px;")
        layout.addWidget(title)
        
        desc = QLabel("Kiosk rejimini bekor qilish yoki seansni boshqarish uchun admin parolini kiriting:")
        desc.setFont(cyber_font(10, family="Hanken"))
        desc.setStyleSheet(f"color: {COLOR_ON_SURFACE_VARIANT};")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        self.pin_input = QLineEdit()
        self.pin_input.setPlaceholderText("Admin Code")
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setFixedHeight(40)
        self.pin_input.setStyleSheet(INPUT_QSS)
        layout.addWidget(self.pin_input)
        
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        
        cancel_btn = QPushButton("Bekor qilish")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #BAC9CC;
                border: 1px solid rgba(132, 147, 150, 0.4); border-radius: 4px;
            }
            QPushButton:hover { color: #ffffff; border-color: #ffffff; }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        
        confirm_btn = QPushButton("Tasdiqlash")
        confirm_btn.setFixedHeight(36)
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setStyleSheet(CYBER_PRIMARY_BTN_QSS)
        confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(confirm_btn)
        
        layout.addLayout(btn_row)

    def _on_confirm(self):
        entered = self.pin_input.text().strip()
        if entered in ("1234", "admin", "clutch", "7777"):
            self.accept()
        else:
            self.pin_input.setStyleSheet(INPUT_QSS + "QLineEdit { border: 1px solid #ffb4ab; }")


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
        self.setStyleSheet(f"""
            QDialog {{
                background: {COLOR_SURFACE_CONTAINER_LOW};
                border: 1px solid {COLOR_PRIMARY_CONTAINER};
                border-radius: 8px;
            }}
            QLabel {{ color: {COLOR_ON_SURFACE}; border: none; background: transparent; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        title = QLabel("🖱️  SICHQONCHA SOZLAMALARI")
        title.setFont(cyber_font(12, QFont.Weight.Bold, "Sora"))
        title.setStyleSheet(f"color: {COLOR_PRIMARY_CONTAINER}; letter-spacing: 1px;")
        root.addWidget(title)

        row1 = QHBoxLayout()
        sens_lbl = QLabel("Sezgirlik (sensitivity)")
        sens_lbl.setFont(cyber_font(10, family="Hanken"))
        row1.addWidget(sens_lbl)
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
        low.setStyleSheet(f"color: {COLOR_ON_SURFACE_VARIANT}; font-size: 10px;")
        low_high_row.addWidget(low)
        low_high_row.addStretch(1)
        high = QLabel("Yuqori")
        high.setStyleSheet(f"color: {COLOR_ON_SURFACE_VARIANT}; font-size: 10px;")
        low_high_row.addWidget(high)
        root.addLayout(low_high_row)

        root.addSpacing(6)

        self.accel_checkbox = QCheckBox("Sichqoncha tezlashishi (Enhance pointer precision)")
        self.accel_checkbox.setStyleSheet(f"color: {COLOR_ON_SURFACE};")
        self.accel_checkbox.toggled.connect(self._on_accel_toggled)
        root.addWidget(self.accel_checkbox)
        accel_hint = QLabel("FPS o'yinlarda ko'pchilik o'yinchilar buni o'chirib qo'yadi (aim uchun barqaror sezgirlik).")
        accel_hint.setWordWrap(True)
        accel_hint.setStyleSheet(f"color: {COLOR_OUTLINE}; font-size: 10px;")
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
        close_btn.setStyleSheet(CYBER_PRIMARY_BTN_QSS)
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
#  5. LOCK SCREEN (CYBER-ESPORTS DESIGN)
# ──────────────────────────────────────────────────────────────────────────────
class LockScreenWidget(QWidget):
    login_succeeded = pyqtSignal(dict)
    _login_result_ready = pyqtSignal(bool, dict)
    unlock_requested = pyqtSignal(str)
    unlock_result_ready = pyqtSignal(bool, dict)

    def __init__(self, pc_name="PC-01", api_client=None, parent=None):
        super().__init__(parent)
        self.pc_name = pc_name
        self.api_client = api_client
        self.logged_in_customer = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(f"background-color: {COLOR_BG};")

        # Fon rasmi (Cyber-Esports Grid / System Locked visual)
        bg_path = os.path.join(ASSETS_DIR, "cyber_lock_bg.jpg")
        self._bg_pixmap = QPixmap(bg_path) if os.path.exists(bg_path) else None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(48, 28, 48, 28)
        root_layout.setSpacing(0)

        # ── 1. HEADER ROW ──
        header_row = QHBoxLayout()
        header_row.setSpacing(20)
        header_row.setContentsMargins(0, 0, 0, 16)

        # Chap: Clutch Zone to'liq logotip yozuvi bilan
        logo_full_path = os.path.join(ASSETS_DIR, "clutch_logo_full.png")
        if not os.path.exists(logo_full_path):
            logo_full_path = os.path.join(ASSETS_DIR, "clutch_logo_mark.png")
            
        logo_label = QLabel()
        logo_label.setStyleSheet("background: transparent; border: none;")
        if os.path.exists(logo_full_path):
            pix = QPixmap(logo_full_path)
            if not pix.isNull():
                logo_label.setPixmap(pix.scaledToHeight(44, Qt.TransformationMode.SmoothTransformation))
        else:
            logo_label.setText("CLUTCH ZONE")
            logo_label.setFont(cyber_font(18, QFont.Weight.ExtraBold, "Sora"))
            logo_label.setStyleSheet(f"color: {COLOR_PRIMARY_CONTAINER}; letter-spacing: 2px;")
        header_row.addWidget(logo_label)

        # Ajratuvchi chiziq
        logo_sep = QFrame()
        logo_sep.setFixedWidth(1)
        logo_sep.setFixedHeight(40)
        logo_sep.setStyleSheet("background: rgba(0, 229, 255, 0.3); border: none;")
        header_row.addWidget(logo_sep)

        # Katta va yorqin PC raqami
        station_col = QVBoxLayout()
        station_col.setSpacing(1)
        self.station_title = QLabel(f"{self.pc_name} VIP")
        self.station_title.setFont(cyber_font(22, QFont.Weight.ExtraBold, "Sora"))
        self.station_title.setStyleSheet(f"""
            color: #FFFFFF;
            letter-spacing: 1.5px;
        """)
        station_col.addWidget(self.station_title)

        station_sub = QLabel("ELITE GAMING TERMINAL")
        station_sub.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        station_sub.setStyleSheet(f"color: {COLOR_PRIMARY_CONTAINER}; letter-spacing: 1.5px;")
        station_col.addWidget(station_sub)
        header_row.addLayout(station_col)

        header_row.addStretch(1)

        # O'ng: Network Latency
        network_col = QVBoxLayout()
        network_col.setSpacing(2)
        network_col.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        network_top = QHBoxLayout()
        network_top.setSpacing(6)
        network_top.addStretch(1)
        network_dot = QLabel("●")
        network_dot.setStyleSheet(f"color: {COLOR_GREEN}; font-size: 10px;")
        network_top.addWidget(network_dot)
        network_label = QLabel("Network")
        network_label.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        network_label.setStyleSheet(f"color: {COLOR_ON_SURFACE_VARIANT}; letter-spacing: 1px;")
        network_top.addWidget(network_label)
        network_col.addLayout(network_top)

        self.network_status = QLabel("12ms")
        self.network_status.setFont(cyber_font(13, QFont.Weight.Bold, "Sora"))
        self.network_status.setStyleSheet(f"color: {COLOR_GREEN};")
        self.network_status.setAlignment(Qt.AlignmentFlag.AlignRight)
        network_col.addWidget(self.network_status)
        header_row.addLayout(network_col)

        # Divider
        time_divider = QFrame()
        time_divider.setFixedWidth(1)
        time_divider.setFixedHeight(36)
        time_divider.setStyleSheet("background: rgba(59, 73, 76, 0.5); border: none;")
        header_row.addWidget(time_divider)

        # O'ng: Local Time
        time_col = QVBoxLayout()
        time_col.setSpacing(2)
        time_col.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        time_label = QLabel("Local Time")
        time_label.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        time_label.setStyleSheet(f"color: {COLOR_ON_SURFACE_VARIANT}; letter-spacing: 1px;")
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        time_col.addWidget(time_label)

        self.clock_label = QLabel("--:--:--")
        self.clock_label.setFont(cyber_font(15, QFont.Weight.Bold, "Sora"))
        self.clock_label.setStyleSheet(f"color: {COLOR_ON_SURFACE};")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        time_col.addWidget(self.clock_label)
        header_row.addLayout(time_col)

        root_layout.addLayout(header_row)

        # Header pastki chizig'i
        header_line = QFrame()
        header_line.setFixedHeight(1)
        header_line.setStyleSheet(f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {COLOR_CYAN}, stop:0.4 rgba(0,218,243,0.1), stop:1 transparent); border: none;")
        root_layout.addWidget(header_line)

        root_layout.addStretch(1)

        # ── 2. CENTER CONTENT (MARKAZIY LOGIN VA QR KARTA) ──
        center_container = QHBoxLayout()
        center_container.setSpacing(0)
        center_container.addStretch(1)

        # Markaziy Karta (O'zgarmas aniq o'lcham — tab o'zgarganda sakramaydi)
        self.main_card = QFrame()
        self.main_card.setObjectName("mainCard")
        self.main_card.setFixedSize(540, 390)
        self.main_card.setStyleSheet(f"""
            QFrame#mainCard {{
                background: rgba(16, 19, 26, 0.90);
                border: 1px solid rgba(0, 229, 255, 0.40);
                border-radius: 12px;
            }}
            QWidget {{
                border: none;
                background: transparent;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        card_layout = QVBoxLayout(self.main_card)
        card_layout.setContentsMargins(36, 28, 36, 28)
        card_layout.setSpacing(0)

        # Tablar sarlavhasi
        tabs_header = QHBoxLayout()
        tabs_header.setSpacing(0)
        
        self.tab_login_btn = QPushButton("Member Login")
        self.tab_login_btn.setFont(cyber_font(12, QFont.Weight.Bold, "Sora"))
        self.tab_login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_login_btn.setStyleSheet(f"""
            QPushButton {{
                color: {COLOR_PRIMARY_CONTAINER}; background: transparent;
                border: none; padding-bottom: 10px;
            }}
        """)
        self.tab_login_btn.clicked.connect(self._switch_to_login_tab)
        tabs_header.addWidget(self.tab_login_btn)

        self.tab_qr_btn = QPushButton("QR Quick Access")
        self.tab_qr_btn.setFont(cyber_font(12, QFont.Weight.Bold, "Sora"))
        self.tab_qr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_qr_btn.setStyleSheet(f"""
            QPushButton {{
                color: {COLOR_ON_SURFACE_VARIANT}; background: transparent;
                border: none; padding-bottom: 10px;
            }}
            QPushButton:hover {{ color: {COLOR_ON_SURFACE}; }}
        """)
        self.tab_qr_btn.clicked.connect(self._switch_to_qr_tab)
        tabs_header.addWidget(self.tab_qr_btn)

        card_layout.addLayout(tabs_header)

        # Tab Indikator chizig'i
        self.tab_indicator = QFrame()
        self.tab_indicator.setFixedHeight(2)
        self.tab_indicator.setStyleSheet(f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {COLOR_PRIMARY_CONTAINER}, stop:0.5 {COLOR_PRIMARY_CONTAINER}, stop:0.51 rgba(59, 73, 76, 0.4), stop:1 rgba(59, 73, 76, 0.4)); border: none;")
        card_layout.addWidget(self.tab_indicator)
        card_layout.addSpacing(22)

        # Tab sahifalari (Fiksatsiyalangan balandlik)
        self.card_stacked = QStackedWidget()
        self.card_stacked.setFixedHeight(275)
        self.card_stacked.setStyleSheet("background: transparent; border: none;")

        # ── 2A. TAB 1: MEMBER LOGIN ──
        self.page_login = QWidget()
        login_vbox = QVBoxLayout(self.page_login)
        login_vbox.setContentsMargins(0, 0, 0, 0)
        login_vbox.setSpacing(0)

        # Login Forma qismi
        self.login_form_widget = QWidget()
        lfw_lo = QVBoxLayout(self.login_form_widget)
        lfw_lo.setContentsMargins(0, 0, 0, 0)
        lfw_lo.setSpacing(12)

        # Username / ID
        phone_box = QVBoxLayout()
        phone_box.setSpacing(4)
        phone_label = QLabel("USERNAME / ID")
        phone_label.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        phone_label.setStyleSheet(f"color: {COLOR_PRIMARY_CONTAINER}; letter-spacing: 1px;")
        phone_box.addWidget(phone_label)

        self.phone_input = IconLineEdit("👤")
        self.phone_input.setPlaceholderText("Enter your pilot tag / Foydalanuvchi nomi")
        self.phone_input.setFixedHeight(46)
        self.phone_input.setStyleSheet(INPUT_QSS + "QLineEdit { padding-right: 42px; border-radius: 6px; }")
        self.phone_input.returnPressed.connect(self._on_login_clicked)
        phone_box.addWidget(self.phone_input)
        lfw_lo.addLayout(phone_box)

        # Access Code
        password_box = QVBoxLayout()
        password_box.setSpacing(4)
        password_label = QLabel("ACCESS CODE")
        password_label.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        password_label.setStyleSheet(f"color: {COLOR_PRIMARY_CONTAINER}; letter-spacing: 1px;")
        password_box.addWidget(password_label)

        self.password_input = IconLineEdit("🔒")
        self.password_input.setPlaceholderText("••••••••")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setFixedHeight(46)
        self.password_input.setStyleSheet(INPUT_QSS + "QLineEdit { padding-right: 42px; border-radius: 6px; }")
        self.password_input.returnPressed.connect(self._on_login_clicked)
        password_box.addWidget(self.password_input)
        lfw_lo.addLayout(password_box)

        self.login_error = QLabel("")
        self.login_error.setStyleSheet("color: #ffb4ab; font-size: 11px;")
        self.login_error.setWordWrap(True)
        self.login_error.hide()
        lfw_lo.addWidget(self.login_error)

        lfw_lo.addSpacing(4)

        # Pastki qator: Forgot Code? + INITIALIZE tugmasi
        bottom_login_row = QHBoxLayout()
        bottom_login_row.setSpacing(12)

        forgot_btn = QPushButton("Forgot Code?")
        forgot_btn.setFont(cyber_font(9, family="Mono"))
        forgot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        forgot_btn.setStyleSheet(f"""
            QPushButton {{
                color: {COLOR_ON_SURFACE_VARIANT}; background: transparent;
                border: none; text-decoration: underline; text-align: left;
            }}
            QPushButton:hover {{ color: {COLOR_PRIMARY_CONTAINER}; }}
        """)
        forgot_btn.clicked.connect(self._on_forgot_clicked)
        bottom_login_row.addWidget(forgot_btn, 1)

        self.login_btn = QPushButton("INITIALIZE  →")
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.setFixedHeight(46)
        self.login_btn.setMinimumWidth(160)
        self.login_btn.setFont(cyber_font(11, QFont.Weight.Bold, "Sora"))
        self.login_btn.setStyleSheet(CYBER_PRIMARY_BTN_QSS)
        self.login_btn.clicked.connect(self._on_login_clicked)
        bottom_login_row.addWidget(self.login_btn, 0)
        lfw_lo.addLayout(bottom_login_row)

        login_vbox.addWidget(self.login_form_widget)

        # Profil Qismi (Kirilgandan keyin ko'rinadi)
        self.profile_widget = QWidget()
        pw_lo = QVBoxLayout(self.profile_widget)
        pw_lo.setContentsMargins(0, 10, 0, 0)
        pw_lo.setSpacing(10)

        self.profile_name = QLabel("")
        self.profile_name.setFont(cyber_font(15, QFont.Weight.Bold, "Sora"))
        self.profile_name.setStyleSheet(f"color: {COLOR_ON_SURFACE};")
        self.profile_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pw_lo.addWidget(self.profile_name)

        self.profile_balance = QLabel("")
        self.profile_balance.setFont(cyber_font(20, QFont.Weight.Bold, "Sora"))
        self.profile_balance.setStyleSheet(f"color: {COLOR_PRIMARY_CONTAINER};")
        self.profile_balance.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pw_lo.addWidget(self.profile_balance)

        self.profile_bonus = QLabel("")
        self.profile_bonus.setFont(cyber_font(11, family="Hanken"))
        self.profile_bonus.setStyleSheet(f"color: {COLOR_GREEN};")
        self.profile_bonus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pw_lo.addWidget(self.profile_bonus)

        self.unlock_error = QLabel("")
        self.unlock_error.setStyleSheet("color: #ffb4ab; font-size: 11px;")
        self.unlock_error.setWordWrap(True)
        self.unlock_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unlock_error.hide()
        pw_lo.addWidget(self.unlock_error)

        pw_lo.addSpacing(6)

        self.unlock_btn = QPushButton("🔓  KOMPYUTERNI OCHISH")
        self.unlock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unlock_btn.setFixedHeight(46)
        self.unlock_btn.setFont(cyber_font(11, QFont.Weight.Bold, "Sora"))
        self.unlock_btn.setStyleSheet(CYBER_PRIMARY_BTN_QSS)
        self.unlock_btn.clicked.connect(self._on_unlock_clicked)
        pw_lo.addWidget(self.unlock_btn)

        logout_btn = QPushButton("Chiqish")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setFixedHeight(36)
        logout_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.05); color: #94a3b8;
                border: 1px solid rgba(255,255,255,0.12); border-radius: 4px;
            }
            QPushButton:hover { color: #e2e8f0; }
        """)
        logout_btn.clicked.connect(self._on_logout_clicked)
        pw_lo.addWidget(logout_btn)

        login_vbox.addWidget(self.profile_widget)
        self.profile_widget.hide()

        self.card_stacked.addWidget(self.page_login)

        # ── 2B. TAB 2: QR QUICK ACCESS ──
        self.page_qr = QWidget()
        qr_vbox = QVBoxLayout(self.page_qr)
        qr_vbox.setContentsMargins(0, 8, 0, 8)
        qr_vbox.setSpacing(10)
        qr_vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)

        qr_box = CyberQRWidget()
        qr_vbox.addWidget(qr_box, 0, Qt.AlignmentFlag.AlignCenter)

        qr_title = QLabel("Scan to Sync")
        qr_title.setFont(cyber_font(13, QFont.Weight.Bold, "Sora"))
        qr_title.setStyleSheet(f"color: {COLOR_PRIMARY_CONTAINER};")
        qr_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_vbox.addWidget(qr_title)

        qr_sub = QLabel("Open the Cyber-Esports app and scan to instantly load your profile.")
        qr_sub.setFont(cyber_font(10, family="Hanken"))
        qr_sub.setStyleSheet(f"color: {COLOR_ON_SURFACE_VARIANT};")
        qr_sub.setWordWrap(True)
        qr_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_vbox.addWidget(qr_sub)

        self.card_stacked.addWidget(self.page_qr)

        card_layout.addWidget(self.card_stacked)
        center_container.addWidget(self.main_card)
        center_container.addStretch(1)

        root_layout.addLayout(center_container)
        root_layout.addStretch(1)

        # ── 3. FOOTER ROW ──
        footer_row = QHBoxLayout()
        footer_row.setSpacing(16)
        footer_row.setContentsMargins(0, 16, 0, 0)
        footer_row.addStretch(1)

        # O'ng: Admin Override + Version
        admin_col = QVBoxLayout()
        admin_col.setSpacing(4)
        admin_col.setAlignment(Qt.AlignmentFlag.AlignRight)

        override_row = QHBoxLayout()
        override_row.setSpacing(8)
        override_row.addStretch(1)
        override_txt = QLabel("Admin Override")
        override_txt.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        override_txt.setStyleSheet(f"color: {COLOR_ON_SURFACE_VARIANT};")
        override_row.addWidget(override_txt)

        self.override_toggle = QPushButton()
        self.override_toggle.setFixedSize(36, 18)
        self.override_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.override_toggle.setStyleSheet("""
            QPushButton {
                background: #32353C; border: 1px solid #849396;
                border-radius: 9px;
            }
            QPushButton:hover { background: #93000A; border-color: #FFB4AB; }
        """)
        self.override_toggle.clicked.connect(self._on_admin_override_clicked)
        override_row.addWidget(self.override_toggle)
        admin_col.addLayout(override_row)

        ver_lbl = QLabel(f"V {get_local_client_version()}_BETA")
        ver_lbl.setFont(cyber_font(7, family="Mono"))
        ver_lbl.setStyleSheet(f"color: {COLOR_OUTLINE};")
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        admin_col.addWidget(ver_lbl)

        footer_row.addLayout(admin_col)
        root_layout.addLayout(footer_row)

        # ── Soat va signallar ──
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        self._login_result_ready.connect(self._apply_login_result)
        self.unlock_result_ready.connect(self._apply_unlock_result)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._bg_pixmap and not self._bg_pixmap.isNull():
            # Rasm butun oynani to'liq egallaydi
            scaled = self._bg_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            # Yengil shaffof qatlam
            painter.fillRect(self.rect(), QColor(11, 14, 20, 100))
        painter.end()

    def _switch_to_login_tab(self):
        self.card_stacked.setCurrentIndex(0)
        self.tab_login_btn.setStyleSheet(f"""
            QPushButton {{
                color: {COLOR_PRIMARY_CONTAINER}; background: transparent;
                border: none; padding-bottom: 8px;
            }}
        """)
        self.tab_qr_btn.setStyleSheet(f"""
            QPushButton {{
                color: {COLOR_ON_SURFACE_VARIANT}; background: transparent;
                border: none; padding-bottom: 8px;
            }}
            QPushButton:hover {{ color: {COLOR_ON_SURFACE}; }}
        """)
        self.tab_indicator.setStyleSheet(f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {COLOR_PRIMARY_CONTAINER}, stop:0.5 {COLOR_PRIMARY_CONTAINER}, stop:0.51 rgba(59, 73, 76, 0.4), stop:1 rgba(59, 73, 76, 0.4)); border: none;")

    def _switch_to_qr_tab(self):
        self.card_stacked.setCurrentIndex(1)
        self.tab_qr_btn.setStyleSheet(f"""
            QPushButton {{
                color: {COLOR_PRIMARY_CONTAINER}; background: transparent;
                border: none; padding-bottom: 8px;
            }}
        """)
        self.tab_login_btn.setStyleSheet(f"""
            QPushButton {{
                color: {COLOR_ON_SURFACE_VARIANT}; background: transparent;
                border: none; padding-bottom: 8px;
            }}
            QPushButton:hover {{ color: {COLOR_ON_SURFACE}; }}
        """)
        self.tab_indicator.setStyleSheet(f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(59, 73, 76, 0.4), stop:0.49 rgba(59, 73, 76, 0.4), stop:0.5 {COLOR_PRIMARY_CONTAINER}, stop:1 {COLOR_PRIMARY_CONTAINER}); border: none;")

    def _on_forgot_clicked(self):
        QMessageBox.information(
            self,
            "Parolni tiklash",
            "Parolni tiklash yoki yangilash uchun klub administratoriga (kassaga) murojaat qiling."
        )

    def _on_tariff_clicked(self, title, price):
        QMessageBox.information(
            self,
            title,
            f"Tanlangan tarif: {title} ({price})\nSeansni faollashtirish uchun kassaga murojaat qiling yoki hisobingiz orqali kiring."
        )

    def _on_admin_override_clicked(self):
        dialog = AdminOverrideDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            global EMERGENCY_UNLOCK_REQUESTED
            EMERGENCY_UNLOCK_REQUESTED = True

    def _update_clock(self):
        self.clock_label.setText(datetime.now().strftime("%H:%M:%S"))

    def set_pc_name(self, pc_name):
        self.pc_name = pc_name
        self.station_title.setText(f"{pc_name} VIP")

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
        self.login_btn.setText("INITIALIZE  →")
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
        self.login_form_widget.hide()
        self.profile_widget.show()

    def _on_logout_clicked(self):
        self.reset_login_state()

    def reset_login_state(self):
        self.logged_in_customer = None
        self.phone_input.clear()
        self.password_input.clear()
        self.login_error.hide()
        self.profile_widget.hide()
        self.login_form_widget.show()

    def _on_unlock_clicked(self):
        if not self.logged_in_customer:
            return
        self.unlock_error.hide()
        self.unlock_btn.setEnabled(False)
        self.unlock_btn.setText("Ochilmoqda...")
        self.unlock_requested.emit(self.logged_in_customer.get('session_token', ''))

    def _apply_unlock_result(self, ok, data):
        if ok:
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
    """TopBar'ning o'ng tarafidagi "CYBER_STRIKER / PLATINUM RANK"
    kapsulasi — doiraviy neon avatar + ism/status matni. Bosilganda Kabinet
    ochiladi."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(48)
        self.setStyleSheet("""
            QFrame {
                background: transparent;
                border: none;
            }
        """)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        self.name_label = QLabel("CYBER_STRIKER")
        self.name_label.setFont(cyber_font(12, QFont.Weight.Bold, "Sora"))
        self.name_label.setStyleSheet("color: #e1e2eb; background: transparent; border: none;")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        text_col.addWidget(self.name_label)

        self.rank_label = QLabel("PLATINUM RANK")
        self.rank_label.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        self.rank_label.setStyleSheet(f"color: {COLOR_GREEN}; background: transparent; border: none; letter-spacing: 1px;")
        self.rank_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        text_col.addWidget(self.rank_label)
        lo.addLayout(text_col)

        self.avatar = QLabel("🎮")
        self.avatar.setFixedSize(40, 40)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setFont(cyber_font(14, QFont.Weight.Bold, "Sora"))
        self.avatar.setStyleSheet(f"""
            color: #ffffff; border: 2px solid rgba(0, 218, 243, 0.5);
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #191C22, stop:1 #0B0E14);
            border-radius: 20px;
        """)
        lo.addWidget(self.avatar)

    def set_data(self, name, station):
        if name:
            self.avatar.setText(name[:1].upper())
            self.name_label.setText(name.upper())
            self.rank_label.setText("VIP MEMBER")
        else:
            self.avatar.setText("🎮")
            self.name_label.setText("CYBER_STRIKER")
            self.rank_label.setText("PLATINUM RANK")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ──────────────────────────────────────────────────────────────────────────────
#  6. NEXUS SIDEBAR & TOP BAR
# ──────────────────────────────────────────────────────────────────────────────
class NexusSidebar(QFrame):
    """Nexus / Cyber-Esports chap vertikal navigatsiya paneli (w-72 / 260px)."""
    tab_changed = pyqtSignal(str)
    stop_session_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(265)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(18, 24, 36, 0.95);
                border-right: 1px solid rgba(255, 255, 255, 0.05);
            }}
            QLabel {{ border: none; background: transparent; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(8)

        # Logo bloki (CLUTCH ZONE / NEXUS)
        logo_row = QHBoxLayout()
        logo_row.setSpacing(10)
        logo_row.setContentsMargins(8, 6, 8, 20)

        logo_full_path = os.path.join(ASSETS_DIR, "clutch_logo_full.png")
        if not os.path.exists(logo_full_path):
            logo_full_path = os.path.join(ASSETS_DIR, "clutch_logo_mark.png")
            
        logo_label = QLabel()
        logo_label.setStyleSheet("background: transparent; border: none;")
        if os.path.exists(logo_full_path):
            pix = QPixmap(logo_full_path)
            if not pix.isNull():
                logo_label.setPixmap(pix.scaledToHeight(32, Qt.TransformationMode.SmoothTransformation))
        else:
            logo_label.setText("🛡️")
            logo_label.setFont(QFont("Segoe UI Emoji", 16))
        logo_row.addWidget(logo_label)

        title = QLabel("CLUTCH ZONE")
        title.setFont(cyber_font(15, QFont.Weight.ExtraBold, "Sora"))
        title.setStyleSheet(f"color: {COLOR_PRIMARY}; letter-spacing: 1.5px;")
        logo_row.addWidget(title)
        logo_row.addStretch(1)
        layout.addLayout(logo_row)

        # Navigatsiya Tugmalari
        self.nav_buttons = {}
        nav_items = [
            ("home", "🏠  HOME"),
            ("tournaments", "🏆  TOURNAMENTS & BONUSES"),
            ("shop", "🛒  SHOP"),
            ("cabinet", "👤  CABINET"),
        ]

        for key, text in nav_items:
            btn = QPushButton(text)
            btn.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(44)
            btn.clicked.connect(lambda _, k=key: self._select_nav(k))
            layout.addWidget(btn)
            self.nav_buttons[key] = btn

        layout.addStretch(1)

        # Pastki Seans Bloki (Progress bar + Vaqtni Tugat)
        session_box = QFrame()
        session_box.setStyleSheet(f"""
            QFrame {{
                background: rgba(11, 14, 20, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 8px;
            }}
        """)
        sb_layout = QVBoxLayout(session_box)
        sb_layout.setContentsMargins(12, 12, 12, 12)
        sb_layout.setSpacing(10)

        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)
        
        self.prog_bar = QProgressBar()
        self.prog_bar.setFixedHeight(4)
        self.prog_bar.setTextVisible(False)
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(75)
        self.prog_bar.setStyleSheet(f"""
            QProgressBar {{
                background: #32353C; border: none; border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {COLOR_PRIMARY_CONTAINER}; border-radius: 2px;
            }}
        """)
        prog_row.addWidget(self.prog_bar, 1)

        self.time_label = QLabel("01:45H")
        self.time_label.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        self.time_label.setStyleSheet("color: #e1e2eb;")
        prog_row.addWidget(self.time_label)
        sb_layout.addLayout(prog_row)

        self.stop_btn = QPushButton("VAQTNI TUGAT")
        self.stop_btn.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setFixedHeight(38)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background: rgba(147, 0, 10, 0.35);
                color: #FFB4AB;
                border: 1px solid rgba(255, 180, 171, 0.35);
                border-radius: 6px;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background: rgba(255, 84, 73, 0.85);
                color: #FFFFFF;
                border: 1px solid #FF5449;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_session_clicked.emit)
        sb_layout.addWidget(self.stop_btn)

        layout.addWidget(session_box)

        self._active_nav = "home"
        self._apply_nav_styles()

    def set_time_remaining(self, text):
        if text:
            clean = text.replace("⏱", "").strip()
            self.time_label.setText(clean)

    def _select_nav(self, key):
        self._active_nav = key
        self._apply_nav_styles()
        self.tab_changed.emit(key)

    def _apply_nav_styles(self):
        for key, btn in self.nav_buttons.items():
            if key == self._active_nav:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: rgba(0, 229, 255, 0.16);
                        color: {COLOR_PRIMARY_FIXED};
                        border: 1px solid rgba(0, 229, 255, 0.4);
                        border-radius: 8px;
                        text-align: left;
                        padding-left: 14px;
                        font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        color: {COLOR_ON_SURFACE_VARIANT};
                        border: 1px solid transparent;
                        border-radius: 8px;
                        text-align: left;
                        padding-left: 14px;
                    }}
                    QPushButton:hover {{
                        background: rgba(255, 255, 255, 0.05);
                        color: #ffffff;
                        border-color: rgba(255, 255, 255, 0.1);
                    }}
                """)


class TopBar(QFrame):
    """Nexus / Cyber-Esports Yuqori qidiruv va profil paneli (h-20 / 72px)."""
    search_changed = pyqtSignal(str)
    cabinet_requested = pyqtSignal()
    mouse_settings_requested = pyqtSignal()
    achievements_requested = pyqtSignal()

    def __init__(self, pc_name="PC-01", parent=None):
        super().__init__(parent)
        self.pc_name = pc_name
        self.setFixedHeight(72)
        self.setStyleSheet(f"""
            QFrame#topBar {{
                background-color: rgba(16, 19, 26, 0.85);
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }}
            QLabel {{ border: none; background: transparent; }}
        """)
        self.setObjectName("topBar")

        lo = QHBoxLayout(self)
        lo.setContentsMargins(28, 0, 28, 0)
        lo.setSpacing(20)

        # Chap: Qidiruv paneli (Search games, friends, or items...)
        search_box = QFrame()
        search_box.setObjectName("searchBox")
        search_box.setFixedHeight(40)
        search_box.setFixedWidth(320)
        search_box.setStyleSheet(f"""
            QFrame#searchBox {{
                background: rgba(39, 42, 49, 0.45);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 20px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        sb_lo = QHBoxLayout(search_box)
        sb_lo.setContentsMargins(14, 0, 14, 0)
        sb_lo.setSpacing(8)

        search_icon = QLabel("🔍")
        search_icon.setFont(QFont("Segoe UI Emoji", 10))
        search_icon.setStyleSheet("color: #bac9cc; border: none; background: transparent;")
        sb_lo.addWidget(search_icon)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search games, friends, or items...")
        self.search_input.setFont(cyber_font(10, family="Hanken"))
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: transparent; border: none; color: #e1e2eb;
            }
        """)
        self.search_input.textChanged.connect(self.search_changed.emit)
        sb_lo.addWidget(self.search_input)
        lo.addWidget(search_box)

        lo.addStretch(1)

        # O'ng: Balans badge (UZS)
        self.balance_badge = QPushButton("💳  0 UZS")
        self.balance_badge.setFont(cyber_font(10, QFont.Weight.Bold, "Mono"))
        self.balance_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.balance_badge.setFixedHeight(38)
        self.balance_badge.setStyleSheet(f"""
            QPushButton {{
                background: {COLOR_SURFACE_CONTAINER_HIGHEST};
                color: {COLOR_PRIMARY_CONTAINER};
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 8px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: {COLOR_SURFACE_VARIANT};
            }}
        """)
        self.balance_badge.clicked.connect(self.cabinet_requested.emit)
        lo.addWidget(self.balance_badge)

        # Ajratuvchi chiziq
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setFixedHeight(32)
        sep.setStyleSheet("background: rgba(255, 255, 255, 0.1); border: none;")
        lo.addWidget(sep)

        # Profil kapsulasi (CYBER_STRIKER / PLATINUM RANK + Avatar)
        self.profile_capsule = ProfileCapsule()
        self.profile_capsule.clicked.connect(self.cabinet_requested.emit)
        lo.addWidget(self.profile_capsule)

    def set_status(self, pc_name, status_text):
        pass

    def set_time_remaining(self, text):
        pass

    def set_logged_in_customer(self, data):
        if data:
            try:
                balance = float(data.get('balance', 0))
            except (TypeError, ValueError):
                balance = 0
            self.balance_badge.setText(f"💳  {balance:,.0f} UZS".replace(',', ' '))
            self.profile_capsule.set_data(data.get('full_name', ''), f"STATION {self.pc_name}")
        else:
            self.balance_badge.setText("💳  0 UZS")
            self.profile_capsule.set_data("", "")


# ──────────────────────────────────────────────────────────────────────────────
#  6b. CUSTOMER CABINET (SYSTEM PREFERENCES / 1:1 CYBER-ESPORTS)
# ──────────────────────────────────────────────────────────────────────────────
class CustomerCabinetPage(QWidget):
    """Mijozning "SYSTEM PREFERENCES" (Shaxsiy Kabinet) sahifasi — 1:1 Cyber-Esports dizayni."""
    _pw_result_ready = pyqtSignal(bool, dict)
    _activity_result_ready = pyqtSignal(bool, dict)
    _save_result_ready = pyqtSignal(bool, dict)
    stop_session_requested = pyqtSignal(str)
    back_requested = pyqtSignal()

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.customer_data = {}
        self.setStyleSheet(f"background-color: {COLOR_BG};")

        self._pw_result_ready.connect(self._apply_password_result)
        self._activity_result_ready.connect(self._apply_activity_result)
        self._save_result_ready.connect(self._apply_save_result)

        main_lo = QVBoxLayout(self)
        main_lo.setContentsMargins(28, 20, 28, 20)
        main_lo.setSpacing(18)

        # ── 1. HEADER (⚙️ SYSTEM PREFERENCES + Back/Close Button) ──
        header_row = QHBoxLayout()
        header_row.setSpacing(14)

        icon_gear = QLabel("⚙️")
        icon_gear.setFont(QFont("Segoe UI Emoji", 20))
        icon_gear.setStyleSheet("background: transparent; border: none;")
        header_row.addWidget(icon_gear)

        title_lbl = QLabel("SYSTEM PREFERENCES")
        title_lbl.setFont(cyber_font(22, QFont.Weight.Bold, "Sora"))
        title_lbl.setStyleSheet("color: #E1E2EB; letter-spacing: 0.5px; border: none; background: transparent;")
        header_row.addWidget(title_lbl)

        header_row.addStretch(1)

        close_btn = QPushButton("✕  ORQAGA")
        close_btn.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedHeight(34)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #BAC9CC;
                border: 1px solid rgba(132, 147, 150, 0.2);
                border-radius: 8px;
                padding: 0 16px;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background: rgba(0, 218, 243, 0.15);
                color: #00E5FF;
                border: 1px solid #00DAF3;
            }
        """)
        close_btn.clicked.connect(self.back_requested.emit)
        header_row.addWidget(close_btn)
        main_lo.addLayout(header_row)

        # ── 2. BODY (Left Tabs Sidebar + Right Content Area) ──
        body_row = QHBoxLayout()
        body_row.setSpacing(20)

        # ── 2A. LEFT TABS SIDEBAR (Pilot Profile, Security, Billing, etc.) ──
        left_tabs = QFrame()
        left_tabs.setFixedWidth(230)
        left_tabs.setStyleSheet("background: transparent; border: none;")
        tabs_lo = QVBoxLayout(left_tabs)
        tabs_lo.setContentsMargins(0, 0, 0, 0)
        tabs_lo.setSpacing(8)

        # Active "Pilot Profile" tab with glowing cyan indicator
        profile_tab = QFrame()
        profile_tab.setStyleSheet("""
            background: rgba(0, 229, 255, 0.12);
            border: 1px solid rgba(0, 218, 243, 0.45);
            border-radius: 12px;
        """)
        pt_lo = QHBoxLayout(profile_tab)
        pt_lo.setContentsMargins(16, 12, 16, 12)
        pt_lo.setSpacing(10)

        pt_icon = QLabel("👤")
        pt_icon.setFont(QFont("Segoe UI Emoji", 11))
        pt_icon.setStyleSheet("border: none; background: transparent;")
        pt_lo.addWidget(pt_icon)

        pt_text = QLabel("Pilot Profile")
        pt_text.setFont(cyber_font(10, QFont.Weight.Bold, "Sora"))
        pt_text.setStyleSheet("color: #00DAF3; border: none; background: transparent;")
        pt_lo.addWidget(pt_text, 1)

        pt_dot = QLabel("●")
        pt_dot.setStyleSheet("color: #00DAF3; font-size: 8px; border: none; background: transparent;")
        pt_lo.addWidget(pt_dot)
        tabs_lo.addWidget(profile_tab)

        # Other navigation items
        other_tabs = [
            ("🛡️", "ACCOUNT SECURITY"),
            ("💳", "BILLING & CP"),
            ("🎛️", "INTERFACE"),
            ("👁️", "PRIVACY"),
            ("🔔", "NOTIFICATIONS")
        ]
        for icon_s, label_s in other_tabs:
            btn = QPushButton(f"  {icon_s}  {label_s}")
            btn.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(40)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #BAC9CC;
                    border: none;
                    border-radius: 10px;
                    text-align: left;
                    padding-left: 12px;
                    letter-spacing: 1px;
                }
                QPushButton:hover {
                    background: rgba(39, 42, 49, 0.45);
                    color: #E1E2EB;
                }
            """)
            # Bu bo'limlar hali qurilmagan — hech qanday reaksiyasiz
            # "o'lik" tugma qoldirish o'rniga, kamida "tez orada"
            # xabarini ko'rsatadi.
            btn.clicked.connect(lambda _, name=label_s: QMessageBox.information(
                self, "Tez orada", f"\"{name}\" bo'limi hali ishlab chiqilmoqda."
            ))
            tabs_lo.addWidget(btn)

        tabs_lo.addStretch(1)

        # Bu tugma shunchaki kabinetdan chiqmaydi — haqiqiy (pulli)
        # seansni to'xtatib, kompyuterni qulflaydi (_on_stop_session_clicked).
        # Nomi shuni aniq aks ettirishi kerak, aks holda mijoz "Chiqish"
        # deb bosib, tasodifan o'z seansini tugatib qo'yishi mumkin —
        # kabinetdan shunchaki chiqish uchun yuqoridagi "✕ ORQAGA" tugmasi bor.
        logout_btn = QPushButton("  ⏻  SEANSNI TUGATISH")
        logout_btn.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setFixedHeight(42)
        logout_btn.setStyleSheet("""
            QPushButton {
                background: rgba(147, 0, 10, 0.25);
                color: #FFB4AB;
                border: 1px solid rgba(255, 180, 171, 0.35);
                border-radius: 10px;
                text-align: left;
                padding-left: 14px;
                letter-spacing: 1px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: rgba(255, 84, 73, 0.85);
                color: #FFFFFF;
                border: 1px solid #FF5449;
            }
        """)
        logout_btn.clicked.connect(self._on_stop_session_clicked)
        tabs_lo.addWidget(logout_btn)

        body_row.addWidget(left_tabs)

        # ── 2B. RIGHT CONTENT COLUMN (Scroll + Sticky Footer) ──
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #10131A; width: 6px; border-radius: 3px; }
            QScrollBar:handle:vertical { background: rgba(132, 147, 150, 0.25); min-height: 25px; border-radius: 3px; }
            QScrollBar:handle:vertical:hover { background: #00DAF3; }
        """)
        scroll.viewport().setStyleSheet("background: transparent;")

        content_widget = QWidget()
        content_lo = QVBoxLayout(content_widget)
        content_lo.setContentsMargins(0, 0, 10, 0)
        content_lo.setSpacing(16)

        # ── SECTION 1: IDENTITY ──
        sec_identity = QFrame()
        sec_identity.setStyleSheet("""
            background: rgba(29, 32, 38, 0.85);
            border: 1px solid rgba(132, 147, 150, 0.18);
            border-radius: 16px;
        """)
        si_lo = QVBoxLayout(sec_identity)
        si_lo.setContentsMargins(22, 18, 22, 18)
        si_lo.setSpacing(14)

        id_title = QLabel("IDENTITY")
        id_title.setFont(cyber_font(12, QFont.Weight.Bold, "Sora"))
        id_title.setStyleSheet("color: #00DAF3; border: none; background: transparent; letter-spacing: 0.5px;")
        si_lo.addWidget(id_title)

        id_row = QHBoxLayout()
        id_row.setSpacing(20)

        # Avatar container with ring and edit icon
        self.avatar_box = QFrame()
        self.avatar_box.setFixedSize(96, 96)
        self.avatar_box.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0B1E2E, stop:0.5 #1E102E, stop:1 #060B12);
            border: 2px solid rgba(0, 218, 243, 0.5);
            border-radius: 14px;
        """)
        av_lo = QVBoxLayout(self.avatar_box)
        av_lo.setContentsMargins(0, 0, 0, 0)
        self.avatar_label = QLabel("⚡")
        self.avatar_label.setFont(QFont("Segoe UI Emoji", 32))
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setStyleSheet("border: none; background: transparent;")
        av_lo.addWidget(self.avatar_label)
        id_row.addWidget(self.avatar_box)

        # Pilot Tag input & info
        tag_col = QVBoxLayout()
        tag_col.setSpacing(6)

        tag_lbl = QLabel("PILOT TAG")
        tag_lbl.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        tag_lbl.setStyleSheet("color: #849396; border: none; background: transparent; letter-spacing: 1px;")
        tag_col.addWidget(tag_lbl)

        self.pilot_tag_input = QLineEdit("CYBER_STRIKER")
        self.pilot_tag_input.setFont(cyber_font(11, QFont.Weight.Bold, "Sora"))
        self.pilot_tag_input.setFixedHeight(40)
        self.pilot_tag_input.setStyleSheet("""
            QLineEdit {
                background: #0B0E14;
                color: #E1E2EB;
                border: 1px solid rgba(132, 147, 150, 0.25);
                border-radius: 8px;
                padding: 0 12px;
            }
            QLineEdit:focus {
                border: 1px solid #00DAF3;
            }
        """)
        tag_col.addWidget(self.pilot_tag_input)

        tag_hint = QLabel("ⓘ This is your public display name across the Clutch Zone network.")
        tag_hint.setFont(cyber_font(9, family="Hanken"))
        tag_hint.setStyleSheet("color: #BAC9CC; border: none; background: transparent;")
        tag_col.addWidget(tag_hint)

        id_row.addLayout(tag_col, 1)
        si_lo.addLayout(id_row)
        content_lo.addWidget(sec_identity)

        # ── SECTION 2: CURRENT RANK & LIFETIME STATS (2 Columns) ──
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)

        # 2A. CURRENT RANK & BONUS BALL CARD
        rank_card = QFrame()
        rank_card.setStyleSheet("""
            background: rgba(29, 32, 38, 0.85);
            border: 1px solid rgba(132, 147, 150, 0.18);
            border-radius: 16px;
        """)
        rc_lo = QVBoxLayout(rank_card)
        rc_lo.setContentsMargins(20, 18, 20, 18)
        rc_lo.setSpacing(12)

        rc_head = QHBoxLayout()
        rc_head_lbl = QLabel("BONUS BALL & DARAJA")
        rc_head_lbl.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        rc_head_lbl.setStyleSheet("color: #849396; border: none; background: transparent; letter-spacing: 1px;")
        rc_head.addWidget(rc_head_lbl)
        rc_head.addStretch(1)

        self.rank_badge = QLabel("PLATINUM")
        self.rank_badge.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        self.rank_badge.setStyleSheet("""
            color: #52FFAC;
            background: rgba(82, 255, 172, 0.12);
            border: 1px solid rgba(82, 255, 172, 0.3);
            border-radius: 4px;
            padding: 2px 8px;
        """)
        rc_head.addWidget(self.rank_badge)
        rc_lo.addLayout(rc_head)

        rp_row = QHBoxLayout()
        rp_row.setSpacing(6)
        rp_row.setAlignment(Qt.AlignmentFlag.AlignBottom)
        self.rp_val = QLabel("3 450")
        self.rp_val.setFont(cyber_font(28, QFont.Weight.Bold, "Sora"))
        self.rp_val.setStyleSheet("color: #E1E2EB; border: none; background: transparent;")
        rp_row.addWidget(self.rp_val)

        rp_unit = QLabel("BALL")
        rp_unit.setFont(cyber_font(10, QFont.Weight.Bold, "Mono"))
        rp_unit.setStyleSheet("color: #00DAF3; border: none; background: transparent; margin-bottom: 5px;")
        rp_row.addWidget(rp_unit)
        rp_row.addStretch(1)
        rc_lo.addLayout(rp_row)

        rc_lo.addStretch(1)

        # Progress bar
        prog_labels = QHBoxLayout()
        self.prog_left_lbl = QLabel("PLATINUM (3 000)")
        self.prog_left_lbl.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        self.prog_left_lbl.setStyleSheet("color: #849396; border: none; background: transparent;")
        prog_labels.addWidget(self.prog_left_lbl)
        prog_labels.addStretch(1)
        self.prog_right_lbl = QLabel("DIAMOND (5 000 BALL)")
        self.prog_right_lbl.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        self.prog_right_lbl.setStyleSheet("color: #849396; border: none; background: transparent;")
        prog_labels.addWidget(self.prog_right_lbl)
        rc_lo.addLayout(prog_labels)

        self.prog_bar = QFrame()
        self.prog_bar.setFixedHeight(6)
        self.prog_bar.setStyleSheet("""
            background: #0B0E14;
            border-radius: 3px;
        """)
        self.pb_lo = QHBoxLayout(self.prog_bar)
        self.pb_lo.setContentsMargins(0, 0, 0, 0)
        self.pb_lo.setSpacing(0)
        self.pb_fill = QFrame()
        self.pb_fill.setStyleSheet("""
            background: #52FFAC;
            border-radius: 3px;
        """)
        self.pb_lo.addWidget(self.pb_fill, 70)
        self.pb_space = QFrame()
        self.pb_space.setStyleSheet("background: transparent;")
        self.pb_lo.addWidget(self.pb_space, 30)
        rc_lo.addWidget(self.prog_bar)

        stats_row.addWidget(rank_card, 1)

        # 2B. LIFETIME STATS CARD
        life_card = QFrame()
        life_card.setStyleSheet("""
            background: rgba(29, 32, 38, 0.85);
            border: 1px solid rgba(132, 147, 150, 0.18);
            border-radius: 16px;
        """)
        lc_lo = QVBoxLayout(life_card)
        lc_lo.setContentsMargins(20, 18, 20, 18)
        lc_lo.setSpacing(12)

        lc_title = QLabel("LIFETIME STATS")
        lc_title.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        lc_title.setStyleSheet("color: #849396; border: none; background: transparent; letter-spacing: 1px;")
        lc_lo.addWidget(lc_title)

        grid_stats = QGridLayout()
        grid_stats.setSpacing(10)

        # Box 1: Hours played
        b1 = QFrame()
        b1.setStyleSheet("background: #0B0E14; border: 1px solid rgba(132, 147, 150, 0.15); border-radius: 8px;")
        b1_lo = QVBoxLayout(b1)
        b1_lo.setContentsMargins(12, 8, 12, 8)
        b1_lo.setSpacing(2)
        b1_tag = QLabel("HOURS PLAYED")
        b1_tag.setFont(cyber_font(7, QFont.Weight.Bold, "Mono"))
        b1_tag.setStyleSheet("color: #849396; border: none; background: transparent;")
        b1_lo.addWidget(b1_tag)
        self.hours_val = QLabel("1,248")
        self.hours_val.setFont(cyber_font(14, QFont.Weight.Bold, "Sora"))
        self.hours_val.setStyleSheet("color: #00DAF3; border: none; background: transparent;")
        b1_lo.addWidget(self.hours_val)
        grid_stats.addWidget(b1, 0, 0)

        # Box 2: Tournament wins
        b2 = QFrame()
        b2.setStyleSheet("background: #0B0E14; border: 1px solid rgba(132, 147, 150, 0.15); border-radius: 8px;")
        b2_lo = QVBoxLayout(b2)
        b2_lo.setContentsMargins(12, 8, 12, 8)
        b2_lo.setSpacing(2)
        b2_tag = QLabel("TOURNAMENT WINS")
        b2_tag.setFont(cyber_font(7, QFont.Weight.Bold, "Mono"))
        b2_tag.setStyleSheet("color: #849396; border: none; background: transparent;")
        b2_lo.addWidget(b2_tag)
        self.wins_val = QLabel("42")
        self.wins_val.setFont(cyber_font(14, QFont.Weight.Bold, "Sora"))
        self.wins_val.setStyleSheet("color: #D1BCFF; border: none; background: transparent;")
        b2_lo.addWidget(self.wins_val)
        grid_stats.addWidget(b2, 0, 1)

        # Box 3: Win Rate (Full width)
        b3 = QFrame()
        b3.setStyleSheet("background: #0B0E14; border: 1px solid rgba(132, 147, 150, 0.15); border-radius: 8px;")
        b3_lo = QHBoxLayout(b3)
        b3_lo.setContentsMargins(12, 8, 12, 8)
        b3_tag = QLabel("WIN RATE")
        b3_tag.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        b3_tag.setStyleSheet("color: #849396; border: none; background: transparent;")
        b3_lo.addWidget(b3_tag)
        b3_lo.addStretch(1)
        self.winrate_val = QLabel("68.5%")
        self.winrate_val.setFont(cyber_font(14, QFont.Weight.Bold, "Sora"))
        self.winrate_val.setStyleSheet("color: #52FFAC; border: none; background: transparent;")
        b3_lo.addWidget(self.winrate_val)
        grid_stats.addWidget(b3, 1, 0, 1, 2)

        lc_lo.addLayout(grid_stats)
        stats_row.addWidget(life_card, 1)

        content_lo.addLayout(stats_row)

        # ── SECTION 3: SECURITY ──
        sec_security = QFrame()
        sec_security.setStyleSheet("""
            background: rgba(29, 32, 38, 0.85);
            border: 1px solid rgba(132, 147, 150, 0.18);
            border-radius: 16px;
        """)
        ss_lo = QVBoxLayout(sec_security)
        ss_lo.setContentsMargins(22, 18, 22, 18)
        ss_lo.setSpacing(14)

        sec_title = QLabel("SECURITY")
        sec_title.setFont(cyber_font(12, QFont.Weight.Bold, "Sora"))
        sec_title.setStyleSheet("color: #00DAF3; border: none; background: transparent; letter-spacing: 0.5px;")
        ss_lo.addWidget(sec_title)

        sec_fields = QHBoxLayout()
        sec_fields.setSpacing(16)

        # Email field
        email_col = QVBoxLayout()
        email_col.setSpacing(4)
        em_lbl = QLabel("REGISTERED EMAIL")
        em_lbl.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        em_lbl.setStyleSheet("color: #849396; border: none; background: transparent; letter-spacing: 1px;")
        email_col.addWidget(em_lbl)
        self.email_input = QLineEdit("striker@nexus.gg")
        self.email_input.setFont(cyber_font(10, family="Hanken"))
        self.email_input.setFixedHeight(38)
        self.email_input.setEnabled(False)
        self.email_input.setStyleSheet("""
            QLineEdit {
                background: rgba(11, 14, 20, 0.6);
                color: #BAC9CC;
                border: 1px solid rgba(132, 147, 150, 0.15);
                border-radius: 8px;
                padding: 0 12px;
            }
        """)
        email_col.addWidget(self.email_input)
        sec_fields.addLayout(email_col, 1)

        # Phone field
        phone_col = QVBoxLayout()
        phone_col.setSpacing(4)
        ph_lbl = QLabel("PHONE NUMBER")
        ph_lbl.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        ph_lbl.setStyleSheet("color: #849396; border: none; background: transparent; letter-spacing: 1px;")
        phone_col.addWidget(ph_lbl)
        self.phone_input = QLineEdit("+998 (90) 123-45-67")
        self.phone_input.setFont(cyber_font(10, family="Hanken"))
        self.phone_input.setFixedHeight(38)
        self.phone_input.setEnabled(False)
        self.phone_input.setStyleSheet("""
            QLineEdit {
                background: rgba(11, 14, 20, 0.6);
                color: #BAC9CC;
                border: 1px solid rgba(132, 147, 150, 0.15);
                border-radius: 8px;
                padding: 0 12px;
            }
        """)
        phone_col.addWidget(self.phone_input)
        sec_fields.addLayout(phone_col, 1)

        ss_lo.addLayout(sec_fields)

        # Change Password Button & Expandable Section
        pw_row = QHBoxLayout()
        self.change_pw_btn = QPushButton("🔒  CHANGE PASSWORD")
        self.change_pw_btn.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        self.change_pw_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change_pw_btn.setFixedHeight(36)
        self.change_pw_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #00DAF3;
                border: 1px solid rgba(0, 218, 243, 0.45);
                border-radius: 8px;
                padding: 0 16px;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background: rgba(0, 218, 243, 0.15);
                color: #00E5FF;
                border: 1px solid #00DAF3;
            }
        """)
        self.change_pw_btn.clicked.connect(self._toggle_security_section)
        pw_row.addWidget(self.change_pw_btn)
        pw_row.addStretch(1)
        ss_lo.addLayout(pw_row)

        # Expandable password form
        self.pw_form = QWidget()
        pwf_lo = QVBoxLayout(self.pw_form)
        pwf_lo.setContentsMargins(0, 10, 0, 0)
        pwf_lo.setSpacing(10)

        pw_inputs_row = QHBoxLayout()
        pw_inputs_row.setSpacing(12)

        self.old_pw_input = QLineEdit()
        self.old_pw_input.setPlaceholderText("Joriy parol")
        self.old_pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.old_pw_input.setFixedHeight(36)
        self.old_pw_input.setStyleSheet(INPUT_QSS)
        pw_inputs_row.addWidget(self.old_pw_input)

        self.new_pw_input = QLineEdit()
        self.new_pw_input.setPlaceholderText("Yangi parol")
        self.new_pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_pw_input.setFixedHeight(36)
        self.new_pw_input.setStyleSheet(INPUT_QSS)
        pw_inputs_row.addWidget(self.new_pw_input)

        self.pw_submit_btn = QPushButton("SAQLASH ✓")
        self.pw_submit_btn.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        self.pw_submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pw_submit_btn.setFixedHeight(36)
        self.pw_submit_btn.setStyleSheet(GRADIENT_BTN_QSS)
        self.pw_submit_btn.clicked.connect(self._on_change_password_clicked)
        pw_inputs_row.addWidget(self.pw_submit_btn)

        pwf_lo.addLayout(pw_inputs_row)

        self.pw_status = QLabel("")
        self.pw_status.setFont(cyber_font(9, family="Hanken"))
        self.pw_status.hide()
        pwf_lo.addWidget(self.pw_status)

        self.pw_form.hide()
        ss_lo.addWidget(self.pw_form)

        content_lo.addWidget(sec_security)

        # ── SECTION 4: TRANSACTIONS & SESSIONS HISTORY ──
        sec_history = QFrame()
        sec_history.setStyleSheet("""
            background: rgba(29, 32, 38, 0.85);
            border: 1px solid rgba(132, 147, 150, 0.18);
            border-radius: 16px;
        """)
        sh_lo = QVBoxLayout(sec_history)
        sh_lo.setContentsMargins(22, 18, 22, 18)
        sh_lo.setSpacing(12)

        hist_title = QLabel("TRANSACTIONS & SESSIONS")
        hist_title.setFont(cyber_font(12, QFont.Weight.Bold, "Sora"))
        hist_title.setStyleSheet("color: #00DAF3; border: none; background: transparent; letter-spacing: 0.5px;")
        sh_lo.addWidget(hist_title)

        self.activity_area = QScrollArea()
        self.activity_area.setFixedHeight(160)
        self.activity_area.setWidgetResizable(True)
        self.activity_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.activity_container = QWidget()
        self.activity_layout = QVBoxLayout(self.activity_container)
        self.activity_layout.setContentsMargins(0, 0, 0, 0)
        self.activity_layout.setSpacing(6)
        self.activity_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.activity_loading = QLabel("Yuklanmoqda...")
        self.activity_loading.setFont(cyber_font(9, family="Hanken"))
        self.activity_loading.setStyleSheet("color: #849396; border: none; background: transparent;")
        self.activity_layout.addWidget(self.activity_loading)
        self.activity_area.setWidget(self.activity_container)
        sh_lo.addWidget(self.activity_area)

        content_lo.addWidget(sec_history)

        scroll.setWidget(content_widget)
        right_col.addWidget(scroll, 1)

        # ── PINNED STICKY FOOTER ──
        sticky_footer = QFrame()
        sticky_footer.setFixedHeight(60)
        sticky_footer.setStyleSheet("""
            QFrame {
                background: rgba(20, 24, 33, 0.95);
                border: 1px solid rgba(132, 147, 150, 0.18);
                border-radius: 12px;
            }
        """)
        sf_lo = QHBoxLayout(sticky_footer)
        sf_lo.setContentsMargins(20, 0, 20, 0)
        sf_lo.setSpacing(12)

        hint_lbl = QLabel("🛡️ Clutch Zone Cyber-Security Protocol Active")
        hint_lbl.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        hint_lbl.setStyleSheet("color: #849396; border: none; background: transparent;")
        sf_lo.addWidget(hint_lbl)
        sf_lo.addStretch(1)

        self.save_btn = QPushButton("SAVE CHANGES")
        self.save_btn.setFont(cyber_font(10, QFont.Weight.Bold, "Sora"))
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setFixedHeight(40)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background: #00E5FF;
                color: #001F24;
                border: none;
                border-radius: 8px;
                padding: 0 28px;
                letter-spacing: 1px;
                font-weight: 800;
            }
            QPushButton:hover {
                background: #52FFAC;
                color: #002111;
            }
        """)
        self.save_btn.clicked.connect(self._on_save_clicked)
        sf_lo.addWidget(self.save_btn)

        right_col.addWidget(sticky_footer, 0)
        body_row.addLayout(right_col, 1)

        main_lo.addLayout(body_row, 1)

    def set_customer(self, data):
        self.customer_data = data or {}
        full_name = self.customer_data.get('full_name') or self.customer_data.get('username') or 'PILOT'
        phone = self.customer_data.get('phone', '')
        email = self.customer_data.get('email') or f"{full_name.lower().replace(' ', '_')}@clutch.gg"

        self.pilot_tag_input.setText(full_name.upper())
        self.phone_input.setText(phone or "Kiritilmagan")
        self.email_input.setText(email)

        first_char = (full_name or '?')[:1].upper()
        self.avatar_label.setText(first_char)

        # Rank / Bonus ball hisoblash tizimi
        try:
            pts = int(self.customer_data.get('bonus_points', 0))
        except (TypeError, ValueError):
            pts = 0

        if pts <= 0 and bal > 0:
            pts = int(bal / 100)
        if pts <= 0:
            pts = 3450  # Default namoyish

        self.rp_val.setText(f"{pts:,}".replace(',', ' '))

        if pts < 500:
            tier_name = "BRONZE"
            tier_color = "#FFB4AB"
            next_name = "SILVER (500 BALL)"
            pct = int((pts / 500) * 100)
            cur_label = f"BRONZE ({pts})"
        elif pts < 1500:
            tier_name = "SILVER"
            tier_color = "#BAC9CC"
            next_name = "GOLD (1 500 BALL)"
            pct = int(((pts - 500) / 1000) * 100)
            cur_label = "SILVER (500)"
        elif pts < 3000:
            tier_name = "GOLD"
            tier_color = "#FFD700"
            next_name = "PLATINUM (3 000 BALL)"
            pct = int(((pts - 1500) / 1500) * 100)
            cur_label = "GOLD (1 500)"
        elif pts < 5000:
            tier_name = "PLATINUM"
            tier_color = "#52FFAC"
            next_name = "DIAMOND (5 000 BALL)"
            pct = int(((pts - 3000) / 2000) * 100)
            cur_label = "PLATINUM (3 000)"
        else:
            tier_name = "DIAMOND"
            tier_color = "#D1BCFF"
            next_name = "LEGEND (10 000 BALL)"
            pct = min(100, int(((pts - 5000) / 5000) * 100))
            cur_label = "DIAMOND (5 000)"

        pct = max(5, min(100, pct))
        self.rank_badge.setText(tier_name)
        self.rank_badge.setStyleSheet(f"""
            color: {tier_color};
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid {tier_color};
            border-radius: 4px;
            padding: 2px 8px;
        """)
        self.prog_left_lbl.setText(cur_label)
        self.prog_right_lbl.setText(next_name)

        self.pb_lo.setStretch(0, pct)
        self.pb_lo.setStretch(1, 100 - pct)

        self.old_pw_input.clear()
        self.new_pw_input.clear()
        self.pw_status.hide()
        self.pw_form.hide()
        self._load_activity()

    def _toggle_security_section(self):
        self.pw_form.setVisible(not self.pw_form.isVisible())

    def _on_save_clicked(self):
        full_name = self.pilot_tag_input.text().strip()
        if not full_name:
            return
        token = self.customer_data.get('session_token', '')
        self.save_btn.setEnabled(False)
        self.save_btn.setText("SAQLANMOQDA...")
        self.api_client.update_profile_async(
            token, full_name,
            on_done=lambda ok, data: self._save_result_ready.emit(ok, data)
        )

    def _apply_save_result(self, ok, data):
        self.save_btn.setEnabled(True)
        if not ok:
            self.save_btn.setText("SAVE CHANGES")
            error = data.get('error', "Saqlashda xatolik yuz berdi") if isinstance(data, dict) else "Saqlashda xatolik yuz berdi"
            QMessageBox.warning(self, "Xatolik", error)
            return

        self.customer_data['full_name'] = data.get('full_name', self.customer_data.get('full_name', ''))
        self.save_btn.setText("SAVED  ✓")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background: #52FFAC;
                color: #002111;
                border: none;
                border-radius: 10px;
                padding: 0 28px;
                letter-spacing: 1px;
                font-weight: 800;
            }
        """)
        QTimer.singleShot(1200, lambda: self.save_btn.setText("SAVE CHANGES"))
        QTimer.singleShot(1200, lambda: self.save_btn.setStyleSheet("""
            QPushButton {
                background: #00E5FF;
                color: #001F24;
                border: none;
                border-radius: 10px;
                padding: 0 28px;
                letter-spacing: 1px;
                font-weight: 800;
            }
            QPushButton:hover {
                background: #52FFAC;
                color: #002111;
            }
        """))

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
        self.pw_submit_btn.setText("SAQLASH ✓")
        if not ok:
            self._show_pw_status(data.get('error', "Xatolik yuz berdi"), error=True)
            return
        self.old_pw_input.clear()
        self.new_pw_input.clear()
        self._show_pw_status("Parol muvaffaqiyatli yangilandi ✓", error=False)

    def _show_pw_status(self, msg, error=True):
        self.pw_status.setStyleSheet(f"color: {'#FFB4AB' if error else '#52FFAC'}; font-size: 11px;")
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
            err.setStyleSheet("color: #FFB4AB;")
            self.activity_layout.addWidget(err)
            return

        sessions = data.get('sessions', [])
        total_minutes = 0
        for s in sessions:
            try:
                total_minutes += int(s.get('duration_minutes') or 0)
            except (TypeError, ValueError):
                pass
        hours, mins = divmod(total_minutes, 60)
        self.hours_val.setText(f"{hours}h {mins}m" if total_minutes else "1,248")

        rows = []
        for t in data.get('transactions', []):
            is_credit = t.get('type') in ('TOPUP', 'BONUS')
            sign = '+' if is_credit else '−'
            color = '#52FFAC' if is_credit else '#FFB4AB'
            try:
                amount = float(t.get('amount', 0))
            except (TypeError, ValueError):
                amount = 0
            label = t.get('note') or t.get('type_display', '')
            rows.append((t.get('created_at', ''), label, f"{sign}{amount:,.0f} UZS", color))
        for s in sessions:
            try:
                price = float(s.get('total_price', 0))
            except (TypeError, ValueError):
                price = 0
            try:
                duration = int(s.get('duration_minutes') or 0)
            except (TypeError, ValueError):
                duration = 0
            h, m = divmod(duration, 60)
            label = f"🎮 {s.get('computer_name', '')} - {h}:{m:02d} daq"
            rows.append((s.get('start_time', ''), label, f"−{price:,.0f} UZS", '#FFB4AB'))

        rows.sort(key=lambda r: r[0] or '', reverse=True)

        if not rows:
            empty = QLabel("Hali harakatlar tarixi yo'q")
            empty.setStyleSheet("color: #849396; font-size: 11px;")
            self.activity_layout.addWidget(empty)
            return

        for created_at, label, amount_text, color in rows[:40]:
            row = QHBoxLayout()
            date_label = QLabel(str(created_at)[:16].replace('T', ' '))
            date_label.setStyleSheet("color: #849396; font-size: 10px; font-family: monospace;")
            row.addWidget(date_label)
            type_label = QLabel(label)
            type_label.setStyleSheet("color: #E1E2EB; font-size: 11px;")
            row.addWidget(type_label, 1)
            amount_label = QLabel(amount_text)
            amount_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold; font-family: monospace;")
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
    lekin o'zining QScrollArea'siz — BarPage'da kartalarni ikki yondan
    teng masofada simmetrik markazlashtirish uchun ishlatiladi."""
    def __init__(self, card_min_width=250, spacing=16, margins=(0, 0, 0, 0), parent=None):
        super().__init__(parent)
        self.card_min_width = card_min_width
        self.spacing = spacing
        self._items = []
        self._current_cols = -1
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(spacing)
        self.grid_layout.setContentsMargins(*margins)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

    def set_items(self, widgets):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)
        self._items = widgets
        self._current_cols = -1
        self._relayout(force=True)

    def _columns_for_width(self, width):
        col_width = self.card_min_width + self.spacing
        return max(1, width // col_width)

    def _relayout(self, force=False):
        if not self._items:
            return
        w = self.width()
        if w <= 50:
            w = 700
        cols = self._columns_for_width(w)
        if cols == self._current_cols and not force:
            return
        self._current_cols = cols

        # Space-between hisobi: chap va o'ng chekkalarga taqalib, oraliqlar teng taqsimlanadi
        total_cards_w = cols * self.card_min_width
        avail_space = w - total_cards_w - 8
        if cols > 1 and avail_space > 0:
            h_gap = max(12, avail_space // (cols - 1))
            self.grid_layout.setHorizontalSpacing(h_gap)
            self.grid_layout.setVerticalSpacing(16)
            self.grid_layout.setContentsMargins(4, 4, 4, 16)
        else:
            self.grid_layout.setHorizontalSpacing(self.spacing)
            self.grid_layout.setVerticalSpacing(16)
            side_margin = max(0, (w - (cols * self.card_min_width + (cols - 1) * self.spacing)) // 2)
            self.grid_layout.setContentsMargins(side_margin, 4, side_margin, 16)

        while self.grid_layout.count():
            self.grid_layout.takeAt(0)

        for index, widget in enumerate(self._items):
            row, col = divmod(index, cols)
            align = Qt.AlignmentFlag.AlignLeft
            if cols > 1:
                if col == 0:
                    align = Qt.AlignmentFlag.AlignLeft
                elif col == cols - 1:
                    align = Qt.AlignmentFlag.AlignRight
                else:
                    align = Qt.AlignmentFlag.AlignHCenter
            self.grid_layout.addWidget(widget, row, col, align)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._items:
            self._relayout()


class ResponsiveGrid(QScrollArea):
    """O'yin kartalarini ikki yondan teng masofada markazlashtirib,
    ekran kengligiga mos ravishda silliq joylashtiruvchi panjara."""
    def __init__(self, card_width=270, spacing=24, parent=None):
        super().__init__(parent)
        self.card_width = card_width
        self.spacing = spacing
        self._items = []
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(f"""
            QScrollArea {{ border: none; background-color: {COLOR_BG}; }}
            QScrollBar:vertical {{
                background: #10131a;
                width: 6px;
                margin: 0px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: #272a31;
                min-height: 20px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #00daf3;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        self.viewport().setStyleSheet(f"background-color: {COLOR_BG};")

        self.container = QWidget()
        self.container.setStyleSheet(f"background-color: {COLOR_BG};")
        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setSpacing(spacing)
        self.grid_layout.setContentsMargins(10, 10, 10, 24)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setWidget(self.container)

    def set_items(self, widgets):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)
        self._items = widgets
        self._relayout()

    def _columns_for_width(self, width):
        col_width = self.card_width + self.spacing
        return max(1, width // col_width)

    def _relayout(self):
        vp_width = max(300, self.viewport().width())
        cols = self._columns_for_width(vp_width)
        for index, widget in enumerate(self._items):
            row, col = divmod(index, cols)
            self.grid_layout.addWidget(widget, row, col, Qt.AlignmentFlag.AlignCenter)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._items:
            self._relayout()


# ──────────────────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
#  8. GAME CARD (BORDERLESS, GLOWING BOX-SHADOW & IMAGE ZOOM HOVER)
# ──────────────────────────────────────────────────────────────────────────────
class GameCard(QFrame):
    """Nexus / Cyber-Esports 270x360 o'yin kartasi:
    - Card border umuman yo'q (border: none)
    - Hover'da: kuchli neon box-shadow (tashqi nur)
    - Hover'da: rasm 1.1x kattalashadi (smooth image zoom)
    - Yangi jozibador elektr-neon tugma rangi
    """
    launch_requested = pyqtSignal(dict)

    def __init__(self, game, parent=None):
        super().__init__(parent)
        self.game = game
        self.card_w = 270
        self.card_h = 360
        self.setFixedSize(self.card_w, self.card_h)
        self.setObjectName("gameCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QFrame#gameCard {
                background: #191C22;
                border: none;
                border-radius: 12px;
            }
        """)

        # Oq / Kulrang (White / Silver) Glow Box-Shadow effekti
        self.glow_effect = QGraphicsDropShadowEffect(self)
        self.glow_effect.setBlurRadius(0)
        self.glow_effect.setColor(QColor(255, 255, 255, 0))
        self.glow_effect.setOffset(0, 0)
        self.setGraphicsEffect(self.glow_effect)

        # Orqa fon rasmi (Cover) — kattalashish animatsiyasi uchun joylashtiriladi
        self.cover = QLabel(self)
        self.cover.setGeometry(0, 0, self.card_w, self.card_h)
        self.cover.setScaledContents(True)
        self.cover.setStyleSheet("border-radius: 12px; background-color: #121824; border: none;")
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setText("🎮")
        self.cover.setFont(QFont("Segoe UI", 40))

        cover_path = game.get('cover_path')
        if cover_path:
            load_image_async(cover_path, self.cover)

        # Pastki matn va tugma konteyneri (Normal holat: Y=262 — button tepasiga aniq marjin berilgan)
        self.overlay = QWidget(self)
        self.overlay.setGeometry(0, 262, self.card_w, 98)
        self.overlay.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 transparent,
                stop:0.18 rgba(11, 14, 20, 0.88),
                stop:0.55 rgba(11, 14, 20, 0.98),
                stop:1 #0B0E14);
            border-bottom-left-radius: 12px;
            border-bottom-right-radius: 12px;
            border: none;
        """)

        over_lo = QVBoxLayout(self.overlay)
        over_lo.setContentsMargins(14, 2, 14, 2)
        over_lo.setSpacing(3)

        # O'yin nomi
        self._name_text = game.get('name', 'Unknown')
        self.name_label = QLabel(self._name_text)
        self.name_label.setFont(cyber_font(13, QFont.Weight.Bold, "Sora"))
        self.name_label.setStyleSheet("color: #FFFFFF; background: transparent; border: none;")
        self.name_label.setWordWrap(True)
        over_lo.addWidget(self.name_label)

        # Status badge (● INSTALLED)
        status_row = QHBoxLayout()
        status_row.setSpacing(5)
        status_dot = QLabel("●")
        status_dot.setStyleSheet("color: #00FFA3; font-size: 8px; background: transparent; border: none;")
        status_row.addWidget(status_dot)

        status_text = QLabel("INSTALLED")
        status_text.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        status_text.setStyleSheet("color: #00FFA3; background: transparent; border: none; letter-spacing: 1px;")
        status_row.addWidget(status_text)
        status_row.addStretch(1)
        over_lo.addLayout(status_row)

        # Tugma bilan matnlar o'rtasida aniq yuqori oraliq (Margin)
        over_lo.addSpacing(7)

        # Play Now Tugmasi (Oddiy holatda foni shaffof, eng pastki qismda)
        self.play_btn = QPushButton("▶  PLAY NOW")
        self.play_btn.setFont(cyber_font(9, QFont.Weight.Bold, "Sora"))
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.setFixedHeight(32)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #00E5FF;
                border: 1px solid rgba(0, 229, 255, 0.55);
                border-radius: 5px;
                letter-spacing: 1px;
                font-weight: 800;
            }
            QPushButton:hover {
                background: #00E5FF;
                color: #001F24;
                border: 1px solid #00E5FF;
            }
        """)
        self.play_btn.clicked.connect(self._on_play_clicked)

        # Button uchun neon Box-Shadow effekti
        self.btn_glow = QGraphicsDropShadowEffect(self.play_btn)
        self.btn_glow.setBlurRadius(0)
        self.btn_glow.setColor(QColor(0, 229, 255, 0))
        self.btn_glow.setOffset(0, 0)
        self.play_btn.setGraphicsEffect(self.btn_glow)

        over_lo.addWidget(self.play_btn)
        over_lo.addStretch(1)

        # 1. Overlay 3px ko'tarilish animatsiyasi (uzoqroq va juda mayin 850ms)
        self.overlay_anim = QPropertyAnimation(self.overlay, b"geometry")
        self.overlay_anim.setDuration(850)
        self.overlay_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 2. Rasm kattalashishi (Cover Zoom) animatsiyasi (850ms)
        self.cover_anim = QPropertyAnimation(self.cover, b"geometry")
        self.cover_anim.setDuration(850)
        self.cover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 3. Box-Shadow silliq nurlanish animatsiyasi (850ms)
        self._shadow_val = 0.0
        self.shadow_anim = QVariantAnimation(self)
        self.shadow_anim.setDuration(850)
        self.shadow_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.shadow_anim.valueChanged.connect(self._on_shadow_animated)

        self._launching = False

    def _on_shadow_animated(self, val):
        self._shadow_val = float(val)
        v = self._shadow_val

        # 1. Card oq/kumushrang box shadow fade
        alpha = int(v * 130)
        radius = int(v * 32)
        self.glow_effect.setColor(QColor(235, 240, 255, alpha))
        self.glow_effect.setBlurRadius(radius)

        # 2. Button neon box shadow fade
        btn_alpha = int(v * 190)
        btn_radius = int(v * 20)
        self.btn_glow.setColor(QColor(0, 229, 255, btn_alpha))
        self.btn_glow.setBlurRadius(btn_radius)

        # 3. Button ranglarining silliq va bir xil tezlikda o'tishi (850ms)
        bg_a = v
        text_g = int(229 * (1.0 - v) + 31 * v)
        text_b = int(255 * (1.0 - v) + 36 * v)
        border_a = 0.55 + 0.45 * v

        self.play_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0, 229, 255, {bg_a:.3f});
                color: rgb(0, {text_g}, {text_b});
                border: 1px solid rgba(0, 229, 255, {border_a:.3f});
                border-radius: 5px;
                letter-spacing: 1px;
                font-weight: 800;
            }}
        """)

    def enterEvent(self, event):
        # Box-shadow va button rangi silliq 850ms OutCubic bilan nurlanadi
        self.shadow_anim.stop()
        self.shadow_anim.setStartValue(self._shadow_val)
        self.shadow_anim.setEndValue(1.0)
        self.shadow_anim.start()

        # Rasm silliq 1.08x kattalashadi (850ms)
        self.cover_anim.stop()
        self.cover_anim.setStartValue(self.cover.geometry())
        self.cover_anim.setEndValue(QRect(-10, -14, self.card_w + 20, self.card_h + 28))
        self.cover_anim.start()

        # O'yin nomi, installed so'zi va button birgalikda 3px yuqoriga ko'tariladi (Y: 262 -> 259)
        self.overlay_anim.stop()
        self.overlay_anim.setStartValue(self.overlay.geometry())
        self.overlay_anim.setEndValue(QRect(0, 259, self.card_w, 101))
        self.overlay_anim.start()

        super().enterEvent(event)

    def leaveEvent(self, event):
        # Box-shadow va button rangi silliq 850ms da so'nadi
        self.shadow_anim.stop()
        self.shadow_anim.setStartValue(self._shadow_val)
        self.shadow_anim.setEndValue(0.0)
        self.shadow_anim.start()

        # Rasm asl o'lchamiga qaytadi
        self.cover_anim.stop()
        self.cover_anim.setStartValue(self.cover.geometry())
        self.cover_anim.setEndValue(QRect(0, 0, self.card_w, self.card_h))
        self.cover_anim.start()

        # Overlay asl holatiga qaytadi (Y: 259 -> 262)
        self.overlay_anim.stop()
        self.overlay_anim.setStartValue(self.overlay.geometry())
        self.overlay_anim.setEndValue(QRect(0, 262, self.card_w, 98))
        self.overlay_anim.start()

        super().leaveEvent(event)

    def _on_play_clicked(self):
        if not self._launching:
            self._launching = True
            self.play_btn.setText("⏳ LAUNCHING...")
            self.play_btn.setEnabled(False)
            self.launch_requested.emit(self.game)
            QTimer.singleShot(6000, self._reset_launch_state)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._launching:
            self._on_play_clicked()
        super().mousePressEvent(event)

    def _reset_launch_state(self):
        self._launching = False
        try:
            self.play_btn.setText("▶  PLAY NOW")
            self.play_btn.setEnabled(True)
        except RuntimeError:
            pass


# ──────────────────────────────────────────────────────────────────────────────
#  9. GAMES PAGE (NEXUS CYBER-ESPORTS HUD & CATALOG)
# ──────────────────────────────────────────────────────────────────────────────
class GamesPage(QWidget):
    game_launch_requested = pyqtSignal(dict)
    tab_switch_requested = pyqtSignal(str)

    def __init__(self, pc_name="PC-01", parent=None):
        super().__init__(parent)
        self.pc_name = pc_name
        self.setStyleSheet(f"background-color: {COLOR_BG};")
        self._all_games = []
        self._active_category = "all"
        self._search_query = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 16, 28, 10)
        root.setSpacing(14)

        # ── 1. HUD SESSION STATUS STRIP ──
        hud_strip = QFrame()
        hud_strip.setFixedHeight(48)
        hud_strip.setStyleSheet(f"""
            QFrame {{
                background: rgba(11, 14, 20, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 8px;
            }}
            QLabel {{ border: none; background: transparent; }}
        """)
        hud_lo = QHBoxLayout(hud_strip)
        hud_lo.setContentsMargins(20, 0, 20, 0)
        hud_lo.setSpacing(18)

        # PC ID
        pc_icon = QLabel("💻")
        pc_icon.setFont(QFont("Segoe UI Emoji", 10))
        hud_lo.addWidget(pc_icon)
        
        pc_label = QLabel(f"PC: {self.pc_name}")
        pc_label.setFont(cyber_font(10, QFont.Weight.Bold, "Mono"))
        pc_label.setStyleSheet("color: #e1e2eb;")
        hud_lo.addWidget(pc_label)

        dot1 = QLabel("•")
        dot1.setStyleSheet("color: #32353c; font-size: 14px;")
        hud_lo.addWidget(dot1)

        # SESSION TIMER
        sess_icon = QLabel("⏱")
        sess_icon.setFont(QFont("Segoe UI Emoji", 10))
        hud_lo.addWidget(sess_icon)

        sess_title = QLabel("SESSION:")
        sess_title.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        sess_title.setStyleSheet(f"color: {COLOR_ON_SURFACE_VARIANT};")
        hud_lo.addWidget(sess_title)

        self.session_timer_label = QLabel("01:45:12")
        self.session_timer_label.setFont(cyber_font(11, QFont.Weight.Bold, "Sora"))
        self.session_timer_label.setStyleSheet(f"color: {COLOR_PRIMARY_CONTAINER};")
        hud_lo.addWidget(self.session_timer_label)

        hud_lo.addStretch(1)

        # LOCAL TIME
        clock_icon = QLabel("🕒")
        clock_icon.setFont(QFont("Segoe UI Emoji", 10))
        hud_lo.addWidget(clock_icon)

        self.local_time_label = QLabel(datetime.now().strftime("%H:%M"))
        self.local_time_label.setFont(cyber_font(11, QFont.Weight.Bold, "Sora"))
        self.local_time_label.setStyleSheet("color: #e1e2eb;")
        hud_lo.addWidget(self.local_time_label)

        root.addWidget(hud_strip)

        # Jonli vaqt hisoblagich
        self._hud_timer = QTimer(self)
        self._hud_timer.timeout.connect(self._update_hud_clock)
        self._hud_timer.start(1000)

        # ── 2. CATEGORY FILTERS ──
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(10)

        self.cat_row = QHBoxLayout()
        self.cat_row.setSpacing(8)
        self.cat_buttons = {}
        filter_bar.addLayout(self.cat_row)
        filter_bar.addStretch(1)

        root.addLayout(filter_bar)

        # Error banner
        self.error_banner = QLabel("")
        self.error_banner.setFont(cyber_font(10, QFont.Weight.Bold, "Sora"))
        self.error_banner.setStyleSheet("color: #ffb4ab; background: rgba(147, 0, 10, 0.3); border: 1px solid rgba(255, 180, 171, 0.3); border-radius: 8px; padding: 10px 16px;")
        self.error_banner.hide()
        root.addWidget(self.error_banner)

        # ── 3. RESPONSIVE GAME GRID ──
        self.grid = ResponsiveGrid(card_width=270, spacing=24)
        root.addWidget(self.grid, 1)

        self._rebuild_category_filters([])

    def _update_hud_clock(self):
        self.local_time_label.setText(datetime.now().strftime("%H:%M"))

    def set_session_time(self, text):
        if text:
            clean = text.replace("⏱", "").replace("ACTIVE ·", "").strip()
            self.session_timer_label.setText(clean)

    def set_search_query(self, query):
        self._search_query = query.strip().lower()
        self._refresh_grid()

    def show_error(self, msg):
        self.error_banner.setText(f"❌  {msg}")
        self.error_banner.show()

    def clear_error(self):
        self.error_banner.hide()

    def set_games(self, games):
        self._all_games = games
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
        while self.cat_row.count() > 0:
            item = self.cat_row.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self.cat_buttons = {}

        # Standart Esports toifalari
        standard_tabs = [("all", "All Games"), ("esports", "Esports"), ("fps", "FPS"), ("moba", "MOBA"), ("steam", "Steam"), ("epic", "Epic")]
        
        # Dinamik toifalarni qo'shish
        all_cats = list(standard_tabs)
        for cat in categories:
            if not any(cat.lower() == k for k, _ in standard_tabs):
                all_cats.append((cat.lower(), cat.capitalize()))

        for key, label in all_cats:
            btn = QPushButton(label)
            btn.setFont(cyber_font(10, QFont.Weight.Bold, "Sora"))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(34)
            btn.clicked.connect(lambda _, k=key: self._select_category(k))
            self.cat_row.addWidget(btn)
            self.cat_buttons[key] = btn

        self._apply_category_styles()

    def _select_category(self, key):
        self._active_category = key
        self._apply_category_styles()
        self._refresh_grid()

    def _apply_category_styles(self):
        for key, btn in self.cat_buttons.items():
            if key == self._active_category:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {COLOR_PRIMARY_CONTAINER};
                        color: #00363D;
                        border: none;
                        border-radius: 17px;
                        padding: 0 18px;
                        font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {COLOR_SURFACE_CONTAINER};
                        color: {COLOR_ON_SURFACE_VARIANT};
                        border: 1px solid rgba(255, 255, 255, 0.05);
                        border-radius: 17px;
                        padding: 0 18px;
                    }}
                    QPushButton:hover {{
                        background: {COLOR_SURFACE_CONTAINER_HIGH};
                        color: #ffffff;
                    }}
                """)

    def _refresh_grid(self):
        games = self._all_games
        if self._active_category != "all":
            games = [g for g in games if (g.get('category') or '').lower() == self._active_category.lower()]

        if self._search_query:
            games = [g for g in games if self._search_query in (g.get('name') or '').lower() or self._search_query in (g.get('category') or '').lower()]

        cards = []
        for g in games:
            card = GameCard(g)
            card.launch_requested.connect(self.game_launch_requested.emit)
            cards.append(card)
        self.grid.set_items(cards)


# ──────────────────────────────────────────────────────────────────────────────
#  10. NEXUS FUEL & SNACKS (BAR / SHOP PAGE)
# ──────────────────────────────────────────────────────────────────────────────
FALLBACK_SNACK_PRODUCTS = [
    {
        "id": "snack-1",
        "name": "Clutch Overdrive Energy",
        "category_name": "ENERGY",
        "price": 450,
        "price_unit": "CP",
        "description": "Maximum caffeine, zero sugar. Enhances reaction times.",
        "stock": 14,
        "is_hot": False,
        "icon": "⚡",
        "bg_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0B1E2E, stop:0.5 #081420, stop:1 #060B12)"
    },
    {
        "id": "snack-2",
        "name": "Focus Flow Elixir",
        "category_name": "ENERGY",
        "price": 350,
        "price_unit": "CP",
        "description": "Nootropic blend for sustained concentration.",
        "stock": 8,
        "is_hot": False,
        "icon": "🧪",
        "bg_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1E102E, stop:0.5 #140A20, stop:1 #0A0612)"
    },
    {
        "id": "snack-3",
        "name": "Spicy Cyber Ramen",
        "category_name": "HOT FOOD",
        "price": 1200,
        "price_unit": "CP",
        "description": "Intense heat, rich pork broth. The classic late-night grind fuel.",
        "stock": 10,
        "is_hot": True,
        "icon": "🍜",
        "bg_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2E1212, stop:0.5 #1F0A0A, stop:1 #120505)"
    },
    {
        "id": "snack-4",
        "name": "Quantum Crunch Chips",
        "category_name": "SNACKS",
        "price": 600,
        "price_unit": "CP",
        "description": "Spicy nacho flavor. Dust-free formula keeps your gear clean.",
        "stock": 25,
        "is_hot": False,
        "icon": "🍿",
        "bg_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #251633, stop:0.5 #180D24, stop:1 #0E0717)"
    },
    {
        "id": "snack-5",
        "name": "Glacier Pure Hydration",
        "category_name": "HYDRATION",
        "price": 250,
        "price_unit": "CP",
        "description": "Alkaline electrolyte water with essential minerals.",
        "stock": 30,
        "is_hot": False,
        "icon": "💧",
        "bg_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0D2436, stop:0.5 #081724, stop:1 #040E17)"
    },
    {
        "id": "snack-6",
        "name": "Cyber Burger Royale",
        "category_name": "HOT FOOD",
        "price": 1500,
        "price_unit": "CP",
        "description": "Double smash beef, melted cheddar, crispy caramelized onions.",
        "stock": 6,
        "is_hot": True,
        "icon": "🍔",
        "bg_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2E1D0E, stop:0.5 #1E1208, stop:1 #120A04)"
    }
]


def _snack_category_icon(name):
    n = (name or '').lower()
    if any(k in n for k in ('energy', 'drink', 'ichim', 'volt', 'redbull', 'monster')):
        return '⚡'
    if any(k in n for k in ('hot', 'food', 'ramen', 'burger', 'taom', 'ovqat')):
        return '🍜'
    if any(k in n for k in ('snack', 'chip', 'cookie', 'shirinlik', 'bar')):
        return '🍪'
    if any(k in n for k in ('hydrat', 'water', 'suv', 'aqua', 'juice', 'sok')):
        return '💧'
    return '🛒'


class SnackProductCard(QFrame):
    """Cyber-Esports Snack & Fuel Card."""
    add_to_cart_clicked = pyqtSignal(dict)

    def __init__(self, product, parent=None):
        super().__init__(parent)
        self.product = product
        try:
            self.stock = max(0, int(product.get('stock', 0)))
        except (TypeError, ValueError):
            self.stock = 10

        self.setFixedWidth(250)
        self.setFixedHeight(355)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("snackCard")

        self.setStyleSheet("""
            QFrame#snackCard {
                background: #191C22;
                border: 1px solid rgba(132, 147, 150, 0.2);
                border-radius: 12px;
            }
            QFrame#snackCard:hover {
                background: #1D2026;
                border: 1px solid #00DAF3;
            }
        """)

        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 12)
        lo.setSpacing(0)

        # ── 1. Cover Box ──
        self.cover_box = QWidget()
        self.cover_box.setFixedHeight(150)
        bg_grad = product.get('bg_gradient') or "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0B1E2E, stop:1 #060B12)"
        self.cover_box.setStyleSheet(f"""
            background: {bg_grad};
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
            border: none;
        """)
        cover_lo = QVBoxLayout(self.cover_box)
        cover_lo.setContentsMargins(10, 10, 10, 8)

        # Top row: HOT badge (left) & Price badge (right)
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        is_hot = product.get('is_hot', False) or 'hot' in (product.get('category_name') or '').lower()
        if is_hot:
            hot_badge = QLabel("HOT")
            hot_badge.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
            hot_badge.setStyleSheet("""
                background: rgba(147, 0, 10, 0.55);
                color: #FFB4AB;
                border: 1px solid rgba(255, 180, 171, 0.45);
                border-radius: 4px;
                padding: 2px 6px;
            """)
            top_row.addWidget(hot_badge)

        top_row.addStretch(1)

        # Price badge
        try:
            price_val = float(product.get('price', 0))
        except (TypeError, ValueError):
            price_val = 0.0
        unit = product.get('price_unit', 'CP')
        price_text = f"{price_val:,.0f} {unit}".replace(',', ' ')
        price_badge = QLabel(price_text)
        price_badge.setFont(cyber_font(10, QFont.Weight.Bold, "Sora"))
        price_badge.setStyleSheet("""
            background: rgba(25, 28, 34, 0.9);
            color: #00DAF3;
            border: 1px solid rgba(0, 218, 243, 0.4);
            border-radius: 6px;
            padding: 2px 8px;
        """)
        top_row.addWidget(price_badge)
        cover_lo.addLayout(top_row)

        # Center product icon/art
        center_icon = QLabel(product.get('icon') or _snack_category_icon(product.get('category_name')))
        center_icon.setFont(QFont("Segoe UI Emoji", 36))
        center_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_icon.setStyleSheet("background: transparent; border: none;")
        cover_lo.addWidget(center_icon, 1)

        lo.addWidget(self.cover_box)

        # ── 2. Content Info (Vertikal va Gorizontal Markazda) ──
        info_widget = QWidget()
        info_widget.setStyleSheet("background: transparent; border: none;")
        info_lo = QVBoxLayout(info_widget)
        info_lo.setContentsMargins(14, 4, 14, 0)
        info_lo.setSpacing(4)

        info_lo.addStretch(1)

        # Title Row (Name + Green status dot) — Markazda
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        name_label = QLabel(product.get('name', 'Unknown'))
        name_label.setFont(cyber_font(12, QFont.Weight.Bold, "Sora"))
        name_label.setStyleSheet("color: #E1E2EB; background: transparent; border: none;")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setWordWrap(True)
        title_row.addWidget(name_label)

        if self.stock > 0:
            status_dot = QLabel("●")
            status_dot.setStyleSheet("color: #52FFAC; font-size: 8px; background: transparent; border: none;")
            title_row.addWidget(status_dot)
        info_lo.addLayout(title_row)

        # Description — Markazda
        desc_text = product.get('description') or "High performance gaming fuel."
        desc_label = QLabel(desc_text)
        desc_label.setFont(cyber_font(9, family="Hanken"))
        desc_label.setStyleSheet("color: #BAC9CC; background: transparent; border: none;")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        desc_label.setFixedHeight(28)
        info_lo.addWidget(desc_label)

        # Stock indicator — Markazda
        stock_text = f"● Omborda: {self.stock} ta" if self.stock > 0 else "Omborda yo'q"
        stock_color = "#52FFAC" if self.stock > 0 else "#FFB4AB"
        stock_label = QLabel(stock_text)
        stock_label.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        stock_label.setStyleSheet(f"color: {stock_color}; background: transparent; border: none;")
        stock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_lo.addWidget(stock_label)

        info_lo.addStretch(1)

        # ── 3. Add to Cart Button ──
        self.add_btn = QPushButton("+  ADD TO CART")
        self.add_btn.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setFixedHeight(34)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #00DAF3;
                border: 1px solid rgba(0, 218, 243, 0.45);
                border-radius: 6px;
                letter-spacing: 1px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: rgba(0, 218, 243, 0.18);
                color: #00E5FF;
                border: 1px solid #00DAF3;
            }
            QPushButton:disabled {
                color: #4F5560;
                border: 1px solid rgba(132, 147, 150, 0.2);
            }
        """)
        self.add_btn.setEnabled(self.stock > 0)
        self.add_btn.clicked.connect(self._on_add_clicked)
        info_lo.addWidget(self.add_btn)

        lo.addWidget(info_widget, 1)

    def _on_add_clicked(self):
        self.add_to_cart_clicked.emit(self.product)
        # Visual feedback: flash ADDED ✓
        self.add_btn.setText("ADDED  ✓")
        self.add_btn.setStyleSheet("""
            QPushButton {
                background: #52FFAC;
                color: #002111;
                border: 1px solid #52FFAC;
                border-radius: 6px;
                letter-spacing: 1px;
                font-weight: 800;
            }
        """)
        QTimer.singleShot(600, self._restore_btn_text)

    def _restore_btn_text(self):
        self.add_btn.setText("+  ADD TO CART")
        self.add_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #00DAF3;
                border: 1px solid rgba(0, 218, 243, 0.45);
                border-radius: 6px;
                letter-spacing: 1px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: rgba(0, 218, 243, 0.18);
                color: #00E5FF;
                border: 1px solid #00DAF3;
            }
        """)


class CartItemWidget(QFrame):
    """Savatdagi bitta mahsulot bloki."""
    qty_changed = pyqtSignal(dict, int)

    def __init__(self, product, qty=1, parent=None):
        super().__init__(parent)
        self.product = product
        self.qty = qty
        self.setFixedHeight(64)
        self.setObjectName("cartItem")
        self.setStyleSheet("""
            QFrame#cartItem {
                background: #10131A;
                border: 1px solid rgba(132, 147, 150, 0.18);
                border-radius: 8px;
            }
            QFrame#cartItem:hover {
                border: 1px solid rgba(0, 218, 243, 0.35);
            }
        """)

        lo = QHBoxLayout(self)
        lo.setContentsMargins(8, 8, 8, 8)
        lo.setSpacing(10)

        # Thumbnail icon box
        bg_grad = product.get('bg_gradient') or "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0B1E2E, stop:1 #060B12)"
        thumb = QLabel(product.get('icon') or _snack_category_icon(product.get('category_name')))
        thumb.setFixedSize(44, 44)
        thumb.setFont(QFont("Segoe UI Emoji", 20))
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet(f"""
            background: {bg_grad};
            border: 1px solid rgba(132, 147, 150, 0.2);
            border-radius: 6px;
        """)
        lo.addWidget(thumb)

        # Title & price
        mid = QVBoxLayout()
        mid.setSpacing(2)
        mid.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        name_lbl = QLabel(product.get('name', ''))
        name_lbl.setFont(cyber_font(11, QFont.Weight.Bold, "Sora"))
        name_lbl.setStyleSheet("color: #E1E2EB; border: none; background: transparent;")
        mid.addWidget(name_lbl)

        try:
            p_val = float(product.get('price', 0))
        except (TypeError, ValueError):
            p_val = 0.0
        unit = product.get('price_unit', 'CP')
        price_lbl = QLabel(f"{p_val:,.0f} {unit}".replace(',', ' '))
        price_lbl.setFont(cyber_font(10, QFont.Weight.Bold, "Sora"))
        price_lbl.setStyleSheet("color: #00DAF3; border: none; background: transparent;")
        mid.addWidget(price_lbl)
        lo.addLayout(mid, 1)

        # Stepper box (+ / qty / -)
        step_box = QFrame()
        step_box.setStyleSheet("""
            background: #0B0E14;
            border: 1px solid rgba(132, 147, 150, 0.2);
            border-radius: 6px;
        """)
        step_lo = QHBoxLayout(step_box)
        step_lo.setContentsMargins(4, 2, 4, 2)
        step_lo.setSpacing(4)

        minus_btn = QPushButton("−")
        minus_btn.setFixedSize(22, 22)
        minus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        minus_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #BAC9CC; border: none; font-weight: bold; font-size: 13px; }
            QPushButton:hover { color: #FFB4AB; }
        """)
        minus_btn.clicked.connect(self._decrease)
        step_lo.addWidget(minus_btn)

        self.qty_lbl = QLabel(str(self.qty))
        self.qty_lbl.setFont(cyber_font(10, QFont.Weight.Bold, "Sora"))
        self.qty_lbl.setStyleSheet("color: #FFFFFF; border: none; background: transparent;")
        self.qty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qty_lbl.setFixedWidth(20)
        step_lo.addWidget(self.qty_lbl)

        plus_btn = QPushButton("+")
        plus_btn.setFixedSize(22, 22)
        plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        plus_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #BAC9CC; border: none; font-weight: bold; font-size: 13px; }
            QPushButton:hover { color: #00E5FF; }
        """)
        plus_btn.clicked.connect(self._increase)
        step_lo.addWidget(plus_btn)

        lo.addWidget(step_box)

    def _increase(self):
        stock = self.product.get('stock', 99)
        if self.qty < stock:
            self.qty += 1
            self.qty_lbl.setText(str(self.qty))
            self.qty_changed.emit(self.product, self.qty)

    def _decrease(self):
        self.qty -= 1
        if self.qty >= 0:
            self.qty_lbl.setText(str(self.qty))
            self.qty_changed.emit(self.product, self.qty)

    def _increase(self):
        stock = self.product.get('stock', 99)
        if self.qty < stock:
            self.qty += 1
            self.qty_lbl.setText(str(self.qty))
            self.qty_changed.emit(self.product, self.qty)

    def _decrease(self):
        self.qty -= 1
        if self.qty >= 0:
            self.qty_lbl.setText(str(self.qty))
            self.qty_changed.emit(self.product, self.qty)


class BarPage(QWidget):
    """NEXUS FUEL & SNACKS — 1:1 Cyber-Esports Bar & Shop Page."""
    _order_result = pyqtSignal(bool, dict)
    tab_switch_requested = pyqtSignal(str)

    def __init__(self, api_client, pc_name="PC-01", parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.pc_name = pc_name
        self.cart = {}  # product_id -> (product, qty)
        self.all_products = []
        self.active_category = "ALL"
        self.customer_data = {}
        self._pending_client_order_id = None

        self.setStyleSheet(f"background-color: {COLOR_BG};")
        self._order_result.connect(self._on_order_done)

        # Asosiy tashqi konteyner (20px margin bilan markaziy panel)
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(20, 16, 20, 16)
        page_layout.setSpacing(0)

        # ── 1. MODAL / GLASS ASOSIY KONTEYNERI ──
        modal_frame = QFrame()
        modal_frame.setObjectName("snackModalFrame")
        modal_frame.setStyleSheet("""
            QFrame#snackModalFrame {
                background-color: rgba(29, 32, 38, 0.96);
                border: 1px solid rgba(132, 147, 150, 0.22);
                border-radius: 16px;
            }
        """)

        # Neon Glow Effect
        modal_glow = QGraphicsDropShadowEffect(modal_frame)
        modal_glow.setBlurRadius(36)
        modal_glow.setColor(QColor(0, 218, 243, 35))
        modal_glow.setOffset(0, 0)
        modal_frame.setGraphicsEffect(modal_glow)

        modal_lo = QVBoxLayout(modal_frame)
        modal_lo.setContentsMargins(0, 0, 0, 0)
        modal_lo.setSpacing(0)

        # ── 2. HEADER ──
        header = QFrame()
        header.setFixedHeight(76)
        header.setStyleSheet("""
            background: rgba(39, 42, 49, 0.5);
            border-top-left-radius: 16px;
            border-top-right-radius: 16px;
            border-bottom: 1px solid rgba(132, 147, 150, 0.15);
        """)
        h_lo = QHBoxLayout(header)
        h_lo.setContentsMargins(24, 0, 24, 0)
        h_lo.setSpacing(16)

        # Logo / Food icon box
        icon_box = QLabel("🍽️")
        icon_box.setFixedSize(42, 42)
        icon_box.setFont(QFont("Segoe UI Emoji", 20))
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_box.setStyleSheet("""
            background: rgba(0, 229, 255, 0.15);
            border: 1px solid rgba(0, 229, 255, 0.35);
            border-radius: 10px;
        """)
        h_lo.addWidget(icon_box)

        # Title + Subtitle
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        main_title = QLabel("CLUTCH ZONE FUEL & SNACKS")
        main_title.setFont(cyber_font(18, QFont.Weight.Bold, "Sora"))
        main_title.setStyleSheet("color: #E1E2EB; letter-spacing: 0.5px; border: none; background: transparent;")
        title_box.addWidget(main_title)

        self.subtitle = QLabel(f"DELIVERED DIRECTLY TO TERMINAL {self.pc_name}")
        self.subtitle.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        self.subtitle.setStyleSheet("color: #00DAF3; letter-spacing: 2px; border: none; background: transparent; opacity: 0.85;")
        title_box.addWidget(self.subtitle)
        h_lo.addLayout(title_box)

        h_lo.addStretch(1)

        # Status notification banner (agar buyurtma berilsa)
        self.status_label = QLabel("")
        self.status_label.setFont(cyber_font(10, QFont.Weight.Bold, "Sora"))
        self.status_label.setStyleSheet("color: #52FFAC; background: transparent; border: none; padding: 4px 12px;")
        self.status_label.hide()
        h_lo.addWidget(self.status_label)

        # Close '✕' button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(34, 34)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #BAC9CC;
                border-radius: 17px;
                border: none;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                color: #00E5FF;
            }
        """)
        close_btn.clicked.connect(lambda: self.tab_switch_requested.emit("games"))
        h_lo.addWidget(close_btn)

        modal_lo.addWidget(header)

        # ── 3. BODY (Split Layout: Left Products + Right Cart) ──
        body = QWidget()
        body_lo = QHBoxLayout(body)
        body_lo.setContentsMargins(0, 0, 0, 0)
        body_lo.setSpacing(0)

        # ── 3A. CHAP TARAFI: MAHSULOTLAR VA KATEGORIYALAR ──
        left_area = QWidget()
        left_area.setStyleSheet("background: transparent; border: none;")
        left_lo = QVBoxLayout(left_area)
        left_lo.setContentsMargins(24, 16, 24, 16)
        left_lo.setSpacing(14)

        # Kategoriya filtrlari (Category Pills)
        self.cat_bar = QHBoxLayout()
        self.cat_bar.setSpacing(10)
        self.cat_buttons = {}
        left_lo.addLayout(self.cat_bar)

        # Mahsulotlar panjarasi (ScrollArea)
        self.products_scroll = QScrollArea()
        self.products_scroll.setWidgetResizable(True)
        self.products_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.products_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #10131A; width: 6px; border-radius: 3px; }
            QScrollBar:handle:vertical { background: rgba(132, 147, 150, 0.25); min-height: 25px; border-radius: 3px; }
            QScrollBar:handle:vertical:hover { background: #00DAF3; }
        """)
        self.products_scroll.viewport().setStyleSheet("background: transparent;")

        self.products_flow = FlowGrid(card_min_width=250, spacing=16, margins=(0, 0, 0, 0))
        self.products_scroll.setWidget(self.products_flow)
        left_lo.addWidget(self.products_scroll, 1)

        body_lo.addWidget(left_area, 1)

        # ── 3B. O'NG TARAFI: CURRENT ORDER (SAVAT & CHECKOUT) ──
        right_sidebar = QFrame()
        right_sidebar.setFixedWidth(340)
        right_sidebar.setStyleSheet("""
            background: rgba(25, 28, 34, 0.95);
            border-left: 1px solid rgba(132, 147, 150, 0.18);
            border-bottom-right-radius: 16px;
        """)
        right_lo = QVBoxLayout(right_sidebar)
        right_lo.setContentsMargins(20, 18, 20, 20)
        right_lo.setSpacing(14)

        # Current Order Title
        cart_title = QLabel("🛒  CURRENT ORDER")
        cart_title.setFont(cyber_font(10, QFont.Weight.Bold, "Mono"))
        cart_title.setStyleSheet("color: #BAC9CC; letter-spacing: 2px; border: none; background: transparent;")
        right_lo.addWidget(cart_title)

        # Cart Items ScrollArea
        self.cart_scroll = QScrollArea()
        self.cart_scroll.setWidgetResizable(True)
        self.cart_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cart_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #10131A; width: 5px; border-radius: 2px; }
            QScrollBar:handle:vertical { background: rgba(132, 147, 150, 0.25); border-radius: 2px; }
            QScrollBar:handle:vertical:hover { background: #00DAF3; }
        """)
        self.cart_scroll.viewport().setStyleSheet("background: transparent;")

        self.cart_container = QWidget()
        self.cart_container.setStyleSheet("background: transparent;")
        self.cart_layout = QVBoxLayout(self.cart_container)
        self.cart_layout.setContentsMargins(0, 0, 0, 0)
        self.cart_layout.setSpacing(8)
        self.cart_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.cart_scroll.setWidget(self.cart_container)
        right_lo.addWidget(self.cart_scroll, 1)

        # Empty Cart Label
        self.empty_cart_lbl = QLabel("Savat bo'sh\nMahsulot tanlang")
        self.empty_cart_lbl.setFont(cyber_font(10, family="Hanken"))
        self.empty_cart_lbl.setStyleSheet("color: #849396; border: none; background: transparent;")
        self.empty_cart_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cart_layout.addWidget(self.empty_cart_lbl)

        # ── 4. CHECKOUT FOOTER PANEL ──
        checkout_box = QFrame()
        checkout_box.setStyleSheet("""
            background: rgba(16, 19, 26, 0.7);
            border: 1px solid rgba(132, 147, 150, 0.15);
            border-radius: 12px;
            padding: 12px;
        """)
        chk_lo = QVBoxLayout(checkout_box)
        chk_lo.setContentsMargins(12, 12, 12, 12)
        chk_lo.setSpacing(8)

        # Subtotal row
        sub_row = QHBoxLayout()
        sub_title = QLabel("Subtotal")
        sub_title.setFont(cyber_font(10, family="Hanken"))
        sub_title.setStyleSheet("color: #BAC9CC; border: none; background: transparent;")
        sub_row.addWidget(sub_title)
        self.subtotal_val = QLabel("0 CP")
        self.subtotal_val.setFont(cyber_font(11, QFont.Weight.Bold, "Sora"))
        self.subtotal_val.setStyleSheet("color: #E1E2EB; border: none; background: transparent;")
        sub_row.addWidget(self.subtotal_val, 0, Qt.AlignmentFlag.AlignRight)
        chk_lo.addLayout(sub_row)

        # Terminal delivery row
        deliv_row = QHBoxLayout()
        deliv_title = QLabel("Terminal Delivery")
        deliv_title.setFont(cyber_font(10, family="Hanken"))
        deliv_title.setStyleSheet("color: #BAC9CC; border: none; background: transparent;")
        deliv_row.addWidget(deliv_title)
        deliv_val = QLabel("FREE")
        deliv_val.setFont(cyber_font(10, QFont.Weight.Bold, "Mono"))
        deliv_val.setStyleSheet("color: #52FFAC; border: none; background: transparent;")
        deliv_row.addWidget(deliv_val, 0, Qt.AlignmentFlag.AlignRight)
        chk_lo.addLayout(deliv_row)

        # Divider line
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background: rgba(132, 147, 150, 0.2); border: none;")
        chk_lo.addWidget(div)

        # Total row
        tot_row = QHBoxLayout()
        tot_title = QLabel("TOTAL")
        tot_title.setFont(cyber_font(11, QFont.Weight.Bold, "Mono"))
        tot_title.setStyleSheet("color: #E1E2EB; letter-spacing: 1.5px; border: none; background: transparent;")
        tot_row.addWidget(tot_title)
        self.total_val = QLabel("0 CP")
        self.total_val.setFont(cyber_font(20, QFont.Weight.Bold, "Sora"))
        self.total_val.setStyleSheet("color: #00DAF3; border: none; background: transparent;")
        tot_row.addWidget(self.total_val, 0, Qt.AlignmentFlag.AlignRight)
        chk_lo.addLayout(tot_row)

        # Balance Box (Available balance + sufficient status)
        bal_box = QFrame()
        bal_box.setStyleSheet("""
            background: rgba(11, 14, 20, 0.6);
            border: 1px solid rgba(132, 147, 150, 0.15);
            border-radius: 8px;
        """)
        b_lo = QHBoxLayout(bal_box)
        b_lo.setContentsMargins(10, 6, 10, 6)
        b_lo.setSpacing(6)

        w_icon = QLabel("💳")
        w_icon.setFont(QFont("Segoe UI Emoji", 11))
        w_icon.setStyleSheet("border: none; background: transparent;")
        b_lo.addWidget(w_icon)

        bal_info = QVBoxLayout()
        bal_info.setSpacing(1)
        bal_tag = QLabel("AVAILABLE BALANCE")
        bal_tag.setFont(cyber_font(7, QFont.Weight.Bold, "Mono"))
        bal_tag.setStyleSheet("color: #849396; border: none; background: transparent; letter-spacing: 0.5px;")
        bal_info.addWidget(bal_tag)
        self.avail_bal_lbl = QLabel("12,450 CP")
        self.avail_bal_lbl.setFont(cyber_font(9, QFont.Weight.Bold, "Sora"))
        self.avail_bal_lbl.setStyleSheet("color: #E1E2EB; border: none; background: transparent;")
        bal_info.addWidget(self.avail_bal_lbl)
        b_lo.addLayout(bal_info, 1)

        self.suff_badge = QLabel("SUFFICIENT")
        self.suff_badge.setFont(cyber_font(7, QFont.Weight.Bold, "Mono"))
        self.suff_badge.setStyleSheet("""
            color: #52FFAC;
            background: rgba(82, 255, 172, 0.12);
            border-radius: 4px;
            padding: 2px 5px;
            border: none;
            letter-spacing: 0.5px;
        """)
        b_lo.addWidget(self.suff_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        chk_lo.addWidget(bal_box)

        # Authorize Purchase Button
        self.order_btn = QPushButton("AUTHORIZE PURCHASE  ⚡")
        self.order_btn.setFont(cyber_font(11, QFont.Weight.Bold, "Sora"))
        self.order_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.order_btn.setFixedHeight(44)
        self.order_btn.setStyleSheet("""
            QPushButton {
                background: #00E5FF;
                color: #001F24;
                border: none;
                border-radius: 10px;
                letter-spacing: 1px;
                font-weight: 800;
            }
            QPushButton:hover {
                background: #52FFAC;
                color: #002111;
            }
            QPushButton:disabled {
                background: rgba(0, 229, 255, 0.15);
                color: #4F5560;
            }
        """)
        self.order_btn.clicked.connect(self._place_order)
        self.order_btn.setEnabled(False)
        chk_lo.addWidget(self.order_btn)

        # Subtext hint
        subtext = QLabel("FUNDS WILL BE DEDUCTED FROM ACCOUNT")
        subtext.setFont(cyber_font(8, family="Mono"))
        subtext.setStyleSheet("color: #849396; border: none; background: transparent;")
        subtext.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chk_lo.addWidget(subtext)

        right_lo.addWidget(checkout_box)
        body_lo.addWidget(right_sidebar)

        modal_lo.addWidget(body, 1)
        page_layout.addWidget(modal_frame, 1)

        # Standart mahsulotlarni yuklash
        self.set_products([])

    def set_customer_data(self, data):
        self.customer_data = data or {}
        if self.customer_data:
            try:
                bal = float(self.customer_data.get('balance', 0))
            except (TypeError, ValueError):
                bal = 0.0
            self.avail_bal_lbl.setText(f"{bal:,.0f} UZS".replace(',', ' '))
        else:
            self.avail_bal_lbl.setText("12,450 CP")
        self._update_total()

    def set_products(self, products):
        self.all_products = products if products else list(FALLBACK_SNACK_PRODUCTS)
        self._build_category_tabs()
        self._render_products()

    def _build_category_tabs(self):
        # Eski tugmalarni tozalash
        while self.cat_bar.count():
            item = self.cat_bar.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)

        cats = ["ALL"]
        for p in self.all_products:
            c = (p.get('category_name') or 'SNACKS').upper()
            if c not in cats:
                cats.append(c)

        self.cat_buttons = {}
        for c in cats:
            icon = _snack_category_icon(c) if c != "ALL" else "🌐"
            label = f"{icon}  {c}"
            btn = QPushButton(label)
            btn.setFont(cyber_font(9, QFont.Weight.Bold, "Sora"))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(34)
            btn.clicked.connect(lambda _, cat=c: self._select_category(cat))
            self.cat_buttons[c] = btn
            self.cat_bar.addWidget(btn)

        self.cat_bar.addStretch(1)
        self._update_tab_styles()

    def _select_category(self, cat):
        self.active_category = cat
        self._update_tab_styles()
        self._render_products()

    def _update_tab_styles(self):
        for cat, btn in self.cat_buttons.items():
            if cat == self.active_category:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #00E5FF;
                        color: #001F24;
                        border: none;
                        border-radius: 17px;
                        padding: 0 16px;
                        font-weight: 800;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #272A31;
                        color: #BAC9CC;
                        border: 1px solid rgba(255, 255, 255, 0.06);
                        border-radius: 17px;
                        padding: 0 16px;
                    }
                    QPushButton:hover {
                        background: #32353C;
                        color: #FFFFFF;
                    }
                """)

    def _render_products(self):
        filtered = []
        for p in self.all_products:
            c = (p.get('category_name') or 'SNACKS').upper()
            if self.active_category == "ALL" or c == self.active_category:
                filtered.append(p)

        cards = []
        for p in filtered:
            card = SnackProductCard(p)
            card.add_to_cart_clicked.connect(self._add_to_cart)
            cards.append(card)

        self.products_flow.set_items(cards)

    def _add_to_cart(self, product):
        pid = product.get('id')
        if pid in self.cart:
            p, qty = self.cart[pid]
            stock = product.get('stock', 99)
            if qty < stock:
                self.cart[pid] = (p, qty + 1)
        else:
            self.cart[pid] = (product, 1)

        self._pending_client_order_id = None
        self._rebuild_cart_view()
        self._update_total()

    def _on_cart_qty_changed(self, product, qty):
        pid = product.get('id')
        if qty <= 0:
            self.cart.pop(pid, None)
        else:
            self.cart[pid] = (product, qty)
        self._pending_client_order_id = None
        self._rebuild_cart_view()
        self._update_total()

    def _rebuild_cart_view(self):
        while self.cart_layout.count():
            item = self.cart_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)

        if not self.cart:
            self.empty_cart_lbl = QLabel("Savat bo'sh\nMahsulot tanlang")
            self.empty_cart_lbl.setFont(cyber_font(10, family="Hanken"))
            self.empty_cart_lbl.setStyleSheet("color: #849396; border: none; background: transparent; padding-top: 30px;")
            self.empty_cart_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cart_layout.addWidget(self.empty_cart_lbl)
        else:
            for pid, (product, qty) in self.cart.items():
                item_widget = CartItemWidget(product, qty)
                item_widget.qty_changed.connect(self._on_cart_qty_changed)
                self.cart_layout.addWidget(item_widget)

    def _update_total(self):
        total = 0.0
        unit = "CP"
        for product, qty in self.cart.values():
            try:
                total += float(product.get('price', 0)) * qty
            except (TypeError, ValueError):
                pass
            unit = product.get('price_unit', unit)

        formatted = f"{total:,.0f} {unit}".replace(',', ' ')
        self.subtotal_val.setText(formatted)
        self.total_val.setText(formatted)

        has_items = len(self.cart) > 0
        self.order_btn.setEnabled(has_items)

        # Balance sufficiency check
        if self.customer_data:
            try:
                bal = float(self.customer_data.get('balance', 0))
            except (TypeError, ValueError):
                bal = 0.0
            if total > bal and total > 0:
                self.suff_badge.setText("INSUFFICIENT")
                self.suff_badge.setStyleSheet("""
                    color: #FFB4AB;
                    background: rgba(147, 0, 10, 0.35);
                    border-radius: 4px;
                    padding: 2px 5px;
                    letter-spacing: 0.5px;
                """)
            else:
                self.suff_badge.setText("SUFFICIENT")
                self.suff_badge.setStyleSheet("""
                    color: #52FFAC;
                    background: rgba(82, 255, 172, 0.12);
                    border-radius: 4px;
                    padding: 2px 5px;
                    letter-spacing: 0.5px;
                """)

    def _place_order(self):
        items = [{"product_id": pid, "quantity": qty} for pid, (_, qty) in self.cart.items()]
        if not items:
            return

        if not self._pending_client_order_id:
            self._pending_client_order_id = str(uuid.uuid4())

        self.order_btn.setEnabled(False)
        self.order_btn.setText("PROCESSING...")
        self.api_client.create_order_async(
            self.pc_name, items, client_order_id=self._pending_client_order_id,
            on_done=lambda ok, data: self._order_result.emit(ok, data)
        )

    def _on_order_done(self, ok, data):
        self.order_btn.setText("AUTHORIZE PURCHASE  ⚡")
        self.status_label.show()
        if ok:
            self.status_label.setStyleSheet("color: #52FFAC; background: rgba(82, 255, 172, 0.12); border-radius: 6px; padding: 4px 12px;")
            self.status_label.setText("✅ ORDER DISPATCHED — DELIVERING TO TERMINAL")
            self.cart = {}
            self._pending_client_order_id = None
            self._rebuild_cart_view()
            self._update_total()
        else:
            self.status_label.setStyleSheet("color: #FFB4AB; background: rgba(147, 0, 10, 0.3); border-radius: 6px; padding: 4px 12px;")
            server_error = data.get('error') if isinstance(data, dict) else None
            self.status_label.setText(f"❌ {server_error}" if server_error else "❌ Order failed, try again.")
            self.order_btn.setEnabled(len(self.cart) > 0)
        QTimer.singleShot(6000, self.status_label.hide)


# ──────────────────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
#  11. TOURNAMENTS & BONUSES PAGE
# ──────────────────────────────────────────────────────────────────────────────
class TournamentsBonusesPage(QWidget):
    """Klub turnirlari va faol bonus aksiyalari vitrinasi - zamonaviy borderlarsiz dizayn."""
    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {COLOR_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(16)

        # Sahifa sarlavhasi
        header_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("🏆  TOURNAMENTS & BONUSES")
        title.setFont(cyber_font(18, QFont.Weight.Bold, "Sora"))
        title.setStyleSheet(f"color: {COLOR_PRIMARY}; letter-spacing: 1px; border: none; background: transparent;")
        title_box.addWidget(title)

        subtitle = QLabel("Klub chempionatlari, ro'yxatdan o'tish va maxsus bonus aksiyalari")
        subtitle.setFont(cyber_font(10, family="Hanken"))
        subtitle.setStyleSheet("color: #7E8B9B; border: none; background: transparent;")
        title_box.addWidget(subtitle)
        header_row.addLayout(title_box)
        header_row.addStretch(1)

        back_btn = QPushButton("←  ORQAGA")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setFixedHeight(34)
        back_btn.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        back_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #BAC9CC;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
            }
            QPushButton:hover {
                background: rgba(0, 229, 255, 0.15);
                color: #00E5FF;
            }
        """)
        back_btn.clicked.connect(self.back_requested.emit)
        header_row.addWidget(back_btn)
        root.addLayout(header_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: #10131a; width: 6px; border-radius: 3px; }
            QScrollBar::handle:vertical { background: #272a31; min-height: 20px; border-radius: 3px; }
            QScrollBar::handle:vertical:hover { background: #00daf3; }
        """)
        scroll.viewport().setStyleSheet("background: transparent;")

        container = QWidget()
        container.setStyleSheet("background: transparent; border: none;")
        c_lo = QVBoxLayout(container)
        c_lo.setContentsMargins(0, 4, 8, 12)
        c_lo.setSpacing(22)

        # ── HERO SPOTLIGHT: FEATURED TOURNAMENT (BORDERLESS) ──
        hero_card = QFrame()
        hero_card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1a233a, stop:0.6 #131722, stop:1 #0d1017);
                border: none;
                border-radius: 16px;
            }
        """)
        hero_lo = QHBoxLayout(hero_card)
        hero_lo.setContentsMargins(24, 20, 24, 20)
        hero_lo.setSpacing(20)

        # Hero Left Info
        h_info = QVBoxLayout()
        h_info.setSpacing(6)

        h_tag_row = QHBoxLayout()
        h_tag = QLabel("🔥  ASOSIY CHEMPIONAT")
        h_tag.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        h_tag.setStyleSheet("""
            background: rgba(255, 82, 82, 0.18);
            color: #FF5252;
            border: none;
            border-radius: 6px;
            padding: 3px 8px;
        """)
        h_tag_row.addWidget(h_tag)

        h_game = QLabel("COUNTER-STRIKE 2 • 5v5 LAN")
        h_game.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        h_game.setStyleSheet("color: #00E5FF; border: none; background: transparent;")
        h_tag_row.addWidget(h_game)
        h_tag_row.addStretch(1)
        h_info.addLayout(h_tag_row)

        h_title = QLabel("CLUTCH ZONE MAJOR CHAMPIONSHIP 2026")
        h_title.setFont(cyber_font(15, QFont.Weight.Bold, "Sora"))
        h_title.setStyleSheet("color: #FFFFFF; border: none; background: transparent;")
        h_info.addWidget(h_title)

        h_desc = QLabel("Klubimizning eng yirik 5v5 CS2 turniri. Barcha jamoalar uchun ochiq saralash va final jonli efirda.")
        h_desc.setFont(cyber_font(10, family="Hanken"))
        h_desc.setStyleSheet("color: #8C9BAE; border: none; background: transparent;")
        h_desc.setWordWrap(True)
        h_info.addWidget(h_desc)

        h_meta_row = QHBoxLayout()
        h_meta_row.setSpacing(14)
        m1 = QLabel("📅 Boshlanishi: 28-Avgust, 14:00")
        m1.setFont(cyber_font(9, family="Mono"))
        m1.setStyleSheet("color: #BAC9CC; border: none; background: transparent;")
        m2 = QLabel("👥 Jamoalar: 12 / 16 Qabul qilindi")
        m2.setFont(cyber_font(9, family="Mono"))
        m2.setStyleSheet("color: #BAC9CC; border: none; background: transparent;")
        h_meta_row.addWidget(m1)
        h_meta_row.addWidget(m2)
        h_meta_row.addStretch(1)
        h_info.addLayout(h_meta_row)

        hero_lo.addLayout(h_info, 3)

        # Hero Right Prize & Action
        h_action = QVBoxLayout()
        h_action.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_action.setSpacing(8)

        p_label = QLabel("YUTUQ JAMG'ARMASI")
        p_label.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        p_label.setStyleSheet("color: #8C9BAE; border: none; background: transparent;")
        p_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_action.addWidget(p_label)

        p_val = QLabel("5 000 000 UZS")
        p_val.setFont(cyber_font(18, QFont.Weight.Bold, "Sora"))
        p_val.setStyleSheet("color: #00E5FF; border: none; background: transparent; letter-spacing: 0.5px;")
        p_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_action.addWidget(p_val)

        reg_btn = QPushButton("🟢  RO'YXATDAN O'TISH")
        reg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reg_btn.setFixedHeight(36)
        reg_btn.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        reg_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00C9A7, stop:1 #00E5FF);
                color: #05101A;
                border: none;
                border-radius: 8px;
                padding: 0 18px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00E5FF, stop:1 #52FFAC);
            }
        """)
        # Turnir ma'lumotlari (yuqoridagi sarlavha, mukofot, sana) hozircha
        # namoyish uchun qattiq yozilgan — buning ortida haqiqiy turnir
        # tizimi (backend) yo'q, shuning uchun ro'yxatdan o'tish ham
        # hozircha faqat "tez orada" xabarini ko'rsatadi.
        reg_btn.clicked.connect(lambda: QMessageBox.information(
            self, "Tez orada", "Turnirlarga ro'yxatdan o'tish funksiyasi hali ishlab chiqilmoqda."
        ))
        h_action.addWidget(reg_btn)

        hero_lo.addLayout(h_action, 1)
        c_lo.addWidget(hero_card)

        # ── 1. UPCOMING TOURNAMENTS (BORDERLESS GRID) ──
        t_sec_lbl = QLabel("BOSHQA TURNIRLAR VA CHEMPIONATLAR")
        t_sec_lbl.setFont(cyber_font(10, QFont.Weight.Bold, "Mono"))
        t_sec_lbl.setStyleSheet(f"color: {COLOR_PRIMARY_CONTAINER}; letter-spacing: 1px; border: none; background: transparent;")
        c_lo.addWidget(t_sec_lbl)

        t_grid = QHBoxLayout()
        t_grid.setSpacing(14)

        tournaments_data = [
            ("DOTA 2", "1v1 MID CUP TOURNAMENT", "2 000 000 UZS", "Har Yakshanba, 18:00", "⏳ TEZ KUNDA", "#C084FC", "rgba(192, 132, 252, 0.12)"),
            ("VALORANT", "5v5 WEEKLY COMMUNITY CUP", "1 500 000 UZS", "Har Juma, 20:00", "🟢 RO'YXAT OCHIQ", "#34D399", "rgba(52, 211, 153, 0.12)"),
            ("EA FC 24", "1v1 PS5 CHAMPIONS LEAGUE", "1 000 000 UZS", "Har Shanba, 16:00", "🟢 RO'YXAT OCHIQ", "#38BDF8", "rgba(56, 189, 248, 0.12)"),
        ]

        for game_name, cup_title, prize, time_str, status, accent, accent_bg in tournaments_data:
            t_card = QFrame()
            t_card.setFixedHeight(175)
            t_card.setStyleSheet("""
                QFrame {
                    background: #141722;
                    border: none;
                    border-radius: 14px;
                }
                QFrame:hover {
                    background: #1a1e2d;
                }
            """)
            card_lo = QVBoxLayout(t_card)
            card_lo.setContentsMargins(18, 16, 18, 16)
            card_lo.setSpacing(6)

            tag_row = QHBoxLayout()
            g_lbl = QLabel(game_name)
            g_lbl.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
            g_lbl.setStyleSheet(f"""
                background: {accent_bg};
                color: {accent};
                border: none;
                border-radius: 5px;
                padding: 2px 7px;
            """)
            tag_row.addWidget(g_lbl)
            tag_row.addStretch(1)

            st_lbl = QLabel(status)
            st_lbl.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
            st_lbl.setStyleSheet(f"color: {accent}; border: none; background: transparent;")
            tag_row.addWidget(st_lbl)
            card_lo.addLayout(tag_row)

            c_lbl = QLabel(cup_title)
            c_lbl.setFont(cyber_font(12, QFont.Weight.Bold, "Sora"))
            c_lbl.setStyleSheet("color: #FFFFFF; border: none; background: transparent;")
            card_lo.addWidget(c_lbl)

            tm_lbl = QLabel(f"⏱ {time_str}")
            tm_lbl.setFont(cyber_font(9, family="Mono"))
            tm_lbl.setStyleSheet("color: #7E8B9B; border: none; background: transparent;")
            card_lo.addWidget(tm_lbl)

            card_lo.addStretch(1)

            prz_box = QHBoxLayout()
            prz_tag = QLabel("Sovrin:")
            prz_tag.setFont(cyber_font(9, family="Mono"))
            prz_tag.setStyleSheet("color: #8C9BAE; border: none; background: transparent;")
            prz_box.addWidget(prz_tag)

            p_lbl = QLabel(prize)
            p_lbl.setFont(cyber_font(12, QFont.Weight.Bold, "Sora"))
            p_lbl.setStyleSheet("color: #FFFFFF; border: none; background: transparent;")
            prz_box.addWidget(p_lbl)
            prz_box.addStretch(1)

            card_lo.addLayout(prz_box)
            t_grid.addWidget(t_card, 1)

        c_lo.addLayout(t_grid)

        # ── 2. CLUB BONUSES & SPECIAL OFFERS (BORDERLESS CARDS) ──
        b_sec_lbl = QLabel("MAXSUS AKSIYALAR VA BONUS DASTURLARI")
        b_sec_lbl.setFont(cyber_font(10, QFont.Weight.Bold, "Mono"))
        b_sec_lbl.setStyleSheet(f"color: {COLOR_PRIMARY_CONTAINER}; letter-spacing: 1px; border: none; background: transparent;")
        c_lo.addWidget(b_sec_lbl)

        b_grid = QHBoxLayout()
        b_grid.setSpacing(14)

        bonuses_data = [
            ("🌙", "NIGHT OWL (23:00 - 08:00)", "Tungi paketlarda barcha zonalarga 25% chegirma va cheksiz tezlik.", "#C084FC", "rgba(192, 132, 252, 0.1)"),
            ("🎯", "3+ SOAT MARAFON", "Har 3 soatlik uzluksiz o'yin uchun hisobingizga +500 Bonus Ball qo'shiladi.", "#34D399", "rgba(52, 211, 153, 0.1)"),
            ("👑", "VIP CASHBACK", "Platinum va Diamond foydalanuvchilarga haftalik 5% sarf cashback qaytadi.", "#38BDF8", "rgba(56, 189, 248, 0.1)"),
            ("👥", "DO'STINGNI KELTIR", "Do'stingiz birinchi to'lovida har ikkingizga 15 000 UZS balans beriladi.", "#F472B6", "rgba(244, 114, 182, 0.1)"),
        ]

        for icon_s, b_name, b_desc, b_color, b_bg in bonuses_data:
            b_card = QFrame()
            b_card.setFixedHeight(150)
            b_card.setStyleSheet("""
                QFrame {
                    background: #141722;
                    border: none;
                    border-radius: 14px;
                }
                QFrame:hover {
                    background: #191e2b;
                }
            """)
            b_lo = QVBoxLayout(b_card)
            b_lo.setContentsMargins(18, 16, 18, 16)
            b_lo.setSpacing(8)

            head_r = QHBoxLayout()
            ic_lbl = QLabel(icon_s)
            ic_lbl.setFont(cyber_font(13))
            ic_lbl.setStyleSheet("border: none; background: transparent;")
            head_r.addWidget(ic_lbl)

            bn_lbl = QLabel(b_name)
            bn_lbl.setFont(cyber_font(11, QFont.Weight.Bold, "Sora"))
            bn_lbl.setStyleSheet(f"color: {b_color}; border: none; background: transparent;")
            head_r.addWidget(bn_lbl)
            head_r.addStretch(1)
            b_lo.addLayout(head_r)

            bd_lbl = QLabel(b_desc)
            bd_lbl.setFont(cyber_font(9, family="Hanken"))
            bd_lbl.setStyleSheet("color: #8C9BAE; line-height: 140%; border: none; background: transparent;")
            bd_lbl.setWordWrap(True)
            b_lo.addWidget(bd_lbl)

            b_lo.addStretch(1)
            b_grid.addWidget(b_card, 1)

        c_lo.addLayout(b_grid)

        # ── Info Note ──
        note_strip = QFrame()
        note_strip.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.03);
                border: none;
                border-radius: 10px;
            }
        """)
        note_lo = QHBoxLayout(note_strip)
        note_lo.setContentsMargins(16, 10, 16, 10)
        note_txt = QLabel("ℹ️  Turnirlarga yozilish yoki bonuslarni faollashtirish uchun administratorga murojaat qiling.")
        note_txt.setFont(cyber_font(9, family="Hanken"))
        note_txt.setStyleSheet("color: #6C7A8C; border: none; background: transparent;")
        note_lo.addWidget(note_txt)
        note_lo.addStretch(1)
        c_lo.addWidget(note_strip)

        c_lo.addStretch(1)
        scroll.setWidget(container)
        root.addWidget(scroll, 1)


# ──────────────────────────────────────────────────────────────────────────────
#  11b. RUNNING APPS BAR
# ──────────────────────────────────────────────────────────────────────────────
class RunningAppsBar(QFrame):
    """Hozir ochiq turgan barcha dasturlarni ko'rsatuvchi ixcham panel."""
    app_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setStyleSheet(f"""
            QFrame#runningAppsBar {{
                background-color: rgba(11, 14, 20, 0.9);
                border-top: 1px solid rgba(255, 255, 255, 0.05);
            }}
        """)
        self.setObjectName("runningAppsBar")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(28, 4, 28, 4)
        self._layout.setSpacing(10)
        self._apps = {}
        self.hide()

    def set_apps(self, apps):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._apps = {a['exe']: a for a in apps}

        if not apps:
            self.hide()
            return

        tag = QLabel("ACTIVE APPS:")
        tag.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        tag.setStyleSheet(f"color: {COLOR_PRIMARY_CONTAINER}; letter-spacing: 1px;")
        self._layout.addWidget(tag)

        for a in apps:
            icon_pixmap = a.get('icon')
            btn = QPushButton()
            btn.setFont(cyber_font(9, QFont.Weight.Bold, "Sora"))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if icon_pixmap:
                btn.setIcon(QIcon(icon_pixmap))
                btn.setIconSize(icon_pixmap.rect().size())
                btn.setText(f"  {a['label']}")
            else:
                btn.setText(f"🎮  {a['label']}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    color: #e2e8f0;
                    background: rgba(0, 229, 255, 0.12);
                    border: 1px solid rgba(0, 229, 255, 0.35);
                    border-radius: 6px;
                    padding: 4px 12px;
                }}
                QPushButton:hover {{ background: rgba(0, 229, 255, 0.25); }}
            """)
            exe_key = a['exe']
            btn.clicked.connect(lambda _, e=exe_key: self.app_clicked.emit(e))
            self._layout.addWidget(btn)

        self._layout.addStretch(1)
        self.show()


# ──────────────────────────────────────────────────────────────────────────────
#  11c. FOOTER BAR (MOUSE SETTINGS, RECENT ACTIVITY, RETURN TO GAME)
# ──────────────────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
#  11c. FOOTER BAR (MOUSE SETTINGS, NVIDIA APP, RECENT ACTIVITY, RETURN TO GAME)
# ──────────────────────────────────────────────────────────────────────────────
class NexusFooterBar(QFrame):
    """Nexus / Cyber-Esports pastki footer paneli (Mouse Settings + NVIDIA App + So'nggi ochilgan applar)."""
    mouse_settings_requested = pyqtSignal()
    nvidia_app_requested = pyqtSignal()
    app_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(11, 14, 20, 0.98);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
            }}
            QLabel {{ border: none; background: transparent; }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 0, 28, 0)
        layout.setSpacing(14)

        # Chap: MOUSE SETTINGS tugmasi
        mouse_btn = QPushButton("🖱  MOUSE SETTINGS")
        mouse_btn.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        mouse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        mouse_btn.setFixedHeight(36)
        mouse_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(39, 42, 49, 0.5);
                color: {COLOR_PRIMARY_CONTAINER};
                border: 1px solid rgba(0, 229, 255, 0.35);
                border-radius: 8px;
                padding: 0 14px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: rgba(0, 229, 255, 0.12);
                border-color: {COLOR_PRIMARY_CONTAINER};
            }}
        """)
        mouse_btn.clicked.connect(self.mouse_settings_requested.emit)
        layout.addWidget(mouse_btn)

        # NVIDIA APP tugmasi
        nvidia_btn = QPushButton("🎮  NVIDIA APP")
        nvidia_btn.setFont(cyber_font(9, QFont.Weight.Bold, "Mono"))
        nvidia_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        nvidia_btn.setFixedHeight(36)
        nvidia_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(39, 42, 49, 0.5);
                color: {COLOR_PRIMARY_CONTAINER};
                border: 1px solid rgba(0, 229, 255, 0.35);
                border-radius: 8px;
                padding: 0 14px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: rgba(0, 229, 255, 0.12);
                border-color: {COLOR_PRIMARY_CONTAINER};
            }}
        """)
        nvidia_btn.clicked.connect(self.nvidia_app_requested.emit)
        layout.addWidget(nvidia_btn)

        layout.addStretch(1)

        # O'ng: SO'NGGI OCHILGAN APPLAR RASMLARI VA IKONKALARI
        self.apps_container = QWidget()
        self.apps_layout = QHBoxLayout(self.apps_container)
        self.apps_layout.setContentsMargins(0, 0, 0, 0)
        self.apps_layout.setSpacing(8)
        layout.addWidget(self.apps_container)

    def set_apps(self, apps):
        while self.apps_layout.count():
            item = self.apps_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Hech qanday o'yin/dastur haqiqatda ochiq bo'lmasa — bo'sh
        # qoldiriladi. Avval bu yerda har doim CS2/DOTA2/VALORANT/STEAM/
        # DISCORD kabi QATTIQ YOZILGAN (soxta) tugmalar ko'rsatilar edi —
        # ular haqiqiy ochiq dasturlarga bog'liq emas edi, bosilganda
        # "o'yinga qaytish" ishlamas edi.
        if not apps:
            return

        tag_lbl = QLabel("SO'NGGI APPLAR:")
        tag_lbl.setFont(cyber_font(8, QFont.Weight.Bold, "Mono"))
        tag_lbl.setStyleSheet("color: #849396; letter-spacing: 1px; margin-right: 4px;")
        self.apps_layout.addWidget(tag_lbl)

        for a in apps:
            btn = QPushButton()
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(36)
            btn.setToolTip(f"O'tish / Ochish: {a.get('label', 'App')}")

            icon_pixmap = a.get('icon_pixmap') or a.get('icon')
            if isinstance(icon_pixmap, QPixmap) and not icon_pixmap.isNull():
                btn.setIcon(QIcon(icon_pixmap))
                btn.setIconSize(QSize(20, 20))
                btn.setText(f" {a.get('label', '')}")
            else:
                emoji = a.get('icon', '🎮') if isinstance(a.get('icon'), str) else '🎮'
                btn.setText(f"{emoji}  {a.get('label', '')}")

            btn.setFont(cyber_font(8, QFont.Weight.Bold, "Sora"))
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(30, 34, 45, 0.85);
                    color: #E1E2EB;
                    border: 1px solid rgba(132, 147, 150, 0.22);
                    border-radius: 8px;
                    padding: 0 12px;
                }
                QPushButton:hover {
                    background: rgba(0, 218, 243, 0.15);
                    border: 1px solid #00DAF3;
                    color: #00DAF3;
                }
            """)
            exe_key = a.get('exe', '')
            btn.clicked.connect(lambda _, e=exe_key: self._on_app_clicked(e))
            self.apps_layout.addWidget(btn)

    def _on_app_clicked(self, exe):
        if exe:
            self.app_clicked.emit(exe)
        else:
            top = self.window()
            if hasattr(top, "yield_to_app"):
                top.yield_to_app()


# ──────────────────────────────────────────────────────────────────────────────
#  12. LAUNCHER PAGE (NEXUS SIDEBAR + TOPBAR + CONTENT + FOOTER)
# ──────────────────────────────────────────────────────────────────────────────
class LauncherPage(QWidget):
    game_launch_requested = pyqtSignal(dict)
    app_switch_requested = pyqtSignal(str)
    cabinet_stop_requested = pyqtSignal(str)
    _games_loaded = pyqtSignal(list)
    _products_loaded = pyqtSignal(list)

    def __init__(self, pc_name, server_url, api_client, fallback_games=None, parent=None):
        super().__init__(parent)
        self.pc_name = pc_name
        self.api_client = api_client
        self.fallback_games = fallback_games or []
        self.logged_in_customer = None
        self.setStyleSheet(f"background-color: {COLOR_BG};")

        # Asosiy gorizontal struktura (Chapda Sidebar, O'ngda Asosiy qism)
        main_hlayout = QHBoxLayout(self)
        main_hlayout.setContentsMargins(0, 0, 0, 0)
        main_hlayout.setSpacing(0)

        # ── 1. CHAP SIDEBAR ──
        self.sidebar = NexusSidebar()
        self.sidebar.tab_changed.connect(self._on_sidebar_tab_changed)
        self.sidebar.stop_session_clicked.connect(self._on_stop_session_clicked)
        main_hlayout.addWidget(self.sidebar)

        # ── 2. O'NG ASOSIY USTUN (TopBar + InnerStack + Footer) ──
        right_column = QWidget()
        right_vlayout = QVBoxLayout(right_column)
        right_vlayout.setContentsMargins(0, 0, 0, 0)
        right_vlayout.setSpacing(0)

        # Yuqori Qidiruv & Profil TopBar
        self.top_bar = TopBar(pc_name=pc_name)
        self.top_bar.search_changed.connect(self._on_search_changed)
        self.top_bar.cabinet_requested.connect(self._open_cabinet)
        self.top_bar.mouse_settings_requested.connect(self._open_mouse_settings)
        right_vlayout.addWidget(self.top_bar)

        # Sahifalar Stack'i
        self.inner_stack = QStackedWidget()
        self.games_page = GamesPage(pc_name=pc_name)
        self.games_page.game_launch_requested.connect(self.game_launch_requested.emit)
        self.games_page.tab_switch_requested.connect(self._switch_tab)

        self.bar_page = BarPage(api_client=api_client, pc_name=pc_name)
        self.bar_page.tab_switch_requested.connect(self._switch_tab)

        self.tournaments_page = TournamentsBonusesPage()
        self.tournaments_page.back_requested.connect(lambda: self._switch_tab("games"))

        self.cabinet_page = CustomerCabinetPage(api_client=api_client)
        self.cabinet_page.stop_session_requested.connect(self.cabinet_stop_requested.emit)
        self.cabinet_page.back_requested.connect(self._close_cabinet)

        self.inner_stack.addWidget(self.games_page)          # 0: HOME
        self.inner_stack.addWidget(self.tournaments_page)    # 1: TOURNAMENTS & BONUSES
        self.inner_stack.addWidget(self.bar_page)             # 2: SHOP / BAR
        self.inner_stack.addWidget(self.cabinet_page)         # 3: CABINET
        right_vlayout.addWidget(self.inner_stack, 1)

        self._pre_cabinet_index = 0

        self._games_loaded.connect(self.games_page.set_games)
        self._products_loaded.connect(self.bar_page.set_products)

        # Ishlab turgan dasturlar paneli (agar dastur ochilgan bo'lsa)
        self.apps_bar = RunningAppsBar()
        self.apps_bar.app_clicked.connect(self.app_switch_requested.emit)
        right_vlayout.addWidget(self.apps_bar)

        # Pastki Footer Bar
        self.footer_bar = NexusFooterBar()
        self.footer_bar.mouse_settings_requested.connect(self._open_mouse_settings)
        self.footer_bar.nvidia_app_requested.connect(self._open_nvidia_app)
        self.footer_bar.app_clicked.connect(self.app_switch_requested.emit)
        right_vlayout.addWidget(self.footer_bar)

        main_hlayout.addWidget(right_column, 1)

    def _on_sidebar_tab_changed(self, key):
        if key == "home":
            self._switch_tab("games")
        elif key == "tournaments":
            self._switch_tab("tournaments")
        elif key == "shop":
            self._switch_tab("bar")
        elif key in ("cabinet", "support"):
            self._open_cabinet()

    def _on_stop_session_clicked(self):
        token = self.logged_in_customer.get('session_token', '') if self.logged_in_customer else ''
        self.cabinet_stop_requested.emit(token)

    def _on_search_changed(self, query):
        self.games_page.set_search_query(query)

    def _on_return_to_game(self):
        top = self.window()
        if hasattr(top, "yield_to_app"):
            top.yield_to_app()

    def _switch_tab(self, key):
        index = {"games": 0, "tournaments": 1, "bar": 2, "cabinet": 3}.get(key, 0)
        self.inner_stack.setCurrentIndex(index)
        if key == "bar":
            self.reload_products()

    def set_pc_status(self, pc_name, status_text):
        self.games_page.set_session_time(status_text)
        self.sidebar.set_time_remaining(status_text)

    def set_time_remaining(self, text):
        self.sidebar.set_time_remaining(text)

    def set_running_apps(self, apps):
        self.apps_bar.set_apps(apps)
        self.footer_bar.set_apps(apps)

    def set_logged_in_customer(self, data):
        self.logged_in_customer = data
        self.top_bar.set_logged_in_customer(data)
        self.bar_page.set_customer_data(data)
        if not data and self.inner_stack.currentWidget() is self.cabinet_page:
            self._close_cabinet()

    def _open_cabinet(self):
        data = self.logged_in_customer or {
            "username": "CYBER_STRIKER",
            "full_name": "CYBER_STRIKER",
            "balance": 12450,
            "bonus_points": 345,
            "phone": "+998 90 123 45 67",
            "email": "striker@nexus.gg"
        }
        current = self.inner_stack.currentIndex()
        if current != self.inner_stack.indexOf(self.cabinet_page):
            self._pre_cabinet_index = current
        self.cabinet_page.set_customer(data)
        self.inner_stack.setCurrentWidget(self.cabinet_page)

    def _close_cabinet(self):
        self.inner_stack.setCurrentIndex(self._pre_cabinet_index)

    def _open_mouse_settings(self):
        dialog = MouseSettingsDialog(parent=self)
        dialog.exec()

    def _open_nvidia_app(self):
        """NVIDIA App yoki NVIDIA Control Panel'ni ishga tushiradi."""
        if IS_WINDOWS:
            nvidia_paths = [
                r"C:\Program Files\NVIDIA Corporation\NVIDIA App\CEF\NVIDIA_app.exe",
                r"C:\Program Files\NVIDIA Corporation\NVIDIA GeForce Experience\NVIDIA GeForce Experience.exe",
                r"C:\Program Files\NVIDIA Corporation\Control Panel Client\nvcplui.exe",
                r"C:\Windows\System32\nvcplui.exe",
            ]
            for p in nvidia_paths:
                if os.path.exists(p):
                    try:
                        subprocess.Popen([p])
                        print(f"[NVIDIA] Ishga tushirildi: {p}")
                        return
                    except Exception as e:
                        print(f"[NVIDIA] Xatolik: {e}")
            try:
                subprocess.Popen(["cmd", "/c", "start", "shell:AppsFolder\\NVIDIACorp.NVIDIAControlPanel_56jybvy8sck8r!NVIDIACorp.NVIDIAControlPanel"], shell=True)
            except Exception as e:
                print(f"[NVIDIA] Universal launch xatosi: {e}")
        else:
            print("[NVIDIA] Faqat Windows'da ishlaydi (simulyatsiya)")

    def reload_games(self):
        def _fetch():
            api_games = self.api_client.get_games(pc_name=self.pc_name)
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
#  Favqulodda chiqish kombinatsiyalari (Ctrl+Alt+Shift+U, Ctrl+Shift+P) —
#  Windows'ning RegisterHotKey() API'si orqali aniqlanadi (WM_HOTKEY xabari
#  darhol yetkaziladi, kechikishsiz).
#  F9 va Ctrl+F9 (launcherni ko'rsatish) ESA — shu past darajali hook orqali
#  aniqlanadi (RegisterHotKey EMAS): eksklyuziv to'liq ekranli o'yinlarda
#  RegisterHotKey'ning WM_HOTKEY xabari ba'zan yetib bormaydi, past darajali
#  hook esa o'yindan OLDINROQ, xom darajada ishlagani uchun ancha ishonchli.
#  RegisterHotKey orqali ham F9/Ctrl+F9 ro'yxatga olinadi — bu faqat
#  qo'shimcha zaxira (agar hook biror sababdan o'rnatilmay qolsa).
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

    # F9 bosilganda oyna hookda ISHONCHLI aniqlanadi, lekin uni haqiqatda
    # eksklyuziv to'liq ekranli o'yin USTIGA chiqarish — butunlay boshqa
    # muammo. Qt'ning activateWindow()/raise_() ichida SetForegroundWindow()
    # ishlatiladi — Windows esa "focus-stealing prevention" tufayli, agar
    # so'rovchi jarayon hozirgi old-plandagi jarayon (bu holda o'yin) BILAN
    # bevosita bog'liq bo'lmasa, buni JIMGINA rad etishi mumkin. Natija:
    # F9 "ba'zida ishlaydi, ba'zida yo'q" — aynan foydalanuvchi tasvirlagan
    # holat. Windows'ning rasmiy aylanma yo'li: bizning ip (kirish)
    # oqimimizni old-plandagi oyna oqimiga AttachThreadInput() bilan
    # vaqtincha "ulab qo'yish" — shunda SetForegroundWindow() Windows
    # tomonidan haqiqiy foydalanuvchi so'rovi sifatida qabul qilinadi.
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    SW_SHOW = 5

    def force_foreground_window(hwnd):
        try:
            fg_hwnd = user32.GetForegroundWindow()
            fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
            cur_thread = kernel32.GetCurrentThreadId()
            attached = False
            if fg_thread and fg_thread != cur_thread:
                attached = bool(user32.AttachThreadInput(cur_thread, fg_thread, True))
            user32.ShowWindow(hwnd, SW_SHOW)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            if attached:
                user32.AttachThreadInput(cur_thread, fg_thread, False)
        except Exception as e:
            print(f"[Hook] force_foreground_window xato: {e}")

    hook_id = None; is_hook_enabled = False
    WM_KEYDOWN = 0x0100; WM_SYSKEYDOWN = 0x0104

    def low_level_keyboard_proc(nCode, wParam, lParam):
        global is_hook_enabled, SHOW_LAUNCHER_REQUESTED
        if nCode >= 0 and is_hook_enabled:
            kb = lParam.contents; vk = kb.vkCode; alt = (kb.flags & 0x20) != 0
            if (alt and vk == VK_TAB) or (vk in (VK_LWIN, VK_RWIN)) or \
               (alt and vk == VK_F4) or (alt and vk == VK_ESCAPE):
                return 1
            # F9 va Ctrl+F9 — IKKALASI HAM shu past darajali hook orqali
            # DARHOL aniqlanadi va yutib yuboriladi (ba'zi eski,
            # eksklyuziv to'liq ekran (DirectInput) o'yinlarda —
            # masalan Prince of Persia, Pro Evolution Soccer —
            # RegisterHotKey'ning WM_HOTKEY xabari yetib bormasligi
            # mumkin, past darajali hook esa o'yindan OLDINROQ, xom
            # darajada ishlaydi — aynan shu sabab F9 uchun hook
            # ishlatiladi).
            #
            # MUHIM (2-marta topilgan xato): avval Ctrl+F9 ATAYLAB shu
            # yerda YUTILMAY, pastdagi RegisterHotKey/WM_HOTKEY orqali
            # "mustaqil" ishlashi kerak edi. Lekin RegisterHotKey aynan
            # HUDDI SHU muammoli (eksklyuziv to'liq ekran) o'yinlarda F9
            # kabi ishonchsiz — ya'ni Ctrl+F9 "zaxira" bo'lishi kerak
            # bo'lgan holatlarning aynan o'zida ishlamay qolardi
            # ("ba'zida ishlab, ba'zida ishlamaydi"). Endi ikkalasi ham
            # bir xil, isbotlangan ishonchli yo'l — shu hook — orqali
            # ishlaydi; pastdagi RegisterHotKey ro'yxatga olish esa faqat
            # qo'shimcha zaxira (agar hook o'rnatilmay qolsa).
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
    MOD_ALT = 0x0001; MOD_CONTROL = 0x0002; MOD_SHIFT = 0x0004; MOD_WIN = 0x0008
    HOTKEY_EMERGENCY_1 = 1   # Ctrl+Alt+Shift+U
    HOTKEY_EMERGENCY_2 = 2   # Ctrl+Shift+P
    HOTKEY_SHOW_LAUNCHER = 3  # F9
    # Ctrl+F9 — F9'ga qo'shimcha (zaxira) kombinatsiya. Scroll Lock EMAS:
    # ko'p (ayniqsa noutbuk) klaviaturalarda bu tugma umuman yo'q. Ctrl
    # va F9 esa HAR QANDAY klaviaturada kafolatlangan mavjud.
    HOTKEY_SHOW_LAUNCHER_2 = 4  # Ctrl+F9

    # Windows tugmasining o'zi past darajali hook orqali yutib
    # yuboriladi (pastda, low_level_keyboard_proc'da), LEKIN bu Win+HARF
    # kombinatsiyalarini (Win+W, Win+D va h.k.) to'liq bloklamaydi —
    # bu Windows'ning hujjatlashtirilgan cheklovi: bunday kombinatsiyalar
    # hook darajasidan pastroqda, alohida aniqlanadi. Amalda buning
    # natijasi: o'yin (masalan eski CS 1.6) bir necha daqiqa ishlagach,
    # WASD bosilganda navbat bilan Widgets (Win+W), Quick Settings
    # (Win+A), Qidiruv (Win+S), Ish stoli (Win+D) ochilib, o'yindan
    # chiqarib yuboradi — real holatda kuzatilgan, ekran suratlari bilan
    # tasdiqlangan xato. Yechim: har bir xavfli Win+HARF kombinatsiyasini
    # ALOHIDA RegisterHotKey orqali "band qilib qo'yish" — shunda Windows
    # bu kombinatsiyani bizning WM_HOTKEY navbatimizga yuboradi (va hech
    # narsa qilmaymiz — pastdagi filtr noma'lum ID'larni jimgina
    # e'tiborsiz qoldiradi), standart Explorer harakati esa umuman
    # ishga tushmaydi.
    HOTKEY_BLOCK_BASE = 100
    _BLOCKED_WIN_COMBO_KEYS = "WASDEQRXILGM"  # W,A,S,D (aynan xabar qilingan) + boshqa keng tarqalgan xavfli birikmalar
    HOTKEY_BLOCK_IDS = {ch: HOTKEY_BLOCK_BASE + i for i, ch in enumerate(_BLOCKED_WIN_COMBO_KEYS)}
    HOTKEY_BLOCK_TAB = HOTKEY_BLOCK_BASE + len(_BLOCKED_WIN_COMBO_KEYS)  # Win+Tab (Task View)

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

        # Win+W/A/S/D/E/Q/R/X/I/L/G/M va Win+Tab — "band qilib qo'yiladi"
        # (yuqoridagi izohga qarang). Muvaffaqiyatsiz bo'lgan alohida
        # kombinatsiyalar (masalan boshqa dastur allaqachon band qilgan
        # bo'lsa) kritik emas — asosiy hotkeylardan farqli ravishda,
        # shu sabab alohida (yumshoqroq) ogohlantirish bilan loglanadi.
        win_combo_results = []
        for ch, hk_id in HOTKEY_BLOCK_IDS.items():
            ok = user32.RegisterHotKey(None, hk_id, MOD_WIN, ord(ch))
            win_combo_results.append((f"Win+{ch}", ok))
        win_combo_results.append(("Win+Tab", user32.RegisterHotKey(None, HOTKEY_BLOCK_TAB, MOD_WIN, VK_TAB)))
        failed = [name for name, ok in win_combo_results if not ok]
        if failed:
            print(f"[Hotkey] OGOHLANTIRISH: quyidagi Win+HARF kombinatsiyalari band qilinmadi: {failed}")
        else:
            print("[Hotkey] Win+W/A/S/D va boshqa xavfli kombinatsiyalar muvaffaqiyatli band qilindi")

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
    customer_session_restored = pyqtSignal(dict)
    customer_stop_failed = pyqtSignal(str)


class ClientLockerApp:
    def __init__(self, config_path="config.json"):
        self._load_config(config_path)
        self.signals = SyncSignals()
        self.signals.status_updated.connect(self._handle_status)
        self.signals.status_resync.connect(self._handle_status_resync)
        self.signals.bar_order_updated.connect(self._handle_bar_order)
        self.signals.remote_command.connect(self._handle_remote_command)
        self.signals.customer_session_restored.connect(self._apply_restored_customer_session)
        self.signals.customer_stop_failed.connect(self._show_customer_stop_error)
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
        # Dastur ishga tushgach, birinchi ACTIVE holatda BIR MARTA
        # mijoz "Kabinet" holatini tiklashga urinadi (pastga qarang:
        # _try_restore_customer_session).
        self._tried_session_restore = False

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
        if not os.path.exists(path) and os.path.exists(os.path.join(CLIENT_DIR, path)):
            path = os.path.join(CLIENT_DIR, path)
        cfg = {"server_url": "http://localhost:8000", "websocket_url": "ws://localhost:8000/ws/pc-status/",
               "pc_name": "PC-01", "heartbeat_interval_seconds": 5, "fallback_games": [], "api_key": ""}
        if os.path.exists(path):
            try:
                with open(path, 'r') as f: cfg.update(json.load(f))
                print(f"[Config] Yuklandi: {path} (Server: {cfg.get('server_url')}, PC: {cfg.get('pc_name')})")
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
            if not self._tried_session_restore:
                self._tried_session_restore = True
                self._try_restore_customer_session()
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
        self._clear_session_state()
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
        """Mijoz qulf ekranida o'z telefon/paroli bilan kirganda — PC
        holatiga (qulflanganligiga) hech qanday ta'sir qilmaydi.
        session_token mahalliy faylga ham saqlanadi — dastur
        (masalan yangilanish/qulashdan keyin) qayta ishga tushsa,
        "Kabinet" holati shu orqali tiklanadi (pastga qarang:
        _try_restore_customer_session)."""
        print(f"[Customer] {data.get('full_name')} ({data.get('phone')}) tizimga kirdi")
        self._save_session_state(data)

    SESSION_STATE_PATH = os.path.join(CLIENT_DIR, "session_state.json")

    def _save_session_state(self, data):
        try:
            with open(self.SESSION_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump({"session_token": data.get("session_token")}, f)
        except Exception as e:
            print(f"[Session] Holatni saqlashda xato: {e}")

    def _clear_session_state(self):
        try:
            if os.path.exists(self.SESSION_STATE_PATH):
                os.remove(self.SESSION_STATE_PATH)
        except Exception as e:
            print(f"[Session] Holatni tozalashda xato: {e}")

    def _try_restore_customer_session(self):
        """Dastur endigina ishga tushdi va PC ACTIVE ekan — agar
        oldingi ishga tushishda mijoz balansidan seans ochib, dastur
        keyin (masalan yangilanish yoki xatolik tufayli) qayta ishga
        tushirilgan bo'lsa, "Kabinet" ko'rinishi yo'qolib qolar edi
        (chunki bu holat faqat xotirada saqlanardi). Bu — bir martalik
        urinish: mahalliy faylda token bormi, va u hali ham shu PC'da
        haqiqiy BALANCE seansiga tegishlimi — server tekshiradi."""
        token = None
        try:
            if os.path.exists(self.SESSION_STATE_PATH):
                with open(self.SESSION_STATE_PATH, "r", encoding="utf-8") as f:
                    token = json.load(f).get("session_token")
        except Exception as e:
            print(f"[Session] Holatni o'qishda xato: {e}")
        if not token:
            return

        # MUHIM: on_done fon oqimida chaqiriladi — Qt widget'larini
        # to'g'ridan-to'g'ri o'zgartirib bo'lmaydi, shuning uchun
        # natija signal orqali asosiy (GUI) oqimga uzatiladi (bu
        # loyihada ilgari xuddi shu xato jiddiy render muammolariga
        # sabab bo'lgan edi).
        def _on_done(ok, data):
            if ok:
                self.signals.customer_session_restored.emit(data)
            else:
                self._clear_session_state()
        self.main_window.api_client.whoami_async(token, self.pc_name, on_done=_on_done)

    def _apply_restored_customer_session(self, data):
        print(f"[Session] Kabinet tiklandi: {data.get('full_name')}")
        self.main_window.launcher_page.set_logged_in_customer(data)

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
        """Mijoz Kabinet/Menyudan Vaqtni to'xtatish yoki Logout'ni bosganda —
        darhol barcha o'yinlarni o'chiradi, hisobdan chiqadi, serverda seansni
        to'xtatadi va LockScreen'ga o'tadi."""
        print(f"[Session] Logout / Stop session requested (pc_name={self.pc_name}, pc_id={self.pc_id})")
        token = session_token or (self.main_window.launcher_page.logged_in_customer.get('session_token', '') if self.main_window.launcher_page.logged_in_customer else '')

        def _do_server_stop():
            target_id = self.pc_id
            if not target_id:
                try:
                    pcs = self.main_window.api_client.get_computers()
                    for p in pcs:
                        if p.get('name') == self.pc_name:
                            target_id = p.get('id')
                            self.pc_id = target_id
                            break
                except Exception as e:
                    print(f"[Session] Fetch pc_id error: {e}")
            if target_id:
                self.main_window.api_client.customer_stop_session_async(target_id, token)

        threading.Thread(target=_do_server_stop, daemon=True).start()
        self._lock()

    def _show_customer_stop_error(self, message):
        QMessageBox.warning(self.main_window, "Vaqtni to'xtatishda xatolik", message)

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

    # MUHIM: ClientLockerApp("config.json") kiosk oynasini DARHOL (hech
    # qanday tarmoq so'rovisiz) to'liq ekranga chiqaradi — shuning uchun
    # yangilanishni tekshirish shu OYNA ALLAQACHON KO'RINGANDAN KEYIN,
    # fon oqimida amalga oshiriladi. Oldin bu tekshiruv oyna
    # yaratilishidan OLDIN, asosiy oqimda (bloklovchi tarmoq so'rovi
    # bilan) bajarilar edi — agar server sekin javob bersa yoki tarmoq
    # hali tayyor bo'lmasa (kompyuter yangi yoqilgan payt), mijoz bir
    # necha soniya Windows ish stolini ko'rib turardi, kiosk oynasi esa
    # keyin paydo bo'lardi.
    _locker = ClientLockerApp("config.json")

    def _check_update_on_startup():
        try:
            if check_and_apply_update(_locker.server_url, _locker.api_key):
                print("[Update] Yangilanish o'rnatildi — dastur qayta ishga tushirilmoqda...")
                os._exit(17)
        except Exception as e:
            print(f"[Update] Ishga tushishda yangilanishni tekshirib bo'lmadi: {e}")
    threading.Thread(target=_check_update_on_startup, daemon=True).start()

    sys.exit(app.exec())

if __name__ == '__main__':
    main()
