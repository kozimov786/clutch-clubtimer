import sys
import os
import ctypes

if sys.platform == 'win32':
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = "1"

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QGuiApplication

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError as e:
    print(f"[TEST] WebEngine import failed: {e}")
    HAS_WEBENGINE = False


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


if HAS_WEBENGINE:
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

app = QApplication(sys.argv)

w, h = get_screen_resolution()
print(f"[TEST] screen resolution: {w}x{h}, HAS_WEBENGINE={HAS_WEBENGINE}")

win = QMainWindow()
win.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
win.setStyleSheet("background-color: red;")

if HAS_WEBENGINE:
    browser = QWebEngineView(win)
    html = """
    <html><body style="background:#00ff00; margin:0;">
    <h1 style="color:black; font-size:60px;">WEBENGINE TEST OK 999</h1>
    </body></html>
    """
    browser.setHtml(html)
    win.setCentralWidget(browser)
    print("[TEST] QWebEngineView created and setHtml called")
else:
    from PyQt6.QtWidgets import QLabel
    label = QLabel("NO WEBENGINE AVAILABLE")
    label.setStyleSheet("color: white; font-size: 48px;")
    win.setCentralWidget(label)

win.setGeometry(0, 0, w, h)
win.setFixedSize(w, h)
win.showFullScreen()
win.raise_()
win.activateWindow()

print("[TEST] window shown")

sys.exit(app.exec())
