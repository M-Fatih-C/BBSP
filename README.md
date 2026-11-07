# MiniCPUZ

A PySide6 desktop system-information utility with tabbed CPU, memory, GPU,
disk/network and operating-system views, plus JSON and HTML report export.
The repository is historically named `BBSP`; the product name in the code is
**MiniCPUZ**.

## Run from source

Use a Python 3.12 virtual environment and a desktop session:

```bash
python3.12 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m app.gui_main
```

`app/gui_main.py` owns the Qt interface and single-instance guard;
`app/system_info.py` collects platform-dependent information;
`app/exporters.py` writes JSON/HTML using `app/resources/` templates and styling.

## Platform and packaging limits

Python/Qt can run on Windows, macOS and Linux, but available information differs.
WMI is Windows-only. SPD/GPU details may depend on Libre/OpenHardwareMonitor,
`decode-dimms`, `nvidia-smi`, `rocm-smi` or other optional tools. Missing tools,
permissions and unsupported hardware can produce incomplete fields. Do not grant
elevated permissions simply to populate every field.

`MiniCPUZ.spec` contains a Windows-oriented PyInstaller recipe:

```powershell
python -m pip install pyinstaller
pyinstaller MiniCPUZ.spec
```

Run that recipe on Windows and validate its packaged resources on a clean machine.
The previously documented `build_windows.bat` and `build_linux.sh` are absent;
their existence or a tested executable is not claimed. macOS/Linux packaging
requires separate adaptation and acceptance.

## Tests and privacy

```bash
python -m pip install Jinja2
python -m unittest discover -s tests -v
```

The exporter regressions use synthetic dictionaries to verify JSON roundtrips and
HTML escaping. They do not inventory the host or validate the GUI, drivers or
Windows packaging. Reports may contain serial numbers, usernames, device names,
paths or network information. Review and redact them before sharing; keep real
exports out of commits.

## License

No license file is included; no new license grant is asserted. Author: [Muhammet Fatih Çetintaş](https://github.com/M-Fatih-C).
