# -*- coding: utf-8 -*-
"""موتور تحلیل کامل SEO + GEO سایت — خزش، بررسی فنی، کلمات کلیدی، امتیازدهی و توصیه‌ها."""
import json
import re
import time
import urllib.parse

from . import fetcher, keywords
from .pageparser import parse_html

AI_BOTS = [
    {"bot": "GPTBot", "org": "OpenAI", "purpose": "جمع‌آوری داده برای آموزش مدل‌ها"},
    {"bot": "OAI-SearchBot", "org": "OpenAI", "purpose": "نمایش در جستجوی ChatGPT"},
    {"bot": "ChatGPT-User", "org": "OpenAI", "purpose": "مرور زنده به درخواست کاربر"},
    {"bot": "ClaudeBot", "org": "Anthropic", "purpose": "آموزش و به‌روزرسانی Claude"},
    {"bot": "PerplexityBot", "org": "Perplexity", "purpose": "موتور پاسخ Perplexity"},
    {"bot": "Google-Extended", "org": "Google", "purpose": "آموزش Gemini (غیر از جستجو)"},
    {"bot": "GoogleOther", "org": "Google", "purpose": "خزش عمومی Google AI"},
    {"bot": "Applebot-Extended", "org": "Apple", "purpose": "Apple Intelligence"},
    {"bot": "CCBot", "org": "Common Crawl", "purpose": "مجموعه داده متن‌باز"},
    {"bot": "Bytespider", "org": "ByteDance", "purpose": "خزنده TikTok/داده"},
    {"bot": "meta-externalagent", "org": "Meta", "purpose": "آموزش مدل‌های متا"},
    {"bot": "Amazonbot", "org": "Amazon", "purpose": "Alexa / مدل‌های آمازون"},
]

GEO_CANDIDATES = ["/llms.txt", "/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml", "/sitemap.xml.gz", "/rss.xml"]

IMG_EXT_RE = re.compile(r"\.(jpg|jpeg|png|gif|webp|svg|avif|bmp)(\?|#|$)", re.I)
LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
PERSIAN_DATE_RE = re.compile(r"(1[34]\d{2}/\d{1,2}/\d{1,2}|20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}\s+(فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)\s+(1[34]\d{2}|20\d{2}))")
QUESTION_RE = re.compile(r"(؟|\?|چه کسی|چگونه|چطور|چیست|چیه|آیا|چه زمانی|کجا|چرا|how to|what is|why|how does)", re.I)
QUESTION_WORDS = re.compile(r"(چگونه|چیست|چرا|کدام|کجا|آیا)", re.I)


class Checker:
    """جمع‌آوری بررسی‌ها با وضعیت و وزن برای امتیازدهی دسته‌بندی‌شده."""

    def __init__(self):
        self.items = []

    def add(self, key, label, status, category, detail="", rec="", priority="متوسط"):
        """status: pass | warn | fail"""
        self.items.append({"key": key, "label": label, "status": status, "category": category,
                           "detail": detail, "rec": rec, "priority": priority})

    def score(self, category):
        tot = w = 0
        weights = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
        for it in self.items:
            if it["category"] == category:
                tot += weights.get(it["status"], 0)
                w += 1
        return round(tot / w * 100) if w else 0


