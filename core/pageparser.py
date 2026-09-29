# -*- coding: utf-8 -*-
"""پارسر HTML سبک بر پایه html.parser استاندارد — استخراج تمام عناصر مهم سئو."""
import json
import re
from html.parser import HTMLParser

SKIP_TAGS = {"script", "style", "template", "svg", "noscript"}
HEAD_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
SEMANTIC_TAGS = ["main", "article", "nav", "header", "footer", "section", "aside", "details", "summary", "time", "figure"]


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.metas = []          # list[dict(kind, key, content)]
        self.headings = []       # list[[tag, text]]
        self.images = []         # list[dict(src, alt, loading)]
        self.anchors = []        # list[dict(href, text, rel)]
        self.ldjson = []         # list[str raw json]
        self.links = []          # list[(rel, href)]
        self.paragraphs = []     # list[str]
        self.text_parts = []
        self.lang = ""
        self.dir = ""
        self.semantic = set()
        self.counts = {"form": 0, "iframe": 0, "table": 0, "img": 0, "a": 0,
                       "video": 0, "button": 0, "input": 0, "details": 0, "time": 0}
        # state machine
        self._skip = 0
        self._in_title = False
        self._title_parts = []
        self._ld_mode = False
        self._ld_parts = []
        self._heading_tag = None
        self._heading_parts = []
        self._anchor = None
        self._anchor_parts = []
        self._in_p = False
        self._p_parts = []

    # ---------- helpers ----------
    def _attr(self, attrs, name, default=""):
        for k, v in attrs:
            if k and k.lower() == name:
                return v or default
        return default

    # ---------- events ----------
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        a = dict((k.lower(), v or "") for k, v in attrs if k)
        if tag == "html":
            self.lang = a.get("lang", "")
            self.dir = a.get("dir", "")
        if tag in SKIP_TAGS:
            self._skip += 1
            if tag == "script" and "ld+json" in a.get("type", "").lower():
                self._ld_mode = True
                self._ld_parts = []
            return
        if self._skip:
            return
        if tag == "title":
            self._in_title = True
            self._title_parts = []
        elif tag == "meta":
            key = a.get("name") or a.get("property") or a.get("itemprop") or a.get("http-equiv")
            if key:
                self.metas.append({"kind": "property" if a.get("property") else ("http-equiv" if a.get("http-equiv") else "name"),
                                   "key": key.strip(), "content": a.get("content", "")})
        elif tag == "link":
            rel = (a.get("rel") or "").strip()
            if rel:
                self.links.append((rel.lower(), a.get("href", "")))
        elif tag == "img":
            self.counts["img"] += 1
            src = a.get("src") or a.get("data-src") or a.get("data-lazy-src") or ""
            if not src and a.get("srcset"):
                src = a["srcset"].split(",")[0].split(" ")[0]
            self.images.append({"src": src, "alt": (a.get("alt") or "").strip(),
                                "loading": a.get("loading", ""), "width": a.get("width", ""), "height": a.get("height", "")})
        elif tag == "a":
            self.counts["a"] += 1
            self._anchor = {"href": a.get("href", ""), "rel": (a.get("rel") or "").lower()}
            self._anchor_parts = []
        elif tag in HEAD_TAGS:
            self._heading_tag = tag
            self._heading_parts = []
        elif tag == "p":
            self._in_p = True
            self._p_parts = []
        elif tag == "details":
            self.counts["details"] += 1
        if tag in SEMANTIC_TAGS:
            self.semantic.add(tag)
        if tag in self.counts:
            self.counts[tag] += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in ("img", "meta", "link", "input", "br", "hr", "source"):
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self._ld_mode:
            self._ld_parts.append(data)
            return
        if self._skip:
            return
        if self._in_title:
            self._title_parts.append(data)
        if self._heading_tag:
            self._heading_parts.append(data)
        if self._anchor is not None:
            self._anchor_parts.append(data)
        if self._in_p:
            self._p_parts.append(data)
        self.text_parts.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in SKIP_TAGS:
            if self._ld_mode and tag == "script":
                raw = "".join(self._ld_parts).strip()
                if raw:
                    self.ldjson.append(raw)
                self._ld_mode = False
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag == "title":
            self.title = re.sub(r"\s+", " ", "".join(self._title_parts)).strip()
            self._in_title = False
        elif tag in HEAD_TAGS and self._heading_tag == tag:
            txt = re.sub(r"\s+", " ", "".join(self._heading_parts)).strip()
            self.headings.append([tag, txt])
            self._heading_tag = None
        elif tag == "a" and self._anchor is not None:
            self._anchor["text"] = re.sub(r"\s+", " ", "".join(self._anchor_parts)).strip()
            self.anchors.append(self._anchor)
            self._anchor = None
        elif tag == "p" and self._in_p:
            txt = re.sub(r"\s+", " ", "".join(self._p_parts)).strip()
            if txt:
                self.paragraphs.append(txt)
            self._in_p = False

    # ---------- results ----------
    def meta(self, key, kind=None):
        key = key.lower()
        for m in self.metas:
            if m["key"].lower() == key and (kind is None or m["kind"] == kind):
                return m["content"]
        return ""

    def og(self):
        out = {}
        for m in self.metas:
            if m["kind"] == "property" and m["key"].lower().startswith("og:"):
                out[m["key"].lower()] = m["content"]
        return out

    def twitter(self):
        out = {}
        for m in self.metas:
            if (m["kind"] == "name" and m["key"].lower().startswith("twitter:")):
                out[m["key"].lower()] = m["content"]
        return out

    def links_by_rel(self, rel):
        rel = rel.lower()
        return [href for r, href in self.links if rel in r]

    @property
    def text(self):
        return re.sub(r"\s+", " ", " ".join(self.text_parts)).strip()

    def structured_types(self):
        """انواع schema.org را از اسکریپت‌های ld+json استخراج می‌کند."""
        types = []
        for raw in self.ldjson:
            try:
                data = json.loads(raw)
            except Exception:
                m = re.findall(r'"@type"\s*:\s*"([^"]+)"', raw)
                types.extend(m)
                continue
            types.extend(_walk_types(data))
        return types

    def structured_author(self):
        for raw in self.ldjson:
            try:
                data = json.loads(raw)
            except Exception:
                continue
            for obj in _walk_objects(data):
                author = obj.get("author")
                if author:
                    if isinstance(author, dict):
                        return author.get("name", "")
                    if isinstance(author, list) and author and isinstance(author[0], dict):
                        return author[0].get("name", "")
                    if isinstance(author, str):
                        return author
        return ""


def _walk_types(node):
    out = []
    if isinstance(node, dict):
        t = node.get("@type")
        if isinstance(t, str):
            out.append(t)
        elif isinstance(t, list):
            out.extend(str(x) for x in t)
        for v in node.values():
            out.extend(_walk_types(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_walk_types(v))
    return out


def _walk_objects(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk_objects(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_objects(v)


def parse_html(html_text):
    """پارس کامل صفحه؛ در صورت خطا نتیجه جزئی برمی‌گردد."""
    p = PageParser()
    try:
        p.feed(html_text)
        p.close()
    except Exception:
        pass
    return p
