# -*- coding: utf-8 -*-
"""ابزار درخواست HTTP فقط با کتابخانه استاندارد پایتون (بدون نیاز به pip)."""
import gzip
import re
import socket
import ssl
import time
import zlib
import urllib.error
import urllib.request

USER_AGENT = "Mozilla/5.0 (compatible; SeoAgentBot/1.0; +SEO-GEO-Audit)"

_MAX_BODY = 8 * 1024 * 1024  # حداکثر ۸ مگابایت دانلود

_SSL_CTX = {}
_OPENERS = {}


def _ssl_context(verify: bool):
    key = "verify" if verify else "noverify"
    if key not in _SSL_CTX:
        if verify:
            _SSL_CTX[key] = ssl.create_default_context()
        else:
            _SSL_CTX[key] = ssl.create_default_context()
            _SSL_CTX[key].check_hostname = False
            _SSL_CTX[key].verify_mode = ssl.CERT_NONE
    return _SSL_CTX[key]


def connect_url(url):
    """بازنویسی اتصالی: روی برخی سیستم‌ها اتصال به نام «localhost» (تلاش IPv6 اول) توسط
    فایروال/پروکسی حدود ۲۰ ثانیه معطل می‌شود؛ برای http لوکال مستقیم به 127.0.0.1 وصل می‌شویم
    و آدرس نمایشی دست‌نخورده می‌ماند."""
    try:
        p = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    if p.scheme != "http" or (p.hostname or "").lower() not in ("localhost", "::1"):
        return url
    hostport = "127.0.0.1" + (f":{p.port}" if p.port else "")
    return urllib.parse.urlunsplit((p.scheme, hostport, p.path, p.query, p.fragment))


def _get_opener(direct, ctx):
    """برای هاست‌های لوکال/داخلی پروکسی سیستم دور زده می‌شود (پروکسی‌ها لوکال را خراب می‌کنند)."""
    key = (direct, ctx is not None, getattr(ctx, "verify_mode", None))
    if key not in _OPENERS:
        handlers = []
        if direct:
            handlers.append(urllib.request.ProxyHandler({}))
        if ctx is not None:
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        _OPENERS[key] = urllib.request.build_opener(*handlers)
    return _OPENERS[key]


class FetchResult:
    __slots__ = ("url", "final_url", "status", "headers", "body", "text",
                 "error", "ttfb_ms", "elapsed_ms", "ok")

    def __init__(self, url):
        self.url = url
        self.final_url = url
        self.status = 0
        self.headers = {}
        self.body = b""
        self.text = ""
        self.error = None
        self.ttfb_ms = 0.0
        self.elapsed_ms = 0.0
        self.ok = False

    @property
    def content_type(self):
        return (self.headers.get("Content-Type") or "").lower()

    @property
    def is_html(self):
        ct = self.content_type
        return ("text/html" in ct) or (ct == "" and bool(self.text)) or bool(self.text and "<html" in self.text[:2000].lower())


def _decode_charset(content_type: str, body: bytes) -> str:
    charset = None
    m = re.search(r"charset=([\w\-]+)", content_type or "", re.I)
    if m:
        charset = m.group(1)
    if not charset:
        head = body[:4096].lower()
        m = re.search(rb'<meta[^>]+charset=["\']?([\w\-]+)', head)
        if m:
            charset = m.group(1).decode("ascii", "ignore")
    for enc in (charset, "utf-8"):
        if not enc:
            continue
        try:
            return body.decode(enc, "replace")
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", "replace")


def _decompress(body: bytes, encoding: str) -> bytes:
    enc = (encoding or "").lower().strip()
    try:
        if enc == "gzip" or body[:2] == b"\x1f\x8b":
            return gzip.decompress(body)
        if enc == "deflate":
            try:
                return zlib.decompress(body)
            except zlib.error:
                return zlib.decompress(body, -zlib.MAX_WBITS)
        if enc == "br":
            try:
                import brotli  # optional
                return brotli.decompress(body)
            except Exception:
                return body
    except Exception:
        return body
    return body


