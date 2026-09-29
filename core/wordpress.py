# -*- coding: utf-8 -*-
"""اتوماسیون سئوی خودکار وردپرس — از طریق XML-RPC و REST API (بدون وابستگی خارجی)."""
import base64
import json
import re
import time
import urllib.parse
import urllib.request
import xmlrpc.client

from . import fetcher, keywords
from .pageparser import parse_html

FIELD_MAP = {
    "yoast": {"meta_desc": "_yoast_wpseo_metadesc", "focus_kw": "_yoast_wpseo_focuskw"},
    "rankmath": {"meta_desc": "rank_math_description", "focus_kw": "rank_math_focus_keyword"},
    "aioseo": {"meta_desc": "_aioseo_description", "focus_kw": "_aioseo_focus_keyword"},
}


class _HttpTransport(xmlrpc.client.Transport):
    def __init__(self, timeout=25):
        super().__init__()
        self._timeout = timeout
        self.user_agent = fetcher.USER_AGENT

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


class _HttpsTransport(xmlrpc.client.SafeTransport):
    def __init__(self, timeout=25, ssl_context=None):
        super().__init__(context=ssl_context)
        self._timeout = timeout
        self.user_agent = fetcher.USER_AGENT

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


class WordPressAutomation:
    def __init__(self, site_url, admin_url, username, password,
                 verify_ssl=True, timeout=25, step=None, cancel=None):
        self._raw_site = site_url or ""
        self._scheme_implicit = not re.match(r"^\s*https?://", self._raw_site, re.I)
        self.site_url, err = fetcher.normalize_url(site_url)
        if err:
            raise ValueError(f"آدرس سایت نامعتبر است: {err}")
        self.admin_url = (admin_url or "").strip()
        self.username = (username or "").strip()
        self.password = password or ""
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.step = step or (lambda *a, **k: None)
        self.cancel = cancel or (lambda: False)
        self.method = None          # 'xmlrpc' | 'rest'
        self.xmlrpc_url = None
        self.detection = {}
        self.ssl_ctx = fetcher._ssl_context(verify_ssl)

    # ---------- ابزار ----------
    def _fetch(self, url, method="GET", headers=None, data=None, timeout=None):
        return fetcher.fetch(url, timeout=timeout or self.timeout, verify_ssl=self.verify_ssl,
                             method=method, headers=headers, data=data)

    def _rest(self, path, method="GET", payload=None):
        url = self.site_url.rstrip("/") + path
        token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json",
                   "Accept": "application/json"}
        data = json.dumps(payload).encode() if payload is not None else None
        return self._fetch(url, method=method, headers=headers, data=data)

    def _rest_json(self, res):
        try:
            return json.loads(res.text)
        except Exception:
            return None

    # ---------- شناسایی ----------
    def detect(self):
        """شناسایی وردپرس، XML-RPC، REST و افزونه سئو."""
        d = {"platform": "نامشخص", "xmlrpc": None, "rest": None, "seo_plugins": [],
             "admin_reachable": None, "version": ""}
        self.step("در حال شناسایی پلتفرم سایت…", "info", 8)
        home = self._fetch(self.site_url)
        if not home.ok and self._scheme_implicit:
            # کاربر اسکیما را ننویسه بود — اسکیمای دیگر را هم امتحان کن (سایت‌های http-only)
            alt = ("http://" if self.site_url.lower().startswith("https://") else "https://") \
                + self.site_url.split("://", 1)[1]
            alt_res = self._fetch(alt, timeout=12)
            if alt_res.ok:
                self.site_url = alt
                home = alt_res
                self.step(f"اتصال از طریق {alt.split('://')[0].upper()} برقرار شد", "info", 9)
        html = home.text or ""
        low = html.lower()
        if "wp-content" in low or "wp-includes" in low or "wordpress" in low:
            d["platform"] = "WordPress"
        parser = parse_html(html)
        gen = (parser.meta("generator") or "")
        if "wordpress" in gen.lower():
            d["platform"] = "WordPress"
            m = re.search(r"wordpress\s+([\d.]+)", gen, re.I)
            if m:
                d["version"] = m.group(1)

        # پلاگین سئو فعال
        if "wpseo" in low or "yoast" in low:
            d["seo_plugins"].append("Yoast SEO")
        if "rank-math" in low or "rank_math" in low:
            d["seo_plugins"].append("Rank Math")
        if "aioseo" in low:
            d["seo_plugins"].append("All in One SEO")

        # XML-RPC
        self.xmlrpc_url = self.site_url.rstrip("/") + "/xmlrpc.php"
        probe = self._fetch(self.xmlrpc_url, timeout=12)
        if probe.status in (200, 405):
            d["xmlrpc"] = "maybe"
        elif probe.status in (403, 503):
            d["xmlrpc"] = "blocked"
        else:
            d["xmlrpc"] = probe.error or f"HTTP {probe.status}"

        # REST
        rest = self._fetch(self.site_url.rstrip("/") + "/wp-json/", timeout=12)
        d["rest"] = "ok" if rest.ok and '"namespaces"' in (rest.text or "") else None

        # پنل ادمین
        if self.admin_url:
            adm = self._fetch(self.admin_url, timeout=12)
            body = (adm.text or "").lower()
            if adm.ok and ("wp-admin" in body or "wp-login" in body or "login" in body or "ورود" in body):
                d["admin_reachable"] = True
            else:
                d["admin_reachable"] = f"غیرقابل تأیید ({adm.status or adm.error})"

        if d["platform"] != "WordPress":
            self.step("هشدار: وردپرس شناسایی نشد؛ ادامه با تلاش روی مسیرهای استاندارد وردپرس.", "warn", 10)
        else:
            v = f" نسخه {d['version']}" if d["version"] else ""
            self.step(f"وردپرس{v} شناسایی شد ✓", "success", 12)
        if d["seo_plugins"]:
            self.step(f"افزونه سئو فعال: {'، '.join(d['seo_plugins'])}", "info", 13)
        self.detection = d
        return d

    # ---------- احراز هویت ----------
    def authenticate(self):
        """ابتدا XML-RPC، سپس REST. خروجی: نام روش یا None."""
        self.step("بررسی نام کاربری و رمز عبور…", "info", 15)

        # --- XML-RPC ---
        if self.detection.get("xmlrpc") != "blocked" and self.xmlrpc_url:
            try:
                scheme = urllib.parse.urlsplit(self.xmlrpc_url).scheme
                if scheme == "https":
                    transport = _HttpsTransport(self.timeout, self.ssl_ctx)
                else:
                    transport = _HttpTransport(self.timeout)
                server = xmlrpc.client.ServerProxy(fetcher.connect_url(self.xmlrpc_url),
                                                   transport=transport, allow_none=True)
                blogs = server.wp.getUsersBlogs(self.username, self.password)
                if isinstance(blogs, list) and blogs:
                    self.method = "xmlrpc"
                    self._server = server
                    self.step("اتصال XML-RPC موفق بود ✓ (احراز هویت تأیید شد)", "success", 20)
                    return "xmlrpc"
            except xmlrpc.client.Fault as f:
                code = getattr(f, "faultCode", 0)
                if code == 403:
                    self.step("XML-RPC: نام کاربری یا رمز عبور اشتباه است.", "error", 20)
                else:
                    self.step(f"XML-RPC در دسترس نیست ({f.faultString[:80]}). تلاش با REST API…", "warn", 18)
            except Exception as e:
                self.step(f"XML-RPC در دسترس نیست ({str(e)[:80]}). تلاش با REST API…", "warn", 18)

        # --- REST ---
        res = self._rest("/wp-json/wp/v2/users/me?context=edit")
        data = self._rest_json(res)
        if res.ok and isinstance(data, dict) and data.get("id"):
            self.method = "rest"
            self._rest_user = data
            self.step("اتصال REST API موفق بود ✓ (Application Password تأیید شد)", "success", 20)
            return "rest"

        if not self.method:
            hint = ("برای REST باید «Application Password» بسازید: وردپرس → کاربران → پروفایل → Application Passwords. "
                    "همچنین اگر افزونه غیرفعال‌کننده XML-RPC دارید، آن را غیرفعال کنید.")
            self.step("احراز هویت ناموفق بود. " + hint, "error", 22)
        return None

    # ---------- اقدامات ----------
    def _analyze_home_for_keywords(self):
        try:
            home = self._fetch(self.site_url)
            parser = parse_html(home.text or "")
            text = parser.text
            heads = " ".join(h[1] for h in parser.headings)
            ranked = keywords.extract_keywords(text, heads, parser.title, limit=12)
            return ranked
        except Exception:
            return []

    def set_blog_description(self, ranked):
        """بهبود توضیح کوتاه سایت (شعار زیر عنوان)."""
        self.step("به‌روزرسانی توضیح کوتاه سایت…", "info", 30)
        brand = ""
        try:
            if self.method == "xmlrpc":
                opts = self._server.wp.getOptions(0, self.username, self.password, ["blog_title", "blog_description"])
                old = opts.get("blog_description", {}).get("value", "")
                brand = opts.get("blog_title", {}).get("value", "")
            else:
                res = self._rest("/wp-json/wp/v2/settings")
                data = self._rest_json(res) or {}
                old = data.get("description", "")
                brand = data.get("title", "")
        except Exception as e:
            self.step(f"خواندن تنظیمات ممکن نشد: {str(e)[:80]}", "error", 32)
            return None

        if old.strip():
            self.step(f"توضیح فعلی سایت: «{old[:80]}» — بدون تغییر حفظ شد (چسبیدن به محتوای فعلی برای سئو بهتر است).", "info", 34)
            return {"old": old, "new": old, "changed": False}

        new = keywords.generate_blog_description(ranked, brand)
        if not new:
            self.step("محتوای کافی برای تولید توضیح سایت پیدا نشد.", "warn", 34)
            return None
        ok = False
        try:
            if self.method == "xmlrpc":
                self._server.wp.setOptions(0, self.username, self.password, {"blog_description": new})
                ok = True
            else:
                res = self._rest("/wp-json/wp/v2/settings", method="POST", payload={"description": new})
                ok = res.ok
        except Exception as e:
            self.step(f"ثبت توضیح سایت ناموفق: {str(e)[:80]}", "error", 35)
        if ok:
            self.step(f"توضیح کوتاه سایت ثبت شد: «{new}» ✓", "success", 35)
        return {"old": old, "new": new, "changed": ok}

    def optimize_posts(self, actions, ranked):
        """بهینه‌سازی متا دیسکریپشن، کلمه کلیدی و تگ مطالب."""
        limit = int(actions.get("limit", 10))
        posts = []
        self.step(f"دریافت {limit} مطلب اخیر…", "info", 40)
        try:
            if self.method == "xmlrpc":
                posts = self._server.wp.getPosts(0, self.username, self.password,
                                                 {"number": limit, "post_type": "post", "post_status": "publish"})
            else:
                res = self._rest(f"/wp-json/wp/v2/posts?per_page={limit}&status=publish&context=edit&_fields=id,link,title,excerpt,content,tags")
                posts = self._rest_json(res) or []
                if not isinstance(posts, list):
                    posts = []
        except Exception as e:
            self.step(f"دریافت مطالب ناموفق: {str(e)[:90]}", "error", 42)
            return {"scanned": 0, "updated": 0, "failed": 0, "changes": []}

        summary = {"scanned": len(posts), "updated": 0, "failed": 0, "changes": []}
        top_kw = keywords.generate_focus_keyword(ranked) if ranked else ""
        existing_tags = []
        for i, post in enumerate(posts):
            if self.cancel():
                self.step("لغو شد — تغییرات تا اینجا ذخیره شده‌اند.", "warn", 90)
                break
            pid = post.get("post_id") or post.get("id")
            ptitle = (post.get("post_title") or post.get("title") or {})
            ptitle = ptitle.get("raw") or ptitle.get("rendered") if isinstance(ptitle, dict) else ptitle
            plink = post.get("link") or ""
            content = post.get("post_content") or (post.get("content") or {}).get("rendered", "") or ""
            excerpt = post.get("post_excerpt") or (post.get("excerpt") or {}).get("raw", "") or ""
            base_prog = 40 + int(i / max(len(posts), 1) * 45)

            try:
                parser = parse_html(content if "<" in content else f"<p>{content}</p>")
                text = parser.text or re.sub(r"<[^>]+>", " ", content)
                kws = keywords.extract_keywords(text, "", ptitle, limit=8)
                kw = kws[0]["term"] if kws else top_kw

                # اگر مطلب قبلاً توضیح دارد، دست نمی‌زنیم
                changes = []
                if excerpt.strip():
                    self.step(f"«{str(ptitle)[:50]}» — توضیح قبلاً دارد ✓", "info", base_prog)
                elif actions.get("meta_desc", True):
                    new_desc = keywords.generate_meta_description(text, fallback=str(ptitle))
                    if new_desc and self._apply_field(pid, FIELD_MAP, "meta_desc", new_desc, post):
                        changes.append(("متا دیسکریپشن", new_desc[:60] + "…"))

                if actions.get("focus_kw", True) and kw:
                    if self._apply_field(pid, FIELD_MAP, "focus_kw", kw, post):
                        changes.append(("کلمه کلیدی فوکوس", kw))

                if actions.get("tags", False) and kws:
                    n = self._apply_tags(pid, post, kws)
                    if n:
                        changes.append(("تگ پیشنهادی", f"{n} تگ جدید"))

                if changes:
                    summary["updated"] += 1
                    summary["changes"].append({"post_id": pid, "title": str(ptitle)[:60], "link": plink,
                                               "fields": [{"name": a, "value": b} for a, b in changes]})
                    detail = "، ".join(f"{a}: {b}" for a, b in changes)
                    self.step(f"«{str(ptitle)[:50]}» به‌روزرسانی شد — {detail} ✓", "success", base_prog + 1)
                else:
                    self.step(f"«{str(ptitle)[:50]}» — نیازی به تغییر نداشت ✓", "info", base_prog)
            except Exception as e:
                summary["failed"] += 1
                self.step(f"«{str(ptitle)[:50]}» خطا: {str(e)[:80]}", "error", base_prog)
            time.sleep(0.2)
        return summary

    def _apply_field(self, pid, fmap, kind, value, post):
        if self.method == "xmlrpc":
            existing = post.get("custom_fields") or []
            entry = None
            for plugin in ("yoast", "rankmath", "aioseo"):
                key = fmap[plugin][kind]
                for cf in existing:
                    if cf.get("key") == key:
                        entry = {"id": cf.get("ID") or cf.get("id"), "key": key, "value": value}
                        break
                if entry:
                    break
            payload = entry or {"key": fmap["yoast"][kind], "value": value}
            self._server.wp.editPost(0, self.username, self.password, pid, {"custom_fields": [payload]})
            return True
        # REST: تلاش برای meta استاندارد افزونه‌ها
        meta_payload = {}
        for plugin in ("yoast", "rankmath", "aioseo"):
            meta_payload[fmap[plugin][kind]] = value
        try:
            res = self._rest(f"/wp-json/wp/v2/posts/{pid}", method="POST", payload={"meta": meta_payload})
            if res.ok:
                return True
        except Exception:
            pass
        # fallback: excerpt برای توضیحات
        if kind == "meta_desc":
            res = self._rest(f"/wp-json/wp/v2/posts/{pid}", method="POST", payload={"excerpt": value})
            return res.ok
        return False

    def _apply_tags(self, pid, post, kws):
        try:
            if self.method == "xmlrpc":
                existing = [t.get("name", "") for t in (post.get("terms") or []) if t.get("taxonomy") == "post_tag"]
                new_tags = keywords.suggest_tags(kws, existing, count=3)
                if not new_tags:
                    return 0
                all_tags = existing + new_tags
                self._server.wp.editPost(0, self.username, self.password, pid,
                                         {"terms_names": {"post_tag": all_tags}})
                return len(new_tags)
            tag_ids = list(post.get("tags") or [])
            added = 0
            for t in keywords.suggest_tags(kws, [], count=3):
                res = self._rest("/wp-json/wp/v2/tags", method="POST", payload={"name": t})
                data = self._rest_json(res)
                if res.ok and data and data.get("id"):
                    tag_ids.append(data["id"])
                    added += 1
                elif res.status == 400 and data and data.get("code") == "term_exists":
                    tag_ids.append(data["data"]["term_id"])
            if added:
                self._rest(f"/wp-json/wp/v2/posts/{pid}", method="POST", payload={"tags": tag_ids})
            return added
        except Exception:
            return 0

    def check_technical(self):
        """بررسی سریع robots و sitemap پس از اقدامات."""
        self.step("بررسی نهایی robots.txt و sitemap…", "info", 92)
        out = {"robots": None, "sitemap": None}
        r = self._fetch(self.site_url.rstrip("/") + "/robots.txt", timeout=10)
        out["robots"] = bool(r.ok and "user-agent" in (r.text or "").lower())
        if not out["robots"]:
            self.step("robots.txt یافت نشد — توصیه: با افزونه سئو ایجادش کنید.", "warn", 94)
        else:
            self.step("robots.txt سالم است ✓", "success", 94)
        s = self._fetch(self.site_url.rstrip("/") + "/wp-sitemap.xml", timeout=10)
        if not (s.ok and "<loc" in (s.text or "").lower()):
            s = self._fetch(self.site_url.rstrip("/") + "/sitemap.xml", timeout=10)
        out["sitemap"] = bool(s.ok and "<loc" in (s.text or "").lower())
        if out["sitemap"]:
            self.step(f"نقشه سایت فعال است ✓ ({s.final_url.split('//')[-1][:60]})", "success", 96)
        else:
            self.step("نقشه سایت (sitemap.xml) یافت نشد — توصیه: فعال‌سازی sitemap در افزونه سئو.", "warn", 96)
        return out

    # ---------- اجرای کامل ----------
    def run(self, actions):
        ranked = self._analyze_home_for_keywords()
        if ranked:
            kws = "، ".join(k["term"] for k in ranked[:5])
            self.step(f"کلمات کلیدی اصلی سایت: {kws}", "info", 28)
        result = {"detection": self.detection, "method": self.method, "summary": {}, "changes": [],
                  "technical": {}, "recommendations": []}

        blog_desc_res = None
        if actions.get("blog_desc", True):
            blog_desc_res = self.set_blog_description(ranked)
            result["blog_description"] = blog_desc_res

        if actions.get("analyze_only"):
            self.step("حالت «فقط تحلیل بدون تغییر» فعال است — هیچ تغییری اعمال نمی‌شود.", "warn", 40)
            summary = {"scanned": 0, "updated": 0, "failed": 0, "changes": []}
        else:
            summary = self.optimize_posts(actions, ranked)
        result["summary"] = summary
        result["changes"] = summary.get("changes", [])
        result["technical"] = self.check_technical()

        s = summary
        self.step(
            f"پایان: {s.get('updated', 0)} مطلب به‌روزرسانی، {s.get('failed', 0)} خطا، "
            f"از {s.get('scanned', 0)} مطلب بررسی‌شده (روش: {self.method})",
            "success", 100)
        recs = []
        if not result["technical"].get("sitemap"):
            recs.append("فعال‌سازی نقشه سایت در افزونه سئو (Yoast/Rank Math → Settings → Sitemaps).")
        if not result["technical"].get("robots"):
            recs.append("ایجاد فایل robots.txt در ریشه سایت.")
        if not self.detection.get("seo_plugins"):
            recs.append("نصب یک افزونه سئو مانند Rank Math یا Yoast برای مدیریت پیشرفته متا و اسکیما.")
        recs.append("برای نتایج کامل‌تر، تحلیل دستی سایت را هم اجرا کنید و فایل گزارش HTML را دریافت کنید.")
        result["recommendations"] = recs
        return result


