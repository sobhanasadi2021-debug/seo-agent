# -*- coding: utf-8 -*-
"""تولید گزارش HTML و متنی مستقل (قابل دانلود و چاپ)."""
import csv
import html as html_mod
import io


def esc(s):
    return html_mod.escape(str(s or ""))


STATUS_FA = {"pass": ("✓", "#16a34a"), "warn": ("!", "#d97706"), "fail": ("✗", "#dc2626")}


def build_html_report(report):
    """گزارش کامل تحلیل به‌صورت فایل HTML مستقل RTL فارسی."""
    score = report.get("score", {})
    site = report.get("site", {})
    total = score.get("total", 0)
    grade = score.get("grade", "-")
    color = "#16a34a" if total >= 80 else ("#d97706" if total >= 60 else "#dc2626")

    cats_html = ""
    for key, c in score.get("categories", {}).items():
        pct = c.get("score", 0)
        cc = "#16a34a" if pct >= 80 else ("#d97706" if pct >= 60 else "#dc2626")
        cats_html += f"""
        <div class="cat"><div class="cat-head"><span>{esc(c.get('label', key))}</span><b style="color:{cc}">{pct}٪</b></div>
        <div class="bar"><div class="bar-fill" style="width:{pct}%;background:{cc}"></div></div></div>"""

    checks_html = ""
    for it in report.get("checks", []):
        icon, c = STATUS_FA.get(it["status"], ("•", "#888"))
        checks_html += f"""<tr><td><span class="st" style="background:{c}1a;color:{c}">{icon}</span></td>
        <td><b>{esc(it['label'])}</b><div class="muted">{esc(it['detail'])}</div></td>
        <td>{esc(dict(meta='متا', content='محتوا', technical='فنی', geo='GEO', structure='ساختار').get(it['category'], it['category']))}</td></tr>"""

    kw_html = ""
    for k in report.get("keywords", {}).get("table", [])[:15]:
        kw_html += f"<tr><td>{esc(k['term'])}</td><td>{k['count']}</td><td>{round(k['score'], 1)}</td></tr>"

    geo_html = ""
    for b in report.get("geo", {}).get("ai_bots", []):
        st = b["status"]
        st_fa = {"allowed": ("مجاز", "#16a34a"), "blocked": ("مسدود", "#dc2626"), "not_mentioned": ("ذکر نشده", "#888")}.get(st, (st, "#888"))
        geo_html += f"""<tr><td><b>{esc(b['bot'])}</b><div class="muted">{esc(b['org'])}</div></td>
        <td>{esc(b['purpose'])}</td><td style="color:{st_fa[1]}"><b>{st_fa[0]}</b></td></tr>"""

    recs_html = ""
    pr_fa = {"بالا": "#dc2626", "متوسط": "#d97706", "پایین": "#2563eb"}
    for i, r in enumerate(report.get("recommendations", []), 1):
        c = pr_fa.get(r.get("priority", ""), "#888")
        recs_html += f"""<div class="rec"><div class="rec-head"><span class="num">{i}</span>
        <b>{esc(r['title'])}</b><span class="badge" style="background:{c}1a;color:{c}">{esc(r['priority'])}</span></div>
        <p>{esc(r['detail'])}</p></div>"""

    crawl_rows = ""
    for p in report.get("crawl", {}).get("pages", []):
        crawl_rows += (f"<tr><td>{esc(p.get('url', '')[:70])}</td><td>{p.get('status')}</td>"
                       f"<td>{p.get('words', '—')}</td><td>{p.get('h1_count', '—')}</td>"
                       f"<td>{'دارد' if p.get('has_desc') else 'ندارد'}</td></tr>")

    serp = report.get("serp", {})
    kws = report.get("keywords", {})
    site_rows = f"""
    <tr><td>آدرس</td><td dir="ltr">{esc(site.get('url'))}</td></tr>
    <tr><td>پلتفرم</td><td>{esc(site.get('cms'))}</td></tr>
    <tr><td>پروتکل</td><td>{'HTTPS ✓' if site.get('https') else 'HTTP (ناامن)'}</td></tr>
    <tr><td>زمان پاسخ سرور</td><td>{site.get('ttfb_ms')} ms</td></tr>
    <tr><td>حجم HTML</td><td>{site.get('html_size_kb')} KB</td></tr>
    <tr><td>فشرده‌سازی</td><td>{esc(site.get('compression'))}</td></tr>
    <tr><td>نقشه سایت</td><td>{'✓ ' + esc(report.get('technical', {}).get('sitemap', {}).get('url', '')) if report.get('technical', {}).get('sitemap', {}).get('found') else 'یافت نشد'}</td></tr>"""

    # نقاط عملکردی
    perf_tips = report.get("performance_tips", [])
    perf_html = ""
    if perf_tips:
        tips_rows = "".join(f'<div class="rec" style="border-right:3px solid #fbbf24"><b>⚡ {esc(t)}</b></div>' for t in perf_tips)
        perf_html = f'<div class="card"><h2>⚡ نکات عملکردی</h2><div style="display:flex;flex-direction:column;gap:8px">{tips_rows}</div></div>'

    css = """
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:Vazirmatn,'Segoe UI',Tahoma,sans-serif;background:#f4f6fb;color:#111827;padding:32px 16px;line-height:1.8}
    .wrap{max-width:900px;margin:0 auto}
    .card{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:24px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
    h1{font-size:22px;margin-bottom:4px} h2{font-size:17px;margin-bottom:14px;color:#111827}
    .muted{color:#6b7280;font-size:12px} .center{text-align:center}
    .score{display:flex;align-items:center;gap:20px;flex-wrap:wrap;justify-content:center}
    .score-num{font-size:52px;font-weight:800}
    .grade{font-size:26px;font-weight:800;background:#f3f4f6;border-radius:12px;padding:6px 18px}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th,td{padding:8px 10px;border-bottom:1px solid #f0f0f0;text-align:right;vertical-align:top}
    th{background:#f9fafb;color:#374151}
    .st{display:inline-block;width:22px;height:22px;border-radius:6px;text-align:center;line-height:22px;font-weight:700}
    .cat{margin-bottom:10px}.cat-head{display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px}
    .bar{background:#f3f4f6;border-radius:99px;height:8px;overflow:hidden}
    .bar-fill{height:100%;border-radius:99px}
    .rec{border:1px solid #f0f0f0;border-radius:12px;padding:12px 14px;margin-bottom:10px}
    .rec-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
    .rec p{font-size:13px;color:#374151;margin-top:6px}
    .num{background:#eef2ff;color:#4f46e5;width:24px;height:24px;border-radius:8px;display:inline-block;text-align:center;line-height:24px;font-weight:700;font-size:12px}
    .badge{font-size:11px;border-radius:99px;padding:2px 10px;font-weight:600}
    .serp{border:1px solid #e5e7eb;border-radius:12px;padding:14px;background:#fafafa}
    .serp .t{color:#1a0dab;font-size:16px} .serp .u{color:#0d652d;font-size:12px;direction:ltr;text-align:left}
    .serp .d{color:#4d5156;font-size:13px;margin-top:4px}
    footer{text-align:center;color:#9ca3af;font-size:12px;padding:20px}
    @media print{body{background:#fff;padding:0}}
    """

    return f"""<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>گزارش سئو {esc(site.get('host', ''))}</title>
<link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap" rel="stylesheet">
<style>{css}</style></head><body><div class="wrap">

<div class="card center">
  <h1>گزارش تحلیل سئو و GEO</h1>
  <p class="muted">تولید شده توسط «سئو ایجنت» — {esc(report.get('started_at', ''))}</p>
  <div class="score" style="margin-top:16px">
    <div class="score-num" style="color:{color}">{total}<span style="font-size:20px">/100</span></div>
    <div class="grade" style="color:{color}">گرید {esc(grade)}</div>
  </div>
  <div style="max-width:520px;margin:20px auto 0">{cats_html}</div>
</div>

<div class="card">
  <h2>📋 مشخصات سایت</h2>
  <table>{site_rows}</table>
</div>

<div class="card">
  <h2>🔎 پیش‌نمایش نتیجه در گوگل</h2>
  <div class="serp">
    <div class="u">{esc(serp.get('url', ''))}</div>
    <div class="t">{esc(serp.get('title', 'بدون عنوان'))}</div>
    <div class="d">{esc(serp.get('description', 'بدون توضیحات'))}</div>
  </div>
</div>

<div class="card">
  <h2>✅ نتایج بررسی‌ها ({len(report.get('checks', []))} مورد)</h2>
  <table><tr><th></th><th>بررسی</th><th>دسته</th></tr>{checks_html}</table>
</div>

<div class="card">
  <h2>🔑 کلمات کلیدی شناسایی‌شده</h2>
  <p class="muted" style="margin-bottom:10px">کلمه کلیدی پیشنهادی: <b>{esc(kws.get('primary', [''])[0] if kws.get('primary') else '—')}</b></p>
  <table><tr><th>عبارت</th><th>تکرار</th><th>امتیاز</th></tr>{kw_html}</table>
</div>

<div class="card">
  <h2>🤖 GEO — دسترسی ربات‌های هوش مصنوعی</h2>
  <p class="muted" style="margin-bottom:10px">llms.txt: {'وجود دارد ✓' if report.get('geo', {}).get('llms_txt') else 'یافت نشد'}</p>
  <table><tr><th>ربات</th><th>کاربرد</th><th>وضعیت</th></tr>{geo_html}</table>
</div>

<div class="card">
  <h2>🛠 توصیه‌های بهبود ({len(report.get('recommendations', []))})</h2>
  {recs_html or '<p>موردی یافت نشد — عالی!</p>'}
</div>

<div class="card">
  <h2>📄 صفحات بررسیشده</h2>
  <table><tr><th>آدرس</th><th>وضعیت</th><th>کلمات</th><th>H1</th><th>توضیحات</th></tr>{crawl_rows or '<tr><td colspan="5">فقط صفحه اصلی</td></tr>'}</table>
</div>

{perf_html}

<footer>سئو ایجنت — تحلیلگر SEO + GEO | این گزارش بهصورت خودکار تولید شده است</footer>
</div></body></html>"""