def fetch(url, timeout=15, verify_ssl=True, method="GET", headers=None, data=None):
    """درخواست HTTP با پشتیبانی gzip و خطای تمیز. خروجی: FetchResult"""
    res = FetchResult(url)
    req_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fa,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }
    if headers:
        req_headers.update(headers)
    body = data.encode("utf-8") if isinstance(data, str) else (data or None)
    connect_to = connect_url(url)
    req = urllib.request.Request(connect_to, data=body, headers=req_headers, method=method)
    start = time.time()
    try:
        is_https = connect_to.lower().startswith("https")
        ctx = _ssl_context(verify_ssl) if is_https else None
        direct = is_local_host(urllib.parse.urlsplit(connect_to).hostname or "")
        opener = _get_opener(direct, ctx)
        with opener.open(req, timeout=timeout) as resp:
            res.ttfb_ms = (time.time() - start) * 1000
            res.status = resp.status
            res.final_url = resp.geturl()
            res.headers = {k: v for k, v in resp.headers.items()}
            res.body = resp.read(_MAX_BODY)
            res.ok = True
    except urllib.error.HTTPError as e:
        res.status = e.code
        res.error = f"HTTP {e.code}"
        try:
            res.headers = {k: v for k, v in e.headers.items()}
            res.body = e.read(_MAX_BODY)
        except Exception:
            pass
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        res.error = str(reason)
        if "CERTIFICATE_VERIFY_FAILED" in res.error:
            res.error = "خطای گواهی SSL (می‌توانید گزینه نادیده‌گرفتن SSL را فعال کنید)"
        elif isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in res.error.lower():
            res.error = f"پاسخی در {timeout} ثانیه دریافت نشد (Timeout)"
    except (socket.timeout, TimeoutError):
        res.error = f"پاسخی در {timeout} ثانیه دریافت نشد (Timeout)"
    except Exception as e:
        res.error = str(e) or e.__class__.__name__
    res.elapsed_ms = (time.time() - start) * 1000
    if res.body:
        res.body = _decompress(res.body, res.headers.get("Content-Encoding", ""))
        res.text = _decode_charset(res.content_type, res.body)
    if res.final_url and "://localhost" in url.lower() and "://127.0.0.1" in res.final_url.lower():
        res.final_url = res.final_url.replace("://127.0.0.1", "://localhost", 1)
    return res


LOCAL_HOST_NAMES = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def is_local_host(host):
    """تشخیص هاست لوکال/شبکه داخلی — این‌ها پیش‌فرض http دارند نه https."""
    h = (host or "").lower().strip("[]").strip(".")
    if h in LOCAL_HOST_NAMES or h.endswith(".local") or h.endswith(".localhost"):
        return True
    m = re.match(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$", h)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a in (10, 127) or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31):
            return True
    return False


def normalize_url(raw):
    """نرمال‌سازی آدرس ورودی کاربر؛ لوکال → http، بقیه → https (مگر اینکه اسکیما صریح باشد)."""
    raw = (raw or "").strip()
    if not raw:
        return None, "آدرس سایت خالی است"
    m = re.match(r"^(https?)://", raw, re.I)
    scheme = m.group(1).lower() if m else None
    # «localhost:3000» بدون پیشوند، هنگام urlsplit به‌عنوان اسکیما پارس می‌شود؛ لنگر می‌گذاریم
    anchor = raw if scheme else "http://" + raw
    try:
        p = urllib.parse.urlsplit(anchor)
    except ValueError:
        return None, "آدرس نامعتبر است"
    host = (p.hostname or "").lower()
    if not host or " " in host:
        return None, "آدرس نامعتبر است"
    if not scheme:
        scheme = "http" if is_local_host(host) else "https"
    path = p.path if p.path not in ("", "/") else ""
    url = f"{scheme}://{p.netloc.lower()}{path}"
    if p.query:
        url += "?" + p.query
    return url, None


def base_url(url):
    p = urllib.parse.urlsplit(url)
    return f"{p.scheme.lower()}://{p.netloc.lower()}"


def host_key(u):
    """کلید یکسان‌سازی هاست — localhost با 127.0.0.1 و [::1] یکی حساب می‌شود."""
    try:
        p = urllib.parse.urlsplit(u)
        h = (p.hostname or "").lower()
        if h.startswith("www."):
            h = h[4:]
        if h in LOCAL_HOST_NAMES:
            h = "localhost"
        port = p.port or (443 if (p.scheme or "http").lower() == "https" else 80)
        return (h, port)
    except ValueError:
        return (u, 0)


def same_host(u1, u2):
    return host_key(u1) == host_key(u2)


def smart_fetch(raw, timeout=15, verify_ssl=True, **kw):
    """دریافت با انتخاب هوشمند اسکیما: اگر کاربر http/https ننویسد و اتصال اول شکست بخورد،
    اسکیمای دیگر امتحان می‌شود (مثلاً سایت‌های http-only یا لوکال‌هاست).
    خروجی: (FetchResult, آدرس_استفاده‌شده, خطا)"""
    url, err = normalize_url(raw)
    if err:
        return None, None, err
    explicit = bool(re.match(r"^\s*https?://", raw or "", re.I))
    res = fetch(url, timeout=timeout, verify_ssl=verify_ssl, **kw)
    used = url
    if not res.ok and not explicit:
        alt = ("http://" if used.lower().startswith("https://") else "https://") + used.split("://", 1)[1]
        res2 = fetch(alt, timeout=timeout, verify_ssl=verify_ssl, **kw)
        if res2.ok or (res2.error is None and res.error is not None):
            res, used = res2, alt
    return res, used, None


SKIP_LINK_RE = re.compile(r"\.(jpg|jpeg|png|gif|webp|svg|ico|pdf|zip|rar|mp3|mp4|avi|doc|docx|xls|xlsx|css|js|woff2?|ttf|eot)(\?|#|$)", re.I)
NON_PAGE_RE = re.compile(r"^(mailto:|tel:|javascript:|data:|#)", re.I)


def is_crawlable(href):
    if not href or NON_PAGE_RE.search(href):
        return False
    if SKIP_LINK_RE.search(href):
        return False
    return True
