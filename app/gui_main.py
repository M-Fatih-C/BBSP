# app/gui_main.py
import os, sys
from typing import Any, Dict, List

from PySide6.QtGui import QIcon, QAction, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem,
    QMessageBox, QLabel, QStatusBar
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

# Support running in three contexts:
# - as a package module (python -m app.gui_main)
# - as a script (python app/gui_main.py)
# - as a PyInstaller-frozen exe (module may be under 'app.*')
try:
    from .system_info import gather_all, human_bytes, get_gpu_info_detailed
    from .exporters import save_json, save_html
except Exception:
    try:
        from app.system_info import gather_all, human_bytes, get_gpu_info_detailed
        from app.exporters import save_json, save_html
    except Exception:
        from system_info import gather_all, human_bytes, get_gpu_info_detailed
        from exporters import save_json, save_html

APP_NAME = "MiniCPUZ"
APP_VERSION = "1.0.0"

# Ensure compatibility if bundled as a frozen executable (e.g., PyInstaller)
if getattr(sys, "frozen", False):
    try:
        import multiprocessing as _mp
        _mp.freeze_support()
    except Exception:
        pass

# Single-instance guard (prevents multiple concurrent windows/processes)
UNIQUE_KEY = "MiniCPUZ_single_instance_v1"

def acquire_single_instance():
    # Try connecting to an existing server (another instance)
    sock = QLocalSocket()
    sock.connectToServer(UNIQUE_KEY)
    if sock.waitForConnected(100):
        # Another instance is already running
        sock.abort()
        return None

    # No instance: create and listen, becoming the owner of the lock
    server = QLocalServer()
    try:
        QLocalServer.removeServer(UNIQUE_KEY)  # cleanup stale lock if any
    except Exception:
        pass
    if not server.listen(UNIQUE_KEY):
        return None
    return server

def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    # PyInstaller onedir sets sys.frozen but not _MEIPASS
    if not base and getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    if base:
        candidates = [
            os.path.join(base, "app", "resources", rel),
            os.path.join(base, "resources", rel),
            os.path.join(base, rel),
        ]
    else:
        moddir = os.path.dirname(__file__)
        candidates = [
            os.path.join(moddir, "resources", rel),
            os.path.join(moddir, rel),
        ]
    for p in candidates:
        if os.path.exists(p):
            return p
    # Fallback to first candidate
    return candidates[0]

def dict_to_table(table: QTableWidget, d: Dict[str, Any]):
    rows = []
    for k, v in d.items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                rows.append((f"{k}.{k2}", v2))
        elif isinstance(v, list):
            rows.append((k, f"[{len(v)} öğe]"))
        else:
            rows.append((k, v))
    table.setRowCount(len(rows))
    table.setColumnCount(2)
    table.setHorizontalHeaderLabels(["Alan", "Değer"])
    for i, (k, v) in enumerate(rows):
        table.setItem(i, 0, QTableWidgetItem(str(k)))
        table.setItem(i, 1, QTableWidgetItem(str(v)))
    table.resizeColumnsToContents()

def list_of_dicts_to_table(table: QTableWidget, arr: List[Dict[str, Any]]):
    cols = set()
    for item in arr:
        cols.update(item.keys())
    cols = sorted(list(cols))
    table.setRowCount(len(arr))
    table.setColumnCount(len(cols))
    table.setHorizontalHeaderLabels(cols)
    for r, item in enumerate(arr):
        for c, colname in enumerate(cols):
            val = item.get(colname, "")
            if isinstance(val, int) and ("memory" in colname or "bytes" in colname):
                val = human_bytes(val)
            table.setItem(r, c, QTableWidgetItem(str(val)))
    table.resizeColumnsToContents()

