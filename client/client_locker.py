"""
client_locker.py  —  Clutch Zone Client PC Locker
===================================================
ARXITEKTURA: SINGLE QMainWindow + QStackedWidget

  MainWindow (bitta, HECH QACHON hide bo'lmaydi)
  ├── QStackedWidget
  │   ├── Page 0: LockScreenWidget   (STATION LOCKED qora fon)
  │   └── Page 1: GameLauncherWidget (O'yinlar katalogi)
  └── BarMenuWindow (float Tool dialog)

Oyna holati:
  LOCK   → stacked_widget.setCurrentIndex(0)
  UNLOCK → stacked_widget.setCurrentIndex(1)

hide() / close() / ikkinchi QMainWindow — TO'LIQ OLIB TASHLANDI.
"""

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
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QPushButton, QFrame, QHBoxLayout, QScrollArea, QGridLayout,
    QLineEdit, QGraphicsDropShadowEffect, QSizePolicy, QStackedWidget
)
from PyQt6.QtGui import QFont, QColor, QPixmap, QGuiApplication

# ──────────────────────────────────────────────────────────────────────────────
#  SIGNALS
# ──────────────────────────────────────────────────────────────────────────────
class SyncSignals(QObject):
    status_updated    = pyqtSignal(dict)
    bar_order_updated = pyqtSignal(dict)


# ──────────────────────────────────────────────────────────────────────────────
#  WINDOWS KEYBOARD HOOK
# ──────────────────────────────────────────────────────────────────────────────
IS_WINDOWS = platform.system() == 'Windows'

if IS_WINDOWS:
    import ctypes
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
#  PAGE 0 — LOCK SCREEN WIDGET
# ──────────────────────────────────────────────────────────────────────────────
class LockScreenWidget(QWidget):
    def __init__(self, pc_name="PC-01", parent=None):
        super().__init__(parent)
        self.pc_name = pc_name
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("background-color: #060911;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setFixedWidth(500)
        card.setStyleSheet("""QFrame { background: rgba(12,18,32,0.94);
            border: 2px solid rgba(0,240,255,0.35); border-radius: 28px; }""")
        sh = QGraphicsDropShadowEffect(card)
        sh.setBlurRadius(40); sh.setColor(QColor(0,240,255,110)); sh.setOffset(0,0)
        card.setGraphicsEffect(sh)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(40,36,40,36); cl.setSpacing(14)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_lbl = QLabel()
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "clutch_logo_full.png")
        if not os.path.exists(logo_path):
            logo_path = os.path.join(os.getcwd(), "client", "assets", "clutch_logo_full.png")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(320,170,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pix)
        else:
            logo_lbl.setText("CLUTCH ZONE")
            logo_lbl.setFont(QFont("Impact", 36, QFont.Weight.Bold))
            logo_lbl.setStyleSheet("color: #00f0ff; letter-spacing: 4px;")
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glow = QGraphicsDropShadowEffect(logo_lbl)
        glow.setBlurRadius(30); glow.setColor(QColor(0,240,255,180)); glow.setOffset(0,0)
        logo_lbl.setGraphicsEffect(glow)
        cl.addWidget(logo_lbl)

        s = QLabel("STATION LOCKED")
        s.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        s.setStyleSheet("color: #ef4444; letter-spacing: 3px;")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(s)

        pc = QLabel(self.pc_name)
        pc.setFont(QFont("Consolas", 34, QFont.Weight.Bold))
        pc.setStyleSheet("color: #00f0ff; letter-spacing: 2px;")
        pc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(pc)

        desc = QLabel("Seansni boshlash uchun administratorga murojaat qiling.")
        desc.setFont(QFont("Segoe UI", 12))
        desc.setStyleSheet("color: #94a3b8;")
        desc.setWordWrap(True); desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(desc)
        root.addWidget(card)

    def keyPressEvent(self, event): event.accept()


