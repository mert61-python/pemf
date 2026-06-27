import os
import sys
from pathlib import Path
import http.server
import socketserver
import threading
import logging

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

class DemaSimulatorWindow(QMainWindow):
    """
    Hafif simülatör başlatıcı.

    Eski sürüm QWebEngineView ile Chromium'u uygulamanın içine gömüyordu.
    Bu, installer'a Qt WebEngine'i eklediği için yüzlerce MB ek yük getiriyordu.
    Production paketinde simülatör varsayılan tarayıcıda açılır.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dema Terapi Simülatörü")
        self.resize(520, 240)

        self.index_file = self._resolve_index_file()
        self.server_url = None
        self.httpd = None

        cen_widget = QWidget()
        self.setCentralWidget(cen_widget)
        layout = QVBoxLayout(cen_widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Dema Terapi Simülatörü")
        title.setStyleSheet("font-size: 16pt; font-weight: 700;")
        layout.addWidget(title)

        if self.index_file and self.index_file.exists():
            info = QLabel("Simülatör varsayılan tarayıcıda açılacak.")
            open_button = QPushButton("Simülatörü Aç")
            open_button.clicked.connect(self.open_in_browser)
            layout.addWidget(info)
            layout.addWidget(open_button)
        else:
            info = QLabel(
                "Simülatör statik dosyaları bulunamadı.\n"
                "dema-terapi-simülatörü/dist klasörünü build edip pakete ekleyin."
            )
            info.setWordWrap(True)
            layout.addWidget(info)

    def _resolve_index_file(self):
        candidates = []
        if getattr(sys, "frozen", False):
            base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            candidates.extend([
                base / "dema-terapi-simülatörü" / "dist" / "index.html",
                Path(sys.executable).parent / "_internal" / "dema-terapi-simülatörü" / "dist" / "index.html",
            ])

        project_base = Path(__file__).resolve().parent.parent
        candidates.append(project_base / "dema-terapi-simülatörü" / "dist" / "index.html")

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[-1]

    def _start_http_server(self):
        if self.server_url:
            return self.server_url

        if not self.index_file or not self.index_file.exists():
            return None

        dist_dir = self.index_file.parent

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=os.fspath(dist_dir), **kwargs)

        try:
            self.httpd = socketserver.TCPServer(("127.0.0.1", 0), QuietHandler)
            port = self.httpd.server_address[1]
            thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            thread.start()
            self.server_url = f"http://127.0.0.1:{port}/"
            return self.server_url
        except Exception as e:
            logging.getLogger(__name__).error(f"Simulator HTTP Server başlatılamadı: {e}")
            return None

    def showEvent(self, event):
        super().showEvent(event)
        if self.index_file and self.index_file.exists():
            self.open_in_browser()

    def open_in_browser(self):
        url = self._start_http_server()
        if url:
            QDesktopServices.openUrl(QUrl(url))
        elif self.index_file and self.index_file.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.fspath(self.index_file)))

    def closeEvent(self, event):
        event.ignore()
        self.hide()
