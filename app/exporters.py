# app/exporters.py
import json, os, sys
from typing import Any, Dict
from jinja2 import Environment, FileSystemLoader, select_autoescape

def _resource_dir() -> str:
    base = getattr(sys, "_MEIPASS", None)
    if not base and getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    if base:
        candidates = [
            os.path.join(base, "app", "resources"),
            os.path.join(base, "resources"),
            base,
        ]
    else:
        moddir = os.path.dirname(__file__)
        candidates = [
            os.path.join(moddir, "resources"),
            moddir,
        ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    return candidates[0]

def save_json(data: Dict[str, Any], out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def save_html(data: Dict[str, Any], out_path: str) -> None:
    env = Environment(loader=FileSystemLoader(_resource_dir()), autoescape=select_autoescape())
    tmpl = env.get_template("report_template.html")
    html = tmpl.render(data=data)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
