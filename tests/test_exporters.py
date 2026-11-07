import json
import tempfile
import unittest
from pathlib import Path

from app.exporters import save_html, save_json


class ExportTests(unittest.TestCase):
    def test_json_preserves_unicode_and_nested_values(self):
        data = {"device": "Sentetik Türkçe", "cpu": {"cores": 4}, "gpus": []}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            save_json(data, str(path))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), data)

    def test_html_escapes_device_values_and_handles_no_gpu(self):
        value = '<script>alert("synthetic")</script>'
        data = {"collected_at": "synthetic", "cpu": {"brand": value},
                "memory": {}, "gpus": [], "network": [],
                "motherboard_bios": {}, "os": {"name": "Synthetic OS"}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.html"
            save_html(data, str(path))
            html = path.read_text(encoding="utf-8")
            self.assertNotIn(value, html)
            self.assertIn("&lt;script&gt;", html)
            self.assertIn("Synthetic OS", html)
            self.assertIn("GPU bilgisi bulunamadı", html)


if __name__ == "__main__":
    unittest.main()
