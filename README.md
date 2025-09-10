# mini-cpuz GUI (Python, PySide6)

Gelişmiş, platformlar arası “CPU‑Z benzeri” GUI uygulaması.
- Detaylı CPU bilgisi (stepping, cache line size — mümkün olduğunca)
- Bellek (RAM) + modüller, opsiyonel SPD (Libre/OpenHardwareMonitor JSON veya decode-dimms)
- GPU genişletme: `nvidia-smi`, `rocm-smi`, `intel_gpu_top` (mevcutsa)
- Anakart/BIOS (Windows WMI)
- OS/uptime
- Export: JSON ve HTML rapor

Not: Bazı düşük seviye bilgiler (TDP, SPD zamanlamaları) işletim sistemi ve yetkilere bağlıdır. Uygulama mümkün olduğunda toplar, yoksa zarifçe atlar.

## Kurulum
- Windows PowerShell:
  - `python -m venv .venv`
  - `.venv\Scripts\Activate.ps1`
  - `pip install -r requirements.txt`
  - `python -m pip install pyinstaller`

## Çalıştırma (Geliştirme)
- `python -m app.gui_main`

## EXE Üretimi (Windows)
İki yol:
- Hızlı komut:
  - `pyinstaller --noconfirm --windowed --onefile ^`
  - `  --name MiniCPUZ ^`
  - `  --add-data "app/resources/report_template.html;resources" ^`
  - `  app/gui_main.py`
  - Çıktı: `dist\MiniCPUZ.exe`

- Veya betik: `scripts\build_exe.bat`
  - `scripts\build_exe.bat`

Uygulama, PyInstaller içinde kaynakları bulmak için `sys._MEIPASS` yolunu kullanır.

## SPD (RAM zamanlamaları) nasıl etkinleşir?
- Windows: LibreHardwareMonitor veya OpenHardwareMonitor çalıştırın ve rapor/JSON çıktısını kaydedin.
  - Varsayılan aranan konumlar:
    - `%ProgramData%\LibreHardwareMonitor\LibreHardwareMonitorReport.json`
    - `%ProgramData%\OpenHardwareMonitor\OpenHardwareMonitorReport.json`
  - Alternatif: Uygulama içinde “SPD JSON Yolu”nu seçerek manuel dosya verin.
- Linux: `sudo decode-dimms` çıktısını bir dosyaya kaydedin ve arayüzden dosya yolunu seçin (parse sınırlıdır).

## GPU Genişletme
- NVIDIA: `nvidia-smi` mevcutsa bellek, sürücü, sıcaklık, güç, fan, saat bilgileri eklenir.
- AMD (ROCm): `rocm-smi` mevcutsa sıcaklık ve kullanım bilgileri eklenir.
- Intel iGPU: `intel_gpu_top -J` JSON modu mevcutsa özet kullanım verisi eklenir.

## Lisans
MIT
