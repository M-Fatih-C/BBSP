"""GUI main window for mini-cpuz (PySide6)."""
import sys
from typing import Any, Dict, List

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .exporters import save_html, save_json
from .system_info import _human_bytes


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
                val = _human_bytes(val)
            table.setItem(r, c, QTableWidgetItem(str(val)))
    table.resizeColumnsToContents()


class SettingsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.spd_path_edit = QLineEdit()
        self.decode_dimms_edit = QLineEdit()
        form = QFormLayout()
        form.addRow("SPD JSON Yolu (Libre/OpenHW):", self.spd_path_edit)
        form.addRow("Linux decode-dimms çıktısı:", self.decode_dimms_edit)
        self.setLayout(form)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("mini-cpuz GUI")
        self.resize(1100, 700)

        self.tabs = QTabWidget()
        self.tbl_cpu = QTableWidget()
        self.tbl_ram = QTableWidget()
        self.tbl_gpu = QTableWidget()
        self.tbl_mb = QTableWidget()
        self.tbl_os = QTableWidget()
        self.tbl_net = QTableWidget()

        self.tabs.addTab(self.tbl_cpu, "CPU")
        self.tabs.addTab(self.tbl_ram, "RAM")
        self.tabs.addTab(self.tbl_gpu, "GPU")
        self.tabs.addTab(self.tbl_mb, "MB/BIOS")
        self.tabs.addTab(self.tbl_os, "OS")
        self.tabs.addTab(self.tbl_net, "Ağ")

        self.btn_refresh = QPushButton("Yenile")
        self.btn_export_json = QPushButton("JSON Kaydet")
        self.btn_export_html = QPushButton("HTML Kaydet")
        self.btn_choose_spd = QPushButton("SPD JSON Seç")
        self.btn_choose_dimms = QPushButton("decode-dimms Seç")

        self.settings = SettingsWidget()

        topbar = QHBoxLayout()
        topbar.addWidget(self.btn_refresh)
        topbar.addStretch()
        topbar.addWidget(self.btn_choose_spd)
        topbar.addWidget(self.btn_choose_dimms)
        topbar.addStretch()
        topbar.addWidget(self.btn_export_json)
        topbar.addWidget(self.btn_export_html)

        wrapper = QWidget()
        v = QVBoxLayout(wrapper)
        v.addLayout(topbar)
        v.addWidget(self.tabs)
        self.setCentralWidget(wrapper)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_export_json.clicked.connect(self.export_json)
        self.btn_export_html.clicked.connect(self.export_html)
        self.btn_choose_spd.clicked.connect(self.choose_spd)
        self.btn_choose_dimms.clicked.connect(self.choose_dimms)

        self.current_data: Dict[str, Any] = {}
        self.spd_path: str | None = None
        self.decode_dimms_path: str | None = None

        # Renkli ve okunaklı bir stil uygula
        self.setStyleSheet(
            """
            QMainWindow { background: #0f172a; }
            QLabel { color: #e2e8f0; }
            QPushButton { background: #2563eb; color: #ffffff; border: none; padding: 6px 10px; border-radius: 6px; }
            QPushButton:hover { background: #1d4ed8; }
            QPushButton:disabled { background: #334155; color: #cbd5e1; }
            QTabBar::tab { background: #1e293b; color: #e2e8f0; padding: 8px 12px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
            QTabBar::tab:selected { background: #334155; }
            QTabWidget::pane { border: 1px solid #334155; top: -1px; }
            QTableWidget { background: #0b1220; color: #e2e8f0; gridline-color: #334155; alternate-background-color: #111827; }
            QHeaderView::section { background: #0b1730; color: #93c5fd; padding: 6px; border: 1px solid #334155; }
            QLineEdit { background: #0b1220; color: #e2e8f0; border: 1px solid #334155; padding: 4px 6px; border-radius: 4px; }
            """
        )

        for tbl in (self.tbl_cpu, self.tbl_ram, self.tbl_gpu, self.tbl_mb, self.tbl_os, self.tbl_net):
            try:
                tbl.setAlternatingRowColors(True)
                tbl.verticalHeader().setVisible(False)
            except Exception:
                pass

        self.refresh()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_gpu_only)
        self.timer.start(5000)

    def choose_spd(self):
        p, _ = QFileDialog.getOpenFileName(self, "SPD JSON Seç", "", "JSON (*.json);;Tüm Dosyalar (*)")
        if p:
            self.spd_path = p
            QMessageBox.information(self, "SPD", f"SPD JSON yolu ayarlandı:\n{p}")
            self.refresh()

    def choose_dimms(self):
        p, _ = QFileDialog.getOpenFileName(self, "decode-dimms çıktısı seç", "", "Text (*.txt);;Tüm Dosyalar (*)")
        if p:
            self.decode_dimms_path = p
            QMessageBox.information(self, "decode-dimms", f"Linux decode-dimms metni ayarlandı:\n{p}")
            self.refresh()

    def refresh_gpu_only(self):
        if not self.current_data:
            return
        from .system_info import get_gpu_info_detailed
        gpus = get_gpu_info_detailed()
        list_of_dicts_to_table(self.tbl_gpu, gpus)

    def refresh(self):
        from .system_info import gather_all
        self.current_data = gather_all(self.spd_path, self.decode_dimms_path)

        dict_to_table(self.tbl_cpu, self.current_data.get("cpu", {}))
        ram = self.current_data.get("memory", {})
        basic = {
            "total": _human_bytes(ram.get("total", 0)),
            "used": _human_bytes(ram.get("used", 0)),
            "available": _human_bytes(ram.get("available", 0)),
            "percent": f"{ram.get('percent',0)}%",
            "swap_used/total": f"{_human_bytes(ram.get('swap_used',0))} / {_human_bytes(ram.get('swap_total',0))} ({ram.get('swap_percent',0)}%)",
        }
        dict_to_table(self.tbl_ram, basic)
        if ram.get("modules"):
            idx = self.tabs.indexOf(self.tbl_ram)
            if idx != -1:
                self.tabs.removeTab(idx)
            container = QWidget()
            lay = QVBoxLayout(container)
            lay.addWidget(QLabel("RAM Özet"))
            tbl_summary = QTableWidget()
            dict_to_table(tbl_summary, basic)
            lay.addWidget(tbl_summary)
            lay.addWidget(QLabel("RAM Modülleri"))
            tbl_mod = QTableWidget()
            list_of_dicts_to_table(tbl_mod, ram["modules"])
            lay.addWidget(tbl_mod)
            if ram.get("spd"):
                lay.addWidget(QLabel("SPD (Zamanlamalar – sınırlı/isteğe bağlı)"))
                tbl_spd = QTableWidget()
                list_of_dicts_to_table(tbl_spd, ram["spd"])
                lay.addWidget(tbl_spd)
            self.tbl_ram = container
            self.tabs.insertTab(1, self.tbl_ram, "RAM")
        list_of_dicts_to_table(self.tbl_gpu, self.current_data.get("gpus", []))
        dict_to_table(self.tbl_mb, self.current_data.get("motherboard_bios", {}))
        dict_to_table(self.tbl_os, self.current_data.get("os", {}))
        # Ağ verisi
        net_rows: List[Dict[str, Any]] = []
        for it in self.current_data.get("network", []):
            net_rows.append({
                "name": it.get("name"),
                "is_up": it.get("is_up"),
                "mac": it.get("mac"),
                "ipv4": ", ".join(it.get("ipv4", [])) if isinstance(it.get("ipv4"), list) else it.get("ipv4"),
                "ipv6": ", ".join(it.get("ipv6", [])) if isinstance(it.get("ipv6"), list) else it.get("ipv6"),
                "speed_mbps": it.get("speed_mbps"),
                "mtu": it.get("mtu"),
            })
        list_of_dicts_to_table(self.tbl_net, net_rows)

    def export_json(self):
        if not self.current_data:
            QMessageBox.warning(self, "Uyarı", "Önce Yenile.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "JSON Kaydet", "report.json", "JSON (*.json)")
        if not p:
            return
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
        if not p:
            return
        try:
            save_html(self.current_data, p)
            QMessageBox.information(self, "Kaydedildi", f"HTML rapor kaydedildi:\n{p}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