def analyze_site(url, pages=8, delay=0.3, verify_ssl=True, step=None, cancel=None, task_id=""):
    """تحلیل کامل سایت. step(msg, level, progress) برای نمایش زنده پیشرفت."""
    step = step or (lambda *a, **k: None)
    cancel = cancel or (lambda: False)
    started = time.time()

    def stopped():
        return cancel()

    res, url, err = fetcher.smart_fetch(url, verify_ssl=verify_ssl)
    if err:
        raise ValueError(err)
    step(f"شروع تحلیل {url}", "info", 3)
    if not res.ok or not res.text:
        raise RuntimeError(f"دسترسی به سایت ممکن نشد: {res.error or res.status}")
    if not fetcher.same_host(res.final_url, url):
        step(f"ریدایرکت به {res.final_url}", "info", 5)
    url = res.final_url
    base = fetcher.base_url(url)
    host = urllib.parse.urlsplit(url).netloc

    page = parse_html(res.text)
    html_size_kb = round(len(res.body) / 1024, 1)
    step(f"صفحه اصلی دریافت شد ({html_size_kb} کیلوبایت)", "success", 10)

    checks = Checker()

    # ---------- متا ----------
    title = page.title or ""
    desc = page.meta("description") or ""
    canonical = (page.links_by_rel("canonical") or [""])[0]
    viewport = page.meta("viewport")
    robots_meta = page.meta("robots")
    charset = page.meta("content-type", kind="http-equiv") or ("UTF-8" if "charset" in res.content_type else "")
    favicon = bool(page.links_by_rel("icon") or page.links_by_rel("shortcut icon"))

    og = page.og()
    tw = page.twitter()

    checks.add("title_exists", "وجود تگ عنوان (Title)", "pass" if title else "fail", "meta",
               title[:80] or "تگ title یافت نشد",
               "برای صفحه یک تگ <title> منحصربه‌فرد و توصیفی قرار دهید." if not title else "", "بالا")
    tlen = len(title)
    checks.add("title_len", "طول عنوان (۳۰ تا ۶۰ کاراکتر)",
               "pass" if 30 <= tlen <= 60 else ("warn" if tlen else "fail"), "meta",
               f"{tlen} کاراکتر",
               "عنوان را بین ۳۰ تا ۶۰ کاراکتر بنویسید؛ کلمه کلیدی اصلی را در ابتدای آن بیاورید."
               if not (30 <= tlen <= 60) and title else "", "بالا")
    dlen = len(desc)
    checks.add("desc_exists", "وجود متا دیسکریپشن", "pass" if desc else "fail", "meta",
               desc[:80] or "متا دیسکریپشن یافت نشد",
               "متا دیسکریپشن ۷۰ تا ۱۶۰ کاراکتری با کلمه کلیدی و دعوت به اقدام بنویسید." if not desc else "", "بالا")
    checks.add("desc_len", "طول متا دیسکریپشن (۷۰ تا ۱۶۰)",
               "pass" if 70 <= dlen <= 160 else ("warn" if dlen else "fail"), "meta",
               f"{dlen} کاراکتر",
               "توضیحات را در بازه ۷۰ تا ۱۶۰ کاراکتر تنظیم کنید تا در نتایج گوگل کامل نمایش داده شود."
               if desc and not (70 <= dlen <= 160) else "", "متوسط")
    checks.add("canonical", "تگ Canonical", "pass" if canonical else "warn", "meta",
               canonical or "یافت نشد", "تگ canonical برای جلوگیری از محتوای تکراری ضروری است." if not canonical else "", "متوسط")
    checks.add("og_tags", "تگ‌های Open Graph (اشتراک‌گذاری)", "pass" if og else "warn", "meta",
               f"{len(og)} تگ", "تگ‌های og:title و og:description و og:image برای نمایش زیبا در شبکه‌های اجتماعی اضافه کنید." if not og else "", "پایین")
    checks.add("twitter_tags", "تگ‌های Twitter Card", "pass" if tw else "warn", "meta",
               f"{len(tw)} تگ", "برای نمایش بهتر لینک در توییتر، تگ‌های twitter:card و twitter:title را اضافه کنید." if not tw else "", "پایین")

    # ---------- محتوا ----------
    body_text = page.text
    words = len(keywords.tokenize(body_text))
    headings = page.headings
    h1 = [h for h in headings if h[0] == "h1"]
    h2 = [h for h in headings if h[0] == "h2"]
    text_ratio = round(len(body_text) / max(len(res.text), 1) * 100, 1)
    paras = page.paragraphs
    avg_para = round(sum(len(keywords.tokenize(p)) for p in paras) / len(paras)) if paras else 0

    lists_count = res.text.lower().count("<li")
    tables = page.counts.get("table", 0)

    checks.add("word_count", "حجم محتوای متنی (حداقل ۳۰۰ کلمه)",
               "pass" if words >= 300 else ("warn" if words >= 120 else "fail"), "content",
               f"{words} کلمه", "محتوای صفحه را به حداقل ۳۰۰ تا ۸۰۰ کلمه مفید برسانید؛ محتوای عمیق‌تر رتبه بهتری می‌گیرد."
               if words < 300 else "", "بالا")
    checks.add("h1", "دقیقاً یک H1 در صفحه", "pass" if len(h1) == 1 else "fail", "content",
               f"{len(h1)} عدد", "دقیقاً یک تگ H1 شامل کلمه کلیدی اصلی داشته باشید." if len(h1) != 1 else "", "بالا")
    checks.add("h2", "استفاده از H2 برای بخش‌بندی", "pass" if len(h2) >= 2 else "warn", "content",
               f"{len(h2)} عدد", "ساختار محتوا را با تیترهای H2 و H3 بخش‌بندی کنید." if len(h2) < 2 else "", "متوسط")
    checks.add("text_ratio", "نسبت متن به کد (بیش از ۱۰٪)", "pass" if text_ratio >= 10 else "warn", "content",
               f"{text_ratio}٪", "حجم کد و اسکریپت‌های اضافی را کم و متن مفید صفحه را بیشتر کنید." if text_ratio < 10 else "", "پایین")
    checks.add("paragraphs", "پاراگراف‌های کوتاه و خوانا", "pass" if 8 <= avg_para <= 70 else "warn", "content",
               f"میانگین {avg_para} کلمه", "پاراگراف‌ها را کوتاه‌تر (حدود ۲۰ تا ۵۰ کلمه) بنویسید تا خوانایی بالا برود."
               if avg_para > 70 else ("" if avg_para >= 8 else "محتوای متنی بیشتری در قالب پاراگراف اضافه کنید."), "پایین")
    checks.add("lists", "استفاده از لیست و جدول", "pass" if (lists_count or tables) else "warn", "content",
               f"لیست: {lists_count}، جدول: {tables}", "از لیست‌های گلوله‌ای و جدول برای خوانایی بهتر و شانس ویژگی اسنیپت گوگل استفاده کنید." if not (lists_count or tables) else "", "پایین")

    # ---------- ساختار و لینک‌ها ----------
    internal, external, nofollow, empty_anchor = [], [], 0, 0
    seen = set()
    for a in page.anchors:
        href = a.get("href", "").strip()
        if not fetcher.is_crawlable(href):
            continue
        href_abs = urllib.parse.urljoin(url, href)
        if fetcher.same_host(href_abs, url):
            internal.append(href_abs)
        else:
            external.append(href_abs)
        if "nofollow" in a.get("rel", ""):
            nofollow += 1
        if not a.get("text"):
            empty_anchor += 1
        seen.add(href_abs)
    internal = list(dict.fromkeys(internal))
    external = list(dict.fromkeys(external))

    images = page.images
    no_alt = [i for i in images if not i["alt"]]
    alt_ratio = round((len(images) - len(no_alt)) / len(images) * 100) if images else 100
    lazy = sum(1 for i in images if i.get("loading") == "lazy")

    iframes = page.counts.get("iframe", 0)

    checks.add("internal_links", "لینک‌سازی داخلی (حداقل ۱۰)", "pass" if len(internal) >= 10 else "warn", "structure",
               f"{len(internal)} لینک داخلی", "با لینک‌دهی داخلی به صفحات مهم، اعتبار صفحه را در سایت پخش کنید." if len(internal) < 10 else "", "متوسط")
    checks.add("external_links", "لینک به منابع معتبر خارجی", "pass" if len(external) >= 2 else "warn", "structure",
               f"{len(external)} لینک خارجی", "چند لینک خارجی به منابع معتبر (با rel=nofollow در صورت نیاز) اعتماد صفحه را بالا می‌برد." if len(external) < 2 else "", "پایین")
    checks.add("empty_anchor", "لینک‌ها دارای متن لنگر", "pass" if empty_anchor == 0 else "warn", "structure",
               f"{empty_anchor} لینک بدون متن", "به لینک‌های تصویری/خالی متن alt یا title معنادار بدهید." if empty_anchor else "", "پایین")
    checks.add("image_alt", "متن جایگزین (alt) تصاویر", "pass" if alt_ratio >= 90 else ("warn" if alt_ratio >= 60 else "fail"), "structure",
               f"{alt_ratio}٪ دارای alt", "برای تمام تصاویر alt توصیفی حاوی کلمه کلیدی مرتبط بنویسید." if alt_ratio < 90 else "", "بالا")
    checks.add("iframes", "تعداد iframe کم", "pass" if iframes <= 2 else "warn", "structure",
               f"{iframes} عدد", "iframe‌های اضافی سرعت و امنیت را کم می‌کنند؛ در صورت امکان حذف کنید." if iframes > 2 else "", "پایین")

    # ---------- تصاویر بزرگ ----------
    large_imgs = [i for i in images if IMG_EXT_RE.search(i.get("src", ""))]

    # ---------- فنی ----------
    is_https = url.lower().startswith("https://")
    server_hdr = res.headers.get("Server", "")
    compression = (res.headers.get("Content-Encoding") or "").lower()
    cache_ctl = res.headers.get("Cache-Control", "")
    hsts = res.headers.get("Strict-Transport-Security", "")
    ttfb = res.ttfb_ms

    mixed = 0
    if is_https:
        for i in images:
            if i.get("src", "").startswith("http://"):
                mixed += 1
        for h in external + internal:
            if h.startswith("http://"):
                mixed += 1

    robots_txt = fetcher.fetch(base + "/robots.txt", verify_ssl=verify_ssl)
    robots_ok = robots_txt.ok and "user-agent" in robots_txt.text.lower()
    sitemap = check_sitemap(base, robots_txt.text if robots_ok else "", verify_ssl)
    llms = fetcher.fetch(base + "/llms.txt", verify_ssl=verify_ssl)
    llms_ok = llms.ok and len(llms.text.strip()) > 0

    # نمونه‌برداری لینک‌های خراب
    step("بررسی سلامت لینک‌ها…", "info", 35)
    broken = check_broken_links(internal[:6] + external[:4], verify_ssl, cancel)
    broken_count = len(broken)

    checks.add("https", "استفاده از HTTPS", "pass" if is_https else "fail", "technical",
               "فعال" if is_https else "غیرفعال", "گواهی SSL نصب کنید و کل سایت را به https ریدایرکت کنید." if not is_https else "", "بالا")
    checks.add("robots", "وجود robots.txt معتبر", "pass" if robots_ok else "warn", "technical",
               robots_txt.text.splitlines()[0][:40] if robots_ok else "یافت نشد", "فایل robots.txt در ریشه سایت قرار دهید." if not robots_ok else "", "متوسط")
    checks.add("sitemap", "نقشه سایت (sitemap.xml)", "pass" if sitemap["found"] else "fail", "technical",
               sitemap.get("url", "یافت نشد") + (f" — {sitemap.get('url_count', 0)} آدرس" if sitemap["found"] else ""),
               "نقشه سایت XML ایجاد و در robots.txt معرفی کنید (در وردپرس افزونه سئو این کار را خودکار می‌کند)." if not sitemap["found"] else "", "بالا")
    checks.add("favicon", "آیکون سایت (Favicon)", "pass" if favicon else "warn", "technical",
               "وجود دارد" if favicon else "یافت نشد", "favicon سایت را تنظیم کنید (در نتایج موبایل گوگل نمایش داده می‌شود)." if not favicon else "", "پایین")
    checks.add("viewport", "متای Viewport (موبایل‌فرندلی)", "pass" if viewport else "fail", "technical",
               viewport[:40] or "یافت نشد", "تگ viewport برای نمایش صحیح در موبایل ضروری است." if not viewport else "", "بالا")
    checks.add("lang", "تعیین زبان صفحه (lang)", "pass" if page.lang else "warn", "technical",
               page.lang or "تعیین نشده", "ویژگی lang=\"fa\" را به تگ html اضافه کنید." if not page.lang else "", "متوسط")
    checks.add("charset", "تعیین انکودینگ (UTF-8)", "pass" if charset else "warn", "technical",
               charset or "نامشخص", "انکودینگ UTF-8 را در هدر یا متا تعیین کنید." if not charset else "", "پایین")
    checks.add("compression", "فشرده‌سازی (gzip/brotli)", "pass" if compression else "warn", "technical",
               compression or "خاموش", "فشرده‌سازی gzip یا brotli را در هاست فعال کنید تا سرعت بارگذاری چند برابر شود." if not compression else "", "متوسط")
    checks.add("ttfb", "زمان پاسخ سرور (زیر ۸۰۰ms)", "pass" if ttfb <= 800 else ("warn" if ttfb <= 1500 else "fail"), "technical",
               f"{int(ttfb)} میلی‌ثانیه", "با کش سمت سرور (WP Rocket/LiteSpeed) یا CDN، زمان پاسخ سرور را زیر ۸۰۰ms بیاورید." if ttfb > 800 else "", "بالا")
    checks.add("page_size", "حجم HTML (زیر ۵۰۰KB)", "pass" if html_size_kb <= 500 else "warn", "technical",
               f"{html_size_kb} KB", "حجم HTML را با حذف کدهای بی‌استفاده و minify کاهش دهید." if html_size_kb > 500 else "", "پایین")
    checks.add("mixed_content", "نبود محتوای ناامن (Mixed Content)", "pass" if mixed == 0 else "fail", "technical",
               f"{mixed} مورد", "تمام منابع http:// را به https:// تغییر دهید؛ مرورگرها آن‌ها را مسدود می‌کنند." if mixed else "", "بالا")
    checks.add("hsts", "هدر امنیتی HSTS", "pass" if hsts else "warn", "technical",
               "فعال" if hsts else "غیرفعال", "هدر Strict-Transport-Security را در تنظیمات هاست/CDN فعال کنید." if not hsts else "", "پایین")
    checks.add("broken_links", "سلامت لینک‌های نمونه", "pass" if broken_count == 0 else ("warn" if broken_count <= 2 else "fail"), "technical",
               f"{broken_count} لینک خراب از نمونه", "لینک‌های خراب شناسایی‌شده را اصلاح یا حذف کنید." if broken_count else "", "متوسط")

    # ---------- داده ساختاریافته ----------
    ld_types = page.structured_types()
    microdata = len(re.findall(r"itemscope", res.text, re.I))
    has_faq_schema = any(t.lower() in ("faqpage", "qapage") for t in ld_types)
    has_org = any(t.lower() in ("organization", "localbusiness", "person", "store") for t in ld_types)
    has_breadcrumb = "breadcrumblist" in [t.lower() for t in ld_types]

    checks.add("schema", "داده ساختاریافته (Schema.org)", "pass" if ld_types or microdata else "fail", "geo",
               ("، ".join(sorted(set(ld_types))[:6]) or "—") + (f" + {microdata} itemscope" if microdata else ""),
               "داده ساختاریافته JSON-LD (Organization، Article، Breadcrumb) اضافه کنید؛ برای GEO حیاتی است."
               if not ld_types and not microdata else "", "بالا")
    checks.add("breadcrumb", "Breadcrumb Schema", "pass" if has_breadcrumb else "warn", "geo",
               "وجود دارد" if has_breadcrumb else "یافت نشد",
               "مسیر راهنما (breadcrumb) با schema اضافه کنید تا در نتایج گوگل و AI نمایش بهتری داشته باشید." if not has_breadcrumb else "", "متوسط")

    # ---------- GEO ----------
    robots_data = parse_robots(robots_txt.text if robots_ok else "")
    bots = []
    for b in AI_BOTS:
        bots.append({**b, "status": bot_status(b["bot"], robots_data)})
    allowed_bots = sum(1 for b in bots if b["status"] == "allowed")
    blocked_bots = sum(1 for b in bots if b["status"] == "blocked")

    faq_like = bool(has_faq_schema) or page.counts.get("details", 0) >= 2 or any(
        QUESTION_RE.search(h[1] or "") for h in headings)
    semantic_ok = len(page.semantic & {"main", "article", "header", "nav", "footer"}) >= 3
    author = page.meta("author") or page.structured_author() or ("rel=author" in res.text.lower())
    dates = page.meta("article:published_time") or page.meta("article:modified_time")
    time_tags = page.counts.get("time", 0)
    date_in_text = bool(PERSIAN_DATE_RE.search(body_text))
    has_date = bool(dates or time_tags or date_in_text)
    quotable = sum(1 for p in paras if 15 <= len(keywords.tokenize(p)) <= 60)
    quotable_ratio = round(quotable / len(paras) * 100) if paras else 0

    checks.add("ai_bots", "دسترسی ربات‌های هوش مصنوعی", "pass" if allowed_bots >= 6 else ("warn" if blocked_bots == 0 else "fail"), "geo",
               f"{allowed_bots} مجاز، {blocked_bots} مسدود از {len(bots)} ربات",
               "در robots.txt ربات‌های هوش مصنوعی (GPTBot، ClaudeBot و…) را مسدود نکنید تا در پاسخ‌های AI نمایش داده شوید." if blocked_bots or allowed_bots < 6 else "", "بالا")
    checks.add("llms_txt", "فایل llms.txt", "pass" if llms_ok else "warn", "geo",
               "وجود دارد" if llms_ok else "یافت نشد",
               "فایل llms.txt در ریشه سایت بسازید و خلاصه محتوای کلیدی سایت را برای مدل‌های AI معرفی کنید." if not llms_ok else "", "متوسط")
    checks.add("faq", "محتوای پرسش و پاسخ (FAQ)", "pass" if faq_like else "warn", "geo",
               "شناسایی شد" if faq_like else "یافت نشد",
               "بخش پرسش‌های متداول با Schema نوع FAQPage اضافه کنید؛ بیشترین شانس نقل‌قول در پاسخ‌های AI را دارد." if not faq_like else "", "بالا")
    checks.add("semantic", "HTML معنایی (main/article/nav)", "pass" if semantic_ok else "warn", "geo",
               "، ".join(sorted(page.semantic)) or "—",
               "از تگ‌های معنایی main و article و nav و header استفاده کنید تا ساختار صفحه برای موتورها روشن باشد." if not semantic_ok else "", "متوسط")
    checks.add("author", "مشخص بودن نویسنده/هویت", "pass" if author else "warn", "geo",
               str(author) if isinstance(author, str) and author else "یافت نشد",
               "نام نویسنده را با متاتگ author یا Schema مشخص کنید؛ اعتبار محتوا (E-E-A-T) را بالا می‌برد." if not author else "", "متوسط")
    checks.add("freshness", "نمایش تاریخ انتشار/به‌روزرسانی", "pass" if has_date else "warn", "geo",
               dates[:25] if dates else ("تگ time" if time_tags else ("در متن" if date_in_text else "یافت نشد")),
               "تاریخ انتشار و به‌روزرسانی را با تگ <time> و schema نمایش دهید؛ تازگی محتوا در GEO مهم است." if not has_date else "", "متوسط")
    checks.add("quotable", "پاراگراف‌های قابل نقل‌قول", "pass" if quotable_ratio >= 40 else "warn", "geo",
               f"{quotable_ratio}٪ پاراگراف‌های مناسب",
               "پاسخ‌های مستقیم و کوتاه (۱۵ تا ۶۰ کلمه) بعد از هر تیتر بنویسید تا AI بتواند آن‌ها را نقل کند." if quotable_ratio < 40 else "", "متوسط")

    # ---------- خزش صفحات داخلی ----------
    crawl_pages = []
    if pages > 1:
        step(f"خزش تا {pages} صفحه داخلی…", "info", 45)
        candidates = []
        for u in internal:
            if u.rstrip("/") == url.rstrip("/"):
                continue
            if u in seen or len(urllib.parse.urlsplit(u).query) > 40:
                continue
            candidates.append(u)
        # اولویت با صفحاتی که در منو/بالای صفحه آمده‌اند
        candidates = list(dict.fromkeys(candidates))[:pages]
        for i, u in enumerate(candidates):
            if stopped():
                step("تحلیل توسط کاربر لغو شد", "warn", 100)
                raise InterruptedError("لغو توسط کاربر")
            if stopped():
                break
            pr = fetcher.fetch(u, verify_ssl=verify_ssl, timeout=12)
            info = {"url": u, "status": pr.status, "ok": pr.ok and pr.status < 400}
            if pr.ok and pr.is_html:
                pp = parse_html(pr.text)
                w = len(keywords.tokenize(pp.text))
                info.update({"title": pp.title[:70], "title_len": len(pp.title),
                             "has_desc": bool(pp.meta("description")), "words": w,
                             "h1_count": sum(1 for h in pp.headings if h[0] == "h1"),
                             "images": pp.counts.get("img", 0),
                             "no_alt": sum(1 for im in pp.images if not im["alt"])})
            crawl_pages.append(info)
            step(f"بررسی {u.split('//')[-1][:60]} — {'✓' if info['ok'] else '✗'}", "info", 45 + int((i + 1) / max(len(candidates), 1) * 20))
            time.sleep(delay)

    pages_with_issues = [p for p in crawl_pages if not p.get("ok") or p.get("h1_count") != 1 or not p.get("has_desc") or not p.get("title")]
    if crawl_pages:
        ok_pages = sum(1 for p in crawl_pages if p.get("ok"))
        checks.add("crawl_status", "دسترس‌پذیری صفحات داخلی", "pass" if ok_pages == len(crawl_pages) else "warn", "technical",
                   f"{ok_pages} از {len(crawl_pages)} صفحه سالم", "صفحاتی که خطا می‌دهند را اصلاح کنید." if ok_pages < len(crawl_pages) else "", "بالا")
        checks.add("site_meta_consistency", "عنوان و توضیحات صفحات داخلی", "pass" if not pages_with_issues else "warn", "meta",
                   f"{len(crawl_pages) - len(pages_with_issues)} از {len(crawl_pages)} صفحه استاندارد",
                   "برای صفحات فهرست‌شده، عنوان یکتا و متا دیسکریپشن بنویسید." if pages_with_issues else "", "متوسط")

    # ---------- کلمات کلیدی ----------
    step("استخراج کلمات کلیدی…", "info", 70)
    headings_text = " ".join(h[1] for h in headings)
    ranked = keywords.extract_keywords(body_text, headings_text, title, limit=20)
    primary = [k["term"] for k in ranked if " " not in k["term"]][:5]
    secondary = [k["term"] for k in ranked if " " in k["term"]][:5]
    suggested_desc = keywords.generate_meta_description(body_text, desc)
    suggested_title = title
    if title and len(title) > 60:
        suggested_title = title[:57].rsplit(" ", 1)[0] + "…"
    elif not title and primary:
        suggested_title = f"{primary[0].title()} | {host}"

    # ---------- امتیاز نهایی ----------
    cat_scores = {}
    cat_weights = {"meta": 20, "content": 20, "technical": 25, "geo": 15, "structure": 10}
    for c, w in cat_weights.items():
        cat_scores[c] = {"score": checks.score(c), "weight": w}
    total = round(sum(v["score"] * v["weight"] for v in cat_scores.values()) / sum(cat_weights.values()))
    grade = ("A+" if total >= 90 else "A" if total >= 80 else "B" if total >= 70 else
             "C" if total >= 60 else "D" if total >= 50 else "F")

    # ---------- توصیه‌ها ----------
    recs = []
    order = {"بالا": 0, "متوسط": 1, "پایین": 2}
    for it in checks.items:
        if it["status"] != "pass" and it["rec"]:
            recs.append({"title": it["label"], "detail": it["rec"], "priority": it["priority"], "category": it["category"]})
    recs.sort(key=lambda r: order.get(r["priority"], 3))

    step("تدوین گزارش نهایی…", "info", 92)

    cms_guess = guess_cms(page, res.text)

    report = {
        "task_id": task_id,
        "type": "analyze",
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_sec": round(time.time() - started, 1),
        "input": {"url": url, "pages": pages},
        "site": {"url": url, "host": host, "status": res.status, "https": is_https, "ttfb_ms": int(ttfb),
                 "total_ms": int(res.elapsed_ms), "html_size_kb": html_size_kb, "compression": compression or "—",
                 "server": server_hdr or "—", "cms": cms_guess, "charset": charset or "—"},
        "score": {"total": total, "grade": grade, "categories": {
            "meta": {"score": cat_scores["meta"]["score"], "label": "متا و عنوان‌ها"},
            "content": {"score": cat_scores["content"]["score"], "label": "محتوا"},
            "technical": {"score": cat_scores["technical"]["score"], "label": "فنی"},
            "geo": {"score": cat_scores["geo"]["score"], "label": "GEO (هوش مصنوعی)"},
            "structure": {"score": cat_scores["structure"]["score"], "label": "ساختار و لینک‌ها"},
        }},
        "meta": {"title": title, "title_len": tlen, "description": desc, "description_len": dlen,
                 "keywords_meta": page.meta("keywords"), "canonical": canonical, "viewport": viewport,
                 "lang": page.lang, "favicon": favicon, "charset": charset, "robots_meta": robots_meta},
        "social": {"og": og, "twitter": tw},
        "headings": {"list": headings[:30], "h1_count": len(h1), "h2_count": len(h2)},
        "content": {"words": words, "text_ratio": text_ratio, "paragraphs": len(paras),
                    "avg_para_words": avg_para, "lists": lists_count, "tables": tables},
        "links": {"internal_count": len(internal), "external_count": len(external), "nofollow": nofollow,
                  "broken": broken, "internal_samples": internal[:12]},
        "images": {"total": len(images), "no_alt": len(no_alt), "alt_ratio": alt_ratio, "lazy": lazy,
                   "missing_alt_samples": [i["src"][:80] for i in no_alt[:8]]},
        "technical": {"robots_txt": robots_ok, "sitemap": sitemap, "llms_txt": llms_ok,
                      "hsts": bool(hsts), "cache": cache_ctl, "mixed_content": mixed,
                      "broken_count": broken_count},
        "structured": {"ldjson_count": len(page.ldjson), "types": sorted(set(ld_types)),
                       "has_faq": has_faq_schema, "has_organization": has_org,
                       "has_breadcrumb": has_breadcrumb, "microdata": microdata},
        "geo": {"ai_bots": bots, "allowed": allowed_bots, "blocked": blocked_bots,
                "llms_txt": llms_ok, "faq_like": faq_like, "semantic": sorted(page.semantic),
                "author": author if isinstance(author, str) else bool(author),
                "has_date": has_date, "date_value": dates, "quotable_ratio": quotable_ratio},
        "keywords": {"table": ranked, "primary": primary, "secondary": secondary,
                     "suggested_title": suggested_title, "suggested_description": suggested_desc,
                     "meta_keywords_tag": page.meta("keywords")},
        "serp": {"title": title or suggested_title, "description": desc or suggested_desc, "url": url},
        "crawl": {"requested": pages, "crawled": len(crawl_pages), "pages": crawl_pages},
        "recommendations": recs,
        "checks": checks.items,
        "performance_tips": _gen_perf_tips(html_size_kb, ttfb, compression, lazy, large_imgs),
    }
    step("تحلیل کامل شد ✓", "success", 100)
    return report


