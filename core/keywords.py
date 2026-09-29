# -*- coding: utf-8 -*-
"""استخراج و پیشنهاد کلمات کلیدی فارسی/انگلیسی (بدون وابستگی خارجی)."""
import re
from collections import Counter

TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

FA_STOPWORDS = set("""
از به با در که را و این آن برای تا است هست هستند بود شده شد می های ها یا هم نیز اما ولی پس اگر چون هر همه هیچ
خیلی بیش کم روی زیر بالا پایین میان بین صورت طریق مورد یکی دو سه خود ما شما او آنها وی من تو ای کند کنند کنید
کرد کردند کرده باشد باشند بشود بوده شدهاست آنچه چنانچه بنابراین ضمن طبق وقتی زمانی حالا اکنون دیگر مثل مانند
کل کلی فعل قبل بعد درباره طبق دیگران طور جور چیز چیزی کجا کی چه چرا چند چندین بر اینجا آنجا الان سپس هنگام
یک تنها فقط حتی البته یعنی گفته گفت بگو میشود بشود دارند دارد داشت داشته بدهد بدهم بدهید بداند بدانم میدهد
میشود نمایند نمایید سریع علاوه ویژه باب ابتدا سپس مجدد فقط خب آیا همان همانی همین چنین بدین بدان آندسته
""".split())

EN_STOPWORDS = set("""
the a an and or but if then else when while at by for with about against between into through during before
after above below to from up down in out on off over under again further once here there all any both each few
more most other some such no nor not only own same so than too very can will just should now i me my we our you
your he him his she her it its they them their what which who whom this that these those am is are was were be
been being have has had having do does did doing would could ought may might must shall of as get got also us
one two click here read more page site website menu search login contact copyright rights reserved terms privacy
home blog post news http https www com net org
""".split())

STOPWORDS = FA_STOPWORDS | EN_STOPWORDS


def tokenize(text):
    text = (text or "").replace("\u200c", " ").lower()
    return TOKEN_RE.findall(text)


def _content_tokens(tokens):
    out = []
    for t in tokens:
        if len(t) < 2 or t in STOPWORDS:
            continue
        if t.isdigit() and len(t) < 4:
            continue
        out.append(t)
    return out


def extract_keywords(text, headings_text="", title_text="", limit=20):
    """کلمات کلیدی با وزن‌دهی به عنوان و هدینگ‌ها. خروجی: list[dict(term, count, score, in_title, in_headings)]"""
    body = tokenize(text)
    heads = tokenize(headings_text)
    ttl = tokenize(title_text)

    raw_counter = Counter(body)
    head_counter = Counter(heads)
    title_counter = Counter(ttl)

    results = {}

    # unigram
    for tok in _content_tokens(body):
        score = raw_counter.get(tok, 0) + 2 * head_counter.get(tok, 0) + 4 * title_counter.get(tok, 0)
        if score <= 0:
            continue
        item = results.setdefault(tok, {"term": tok, "count": 0, "score": 0,
                                         "in_title": tok in title_counter, "in_headings": tok in head_counter})
        item["count"] += raw_counter.get(tok, 0)
        item["score"] += score

    # bigram / trigram روی توکن‌های معنادار
    ct = _content_tokens(body)
    for n, weight in ((2, 2.2), (3, 3.0)):
        for i in range(len(ct) - n + 1):
            gram = " ".join(ct[i:i + n])
            cnt = 0
            for j in range(len(body) - n + 1):
                seg = " ".join(_content_tokens(body[j:j + n]))
                if seg == gram:
                    cnt += 1
            if cnt >= 2 or (cnt >= 1 and n == 2 and _in_head_gram(heads, ct[i:i + n])):
                score = cnt * weight
                if _in_head_gram(heads, ct[i:i + n]):
                    score *= 2
                item = results.setdefault(gram, {"term": gram, "count": cnt, "score": score,
                                                  "in_title": False, "in_headings": _in_head_gram(heads, ct[i:i + n])})
                item["score"] += score
                item["count"] = max(item["count"], cnt)

    ranked = sorted(results.values(), key=lambda x: (-x["score"], -x["count"]))
    return ranked[:limit]


def _in_head_gram(head_tokens, gram_tokens):
    g = " ".join(gram_tokens)
    h = " ".join(head_tokens)
    return g in h


def generate_meta_description(text, fallback="", max_len=158):
    """تولید توضیحات متا از ابتدای محتوای معنادار صفحه."""
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) < 40 and fallback:
        text = re.sub(r"\s+", " ", fallback).strip()
    if not text:
        return ""
    # جمله اول کامل + جمله دوم در صورت نیاز
    sentences = re.split(r"(?<=[.!?؟!。])\s+", text)
    desc = ""
    for s in sentences:
        if not s:
            continue
        if len(desc) + len(s) + 1 > max_len:
            break
        desc = (desc + " " + s).strip()
        if len(desc) >= max_len * 0.6:
            break
    if not desc:
        desc = text[:max_len]
    if len(desc) > max_len:
        cut = desc[:max_len]
        if " " in cut:
            cut = cut[:cut.rfind(" ")]
        desc = cut.rstrip("،,.؟!:") + "…"
    return desc


def generate_focus_keyword(ranked, exclude=None):
    """بهترین کلمه کلیدی (ترجیحاً عبارت) از رتبه‌بندی کلمات."""
    exclude = set(exclude or [])
    for item in ranked:
        if item["term"] not in exclude:
            return item["term"]
    return ranked[0]["term"] if ranked else ""


def suggest_tags(ranked, existing=None, count=3):
    """پیشنهاد تگ بر اساس کلمات پرتکرار که تکراری نباشند."""
    existing = {e.lower() for e in (existing or [])}
    tags = []
    for item in ranked:
        t = item["term"]
        if t in existing or len(tags) >= count:
            continue
        if any(t in x or x in t for x in tags):
            continue
        tags.append(t)
    return tags


def generate_blog_description(keywords_list, brand="", max_len=160):
    """توضیح کوتاه سایت برای تنظیم blog_description وردپرس."""
    kws = [k["term"] for k in (keywords_list or [])[:3]]
    if not kws:
        return ""
    brand = brand.strip()
    if brand and len(brand) <= 30:
        text = f"{brand} | مرجع تخصصی {kws[0]}" + (f" و {kws[1]}" if len(kws) > 1 else "") + " با مقالات راهنما و نکات کاربردی"
    else:
        text = f"مرجع تخصصی {kws[0]}" + (f" و {kws[1]}" if len(kws) > 1 else "") + "؛ مقالات، راهنماها و نکات کاربردی"
    return text[:max_len]
