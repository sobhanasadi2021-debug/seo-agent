# -*- coding: utf-8 -*-
"""
سئو ایجنت — سرور وب و API
اجرا:  python app.py   سپس  http://127.0.0.1:8791
بدون هیچ وابستگی خارجی (فقط کتابخانه استاندارد پایتون).
"""
import json
import mimetypes
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

sys.path.insert(0, BASE_DIR)
from core import tasks                                          # noqa: E402
from core.report import build_html_report, build_text_report, build_csv_report  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# برای دیپلوی: PORT/HOST را از متغیر محیطی بخوان (پیش‌فرض: لوکال)
PORT = int(os.environ.get("PORT", "8791"))
HOST = os.environ.get("HOST", "127.0.0.1")
# اگر AGENT_TOKEN ست شود، همه APIها نیازمند توکن می‌شوند (برای دیپلوی عمومی)
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "").strip()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ---------------- helpers ----------------
    def _send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # هدرهای امنیتی برای اجرای روی هاست عمومی
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (ConnectionAbortedError, BrokenPipeError):
                pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self._send(code, body)

    def _error(self, msg, code=400):
        self._json({"ok": False, "error": msg}, code)

    def _body_json(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        raw = self.rfile.read(n) if n else b""
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _serve_static(self, rel_path):
        rel_path = rel_path.lstrip("/")
        full = os.path.normpath(os.path.join(STATIC_DIR, rel_path))
        if not full.startswith(os.path.abspath(STATIC_DIR)) or not os.path.isfile(full):
            self._error("فایل یافت نشد", 404)
            return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            body = f.read()
        self._send(200, body, ctype)

    def _token_ok(self, path, qs):
        """اگر AGENT_TOKEN ست شده باشد، APIها نیازمند توکن هستند (هدر یا ?token=)."""
        if not AGENT_TOKEN or not path.startswith("/api/") or path == "/api/health":
            return True
        tok = self.headers.get("X-Agent-Token") or (qs.get("token") or [""])[0]
        return tok == AGENT_TOKEN

    def _report_missing_page(self):
        html = ("<!doctype html><html lang=\"fa\" dir=\"rtl\"><head><meta charset=\"utf-8\">"
                "<title>گزارش موجود نیست</title><style>"
                "body{font-family:Vazirmatn,Tahoma,sans-serif;background:#0b1322;color:#e8edf7;"
                "display:grid;place-items:center;height:100vh;margin:0}"
                ".box{background:#111c30;border:1px solid #22304e;padding:32px 44px;border-radius:18px;text-align:center}"
                "</style></head><body><div class='box'><h1>📋 گزارش در دسترس نیست</h1>"
                "<p>این گزارش دیگر در حافظه سرور نیست (سرور ری‌استارت شده است).</p>"
                "<p>برای گزارش جدید، یک تحلیل تازه اجرا کنید.</p></div></body></html>")
        self._send(404, html.encode("utf-8"), "text/html; charset=utf-8")

    # ---------------- routes ----------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if not self._token_ok(path, qs):
            self._error("توکن نامعتبر است — پنل را با ?token=... باز کنید", 401)
            return

        if path in ("/", "/index.html"):
            self._serve_static("index.html")
        elif path.startswith("/static/"):
            self._serve_static(path[len("/static/"):])
        elif path == "/favicon.ico":
            self._serve_static("logo.svg")
        elif path == "/api/health":
            self._json({"ok": True, "app": "seo-agent", "version": "1.0"})
        elif path == "/api/task/status":
            tid = (qs.get("id") or [""])[0]
            t = tasks.get_task(tid)
            if not t:
                self._error("تسک یافت نشد", 404)
            else:
                self._json({"ok": True, "task": t})
        elif path == "/api/history":
            self._json({"ok": True, "history": tasks.list_history()})
        elif path.startswith("/api/history/"):
            hid = path.rsplit("/", 1)[-1]
            item = tasks.get_history_item(hid)
            if not item:
                self._error("یافت نشد", 404)
            else:
                self._json({"ok": True, **item})
        elif path == "/api/report/html":
            tid = (qs.get("id") or [""])[0]
            t = tasks.get_task(tid)
            if not t or not t.get("result"):
                self._report_missing_page()
                return
            result = t["result"]
            if result.get("type") == "analyze":
                html = build_html_report(result)
                fname = f"seo-report-{tid}.html"
            else:
                html = self._auto_report_html(result, tid)
                fname = f"auto-seo-log-{tid}.html"
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8",
                       {"Content-Disposition": f'attachment; filename="{fname}"'})
        elif path == "/api/report/csv":
            tid = (qs.get("id") or [""])[0]
            t = tasks.get_task(tid)
            if not t or not t.get("result") or t["result"].get("type") != "analyze":
                self._report_missing_page()
                return
            body = build_csv_report(t["result"]).encode("utf-8")
            self._send(200, body, "text/csv; charset=utf-8",
                       {"Content-Disposition": f'attachment; filename="seo-report-{tid}.csv"'})
        elif path == "/api/report/text":
            tid = (qs.get("id") or [""])[0]
            t = tasks.get_task(tid)
            if not t or not t.get("result") or t["result"].get("type") != "analyze":
                self._report_missing_page()
                return
            body = build_text_report(t["result"]).encode("utf-8")
            self._send(200, body, "text/plain; charset=utf-8")
        else:
            self._error("مسیر یافت نشد", 404)

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        if not self._token_ok(path, qs):
            self._error("توکن نامعتبر است — پنل را با ?token=... باز کنید", 401)
            return
        data = self._body_json()
        if path == "/api/task/start":
            ttype = data.get("type")
            params = data.get("params", {})
            if ttype not in ("analyze", "auto"):
                self._error("نوع تسک باید analyze یا auto باشد")
                return
            if ttype == "analyze" and not params.get("url"):
                self._error("آدرس سایت را وارد کنید")
                return
            if ttype == "auto":
                missing = [k for k in ("site_url", "username", "password") if not params.get(k)]
                if missing:
                    self._error("فیلدهای الزامی: " + "، ".join(missing))
                    return
            tid = tasks.start_task(ttype, params)
            self._json({"ok": True, "task_id": tid})
        elif path == "/api/task/cancel":
            tid = data.get("id", "")
            self._json({"ok": tasks.cancel_task(tid)})
        elif path == "/api/history/clear":
            tasks.clear_history()
            self._json({"ok": True})
        else:
            self._error("مسیر یافت نشد", 404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        if not self._token_ok(path, qs):
            self._error("توکن نامعتبر است — پنل را با ?token=... باز کنید", 401)
            return
        if path.startswith("/api/history/"):
            hid = path.rsplit("/", 1)[-1]
            self._json({"ok": tasks.delete_history_item(hid)})
        else:
            self._error("مسیر یافت نشد", 404)

    def _auto_report_html(self, result, tid):
        rows = ""
        for c in result.get("changes", []):
            fields = "، ".join(f"{f['name']}: {f['value']}" for f in c.get("fields", []))
            rows += (f"<tr><td>{c.get('title', '')}</td><td>{fields}</td>"
                     f"<td dir='ltr'>{c.get('link', '')[:50]}</td></tr>")
        s = result.get("summary", {})
        det = result.get("detection", {})
        recs = "".join(f"<li>{r}</li>" for r in result.get("recommendations", []))
        return f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<title>گزارش سئوی خودکار {tid}</title>
<style>body{{font-family:Vazirmatn,Tahoma,sans-serif;max-width:860px;margin:30px auto;padding:0 16px;line-height:1.9}}
table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #eee;padding:8px;font-size:14px}}
h1{{font-size:20px}} .muted{{color:#777;font-size:13px}}</style></head><body>
<h1>گزارش سئوی خودکار وردپرس</h1>
<p class="muted">{result.get('started_at', '')} — روش: {result.get('method', '')}</p>
<ul><li>مطالب بررسی‌شده: {s.get('scanned', 0)}</li><li>به‌روزرسانی‌شده: {s.get('updated', 0)}</li>
<li>خطاها: {s.get('failed', 0)}</li><li>پلتفرم: {det.get('platform', '—')}</li></ul>
<h2>تغییرات</h2><table><tr><th>مطلب</th><th>تغییرات</th><th>لینک</th></tr>{rows or '<tr><td colspan="3">تغییری اعمال نشد</td></tr>'}</table>
<h2>توصیه‌های بعدی</h2><ul>{recs}</ul></body></html>"""

    def log_message(self, fmt, *args):
        # لاگ بدون query string تا هیچ توکن/داده‌ای در لاگ‌های سرور نماند
        try:
            if args and isinstance(args[0], str) and "?" in args[0]:
                args = (args[0].split("?", 1)[0],) + args[1:]
            sys.stdout.write(f"[http] {fmt % args}\n")
        except Exception:
            pass


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print("=" * 56)
    print("  سئو ایجنت | SEO + GEO Agent")
    print(f"  آدرس:  http://{HOST}:{PORT}")
    if AGENT_TOKEN:
        print(f"  محافظت‌شده با توکن: ?token={AGENT_TOKEN}")
    print("  برای توقف: Ctrl+C")
    print("=" * 56)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nسرور متوقف شد.")


if __name__ == "__main__":
    main()