def guess_cms(page, html):
    gen = (page.meta("generator") or "").lower()
    if "wordpress" in gen:
        return "WordPress"
    if "shopify" in gen or "cdn.shopify" in html:
        return "Shopify"
    if "wix" in gen or "static.parastorage" in html:
        return "Wix"
    if "joomla" in gen:
        return "Joomla"
    if "drupal" in gen:
        return "Drupal"
    if "wp-content" in html or "wp-includes" in html:
        return "WordPress"
    return "نامشخص"


def parse_robots(text):
    groups = {}
    sitemaps = []
    agents = []
    last_directive = False
    for line in (text or "").splitlines():
        line = line.split("#")[0].strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip().lower(), v.strip()
        if k == "user-agent":
            if last_directive:
                agents = []
            agents.append(v)
            last_directive = False
        elif k == "sitemap":
            sitemaps.append(v)
        elif k in ("allow", "disallow", "crawl-delay"):
            for a in agents:
                g = groups.setdefault(a, {"allow": [], "disallow": [], "delay": None})
                if k == "crawl-delay":
                    g["delay"] = v
                else:
                    g[k].append(v)
            last_directive = True
    return {"groups": groups, "sitemaps": sitemaps}


def bot_status(bot, robots_data):
    g = robots_data["groups"]
    star = g.get("*", {"allow": [], "disallow": []})
    own = g.get(bot)
    if own:
        if "/" in own["disallow"]:
            return "blocked"
        if "/" in own["allow"]:
            return "allowed"
    if "/" in star["disallow"] and "/" not in star["allow"]:
        return "blocked"
    return "not_mentioned"


