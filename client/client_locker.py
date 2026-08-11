"""
client_locker.py  —  Clutch Zone Client PC Locker (Windows Native Win32 API & High-DPI Awareness Architecture)
===================================================================================
1. SetProcessDpiAwarenessContext/SetProcessDpiAwareness called before QApplication
   instantiation, AND Qt's own HiDPI auto-scaling disabled — this prevents the
   "double DPI scaling" bug where Windows (physical pixels) and Qt (device-pixel-
   ratio scaling) both scale the same geometry, shrinking the window into a
   corner of the screen at 125%/150% display scale.
2. Win32 Native GetSystemMetrics(SM_CXSCREEN / SM_CYSCREEN) geometry calculation with force_native_fullscreen().
3. ShowEvent override for LockScreenWindow, LockerWindow, LauncherWindow & MainWindow.
4. Expanding setSizePolicy on root containers and centered responsive card / launcher grid.
"""

import sys
import os
import ctypes

# ──────────────────────────────────────────────────────────────────────────────
#  1. CRITICAL: SET PROCESS DPI AWARENESS (QApplication yaratilishidan OLDIN)
#     va Qt'ning o'z HiDPI scale qatlamini o'chirish.
#
#     Root cause: Windows darajasida Per-Monitor DPI Aware o'rnatilgach,
#     GetSystemMetrics() FIZIK piksellarni qaytaradi (masalan 1920x1080).
#     Agar shu qiymatlar setGeometry()/setFixedSize()ga uzatilganda Qt6'ning
#     o'z HiDPI scaling qatlami HAM ishlab tursa, Qt bu qiymatni yana bir
#     bor devicePixelRatio'ga bo'lib tashlaydi (masalan 1.5x) — natijada
#     oyna w/1.5 x h/1.5 o'lchamda, ekranning (0,0) burchagida chizilib
#     qoladi. Buni oldini olish uchun Qt scaling'ni butunlay o'chiramiz va
#     geometriyani faqat native Win32 fizik piksellar bilan boshqaramiz.
# ──────────────────────────────────────────────────────────────────────────────
if sys.platform == 'win32':
    try:
        # Windows 10 1703+ uchun eng ishonchli usul: Per-Monitor-V2 DPI
        # awareness — monitor almashtirilganda yoki scale dinamik
        # o'zgarganda ham to'g'ri qayta hisoblanadi.
        DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
        ctypes.windll.user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    # Windows darajasida DPI allaqachon qo'lda (native) boshqarilyapti,
    # shuning uchun Qt'ning avtomatik HiDPI scale qatlami o'chiriladi —
    # aks holda yuqoridagi "double scaling" xatosi yuzaga keladi.
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = "1"

import time
import json
import socket
import subprocess
import platform
import threading
import requests
import websocket

from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal, QObject, QUrl, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QPushButton, QFrame, QHBoxLayout, QScrollArea, QGridLayout,
    QLineEdit, QGraphicsDropShadowEffect, QSizePolicy, QStackedWidget
)
from PyQt6.QtGui import QFont, QColor, QPixmap, QGuiApplication

# ──────────────────────────────────────────────────────────────────────────────
#  2. NATIVE GEOMETRY CALCULATION (fizik piksellar — Qt scaling o'chirilgan)
# ──────────────────────────────────────────────────────────────────────────────
def get_screen_resolution():
    if sys.platform == 'win32':
        try:
            width = ctypes.windll.user32.GetSystemMetrics(0)   # SM_CXSCREEN
            height = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN
            if width > 0 and height > 0:
                return width, height
        except Exception as e:
            print(f"[user32 API Error] {e}")

    screen = QGuiApplication.primaryScreen().geometry()
    return screen.width(), screen.height()


# ──────────────────────────────────────────────────────────────────────────────
#  3. FORCE FULLSCREEN & SHOW EVENT OVERRIDE
# ──────────────────────────────────────────────────────────────────────────────
class FullscreenMixin:
    def force_native_fullscreen(self):
        w, h = get_screen_resolution()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setGeometry(0, 0, w, h)
        self.setFixedSize(w, h)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event):
        super().showEvent(event)
        self.force_native_fullscreen()


