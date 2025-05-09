
# python my_voice_assistant\desktop_pet.py启动
# conda activate  E:\python_virtual_environments\python3.10.6test

# python desktop_pet.py启动

import sys, os
import ctypes
from PyQt5.QtCore import Qt, QUrl, QObject, pyqtSlot
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
from PyQt5.QtWebChannel import QWebChannel

# Win32 常量
GWL_EXSTYLE   = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

class TransparentWebView(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Web 内容透明
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.page().setBackgroundColor(Qt.transparent)
        # 允许点击穿透
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # 本地缓存
        self.settings().setAttribute(QWebEngineSettings.LocalStorageEnabled, True)

class Bridge(QObject):
    def __init__(self, view, main_window):
        super().__init__()
        self._view = view
        self._win = main_window

    @pyqtSlot(bool)
    def setMouseTransparent(self, transparent):
        # 同时设置主窗口和 WebView 点击穿透
        self._win.setAttribute(Qt.WA_TransparentForMouseEvents, transparent)
        self._view.setAttribute(Qt.WA_TransparentForMouseEvents, transparent)

    @pyqtSlot(int, int)
    def moveWindowBy(self, dx, dy):
        geo = self._win.geometry()
        self._win.setGeometry(
            geo.x() + dx,
            geo.y() + dy,
            geo.width(),
            geo.height()
        )

class DesktopPet(QMainWindow):
    def __init__(self):
        super().__init__()
        # 无边框、透明、置顶、任务栏不显示
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 初始让窗口接收鼠标穿透
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        # Win32 点击穿透
        if sys.platform == 'win32':
            hwnd = int(self.winId())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            )

        # 创建 WebView
        self.view = TransparentWebView(self)
        web_settings = self.view.settings()
        web_settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        web_settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)

        current_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(current_dir, 'frontend', 'index.html')
        url = QUrl.fromLocalFile(html_path) if os.path.exists(html_path) else QUrl('http://localhost:8000/index.html')
        self.view.load(url)

        self.setCentralWidget(self.view)

        # WebChannel
        channel = QWebChannel(self.view.page())
        self.bridge = Bridge(self.view, self)
        channel.registerObject('bridge', self.bridge)
        self.view.page().setWebChannel(channel)

        # 注入 JS 切换穿透
        self.view.loadFinished.connect(self.onLoadFinished)

    def onLoadFinished(self, success):
        if not success:
            print('页面加载失败!')
            return
        # 注入运行时检测脚本
        js = '''(function() {
            // 复用前端 isPointInModel 函数
            document.addEventListener('pointermove', e => {
                if (typeof isPointInModel !== 'function') return;
                const over = isPointInModel(e.clientX, e.clientY);
                bridge.setMouseTransparent(!over);
            });
        })();'''
        self.view.page().runJavaScript(js)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.showFullScreen()
    sys.exit(app.exec_())