def build_text_report(report):
    lines = [f"گزارش سئو {report.get('site', {}).get('url', '')}",
             f"تاریخ: {report.get('started_at', '')}",
             f"امتیاز کل: {report.get('score', {}).get('total', 0)} از 100 — گرید {report.get('score', {}).get('grade', '')}",
             "", "— بررسی‌ها —"]
    for it in report.get("checks", []):
        mark = {"pass": "✓", "warn": "!", "fail": "✗"}[it["status"]]
        lines.append(f"[{mark}] {it['label']} — {it['detail']}")
    lines.append("")
    lines.append("— توصیه‌ها —")
    for i, r in enumerate(report.get("recommendations", []), 1):
        lines.append(f"{i}. ({r['priority']}) {r['title']}: {r['detail']}")
    return "\n".join(lines)


def build_csv_report(report):
    """خروجی CSV (سازگار با اکسل فارسی با BOM) — بررسی‌ها + صفحات خزش‌شده."""
    buf = io.StringIO()
    w = csv.writer(buf)
    score = report.get("score", {})
    w.writerow(["گزارش سئو", report.get("site", {}).get("url", ""), "",
                f"امتیاز: {score.get('total', 0)}", f"گرید: {score.get('grade', '')}"])
    w.writerow(["بخش", "عنوان", "وضعیت", "جزئیات", "دسته"])
    st_fa = {"pass": "موفق", "warn": "هشدار", "fail": "ناموفق"}
    cat_fa = {"meta": "متا", "content": "محتوا", "technical": "فنی", "geo": "GEO", "structure": "ساختار"}
    for it in report.get("checks", []):
        w.writerow(["بررسی", it.get("label", ""), st_fa.get(it.get("status"), ""),
                    it.get("detail", ""), cat_fa.get(it.get("category"), it.get("category", ""))])
    w.writerow([])
    w.writerow(["آدرس صفحه", "وضعیت", "کلمات", "H1", "توضیحات", "تصاویر بدون alt"])
    for p in report.get("crawl", {}).get("pages", []):
        w.writerow([p.get("url", ""), p.get("status", ""), p.get("words", ""),
                    p.get("h1_count", ""), "دارد" if p.get("has_desc") else "ندارد", p.get("no_alt", "")])
    w.writerow([])
    w.writerow(["کلمه کلیدی", "تکرار", "وزن"])
    for k in report.get("keywords", {}).get("table", []):
        w.writerow([k.get("term", ""), k.get("count", ""), round(k.get("score", 0), 1)])
    return "\ufeff" + buf.getvalue()