# ──────────────────────────────────────────────────────────────────────────────
#  4. RESPONSIVE GAME GRID
# ──────────────────────────────────────────────────────────────────────────────
class ResponsiveGameGrid(QScrollArea):
    def __init__(self, card_min_width=220, card_height=280, spacing=16, parent=None):
        super().__init__(parent)
        self.card_min_width = card_min_width
        self.card_height = card_height
        self.spacing = spacing
        self._items = []
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { border: none; background-color: #060911; }")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.container = QWidget()
        self.container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.container.setStyleSheet("QWidget { background-color: #060911; }")

        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setSpacing(spacing)
        self.grid_layout.setContentsMargins(24, 24, 24, 24)
        self.setWidget(self.container)

    def set_items(self, widgets):
        self._items = widgets
        self._relayout()

    def _columns_for_width(self, width):
        col_width = self.card_min_width + self.spacing
        return max(1, width // col_width)

    def _relayout(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)
        cols = self._columns_for_width(self.viewport().width())
        for index, widget in enumerate(self._items):
            row, col = divmod(index, cols)
            self.grid_layout.addWidget(widget, row, col)
            widget.setMinimumWidth(self.card_min_width)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()


# ──────────────────────────────────────────────────────────────────────────────
#  QWEBENGINEVIEW IMPORTS & FALLBACK
# ──────────────────────────────────────────────────────────────────────────────
HAS_WEBENGINE = False
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage
    from PyQt6.QtWebChannel import QWebChannel
    HAS_WEBENGINE = True
except ImportError as err:
    print(f"[WebEngine Warning] PyQt6.QtWebEngineWidgets import qilib bo'lmadi: {err}")
    print("Iltimos, `pip install PyQt6-WebEngine` buyrug'ini bajaring.")


class PyQtBridge(QObject):
    game_launch_requested = pyqtSignal(str, str, str)

    @pyqtSlot(str, str, str)
    def launchGame(self, exe_path, game_name, working_directory):
        print(f"[WebBridge] launchGame buyrug'i keldi: '{game_name}' -> {exe_path}")
        self.game_launch_requested.emit(exe_path, game_name, working_directory)


class SyncSignals(QObject):
    status_updated    = pyqtSignal(dict)
    bar_order_updated = pyqtSignal(dict)


IS_WINDOWS = platform.system() == 'Windows'

if IS_WINDOWS:
    from ctypes import wintypes
    user32  = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    WH_KEYBOARD_LL = 13
    VK_TAB = 0x09; VK_LWIN = 0x5B; VK_RWIN = 0x5C; VK_F4 = 0x73; VK_ESCAPE = 0x1B

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
            ("flags",  wintypes.DWORD), ("time",     wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
        ]
    HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT))
    hook_id = None; is_hook_enabled = False

    def low_level_keyboard_proc(nCode, wParam, lParam):
        global is_hook_enabled
        if nCode >= 0 and is_hook_enabled:
            kb = lParam.contents; vk = kb.vkCode; alt = (kb.flags & 0x20) != 0
            if (alt and vk == VK_TAB) or (vk in (VK_LWIN, VK_RWIN)) or \
               (alt and vk == VK_F4) or (vk == VK_ESCAPE and (kb.flags & 0x01)):
                return 1
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
            user32.UnhookWindowsHookEx(hook_id); hook_id = None
else:
    def install_keyboard_hook():   print("[Hook] enabled (sim)")
    def uninstall_keyboard_hook(): print("[Hook] disabled (sim)")


