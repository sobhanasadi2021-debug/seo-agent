# -*- coding: utf-8 -*-
"""سرور وردپرس ساختگی (XML-RPC + صفحات ساده) برای تست حالت خودکار — بدون سایت واقعی.

اجرا:  python test/mock_wp.py      (پورت 8098)
ورود:  admin / admin123
"""
import json
import os
import sys
import xmlrpc.client
from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler

PORT = 8099
USER, PASS = "admin", "admin123"
HERE = os.path.dirname(os.path.abspath(__file__))
EDITS_FILE = os.path.join(HERE, "wp_edits.json")

POSTS = [
    {
        "post_id": "101", "post_title": "بهترین لپ‌تاپ ۱۴۰۵ برای کارهای گرافیکی",
        "post_type": "post", "post_status": "publish", "post_excerpt": "",
        "post_content": "<p>راهنمای کامل خرید لپ‌تاپ گرافیکی برای طراحان. لپ‌تاپ گرافیکی مناسب باید کارت گرافیک قوی و پردازنده نسل جدید داشته باشد. در این مقاله لپ‌تاپ گرافیکی اقتصادی و حرفه‌ای را معرفی می‌کنیم و نکات مهم خرید لپ‌تاپ را بررسی می‌کنیم.</p>",
        "link": f"http://127.0.0.1:{PORT}/?p=101", "custom_fields": [], "terms": [],
    },
    {
        "post_id": "102", "post_title": "معرفی گوشی‌های پرچمدار سال",
        "post_type": "post", "post_status": "publish", "post_excerpt": "خلاصه موجود",
        "post_content": "<p>گوشی پرچمدار امسال با دوربین پیشرفته و باتری قوی معرفی شد. گوشی پرچمدار بازار را داغ کرده است.</p>",
        "link": f"http://127.0.0.1:{PORT}/?p=102", "custom_fields": [], "terms": [],
    },
]

OPTIONS = {"blog_title": "تک‌شاپ", "blog_description": ""}

HOME_HTML = """<!doctype html><html lang="fa"><head><title>تک‌شاپ</title>
<meta name="generator" content="WordPress 6.5"></head>
<body><nav><a href="/?p=101">لپ‌تاپ</a><a href="/?p=102">گوشی</a></nav>
<p>فروشگاه تک‌شاپ مرجع خرید لپ‌تاپ و گوشی موبایل با بهترین قیمت و گارانتی معتبر است.</p>
<!-- wp-content / wp-includes --></body></html>"""

ROBOTS = "User-agent: *\nAllow: /\nSitemap: http://127.0.0.1:%d/sitemap.xml\n" % PORT
SITEMAP = '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>http://127.0.0.1:%d/</loc></url><url><loc>http://127.0.0.1:%d/?p=101</loc></url></urlset>' % (PORT, PORT)


class Handler(SimpleXMLRPCRequestHandler):
    rpc_paths = ("/xmlrpc.php",)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/xmlrpc.php":
            self.send_response(405)
            self.end_headers()
        elif path == "/robots.txt":
            body = ROBOTS.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/wp-sitemap.xml" or path == "/sitemap.xml":
            body = SITEMAP.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = HOME_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def _auth_ok(username, password):
    if username != USER or password != PASS:
        raise xmlrpc.client.Fault(403, "Incorrect username or password.")
    return True


def wp_getUsersBlogs(username, password):
    _auth_ok(username, password)
    return [{"blog_id": "1", "blogname": OPTIONS["blog_title"], "is_admin": True, "url": f"http://127.0.0.1:{PORT}/"}]


def wp_getOptions(blog_id, username, password, options=None):
    _auth_ok(username, password)
    return {k: {"value": v} for k, v in OPTIONS.items()}


def wp_setOptions(blog_id, username, password, new_options):
    _auth_ok(username, password)
    for k, v in (new_options or {}).items():
        OPTIONS[k] = v
    _log("setOptions", new_options)
    return {k: {"value": v} for k, v in OPTIONS.items()}


def wp_getPosts(blog_id, username, password, flt=None):
    _auth_ok(username, password)
    n = int((flt or {}).get("number", 10))
    return [dict(p) for p in POSTS[:n]]


def wp_getPost(blog_id, username, password, post_id):
    _auth_ok(username, password)
    for p in POSTS:
        if str(p["post_id"]) == str(post_id):
            return dict(p)
    raise xmlrpc.client.Fault(404, "Invalid post ID.")


def wp_editPost(blog_id, username, password, post_id, content):
    _auth_ok(username, password)
    for p in POSTS:
        if str(p["post_id"]) == str(post_id):
            existing = {cf["key"]: cf for cf in p.get("custom_fields", [])}
            for cf in content.get("custom_fields", []):
                key = cf["key"]
                if "id" in cf and cf.get("id"):
                    existing[key] = {"ID": cf["id"], "key": key, "value": cf["value"]}
                else:
                    if key in existing:
                        existing[key]["value"] = cf["value"]
                    else:
                        existing[key] = {"ID": f"cf{len(existing) + 1}", "key": key, "value": cf["value"]}
            p["custom_fields"] = list(existing.values())
            if "terms_names" in content:
                p["terms"] = [{"taxonomy": "post_tag", "name": t} for t in content["terms_names"].get("post_tag", [])]
            _log("editPost", {"post_id": post_id, "content": content})
            return True
    raise xmlrpc.client.Fault(404, "Invalid post ID.")


def _log(action, data):
    edits = []
    try:
        with open(EDITS_FILE, "r", encoding="utf-8") as f:
            edits = json.load(f)
    except Exception:
        edits = []
    edits.append({"action": action, "data": data})
    with open(EDITS_FILE, "w", encoding="utf-8") as f:
        json.dump(edits, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    server = SimpleXMLRPCServer(("127.0.0.1", PORT), requestHandler=Handler, allow_none=True, logRequests=False)
    server.register_introspection_functions()
    server.register_function(wp_getUsersBlogs, "wp.getUsersBlogs")
    server.register_function(wp_getOptions, "wp.getOptions")
    server.register_function(wp_setOptions, "wp.setOptions")
    server.register_function(wp_getPosts, "wp.getPosts")
    server.register_function(wp_getPost, "wp.getPost")
    server.register_function(wp_editPost, "wp.editPost")
    print(f"ماک وردپرس روی http://127.0.0.1:{PORT} — یوزر {USER} / پس {PASS}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