def run_auto_seo(params, step, cancel):
    """نقطه ورود تسک خودکار برای task manager."""
    wp = WordPressAutomation(
        site_url=params.get("site_url", ""),
        admin_url=params.get("admin_url", ""),
        username=params.get("username", ""),
        password=params.get("password", ""),
        verify_ssl=params.get("verify_ssl", True),
        step=step, cancel=cancel,
    )
    if params.get("admin_url"):
        step(f"بررسی آدرس پنل ادمین: {params['admin_url']}", "info", 5)
    wp.detect()
    if wp.cancel():
        raise InterruptedError("لغو توسط کاربر")
    if wp.detection.get("admin_reachable") is not True and params.get("admin_url"):
        step("پنل ادمین از بیرون تأیید نشد (احتمالاً با محافظت امنیتی مسدود است) — این مانع کار ما نیست.", "warn", 14)
    method = wp.authenticate()
    if not method:
        raise RuntimeError("ورود به سایت ناموفق بود — جزئیات در لاگ بالا آمده است.")
    actions = {
        "blog_desc": params.get("blog_desc", True),
        "meta_desc": params.get("meta_desc", True),
        "focus_kw": params.get("focus_kw", True),
        "tags": params.get("tags", False),
        "analyze_only": params.get("analyze_only", False),
        "limit": params.get("limit", 10),
    }
    return wp.run(actions)
