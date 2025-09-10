# app/exporters.py
import json
import os
import sys
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape

def save_json(data: Dict[str, Any], out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _resource_dir() -> str:
    # Handle PyInstaller
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(__file__)
    return os.path.join(base, "resources")

def save_html(data: Dict[str, Any], out_path: str) -> None:
    env = Environment(
        loader=FileSystemLoader(_resource_dir()),
        autoescape=select_autoescape()
    )
    tmpl = env.get_template("report_template.html")
    html = tmpl.render(data=data)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
