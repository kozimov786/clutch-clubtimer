import sys
import ctypes

if sys.platform == 'win32':
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass

from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication


def get_screen_resolution():
    if sys.platform == 'win32':
        try:
            w = ctypes.windll.user32.GetSystemMetrics(0)
            h = ctypes.windll.user32.GetSystemMetrics(1)
            if w > 0 and h > 0:
                return w, h
        except Exception:
            pass
    screen = QGuiApplication.primaryScreen().geometry()
    return screen.width(), screen.height()


app = QApplication(sys.argv)

w, h = get_screen_resolution()
print(f"[TEST] screen resolution: {w}x{h}")

win = QMainWindow()
win.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
win.setStyleSheet("background-color: red;")

label = QLabel("SINOV MATNI 12345 KO'RINYAPTIMI?")
label.setStyleSheet("color: white; font-size: 48px; font-weight: bold; background-color: red;")
label.setAlignment(Qt.AlignmentFlag.AlignCenter)
win.setCentralWidget(label)

win.setGeometry(0, 0, w, h)
win.setFixedSize(w, h)
win.showFullScreen()
win.raise_()
win.activateWindow()

print("[TEST] window shown, close with Ctrl+Alt+Shift+U-style: just Alt+F4 or close terminal")

sys.exit(app.exec())