# ──────────────────────────────────────────────────────────────────────────────
#  LOCKER WINDOW / LOCKSCREEN WINDOW
# ──────────────────────────────────────────────────────────────────────────────
class LockScreenWindow(FullscreenMixin, QWidget):
    """
    LockScreenWindow — Fallback Native Lock Screen Widget with Win32 Native Fullscreen & High-DPI Awareness
    """
    def __init__(self, pc_name="PC-01", parent=None):
        super().__init__(parent)
        self.pc_name = pc_name
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("QWidget { background-color: #060911; }")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        main_container = QWidget(self)
        main_container.setObjectName("mainContainer")
        main_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_container.setStyleSheet("QWidget#mainContainer { background-color: #060911; }")
        
        container_layout = QVBoxLayout(main_container)
        container_layout.setContentsMargins(20, 20, 20, 20)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("lockCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        card.setMinimumSize(420, 260)
        card.setMaximumSize(600, 360)
        card.setStyleSheet("""
            QFrame#lockCard {
                background: #060911;
                border: 2px solid rgba(0,240,255,0.35);
                border-radius: 16px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(40, 36, 40, 36)
        cl.setSpacing(14)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        s = QLabel("STATION LOCKED")
        s.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        s.setStyleSheet("color: #ef4444; letter-spacing: 3px;")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(s)

        pc = QLabel(self.pc_name)
        pc.setFont(QFont("Consolas", 42, QFont.Weight.Bold))
        pc.setStyleSheet("color: #00f0ff; letter-spacing: 2px;")
        pc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(pc)

        desc = QLabel("Seansni boshlash uchun administratorga murojaat qiling.")
        desc.setFont(QFont("Segoe UI", 14))
        desc.setStyleSheet("color: #94a3b8;")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(desc)

        container_layout.addWidget(card)
        main_layout.addWidget(main_container)

        self.force_native_fullscreen()

    def keyPressEvent(self, event): event.accept()


class LockerWindow(FullscreenMixin, QMainWindow):
    """
    LockerWindow — Kassa Serveridagi Web Launcher URL manzilidan LOCK panelini yuklaydi.
    """
    def __init__(self, pc_name="PC-01", server_url="http://localhost:8001", parent=None):
        super().__init__(parent)
        self.pc_name = pc_name
        self.server_url = server_url.rstrip('/')
        self.url = f"{self.server_url}/launcher/?pc_name={pc_name}&mode=lock"

        self.setWindowTitle(f"Clutch Zone Locker - {pc_name}")
        self.setStyleSheet("QMainWindow { background-color: #060911; }")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._init_web_engine()
        self.force_native_fullscreen()

    def _init_web_engine(self):
        if HAS_WEBENGINE:
            self.browser = QWebEngineView(self)
            self.browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.browser.setZoomFactor(1.0)
            
            profile = QWebEngineProfile.defaultProfile()
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            profile.clearHttpCache()

            settings = profile.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2DCanvasEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)

            try:
                QWebEngineSettings.globalSettings().setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, False)
            except Exception:
                pass

            self.browser.page().loadFinished.connect(self._apply_full_viewport_css)

            timestamp_url = f"{self.url}&_t={int(time.time() * 1000)}"
            self.browser.setUrl(QUrl(timestamp_url))
            self.setCentralWidget(self.browser)
        else:
            lock_widget = LockScreenWindow(pc_name=self.pc_name, parent=self)
            self.setCentralWidget(lock_widget)

    def _apply_full_viewport_css(self, ok):
        if ok and HAS_WEBENGINE and hasattr(self, 'browser'):
            js_fix = """
            var meta = document.querySelector('meta[name="viewport"]');
            if (!meta) {
                meta = document.createElement('meta');
                meta.name = 'viewport';
                document.getElementsByTagName('head')[0].appendChild(meta);
            }
            meta.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no';
            document.body.style.width = '100vw';
            document.body.style.height = '100vh';
            document.body.style.overflow = 'hidden';
            """
            self.browser.page().runJavaScript(js_fix)

    def reload_page(self):
        if HAS_WEBENGINE and hasattr(self, 'browser'):
            timestamp_url = f"{self.url}&_t={int(time.time() * 1000)}"
            self.browser.setUrl(QUrl(timestamp_url))
            self.browser.reload()

    def show_locker(self):
        self.reload_page()
        self.force_native_fullscreen()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                QTimer.singleShot(80, self.force_native_fullscreen)

    def closeEvent(self, event): event.ignore()
    def keyPressEvent(self, event): event.accept()


# ──────────────────────────────────────────────────────────────────────────────
#  LAUNCHER WINDOW
# ──────────────────────────────────────────────────────────────────────────────
class LauncherWindow(FullscreenMixin, QMainWindow):
    """
    LauncherWindow — Kassa Serveridagi Web Launcher URL manzilidan O'yinlar va Bar panelini yuklaydi.
    """
    game_launched_signal = pyqtSignal(dict)

    def __init__(self, pc_name="PC-01", server_url="http://localhost:8001",
                 fallback_games=None, on_bar_click=None, parent=None):
        super().__init__(parent)
        self.pc_name = pc_name
        self.server_url = server_url.rstrip('/')
        self.fallback_games = fallback_games or []
        self.on_bar_click = on_bar_click
        self.url = f"{self.server_url}/launcher/?pc_name={pc_name}&mode=launcher"

        self.setWindowTitle(f"Clutch Zone Game Launcher - {pc_name}")
        self.setStyleSheet("QMainWindow { background-color: #060911; }")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._init_web_engine()
        self.force_native_fullscreen()

    def _init_web_engine(self):
        if HAS_WEBENGINE:
            self.browser = QWebEngineView(self)
            self.browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.browser.setZoomFactor(1.0)
            
            profile = QWebEngineProfile.defaultProfile()
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            profile.clearHttpCache()

            settings = profile.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2DCanvasEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)

            try:
                QWebEngineSettings.globalSettings().setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, False)
            except Exception:
                pass

            self.channel = QWebChannel()
            self.bridge = PyQtBridge()
            self.bridge.game_launch_requested.connect(self._on_bridge_game_launch)
            self.channel.registerObject("pyqt_bridge", self.bridge)
            self.browser.page().setWebChannel(self.channel)

            self.browser.page().loadFinished.connect(self._apply_full_viewport_css)

            timestamp_url = f"{self.url}&_t={int(time.time() * 1000)}"
            self.browser.setUrl(QUrl(timestamp_url))
            self.setCentralWidget(self.browser)
        else:
            grid = ResponsiveGameGrid(card_min_width=220, card_height=280, parent=self)
            self.setCentralWidget(grid)

    def _apply_full_viewport_css(self, ok):
        if ok and HAS_WEBENGINE and hasattr(self, 'browser'):
            js_fix = """
            var meta = document.querySelector('meta[name="viewport"]');
            if (!meta) {
                meta = document.createElement('meta');
                meta.name = 'viewport';
                document.getElementsByTagName('head')[0].appendChild(meta);
            }
            meta.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no';
            document.body.style.width = '100vw';
            document.body.style.height = '100vh';
            document.body.style.overflow = 'hidden';
            """
            self.browser.page().runJavaScript(js_fix)

    def reload_page(self):
        if HAS_WEBENGINE and hasattr(self, 'browser'):
            timestamp_url = f"{self.url}&_t={int(time.time() * 1000)}"
            self.browser.setUrl(QUrl(timestamp_url))
            self.browser.reload()

    def show_launcher(self):
        self.reload_page()
        self.force_native_fullscreen()

    def _on_bridge_game_launch(self, exe_path, game_name, working_directory):
        self.game_launched_signal.emit({
            'name': game_name,
            'executable_path': exe_path,
            'working_directory': working_directory
        })

    def update_timer(self, seconds):
        if HAS_WEBENGINE and hasattr(self, 'browser'):
            js_code = f"if (typeof updateTimer === 'function') updateTimer({seconds});"
            self.browser.page().runJavaScript(js_code)

    def load_games(self):
        if HAS_WEBENGINE and hasattr(self, 'browser'):
            self.browser.page().runJavaScript("if (typeof loadGames === 'function') loadGames();")

    def show_launch_error(self, msg="O'yin fayli topilmadi"):
        if HAS_WEBENGINE and hasattr(self, 'browser'):
            safe_msg = msg.replace("'", "\\'")
            self.browser.page().runJavaScript(f"alert('❌ {safe_msg}');")

    def show_launch_success(self, name):
        if HAS_WEBENGINE and hasattr(self, 'browser'):
            safe_name = name.replace("'", "\\'")
            self.browser.page().runJavaScript(f"console.log('Game launched: {safe_name}');")

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                QTimer.singleShot(80, self.force_native_fullscreen)

    def closeEvent(self, event): event.ignore()


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN WINDOW
# ──────────────────────────────────────────────────────────────────────────────
class MainWindow(FullscreenMixin, QMainWindow):
    PAGE_LOCK     = 0
    PAGE_LAUNCHER = 1

    def __init__(self, pc_name="PC-01", server_url="http://localhost:8001",
                 fallback_games=None, on_bar_click=None):
        super().__init__()
        self.pc_name = pc_name
        self.server_url = server_url

        self.setWindowTitle(f"Clutch Zone Client Locker - {pc_name}")
        self.setStyleSheet("QMainWindow, QWidget { background-color: #060911; }")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.locker_win   = LockerWindow(pc_name=pc_name, server_url=server_url)
        self.launcher_win = LauncherWindow(
            pc_name=pc_name, server_url=server_url,
            fallback_games=fallback_games or [], on_bar_click=on_bar_click
        )

        self.stacked = QStackedWidget()
        self.stacked.setStyleSheet("QStackedWidget { background-color: #060911; }")
        self.stacked.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.stacked.addWidget(self.locker_win)      # Page 0
        self.stacked.addWidget(self.launcher_win)    # Page 1
        self.stacked.setCurrentIndex(self.PAGE_LOCK)
        self.setCentralWidget(self.stacked)
        self.force_native_fullscreen()

    def switch_to_lock(self):
        self.locker_win.show_locker()
        self.stacked.setCurrentIndex(self.PAGE_LOCK)
        self.force_native_fullscreen()

    def switch_to_launcher(self):
        self.launcher_win.show_launcher()
        self.stacked.setCurrentIndex(self.PAGE_LAUNCHER)
        self.force_native_fullscreen()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                QTimer.singleShot(80, self.force_native_fullscreen)

    def closeEvent(self, event): event.ignore()

    @property
    def game_launched_signal(self): return self.launcher_win.game_launched_signal
    def update_timer(self, s): self.launcher_win.update_timer(s)
    def load_games(self): self.launcher_win.load_games()
    def show_launch_error(self, msg): self.launcher_win.show_launch_error(msg)
    def show_launch_success(self, name): self.launcher_win.show_launch_success(name)


# ──────────────────────────────────────────────────────────────────────────────
#  TIMER OVERLAY
# ──────────────────────────────────────────────────────────────────────────────
class TimerOverlayWidget(QWidget):
    def __init__(self, pc_name="PC-01", on_bar_click=None):
        super().__init__()
        self.pc_name = pc_name
        self.on_bar_click = on_bar_click
        self._build_ui()

    def _build_ui(self):
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        width, height = get_screen_resolution()
        self.move(width - 370, 20)

        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        con = QFrame()
        con.setStyleSheet("QFrame{background:rgba(10,14,23,0.92);border:1px solid rgba(0,240,255,0.4);border-radius:16px;}")
        cl = QHBoxLayout(con)
        cl.setContentsMargins(14, 8, 14, 8)
        tb = QVBoxLayout()
        tb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label = QLabel("00:00:00")
        self.timer_label.setFont(QFont("Consolas", 18, QFont.Weight.Bold))
        self.timer_label.setStyleSheet("color:#00f0ff;")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tb.addWidget(self.timer_label)
        sub = QLabel(f"{self.pc_name} - ACTIVE SESSION")
        sub.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        sub.setStyleSheet("color:#10b981;letter-spacing:1px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tb.addWidget(sub)
        cl.addLayout(tb)
        bb = QPushButton("🍸 BAR")
        bb.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        bb.setStyleSheet("QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #a855f7,stop:0.5 #d946ef,stop:1 #ec4899);color:#fff;border:1px solid rgba(255,255,255,0.4);border-radius:12px;font-weight:bold;}QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #c084fc,stop:1 #f472b6);border:1px solid #00f0ff;}")
        if self.on_bar_click: bb.clicked.connect(self.on_bar_click)
        cl.addWidget(bb)
        lo.addWidget(con)

    def update_timer(self, seconds):
        if seconds <= 0:
            self.timer_label.setText("00:00:00")
            return
        self.timer_label.setText(f"{seconds//3600:02d}:{(seconds%3600)//60:02d}:{seconds%60:02d}")


# ──────────────────────────────────────────────────────────────────────────────
#  APPLICATION CONTROLLER
# ──────────────────────────────────────────────────────────────────────────────
class ClientLockerApp:
    def __init__(self, config_path="config.json"):
        self._load_config(config_path)
        self.signals = SyncSignals()
        self.signals.status_updated.connect(self._handle_status)
        self.signals.bar_order_updated.connect(self._handle_bar_order)
        self.launched_processes = []
        self.current_status = 'LOCKED'
        self.time_remaining = 0

        self.main_window = MainWindow(
            pc_name=self.pc_name, server_url=self.server_url,
            fallback_games=self.fallback_games
        )
        self.main_window.game_launched_signal.connect(self._handle_game_launch)

        self.overlay = TimerOverlayWidget(pc_name=self.pc_name)
        self.overlay.hide()

        self.countdown = QTimer()
        self.countdown.timeout.connect(self._tick)
        self.countdown.start(1000)

        install_keyboard_hook()
        self.main_window.switch_to_lock()

        threading.Thread(target=self._run_sync, daemon=True).start()

    def _load_config(self, path):
        cfg = {"server_url": "http://localhost:8001", "websocket_url": "ws://localhost:8001/ws/pc-status/",
               "pc_name": "PC-01", "heartbeat_interval_seconds": 5, "fallback_games": []}
        if os.path.exists(path):
            try:
                with open(path, 'r') as f: cfg.update(json.load(f))
            except Exception as e: print(f"[Config] {e}")
        self.server_url = cfg["server_url"]
        self.ws_url = cfg["websocket_url"]
        self.pc_name = cfg["pc_name"]
        self.heartbeat_interval = cfg["heartbeat_interval_seconds"]
        self.fallback_games = cfg.get("fallback_games", [])

    def _handle_status(self, data):
        new_status = data.get('status', 'LOCKED')
        seconds = data.get('time_remaining', 0)
        self.time_remaining = seconds
        if new_status in ('ACTIVE', 'WARNING'):
            if self.current_status == 'LOCKED':
                self._unlock()
            self.current_status = new_status
            self.overlay.update_timer(self.time_remaining)
            self.main_window.update_timer(self.time_remaining)
        else:
            if self.current_status != 'LOCKED':
                self._lock()

    def _handle_bar_order(self, data): pass

    def _unlock(self):
        print("[Locker] UNLOCK -> LauncherWindow (Web Launcher)")
        uninstall_keyboard_hook()
        self.main_window.load_games()
        self.main_window.switch_to_launcher()
        self.main_window.force_native_fullscreen()
        self.overlay.show()
        self.current_status = 'ACTIVE'

    def _lock(self):
        print("[Locker] LOCK -> LockerWindow (Web Lock Screen)")
        self.current_status = 'LOCKED'
        self.time_remaining = 0
        self.overlay.hide()
        self.main_window.switch_to_lock()
        self.main_window.force_native_fullscreen()
        install_keyboard_hook()
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
                self.overlay.update_timer(self.time_remaining)
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
                r = requests.post(f"{self.server_url}/api/computers/heartbeat/", json={"pc_name": self.pc_name, "ip_address": local_ip}, timeout=4)
                if r.status_code == 200:
                    self.signals.status_updated.emit(r.json())
            except Exception as e:
                print(f"[Heartbeat] {e}")
            time.sleep(self.heartbeat_interval)

    def _run_ws(self):
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
        def on_open(ws): print("[WS] Connected")
        def on_error(ws, e): print(f"[WS] Error: {e}")
        while True:
            try:
                ws = websocket.WebSocketApp(self.ws_url, on_message=on_message, on_error=on_error)
                ws.run_forever()
            except Exception as e:
                print(f"[WS] Failed: {e}")
            time.sleep(3)


# ──────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────
def main():
    # DPI awareness va Qt HiDPI scaling o'chirish fayl boshida (QApplication
    # yaratilishidan oldin, hatto PyQt6 import qilinishidan oldin) allaqachon
    # bajarilgan — bu yerda takrorlash shart emas.
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QWidget {
            background-color: #060911;
            color: #e2e8f0;
            font-family: 'Segoe UI', 'Inter', 'SF Pro', -apple-system, sans-serif;
        }
    """)
    _locker = ClientLockerApp("config.json")
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