class GatherWorker(QObject):
    done = Signal(dict)
    def __init__(self, spd_path=None, dimms_path=None):
        super().__init__()
        self.spd_path = spd_path
        self.dimms_path = dimms_path
    def run(self):
        data = gather_all(self.spd_path, self.dimms_path)
        self.done.emit(data)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(resource_path("logo.png")))
        self.resize(1200, 760)

        # Menubar
        menubar = self.menuBar()
        file_menu = menubar.addMenu("Dosya")
        self.act_refresh = QAction("Yenile", self)
        self.act_export_json = QAction("JSON Kaydet", self)
        self.act_export_html = QAction("HTML Kaydet", self)
        file_menu.addAction(self.act_refresh)
        file_menu.addSeparator()
        file_menu.addAction(self.act_export_json)
        file_menu.addAction(self.act_export_html)
        help_menu = menubar.addMenu("Yardım")
        self.act_about = QAction("Hakkında", self)
        help_menu.addAction(self.act_about)

        # Header with logo & title
        header = QWidget()
        h = QHBoxLayout(header)
        logo = QLabel()
        pm = QPixmap(resource_path("logo.png"))
        logo.setPixmap(pm.scaledToHeight(40, Qt.SmoothTransformation))
        title = QLabel(f"<b>{APP_NAME}</b> <span style='color:#9ca3af'>v{APP_VERSION}</span>")
        title.setStyleSheet("font-size:18px; margin-left:8px;")
        h.addWidget(logo)
        h.addWidget(title)
        h.addStretch()

        # Action buttons
        self.btn_refresh = QPushButton("Yenile")
        self.btn_export_json = QPushButton("JSON Kaydet")
        self.btn_export_html = QPushButton("HTML Kaydet")
        h.addWidget(self.btn_refresh)
        h.addWidget(self.btn_export_json)
        h.addWidget(self.btn_export_html)

        # Tabs
        self.tabs = QTabWidget()
        self.tbl_cpu = QTableWidget()
        # RAM panel: summary + modules + SPD
        self.ram_panel = QWidget()
        _ram_layout = QVBoxLayout(self.ram_panel)
        self.tbl_ram_summary = QTableWidget()
        self.tbl_ram_modules = QTableWidget()
        self.tbl_ram_spd = QTableWidget()
        _ram_layout.addWidget(self.tbl_ram_summary)
        _ram_layout.addWidget(self.tbl_ram_modules)
        _ram_layout.addWidget(self.tbl_ram_spd)
        self.tbl_gpu = QTableWidget()
        self.tbl_mb = QTableWidget()
        self.tbl_os = QTableWidget()
        self.tbl_net = QTableWidget()
        self.tabs.addTab(self.tbl_cpu, "CPU")
        self.tabs.addTab(self.ram_panel, "RAM")
        self.tabs.addTab(self.tbl_gpu, "GPU")
        self.tabs.addTab(self.tbl_mb, "MB/BIOS")
        self.tabs.addTab(self.tbl_os, "OS")
        self.tabs.addTab(self.tbl_net, "Ağ")

        # Status bar
        self.setStatusBar(QStatusBar(self))

        # Central layout
        wrapper = QWidget()
        v = QVBoxLayout(wrapper)
        v.addWidget(header)
        v.addWidget(self.tabs)
        self.setCentralWidget(wrapper)

        # Signals
        self.act_refresh.triggered.connect(self.refresh)
        self.act_export_json.triggered.connect(self.export_json)
        self.act_export_html.triggered.connect(self.export_html)
        self.act_about.triggered.connect(self.show_about)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_export_json.clicked.connect(self.export_json)
        self.btn_export_html.clicked.connect(self.export_html)
        # Populate Network tab on selection
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.current_data: Dict[str, Any] = {}
        self.spd_path: str | None = None
        self.decode_dimms_path: str | None = None

        # Stylesheet
        try:
            with open(resource_path("style.qss"), "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except Exception:
            pass

        self.refresh()  # async

        # Auto refresh GPU table every 5s (lightweight)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_gpu_only)
        self.timer.start(5000)

    def _on_tab_changed(self, idx: int):
        try:
            if self.tabs.widget(idx) is self.tbl_net:
                self._fill_network()
        except Exception:
            pass

    def show_about(self):
        QMessageBox.information(self, "Hakkında",
            f"<h3>{APP_NAME}</h3>"
            f"<p>Sistem bilgi aracı (CPU/RAM/GPU/MB/OS).</p>"
            f"<p>Versiyon: {APP_VERSION}</p>"
            f"<p>© 2025</p>")

    def _start_worker(self):
        self.thread = QThread(self)
        self.worker = GatherWorker(self.spd_path, self.decode_dimms_path)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.done.connect(self._on_data)
        self.worker.done.connect(self._after_data)
        self.worker.done.connect(self.thread.quit)
        self.thread.start()

    def refresh(self):
        self.statusBar().showMessage("Veriler toplanıyor…")
        self._start_worker()

    def _on_data(self, data: Dict[str, Any]):
        self.current_data = data
        # CPU
        dict_to_table(self.tbl_cpu, self.current_data.get("cpu", {}))
        # RAM
        ram = self.current_data.get("memory", {})
        ram_summary = {
            "total": human_bytes(ram.get("total", 0)),
            "used": human_bytes(ram.get("used", 0)),
            "available": human_bytes(ram.get("available", 0)),
            "percent": f"{ram.get('percent',0)}%",
            "swap_used/total": f"{human_bytes(ram.get('swap_used',0))} / {human_bytes(ram.get('swap_total',0))} ({ram.get('swap_percent',0)}%)"
        }
        dict_to_table(self.tbl_ram_summary, ram_summary)
        # RAM modules, if present
        try:
            mods = ram.get("modules", []) or []
            list_of_dicts_to_table(self.tbl_ram_modules, mods)
        except Exception:
            pass
        # SPD timings, if present
        try:
            spd = ram.get("spd", []) or []
            list_of_dicts_to_table(self.tbl_ram_spd, spd)
        except Exception:
            pass
        # GPU
        list_of_dicts_to_table(self.tbl_gpu, self.current_data.get("gpus", []))
        # MB/BIOS
        dict_to_table(self.tbl_mb, self.current_data.get("motherboard_bios", {}))
        # OS
        dict_to_table(self.tbl_os, self.current_data.get("os", {}))
        self.statusBar().showMessage("Hazır", 2000)

    def refresh_gpu_only(self):
        if not self.current_data:
            return
        # re-collect only GPU (quick)
        try:
            gpus = get_gpu_info_detailed()
            list_of_dicts_to_table(self.tbl_gpu, gpus)
        except Exception:
            pass

    def export_json(self):
        if not self.current_data:
            QMessageBox.warning(self, "Uyarı", "Önce Yenile.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "JSON Kaydet", "report.json", "JSON (*.json)")
        if not p: return
        try:
            save_json(self.current_data, p)
            QMessageBox.information(self, "Kaydedildi", f"JSON rapor kaydedildi:\n{p}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))

    def export_html(self):
        if not self.current_data:
            QMessageBox.warning(self, "Uyarı", "Önce Yenile.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "HTML Kaydet", "report.html", "HTML (*.html)")
        if not p: return
        try:
            save_html(self.current_data, p)
            QMessageBox.information(self, "Kaydedildi", f"HTML rapor kaydedildi:\n{p}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))

    def _after_data(self, data: Dict[str, Any]):
        # Fill network table once data is available
        self._fill_network()

    def _fill_network(self):
        if not self.current_data:
            return
        list_of_dicts_to_table(self.tbl_net, self.current_data.get("network", []))

def main():
    app = QApplication(sys.argv)

    # Enforce single-instance right after QApplication is created
    single_server = acquire_single_instance()
    if single_server is None:
        # Another instance is running → exit quietly
        sys.exit(0)

    app.setWindowIcon(QIcon(resource_path("logo.png")))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
