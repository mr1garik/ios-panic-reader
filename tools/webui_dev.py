# -*- coding: utf-8 -*-
"""Новый интерфейс в обычном браузере — для разработки и автотестов (без pywebview).

Отдаёт страницу app/web и вызовы Python по HTTP: POST /api/<метод> с JSON-списком аргументов.
  python tools/webui_dev.py [--demo] [--port 8765] [--lang ru]
--demo — вымышленный телефон и логи (как для скриншотов README).
"""

import argparse
import functools
import http.server
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_server(port=0, demo=True, lang="ru", theme=None):
    sys.path.insert(0, os.path.join(ROOT, "app"))
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    dev = None
    if demo:
        import screenshots as S
        home, logs = S.make_demo_home()
        os.environ["HOME"] = os.environ["USERPROFILE"] = home
        dev = dict(udid=S.SERIAL, name="iPhone", product="iPhone14,5", model="iPhone 13", ios="18.6", build="22G86",
                   serial=S.SERIAL, imei="356789012345678", is_iphone=True, battery_health=84,
                   battery_mah="2700/3227 mAh", battery_cycles=512, dir=logs)
    os.environ["IOSPR_LANG"] = lang
    import webui
    backend = webui.Backend(with_device=False)
    if theme:
        backend.history.set_setting("theme", theme)
    if dev:
        backend.events.put(("pulled", dev))
        backend.connected.add(dev["udid"])
    web = webui.WEB_DIR

    class H(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            name = self.path.rsplit("/", 1)[-1]
            n = int(self.headers.get("Content-Length") or 0)
            args = json.loads(self.rfile.read(n) or b"[]")
            if name.startswith("_") or not hasattr(backend, name):
                self.send_error(404)
                return
            try:
                res = getattr(backend, name)(*args)
                body = json.dumps(res, ensure_ascii=False, default=str).encode()
                self.send_response(200)
            except Exception as e:
                import traceback
                traceback.print_exc()
                webui._log_error(name, traceback.format_exc())
                body = json.dumps({"error": str(e)}).encode()
                self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(H, directory=web))
    srv.backend = backend
    return srv


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--lang", default="ru")
    a = ap.parse_args()
    s = make_server(a.port, a.demo, a.lang)
    print(f"http://127.0.0.1:{s.server_address[1]}/index.html", flush=True)
    s.serve_forever()
