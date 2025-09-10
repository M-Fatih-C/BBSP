# MiniCPUZ — GUI & EXE Ready

CPU-Z benzeri sistem bilgi aracı. PySide6 tab'lı arayüz, JSON/HTML export, markalı logo ve karanlık tema ile gelir.
Windows'ta PyInstaller ile tek dosya **.exe** üretimi hazırdır.

## Kurulum
```bash
python -m venv .venv && . .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app/gui_main.py
```

## Windows'ta .exe üretimi
```bat
build_windows.bat
```
- PNG'den `.ico` üretir ve `dist\MiniCPUZ.exe` çıktısını oluşturur.
- Gerekli kaynaklar (`logo.png`, `style.qss`, `report_template.html`) EXE içine eklenir.

## Linux/macOS paketleme
```bash
./build_linux.sh
```

## İsteğe bağlı veri kaynakları
- **SPD** (RAM zamanlamaları): Windows'ta Libre/OpenHardwareMonitor JSON raporu, Linux'ta `decode-dimms` çıktısı.
- **GPU ek metrikler**: NVIDIA için `nvidia-smi`, AMD için `rocm-smi`, Intel için `intel_gpu_top -J` mevcutsa kullanılır.

> Not: Bazı komutlar root/izin gerektirebilir. Bulunamazsa sessizce atlanır.