# ──────────────────────────────────────────────────────────────────────────────
#  IMAGE CACHE
# ──────────────────────────────────────────────────────────────────────────────
class ImageCache(QObject):
    cache = {}
    image_downloaded_signal = pyqtSignal(str, QPixmap)

    def fetch_image(self, url, w, h):
        if not url or url in self.cache: return
        def fetch():
            try:
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    pix = QPixmap()
                    pix.loadFromData(r.content)
                    if not pix.isNull():
                        scaled = pix.scaled(w,h,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
                        ImageCache.cache[url] = scaled
                        self.image_downloaded_signal.emit(url, scaled)
            except Exception as e: print(f"[ImageCache] {e}")
        threading.Thread(target=fetch, daemon=True).start()

    @classmethod
    def get_cached(cls, path, w, h):
        if not path: return None
        if path in cls.cache: return cls.cache[path]
        resolved = path
        if not os.path.exists(resolved):
            sd = os.path.dirname(os.path.abspath(__file__))
            for alt in [os.path.join(sd,path), os.path.join(sd,"assets","games",os.path.basename(path))]:
                if os.path.exists(alt): resolved = alt; break
        if os.path.exists(resolved):
            pix = QPixmap(resolved)
            if not pix.isNull():
                scaled = pix.scaled(w,h,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
                cls.cache[path] = scaled; return scaled
        return None


# ──────────────────────────────────────────────────────────────────────────────
#  PAGE 1 — GAME LAUNCHER WIDGET
# ──────────────────────────────────────────────────────────────────────────────
class GameLauncherWidget(QWidget):
    game_launched_signal = pyqtSignal(dict)

    def __init__(self, pc_name="PC-01", server_url="http://localhost:8000",
                 fallback_games=None, on_bar_click=None, parent=None):
        super().__init__(parent)
        self.pc_name = pc_name; self.server_url = server_url
        self.fallback_games = fallback_games or []; self.on_bar_click = on_bar_click
        self.games = []; self.current_category = None; self.search_query = ""
        self.pixmap_labels = {}
        self.image_downloader = ImageCache()
        self.image_downloader.image_downloaded_signal.connect(self._on_image_downloaded)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #0a0e17; color: #e2e8f0;
                font-family: 'Segoe UI','Inter',sans-serif; }
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { border:none; background:#0f172a; width:8px; border-radius:4px; }
            QScrollBar::handle:vertical { background:#334155; border-radius:4px; }
            QScrollBar::handle:vertical:hover { background:#00f0ff; }
            QLineEdit { background:rgba(15,23,42,0.9); color:#f8fafc;
                border:1px solid rgba(0,240,255,0.3); border-radius:12px; padding:8px 16px; font-size:14px; }
            QLineEdit:focus { border:1px solid #00f0ff; }
        """)
        main = QVBoxLayout(self)
        main.setContentsMargins(36,28,36,28); main.setSpacing(20)

        # Header
        hdr = QHBoxLayout()
        tb = QVBoxLayout()
        t = QLabel("🎮 CLUTCH ZONE"); t.setFont(QFont("Segoe UI",24,QFont.Weight.Bold))
        t.setStyleSheet("color:#00f0ff;letter-spacing:2px;")
        sub = QLabel(f"GAME CATALOG LAUNCHER • {self.pc_name}")
        sub.setFont(QFont("Segoe UI",10,QFont.Weight.Bold))
        sub.setStyleSheet("color:#94a3b8;letter-spacing:1px;")
        tb.addWidget(t); tb.addWidget(sub)
        hdr.addLayout(tb); hdr.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 O'yin nomini qidirish...")
        self.search_input.setFixedWidth(290)
        self.search_input.textChanged.connect(self._on_search)
        hdr.addWidget(self.search_input)

        self.timer_label = QLabel("00:00:00")
        self.timer_label.setFont(QFont("Consolas",16,QFont.Weight.Bold))
        self.timer_label.setStyleSheet("color:#10b981;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.3);border-radius:12px;padding:8px 16px;")
        hdr.addWidget(self.timer_label)

        bar_btn = QPushButton("🍸 BAR MENU")
        bar_btn.setFont(QFont("Segoe UI",11,QFont.Weight.Bold))
        bar_btn.setStyleSheet("""QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #a855f7,stop:0.5 #d946ef,stop:1 #ec4899);color:#fff;border:1px solid rgba(255,255,255,0.4);border-radius:12px;padding:10px 20px;font-weight:bold;letter-spacing:1px;}
            QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #c084fc,stop:1 #f472b6);border:1px solid #00f0ff;}""")
        if self.on_bar_click: bar_btn.clicked.connect(self.on_bar_click)
        hdr.addWidget(bar_btn)
        main.addLayout(hdr)

        # Category bar
        cat_bar = QHBoxLayout(); cat_bar.setSpacing(12)
        self.cat_buttons = {}
        for code, label in [("ALL","🌐 Barchasi"),("FPS","🎯 FPS / Shooter"),("Action","⚔️ Action / RPG"),("Sports","⚽ Sports / Racing"),("Strategy","🧠 Strategy / MOBA")]:
            btn = QPushButton(label); btn.setFont(QFont("Segoe UI",10,QFont.Weight.Bold))
            btn.setStyleSheet(self._cat_style(code=="ALL"))
            btn.clicked.connect(lambda _,c=code: self._set_category(c))
            cat_bar.addWidget(btn); self.cat_buttons[code] = btn
        cat_bar.addStretch(); main.addLayout(cat_bar)

        self.status_msg = QLabel("O'yin tanlang va 'Ishga tushirish' tugmasini bosing")
        self.status_msg.setFont(QFont("Segoe UI",10))
        self.status_msg.setStyleSheet("color:#94a3b8;background:rgba(15,23,42,0.7);border:1px solid rgba(255,255,255,0.05);border-radius:8px;padding:8px 14px;")
        main.addWidget(self.status_msg)

        self.scroll_area = QScrollArea(); self.scroll_area.setWidgetResizable(True)
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(24); self.grid_layout.setContentsMargins(0,0,0,0)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.grid_widget)
        main.addWidget(self.scroll_area, stretch=1)

    def _cat_style(self, active):
        if active: return "QPushButton{background:rgba(0,240,255,0.25);color:#00f0ff;border:1px solid #00f0ff;border-radius:12px;padding:8px 18px;}"
        return "QPushButton{background:rgba(30,41,59,0.5);color:#94a3b8;border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:8px 18px;}QPushButton:hover{background:rgba(51,65,85,0.8);color:#e2e8f0;}"

    def _set_category(self, code):
        self.current_category = None if code=="ALL" else code
        for c,btn in self.cat_buttons.items(): btn.setStyleSheet(self._cat_style(c==code))
        self._render_games()

    def _on_search(self, text):
        self.search_query = text.strip().lower(); self._render_games()

    def update_timer(self, seconds):
        if seconds<=0: self.timer_label.setText("00:00:00"); return
        self.timer_label.setText(f"{seconds//3600:02d}:{(seconds%3600)//60:02d}:{seconds%60:02d}")

    def load_games(self):
        try:
            res = requests.get(f"{self.server_url}/api/games/", timeout=4)
            self.games = res.json() if res.status_code==200 else self.fallback_games
        except Exception as e:
            print(f"[GameLauncher] {e}"); self.games = self.fallback_games
        self._render_games()

    def _on_image_downloaded(self, url, pixmap):
        if url in self.pixmap_labels:
            for lbl in self.pixmap_labels[url]: lbl.setPixmap(pixmap)

    def _render_games(self):
        for i in reversed(range(self.grid_layout.count())):
            w = self.grid_layout.itemAt(i).widget()
            if w: w.setParent(None)
        self.pixmap_labels.clear()

        filtered = [g for g in self.games
            if (not self.current_category or g.get('category')==self.current_category)
            and (not self.search_query or self.search_query in g.get('name','').lower())]

        col_count=4
        for c in range(col_count): self.grid_layout.setColumnStretch(c,1)
        sd = os.path.dirname(os.path.abspath(__file__))

        for idx, game in enumerate(filtered):
            card = QFrame(); card.setFixedHeight(290)
            card.setStyleSheet("QFrame{background:rgba(14,21,36,0.92);border:1.5px solid rgba(0,240,255,0.25);border-radius:18px;}QFrame:hover{border:1.5px solid #00f0ff;background:rgba(20,32,56,0.96);}")
            shadow = QGraphicsDropShadowEffect(card)
            shadow.setBlurRadius(20); shadow.setColor(QColor(0,240,255,75)); shadow.setOffset(0,0)
            card.setGraphicsEffect(shadow)
            cl = QVBoxLayout(card); cl.setContentsMargins(12,12,12,12); cl.setSpacing(10)

            cover = QLabel(); cover.setFixedHeight(158); cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cover.setStyleSheet("background:linear-gradient(135deg,#0d1527 0%,#1e293b 100%);border-radius:12px;")
            url = game.get('cover_path','')
            pix = ImageCache.get_cached(url,300,158)
            if pix:
                cover.setPixmap(pix)
            else:
                fl = os.path.join(sd,"assets","clutch_logo_full.png")
                if not os.path.exists(fl): fl = os.path.join(os.getcwd(),"client","assets","clutch_logo_full.png")
                if os.path.exists(fl):
                    cover.setPixmap(QPixmap(fl).scaled(240,130,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
                else:
                    cover.setText(f"🎮\n{game.get('name')}"); cover.setFont(QFont("Segoe UI",12,QFont.Weight.Bold))
                    cover.setStyleSheet("color:#00f0ff;background:rgba(0,240,255,0.1);border-radius:12px;")
                if url and (url.startswith("http://") or url.startswith("https://")):
                    self.pixmap_labels.setdefault(url,[]).append(cover)
                    self.image_downloader.fetch_image(url,300,158)
            cl.addWidget(cover)

            ir = QHBoxLayout()
            nm = QLabel(game.get('name','Unknown Game')); nm.setFont(QFont("Segoe UI",11,QFont.Weight.Bold))
            nm.setStyleSheet("color:#ffffff;"); nm.setWordWrap(True); ir.addWidget(nm,stretch=1)
            cp = QLabel(game.get('category','FPS')); cp.setFont(QFont("Segoe UI",8,QFont.Weight.Bold))
            cp.setStyleSheet("color:#38bdf8;background:rgba(56,189,248,0.15);border-radius:6px;padding:3px 8px;"); ir.addWidget(cp)
            cl.addLayout(ir)

            pb = QPushButton("▶ ISHGA TUSHIRISH"); pb.setFont(QFont("Segoe UI",10,QFont.Weight.Bold))
            pb.setStyleSheet("""QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #00f0ff,stop:1 #10b981);color:#030712;border:none;border-radius:10px;padding:9px;font-weight:bold;letter-spacing:1px;}
                QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #10b981,stop:1 #00f0ff);color:#fff;border:1px solid #00f0ff;}""")
            pb.clicked.connect(lambda _,g=game: self._launch_game(g)); cl.addWidget(pb)
            self.grid_layout.addWidget(card, idx//col_count, idx%col_count)

    def _launch_game(self, game):
        self.status_msg.setText(f"⏳ {game.get('name','Game')} tekshirilmoqda...")
        self.status_msg.setStyleSheet("color:#00f0ff;background:rgba(0,240,255,0.15);border:1px solid rgba(0,240,255,0.3);border-radius:8px;padding:8px 14px;")
        self.game_launched_signal.emit(game)

    def show_launch_error(self, msg="O'yin fayli topilmadi"):
        self.status_msg.setText(f"❌ {msg}")
        self.status_msg.setStyleSheet("color:#ef4444;background:rgba(239,68,68,0.18);border:1px solid rgba(239,68,68,0.4);border-radius:8px;padding:8px 14px;font-weight:bold;")

    def show_launch_success(self, name):
        self.status_msg.setText(f"🚀 {name} ishga tushirildi!")
        self.status_msg.setStyleSheet("color:#10b981;background:rgba(16,185,129,0.18);border:1px solid rgba(16,185,129,0.4);border-radius:8px;padding:8px 14px;font-weight:bold;")


# ──────────────────────────────────────────────────────────────────────────────
#  BAR MENU (float Tool dialog)
# ──────────────────────────────────────────────────────────────────────────────
class BarMenuWindow(QWidget):
    closed_signal = pyqtSignal()

    def __init__(self, pc_name="PC-01", server_url="http://localhost:8000"):
        super().__init__(); self.pc_name=pc_name; self.server_url=server_url
        self.cart={}; self.products=[]; self.categories=[]; self.current_category_id=None
        self._build_ui()

    def hideEvent(self, e): self.closed_signal.emit(); super().hideEvent(e)

    def _build_ui(self):
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.FramelessWindowHint|Qt.WindowType.Tool)
        self.setFixedSize(850,560)
        sg = QApplication.primaryScreen().geometry()
        self.move((sg.width()-850)//2,(sg.height()-560)//2)
        self.setStyleSheet("QWidget{background-color:#090d16;color:#e2e8f0;font-family:'Segoe UI','Inter',sans-serif;}QScrollArea{border:none;background:transparent;}QScrollBar:vertical{border:none;background:#0f172a;width:6px;border-radius:3px;}QScrollBar::handle:vertical{background:#334155;border-radius:3px;}")

        ml = QVBoxLayout(self); ml.setContentsMargins(0,0,0,0)
        con = QFrame(); con.setStyleSheet("QFrame{background:rgba(15,23,42,0.98);border:2px solid rgba(0,240,255,0.4);border-radius:22px;}")
        cs = QGraphicsDropShadowEffect(con); cs.setBlurRadius(30); cs.setColor(QColor(0,240,255,120)); cs.setOffset(0,0)
        con.setGraphicsEffect(cs); cl = QVBoxLayout(con); cl.setContentsMargins(20,16,20,20)

        hdr = QHBoxLayout()
        ht = QLabel("🍸 CLUTCH ZONE BAR & REFRESHMENTS"); ht.setFont(QFont("Segoe UI",16,QFont.Weight.Bold)); ht.setStyleSheet("color:#00f0ff;letter-spacing:1px;")
        xb = QPushButton("✕"); xb.setFixedSize(32,32); xb.setFont(QFont("Segoe UI",14,QFont.Weight.Bold))
        xb.setStyleSheet("QPushButton{background:rgba(239,68,68,0.2);color:#ef4444;border:1px solid rgba(239,68,68,0.4);border-radius:16px;}QPushButton:hover{background:rgba(239,68,68,0.4);color:#fff;}")
        xb.clicked.connect(self.hide); hdr.addWidget(ht); hdr.addStretch(); hdr.addWidget(xb); cl.addLayout(hdr)

        body = QHBoxLayout(); body.setContentsMargins(0,10,0,0)
        cat_v = QVBoxLayout()
        self.cat_widget = QWidget(); self.cat_layout = QHBoxLayout(self.cat_widget)
        self.cat_layout.setContentsMargins(0,0,0,0); self.cat_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        cat_v.addWidget(self.cat_widget)
        self.product_scroll = QScrollArea(); self.product_scroll.setWidgetResizable(True)
        self.product_grid_widget = QWidget(); self.product_grid_layout = QGridLayout(self.product_grid_widget)
        self.product_grid_layout.setSpacing(12); self.product_grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
        self.product_scroll.setWidget(self.product_grid_widget); cat_v.addWidget(self.product_scroll)
        body.addLayout(cat_v, stretch=2)

        cf = QFrame(); cf.setFixedWidth(290); cf.setStyleSheet("QFrame{background:rgba(10,15,29,0.9);border:1px solid rgba(255,255,255,0.08);border-radius:16px;}")
        cfl = QVBoxLayout(cf); cfl.setContentsMargins(14,14,14,14)
        ct = QLabel("🛒 BUYURTMA SAVATI"); ct.setFont(QFont("Segoe UI",12,QFont.Weight.Bold)); ct.setStyleSheet("color:#c084fc;"); cfl.addWidget(ct)
        self.cart_scroll = QScrollArea(); self.cart_scroll.setWidgetResizable(True)
        self.cart_container = QWidget(); self.cart_items_layout = QVBoxLayout(self.cart_container)
        self.cart_items_layout.setContentsMargins(0,0,0,0); self.cart_items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.cart_scroll.setWidget(self.cart_container); cfl.addWidget(self.cart_scroll)
        self.status_banner = QLabel(""); self.status_banner.setWordWrap(True)
        self.status_banner.setFont(QFont("Segoe UI",9,QFont.Weight.Bold))
        self.status_banner.setStyleSheet("color:#f59e0b;background:rgba(245,158,11,0.15);border:1px solid rgba(245,158,11,0.3);border-radius:8px;padding:6px;")
        self.status_banner.setAlignment(Qt.AlignmentFlag.AlignCenter); self.status_banner.hide(); cfl.addWidget(self.status_banner)
        self.total_label = QLabel("Jami: 0 UZS"); self.total_label.setFont(QFont("Segoe UI",14,QFont.Weight.Bold))
        self.total_label.setStyleSheet("color:#10b981;"); self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight); cfl.addWidget(self.total_label)
        self.send_order_btn = QPushButton("🛍️ BUYURTMA YUBORISH"); self.send_order_btn.setFont(QFont("Segoe UI",11,QFont.Weight.Bold))
        self.send_order_btn.setStyleSheet("QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #00f0ff,stop:1 #0284c7);color:#030712;border:none;border-radius:12px;padding:12px;}QPushButton:hover{background:#00f0ff;}")
        self.send_order_btn.clicked.connect(self._submit_order); cfl.addWidget(self.send_order_btn)
        body.addWidget(cf, stretch=1); cl.addLayout(body); ml.addWidget(con)

    def load_data(self):
        try:
            rc = requests.get(f"{self.server_url}/api/categories/",timeout=4)
            rp = requests.get(f"{self.server_url}/api/products/",timeout=4)
            if rc.status_code==200: self.categories=rc.json()
            if rp.status_code==200: self.products=rp.json()
            self._render_categories(); self._render_products()
        except Exception as e: print(f"[BarMenu] {e}")

    def _render_categories(self):
        for i in reversed(range(self.cat_layout.count())):
            w=self.cat_layout.itemAt(i).widget()
            if w: w.setParent(None)
        ab=QPushButton("Barchasi"); ab.setFont(QFont("Segoe UI",9,QFont.Weight.Bold))
        ab.setStyleSheet("background:rgba(0,240,255,0.2);color:#00f0ff;border:1px solid #00f0ff;border-radius:10px;padding:6px 12px;")
        ab.clicked.connect(lambda: self._set_category(None)); self.cat_layout.addWidget(ab)
        for cat in self.categories:
            btn=QPushButton(f"{cat.get('icon','🍿')} {cat['name']}"); btn.setFont(QFont("Segoe UI",9,QFont.Weight.Bold))
            btn.setStyleSheet("background:rgba(30,41,59,0.6);color:#94a3b8;border:1px solid rgba(255,255,255,0.1);border-radius:10px;padding:6px 12px;")
            cid=cat['id']; btn.clicked.connect(lambda _,c=cid: self._set_category(c)); self.cat_layout.addWidget(btn)

    def _set_category(self,cat_id): self.current_category_id=cat_id; self._render_products()

    def _render_products(self):
        for i in reversed(range(self.product_grid_layout.count())):
            w=self.product_grid_layout.itemAt(i).widget()
            if w: w.setParent(None)
        filtered=[p for p in self.products if self.current_category_id is None or p.get('category')==self.current_category_id]
        for idx,p in enumerate(filtered):
            card=QFrame(); card.setFixedSize(240,130)
            card.setStyleSheet("QFrame{background:rgba(18,27,46,0.85);border:1px solid rgba(255,255,255,0.08);border-radius:14px;}")
            c=QVBoxLayout(card); c.setContentsMargins(12,10,12,10)
            n=QLabel(p['name']); n.setFont(QFont("Segoe UI",10,QFont.Weight.Bold)); n.setStyleSheet("color:#fff;"); n.setWordWrap(True); c.addWidget(n)
            info=QLabel(f"{float(p['price']):,.0f} UZS | Stock: {p['stock']}"); info.setFont(QFont("Consolas",9)); info.setStyleSheet("color:#38bdf8;"); c.addWidget(info)
            ab=QPushButton("➕ Savatga Qo'shish"); ab.setFont(QFont("Segoe UI",9,QFont.Weight.Bold)); ab.setEnabled(p['stock']>0)
            ab.setStyleSheet("QPushButton{background:rgba(16,185,129,0.2);color:#10b981;border:1px solid rgba(16,185,129,0.4);border-radius:8px;padding:5px;}QPushButton:hover{background:rgba(16,185,129,0.4);color:#fff;}QPushButton:disabled{background:rgba(100,116,139,0.2);color:#64748b;border:none;}")
            ab.clicked.connect(lambda _,prod=p: self._add_to_cart(prod)); c.addWidget(ab)
            self.product_grid_layout.addWidget(card,idx//2,idx%2)

    def _add_to_cart(self,prod):
        pid=prod['id']
        if pid in self.cart:
            if self.cart[pid]['quantity']<prod['stock']: self.cart[pid]['quantity']+=1
        else:
            self.cart[pid]={'id':pid,'name':prod['name'],'price':float(prod['price']),'quantity':1}
        self._render_cart()

    def _render_cart(self):
        for i in reversed(range(self.cart_items_layout.count())):
            w=self.cart_items_layout.itemAt(i).widget()
            if w: w.setParent(None)
        total=0
        for pid,item in self.cart.items():
            sub=item['price']*item['quantity']; total+=sub
            iw=QWidget(); il=QHBoxLayout(iw); il.setContentsMargins(0,4,0,4)
            lbl=QLabel(f"{item['name']}\n{sub:,.0f} UZS"); lbl.setFont(QFont("Segoe UI",9)); lbl.setStyleSheet("color:#e2e8f0;"); il.addWidget(lbl,stretch=2)
            bm=QPushButton("-"); bm.setFixedSize(22,22); bm.setStyleSheet("background:#1e293b;color:#fff;border-radius:4px;")
            bm.clicked.connect(lambda _,p=pid: self._update_qty(p,-1)); il.addWidget(bm)
            ql=QLabel(str(item['quantity'])); ql.setFont(QFont("Consolas",10,QFont.Weight.Bold)); ql.setStyleSheet("color:#00f0ff;"); il.addWidget(ql)
            bp=QPushButton("+"); bp.setFixedSize(22,22); bp.setStyleSheet("background:#1e293b;color:#fff;border-radius:4px;")
            bp.clicked.connect(lambda _,p=pid: self._update_qty(p,1)); il.addWidget(bp)
            self.cart_items_layout.addWidget(iw)
        self.total_label.setText(f"Jami: {total:,.0f} UZS")

    def _update_qty(self,pid,change):
        if pid in self.cart:
            self.cart[pid]['quantity']+=change
            if self.cart[pid]['quantity']<=0: del self.cart[pid]
            self._render_cart()

    def _submit_order(self):
        if not self.cart: return
        payload={"pc_name":self.pc_name,"items":[{"product_id":pid,"quantity":v['quantity']} for pid,v in self.cart.items()]}
        try:
            res=requests.post(f"{self.server_url}/api/orders/",json=payload,timeout=5)
            if res.status_code==201:
                self.cart={}; self._render_cart()
                self._banner("⏳ Buyurtmangiz yuborildi! Admin tasdiqlashini kuting.","#f59e0b")
            else:
                self._banner(f"❌ {res.json().get('error','Xatolik!')}","#ef4444")
        except: self._banner("❌ Serverga ulanib bo'lmadi!","#ef4444")

    def _banner(self,text,color):
        self.status_banner.setText(text)
        self.status_banner.setStyleSheet(f"color:{color};background:rgba(100,100,100,0.15);border:1px solid rgba(100,100,100,0.3);border-radius:8px;padding:6px;")
        self.status_banner.show()

    def update_order_status(self,data):
        s=data.get('status'); m={
            'PENDING': (f"⏳ Buyurtma #{data.get('id')} kutilmoqda...","#f59e0b"),
            'APPROVED':(f"👍 Buyurtma #{data.get('id')} tasdiqlandi!","#00f0ff"),
            'DELIVERED':(f"🚚 Buyurtma #{data.get('id')} topshirildi!","#10b981"),
            'CANCELLED':(f"❌ Buyurtma #{data.get('id')} bekor qilindi.","#ef4444"),
        }
        if s in m: self._banner(*m[s])


# ──────────────────────────────────────────────────────────────────────────────
#  TIMER OVERLAY (top-right Tool widget)
# ──────────────────────────────────────────────────────────────────────────────
class TimerOverlayWidget(QWidget):
    def __init__(self,pc_name="PC-01",on_bar_click=None):
        super().__init__(); self.pc_name=pc_name; self.on_bar_click=on_bar_click; self._build_ui()

    def _build_ui(self):
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.FramelessWindowHint|Qt.WindowType.SubWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground); self.setFixedSize(350,75)
        sg=QApplication.primaryScreen().geometry(); self.move(sg.width()-370,20)
        lo=QHBoxLayout(self); lo.setContentsMargins(0,0,0,0)
        con=QFrame(); con.setStyleSheet("QFrame{background:rgba(10,14,23,0.92);border:1px solid rgba(0,240,255,0.4);border-radius:16px;}")
        cl=QHBoxLayout(con); cl.setContentsMargins(14,8,14,8)
        tb=QVBoxLayout(); tb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label=QLabel("00:00:00"); self.timer_label.setFont(QFont("Consolas",18,QFont.Weight.Bold))
        self.timer_label.setStyleSheet("color:#00f0ff;"); self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter); tb.addWidget(self.timer_label)
        sub=QLabel(f"{self.pc_name} - ACTIVE SESSION"); sub.setFont(QFont("Segoe UI",8,QFont.Weight.Bold))
        sub.setStyleSheet("color:#10b981;letter-spacing:1px;"); sub.setAlignment(Qt.AlignmentFlag.AlignCenter); tb.addWidget(sub); cl.addLayout(tb)
        bb=QPushButton("🍸 BAR"); bb.setFont(QFont("Segoe UI",10,QFont.Weight.Bold)); bb.setFixedSize(85,45)
        bb.setStyleSheet("QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #a855f7,stop:0.5 #d946ef,stop:1 #ec4899);color:#fff;border:1px solid rgba(255,255,255,0.4);border-radius:12px;font-weight:bold;}QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #c084fc,stop:1 #f472b6);border:1px solid #00f0ff;}")
        if self.on_bar_click: bb.clicked.connect(self.on_bar_click)
        cl.addWidget(bb); lo.addWidget(con)

    def update_timer(self,seconds):
        if seconds<=0: self.timer_label.setText("00:00:00"); return
        self.timer_label.setText(f"{seconds//3600:02d}:{(seconds%3600)//60:02d}:{seconds%60:02d}")


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN WINDOW  — BITTA OYNA, HECH QACHON hide() QILINMAYDI
# ──────────────────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    """
    Yagona fullscreen oyna:
      stacked  index 0 → LockScreenWidget
      stacked  index 1 → GameLauncherWidget

    Oyna HECH QACHON hide() / close() qilinmaydi.
    Faqat stacked_widget sahifasi almashadi.
    """
    PAGE_LOCK     = 0
    PAGE_LAUNCHER = 1

    def __init__(self, pc_name="PC-01", server_url="http://localhost:8000",
                 fallback_games=None, on_bar_click=None):
        super().__init__()
        self.pc_name = pc_name

        # Window flags — bir marta, o'zgartirilmaydi
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        if IS_WINDOWS:
            flags |= Qt.WindowType.WindowDoesNotAcceptFocus
        self.setWindowFlags(flags)
        self.setWindowTitle("Clutch Zone Client Locker")

        # Pages
        self.lock_page     = LockScreenWidget(pc_name=pc_name)
        self.launcher_page = GameLauncherWidget(
            pc_name=pc_name, server_url=server_url,
            fallback_games=fallback_games or [], on_bar_click=on_bar_click
        )

        # Stacked widget
        self.stacked = QStackedWidget()
        self.stacked.addWidget(self.lock_page)      # index 0
        self.stacked.addWidget(self.launcher_page)  # index 1
        self.stacked.setCurrentIndex(self.PAGE_LOCK)
        self.setCentralWidget(self.stacked)

        # Fullscreen — bir marta
        screen = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.showFullScreen()

    def switch_to_lock(self):
        """LOCKED: LockScreen sahifasiga o'tish."""
        self.stacked.setCurrentIndex(self.PAGE_LOCK)

    def switch_to_launcher(self):
        """ACTIVE: GameLauncher sahifasiga o'tish."""
        self.stacked.setCurrentIndex(self.PAGE_LAUNCHER)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                QTimer.singleShot(80, self._restore_fullscreen)

    def _restore_fullscreen(self):
        screen = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(screen); self.showFullScreen()
        self.raise_(); self.activateWindow()

    def closeEvent(self, event): event.ignore()

    def keyPressEvent(self, event):
        if self.stacked.currentIndex() == self.PAGE_LOCK: event.accept()
        else: super().keyPressEvent(event)

    # Forwarders
    @property
    def game_launched_signal(self): return self.launcher_page.game_launched_signal
    def update_timer(self, s): self.launcher_page.update_timer(s)
    def load_games(self): self.launcher_page.load_games()
    def show_launch_error(self, msg): self.launcher_page.show_launch_error(msg)
    def show_launch_success(self, name): self.launcher_page.show_launch_success(name)


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

        # Bar menu (float)
        self.bar_menu = BarMenuWindow(self.pc_name, self.server_url)

        # Single main window
        self.main_window = MainWindow(
            pc_name=self.pc_name, server_url=self.server_url,
            fallback_games=self.fallback_games, on_bar_click=self._toggle_bar
        )
        self.main_window.game_launched_signal.connect(self._handle_game_launch)

        # Timer overlay (top-right)
        self.overlay = TimerOverlayWidget(pc_name=self.pc_name, on_bar_click=self._toggle_bar)
        self.overlay.hide()

        # Countdown timer
        self.countdown = QTimer()
        self.countdown.timeout.connect(self._tick)
        self.countdown.start(1000)

        # Initial state: LOCKED
        install_keyboard_hook()
        self.main_window.switch_to_lock()

        # Background sync
        threading.Thread(target=self._run_sync, daemon=True).start()

    def _load_config(self, path):
        cfg = {"server_url":"http://localhost:8000","websocket_url":"ws://localhost:8000/ws/pc-status/",
               "pc_name":"PC-01","heartbeat_interval_seconds":5,"fallback_games":[]}
        if os.path.exists(path):
            try:
                with open(path,'r') as f: cfg.update(json.load(f))
            except Exception as e: print(f"[Config] {e}")
        self.server_url=cfg["server_url"]; self.ws_url=cfg["websocket_url"]
        self.pc_name=cfg["pc_name"]; self.heartbeat_interval=cfg["heartbeat_interval_seconds"]
        self.fallback_games=cfg.get("fallback_games",[])

    def _toggle_bar(self):
        if self.bar_menu.isVisible():
            self.bar_menu.hide()
        else:
            self.bar_menu.load_data(); self.bar_menu.show()
            self.bar_menu.raise_(); self.bar_menu.activateWindow()

    def _handle_status(self, data):
        new_status=data.get('status','LOCKED'); seconds=data.get('time_remaining',0)
        self.time_remaining=seconds
        if new_status in ('ACTIVE','WARNING') and seconds>0:
            if self.current_status=='LOCKED': self._unlock()
            self.current_status=new_status
            self.overlay.update_timer(self.time_remaining)
            self.main_window.update_timer(self.time_remaining)
        else:
            if self.current_status!='LOCKED': self._lock()

    def _handle_bar_order(self, data): self.bar_menu.update_order_status(data)

    def _unlock(self):
        """UNLOCK: faqat stacked page 1 ga o'tadi, MainWindow yashirilmaydi."""
        print("[Locker] UNLOCK → GameLauncherWidget (page 1)")
        uninstall_keyboard_hook()
        self.main_window.load_games()
        self.main_window.switch_to_launcher()   # setCurrentIndex(1)
        self.overlay.show()
        self.current_status='ACTIVE'

    def _lock(self):
        """LOCK: faqat stacked page 0 ga o'tadi, MainWindow yashirilmaydi."""
        print("[Locker] LOCK → LockScreenWidget (page 0)")
        self.current_status='LOCKED'; self.time_remaining=0
        self.bar_menu.hide(); self.overlay.hide()
        self.main_window.switch_to_lock()       # setCurrentIndex(0)
        install_keyboard_hook()
        self._kill_games()

    def _kill_games(self):
        for proc in self.launched_processes:
            try: proc.terminate(); proc.kill()
            except Exception as e: print(f"[Cleanup] {e}")
        self.launched_processes.clear()
        if IS_WINDOWS:
            for exe in ["cs2.exe","VALORANT.exe","TslGame.exe","GTA5.exe","Cyberpunk2077.exe",
                        "RDR2.exe","FC24.exe","NFSUnbound.exe","NBA2K24.exe","dota2.exe","LeagueClient.exe"]:
                try: subprocess.run(["taskkill","/F","/IM",exe],capture_output=True)
                except: pass

    def _handle_game_launch(self, game):
        exe=game.get('executable_path'); cwd_=game.get('working_directory'); name=game.get('name','Game')
        print(f"[Launcher] '{name}' → {exe}")
        if exe and os.path.exists(exe):
            try:
                cwd=None
                if cwd_ and os.path.exists(cwd_): cwd=cwd_
                elif exe and os.path.dirname(exe): cwd=os.path.dirname(exe)
                proc=subprocess.Popen([exe],cwd=cwd); self.launched_processes.append(proc)
                print(f"[Launcher] PID: {proc.pid}"); self.main_window.show_launch_success(name)
            except Exception as e:
                print(f"[Launcher] Error: {e}"); self.main_window.show_launch_error(f"Xatolik: {e}")
        else:
            print(f"[Launcher] Not found: {exe}")
            self.main_window.show_launch_error("O'yin fayli topilmadi, iltimos admonga murojaat qiling")

    def _tick(self):
        if self.current_status in ('ACTIVE','WARNING'):
            if self.time_remaining>0:
                self.time_remaining-=1
                self.overlay.update_timer(self.time_remaining)
                self.main_window.update_timer(self.time_remaining)
            else: self._lock()

    def _run_sync(self):
        threading.Thread(target=self._run_ws,daemon=True).start()
        while True:
            try:
                r=requests.post(f"{self.server_url}/api/computers/heartbeat/",json={"pc_name":self.pc_name},timeout=4)
                if r.status_code==200: self.signals.status_updated.emit(r.json())
            except Exception as e: print(f"[Heartbeat] {e}")
            time.sleep(self.heartbeat_interval)

    def _run_ws(self):
        def on_message(ws,msg):
            try:
                d=json.loads(msg)
                if d.get('type')=='BAR_ORDER_UPDATE':
                    o=d.get('order',{}); obj=o.get('order',o)
                    if obj.get('computer_name')==self.pc_name: self.signals.bar_order_updated.emit(obj)
                else:
                    pc=d.get('pc',{})
                    if pc.get('name')==self.pc_name: self.signals.status_updated.emit(pc)
                    elif d.get('action')=='EMERGENCY_LOCK_ALL': self.signals.status_updated.emit({'status':'LOCKED','time_remaining':0})
            except Exception as e: print(f"[WS] {e}")
        def on_open(ws): print("[WS] Connected")
        def on_error(ws,e): print(f"[WS] Error: {e}")
        while True:
            try:
                ws=websocket.WebSocketApp(self.ws_url,on_message=on_message,on_open=on_open,on_error=on_error)
                ws.run_forever()
            except Exception as e: print(f"[WS] Failed: {e}")
            time.sleep(3)


# ──────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────
def main():
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    _locker = ClientLockerApp("config.json")
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