def check_sitemap(base, robots_text, verify_ssl):
    sitemaps = parse_robots(robots_text)["sitemaps"] if robots_text else []
    if not sitemaps:
        sitemaps = [base + c for c in GEO_CANDIDATES if c.startswith("/sitemap") or c == "/rss.xml"][:3]
        sitemaps = [s for s in [base + "/sitemap.xml", base + "/sitemap_index.xml", base + "/wp-sitemap.xml"]]
    for s in sitemaps[:3]:
        r = fetcher.fetch(s, verify_ssl=verify_ssl, timeout=12)
        if r.ok and ("<loc" in r.text.lower() or "sitemapindex" in r.text.lower()):
            return {"found": True, "url": s, "url_count": len(LOC_RE.findall(r.text))}
    return {"found": False, "url": "", "url_count": 0}


def _gen_perf_tips(html_size_kb, ttfb_ms, compression, lazy_count, large_imgs):
    """تولید نکات عملکردی بر اساس دادههای صفحه."""
    tips = []
    if html_size_kb > 300:
        tips.append(f"حجم HTML زیاد است ({html_size_kb}KB) — کدهای اضافی را حذف یا minify کنید.")
    if ttfb_ms > 800:
        tips.append(f"زمان پاسخ سرور کند است ({int(ttfb_ms)}ms) — از کش سمت سرور استفاده کنید.")
    if not compression:
        tips.append("فشردهسازی gzip/brotli فعال نیست — آن را در هاست فعال کنید.")
    if large_imgs:
        tips.append(f"{len(large_imgs)} تصویر بزرگ شناسایی شد — فشرده‌سازی و تبدیل به WebP پیشنهاد میشود.")
    if lazy_count == 0 and len([i for i in large_imgs]) > 0:
        tips.append("برای تصاویر بزرگ از loading=lazy استفاده کنید.")
    return tips


def check_broken_links(links, verify_ssl, cancel):
    broken = []
    for u in links[:10]:
        if cancel():
            break
        r = fetcher.fetch(u, method="HEAD", verify_ssl=verify_ssl, timeout=10)
        if not r.ok or r.status >= 400:
            if r.status in (403, 405, 429, 501, 404, 410) or not r.ok:
                r2 = fetcher.fetch(u, verify_ssl=verify_ssl, timeout=10)
                if not r2.ok or r2.status >= 400:
                    broken.append({"url": u[:90], "status": r2.status or r.status})
        time.sleep(0.15)
    return broken


def build_auto_report_summary(auto_result):
    """خلاصه متنی نتیجه سئوی خودکار برای تاریخچه."""
    s = auto_result.get("summary", {})
    return f"{s.get('posts_updated', 0)} مطلب به‌روزرسانی شد"
