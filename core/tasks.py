# -*- coding: utf-8 -*-
"""مدیریت تسک‌های پس‌زمینه (تحلیل/سئوی خودکار) + تاریخچه ذخیره‌شده."""
import json
import os
import threading
import time
import traceback
import uuid

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
MAX_HISTORY = 60

_lock = threading.Lock()
_tasks = {}
_history = None
_history_lock = threading.Lock()


class Task:
    def __init__(self, tid, ttype):
        self.id = tid
        self.type = ttype
        self.status = "running"      # running | done | error | cancelled
        self.steps = []
        self.progress = 0
        self.result = None
        self.error = None
        self.cancelled = False
        self.started = time.time()

    def step(self, msg, level="info", progress=None):
        if progress is not None:
            self.progress = max(self.progress, int(progress))
        self.steps.append({"t": time.strftime("%H:%M:%S"), "msg": str(msg)[:400], "level": level})

    def to_dict(self, include_result=False):
        d = {"id": self.id, "type": self.type, "status": self.status, "progress": self.progress,
             "steps": self.steps, "error": self.error, "elapsed": round(time.time() - self.started, 1)}
        if include_result:
            d["result"] = self.result
        return d


def start_task(ttype, params):
    from . import analyzer, wordpress
    tid = uuid.uuid4().hex[:12]
    task = Task(tid, ttype)
    _tasks[tid] = task

    def _check_cancel():
        return task.cancelled

    def _worker():
        try:
            if ttype == "analyze":
                result = analyzer.analyze_site(
                    params.get("url", ""),
                    pages=int(params.get("pages", 8)),
                    delay=float(params.get("delay", 0.3)),
                    verify_ssl=bool(params.get("verify_ssl", True)),
                    step=task.step, cancel=_check_cancel, task_id=tid)
            elif ttype == "auto":
                result = wordpress.run_auto_seo(params, task.step, _check_cancel)
            else:
                raise ValueError("نوع تسک نامعتبر است")
            if task.cancelled:
                task.status = "cancelled"
            else:
                task.result = result
                task.status = "done"
                add_history(tid, ttype, result)
        except InterruptedError:
            task.status = "cancelled"
            task.step("تسک لغو شد.", "warn", 100)
        except Exception as e:
            task.status = "error"
            task.error = f"{e}"
            task.step(f"خطا: {e}", "error", 100)
            traceback.print_exc()

    threading.Thread(target=_worker, daemon=True).start()
    return tid


def get_task(tid, include_result=True):
    t = _tasks.get(tid)
    if not t:
        return None
    return t.to_dict(include_result=include_result)


def cancel_task(tid):
    t = _tasks.get(tid)
    if t and t.status == "running":
        t.cancelled = True
        return True
    return False


# ---------------- تاریخچه ----------------
def _load_history():
    global _history
    if _history is None:
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                _history = json.load(f)
        except Exception:
            _history = []
    return _history


def _save_history():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(_history, f, ensure_ascii=False, indent=1)


def add_history(tid, ttype, result):
    with _history_lock:
        hist = _load_history()
        entry = {"id": tid, "type": ttype, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        if ttype == "analyze":
            entry["url"] = result.get("input", {}).get("url", "")
            entry["score"] = result.get("score", {}).get("total")
            entry["grade"] = result.get("score", {}).get("grade")
            entry["recommendations"] = len(result.get("recommendations", []))
            entry["pages"] = result.get("crawl", {}).get("crawled", 1)
        else:
            entry["url"] = result.get("detection", {}).get("site_url") or ""
            s = result.get("summary", {})
            entry["score"] = None
            entry["updated"] = s.get("updated", 0)
            entry["scanned"] = s.get("scanned", 0)
            entry["method"] = result.get("method")
        hist.insert(0, entry)
        del hist[MAX_HISTORY:]
        _save_history()


def list_history():
    with _history_lock:
        return list(_load_history())


def get_history_item(hid):
    from . import analyzer as _a  # noqa
    hist = _load_history()
    for h in hist:
        if h["id"] == hid:
            task = _tasks.get(hid)
            if task and task.result:
                return {"entry": h, "report": task.result}
            return {"entry": h, "report": None}
    return None


def delete_history_item(hid):
    global _history
    with _history_lock:
        hist = _load_history()
        before = len(hist)
        _history = [h for h in hist if h["id"] != hid]
        _save_history()
        return len(_history) < before


def clear_history():
    with _history_lock:
        global _history
        _history = []
        _save_history()
