/* سئو ایجنت — منطق فرانت‌اند */
"use strict";

const $ = (id) => document.getElementById(id);
const $$ = (sel) => document.querySelectorAll(sel);

/* توکن دسترسی (برای دیپلوی عمومی با AGENT_TOKEN) — از ?token= خوانده و ذخیره می‌شود */
const TOKEN = (() => {
  try {
    const t = new URLSearchParams(location.search).get("token");
    if (t) { localStorage.setItem("agentToken", t); return t; }
    return localStorage.getItem("agentToken") || "";
  } catch { return ""; }
})();
const withToken = (p) => (TOKEN ? p + (p.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(TOKEN) : p);

const state = {
  theme: localStorage.getItem("theme") || "dark",
  analysis: null,
  taskId: null,
  autoTaskId: null,
  poll: {},          // taskId -> {timer, lastIdx, onDone, onError}
  running: { manual: false, auto: false },
};

/* ---------------- ابزار پایه ---------------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg, type = "ok") {
  const el = document.createElement("div");
  el.className = `toast toast-${type === "err" ? "err" : "ok"}`;
  el.textContent = msg;
  $("toasts").appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .4s"; }, 3200);
  setTimeout(() => el.remove(), 3700);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("کپی شد ✓");
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); toast("کپی شد ✓"); } catch { toast("کپی ناموفق بود", "err"); }
    ta.remove();
  }
}

function downloadBlob(content, filename, type) {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

async function api(path, opts = {}) {
  const res = await fetch(withToken(path), { headers: { "Content-Type": "application/json" }, ...opts });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.error || `خطای سرور (${res.status})`);
  return data;
}

function scoreColor(score) {
  return score >= 80 ? "var(--success)" : score >= 60 ? "var(--warn)" : "var(--danger)";
}

/* ---------------- تب‌ها و تم ---------------- */
function switchTab(name) {
  $$(".tab").forEach((t) => t.classList.remove("active"));
  $(`tab-${name}`).classList.add("active");
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (name === "history") loadHistory();
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  $("themeBtn").textContent = state.theme === "dark" ? "☀️" : "🌙";
  localStorage.setItem("theme", state.theme);
}

$$(".nav-btn").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
$$("[data-goto]").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.goto)));
$("themeBtn").addEventListener("click", () => { state.theme = state.theme === "dark" ? "light" : "dark"; applyTheme(); });

/* ---------------- وضعیت سرور ---------------- */
async function checkHealth() {
  try {
    await api("/api/health");
    $("serverDot").className = "dot dot-on";
    $("serverDot").title = "سرور فعال است";
    $("dashServer").textContent = "فعال";
  } catch {
    $("serverDot").className = "dot dot-off";
    $("dashServer").textContent = "قطع";
  }
}

/* ---------------- سیستم نظرسنجی تسک ---------------- */
function pollTask(taskId, { onStep, onProgress, onDone, onError }) {
  state.poll[taskId] = { lastIdx: 0, timer: null };
  const p = state.poll[taskId];
  p.timer = setInterval(async () => {
    try {
      const { task } = await api(`/api/task/status?id=${taskId}`);
      if (p.lastIdx < task.steps.length) {
        const fresh = task.steps.slice(p.lastIdx);
        fresh.forEach((s) => onStep && onStep(s));
        p.lastIdx = task.steps.length;
      }
      onProgress && onProgress(task);
      if (task.status === "done") { clearInterval(p.timer); delete state.poll[taskId]; onDone && onDone(task); }
      else if (task.status === "error") { clearInterval(p.timer); delete state.poll[taskId]; onError && onError(task); }
      else if (task.status === "cancelled") { clearInterval(p.timer); delete state.poll[taskId]; onError && onError({ error: "لغو شد" }); }
    } catch (e) {
      clearInterval(p.timer); delete state.poll[taskId];
      onError && onError(e);
    }
  }, 900);
}

/* ---------------- تحلیل دستی ---------------- */
function startAnalysis(params) {
  state.running.manual = true;
  $("runBtn").disabled = true;
  $("mProgress").classList.remove("hidden");
  $("mSteps").classList.remove("hidden");
  $("mSteps").innerHTML = "";
  $("mBar").style.width = "0%";
  $("mPct").textContent = "0٪";
  $("mStep").textContent = "آماده‌سازی…";

  api("/api/task/start", { method: "POST", body: JSON.stringify({ type: "analyze", params }) })
    .then(({ task_id }) => {
      state.taskId = task_id;
      $("mStep").textContent = "در حال اتصال به سایت…";
      pollTask(task_id, {
        onStep: (s) => {
          const ln = document.createElement("div");
          ln.className = "ln";
          ln.innerHTML = `<span class="t">${esc(s.t)}</span><span class="lvl-${esc(s.level)}">${esc(s.msg)}</span>`;
          $("mSteps").appendChild(ln);
          $("mSteps").scrollTop = $("mSteps").scrollHeight;
          $("mStep").textContent = s.msg.slice(0, 70);
        },
        onProgress: (task) => {
          $("mBar").style.width = `${task.progress}%`;
          $("mPct").textContent = `${task.progress}٪`;
        },
        onDone: (task) => {
          state.running.manual = false;
          $("runBtn").disabled = false;
          $("mProgress").classList.add("hidden");
          state.analysis = task.result;
          renderReport(task.result);
          toast("تحلیل کامل شد ✓");
          loadHistory();
        },
        onError: (task) => {
          state.running.manual = false;
          $("runBtn").disabled = false;
          $("mProgress").classList.add("hidden");
          const msg = task?.error || (task?.steps || []).slice(-1)[0]?.msg || "خطای نامشخص";
          toast(`تحلیل ناموفق: ${msg}`, "err");
        },
      });
    })
    .catch((e) => {
      state.running.manual = false;
      $("runBtn").disabled = false;
      $("mProgress").classList.add("hidden");
      toast(e.message, "err");
    });
}

$("runBtn").addEventListener("click", () => {
  const url = $("mUrl").value.trim();
  if (!url) { toast("آدرس سایت را وارد کنید", "err"); $("mUrl").focus(); return; }
  startAnalysis({
    url,
    pages: parseInt($("mPages").value, 10),
    delay: parseFloat($("mDelay").value),
    verify_ssl: !$("mSsl").checked,
  });
});
$("mCancel").addEventListener("click", async () => {
  if (state.taskId) { await api("/api/task/cancel", { method: "POST", body: JSON.stringify({ id: state.taskId }) }); toast("درخواست لغو ارسال شد"); }
});
$("dashQuickRun").addEventListener("click", () => {
  const url = $("dashQuickUrl").value.trim();
  if (!url) { toast("آدرس سایت را وارد کنید", "err"); return; }
  $("mUrl").value = url;
  switchTab("manual");
  startAnalysis({ url, pages: 8, delay: 0.3, verify_ssl: true });
});
$("dashQuickUrl").addEventListener("keydown", (e) => { if (e.key === "Enter") $("dashQuickRun").click(); });

/* ---------------- رندر گزارش ---------------- */
function renderReport(r) {
  $("mResults").classList.remove("hidden");
  const score = r.score?.total ?? 0;
  const C = 2 * Math.PI * 52;
  const fg = $("ringFg");
  fg.style.strokeDasharray = C;
  fg.style.strokeDashoffset = C * (1 - score / 100);
  fg.style.stroke = scoreColor(score);
  $("ringScore").textContent = score;
  $("ringGrade").textContent = `گرید ${r.score?.grade ?? "-"}`;
  $("ringScore").style.color = scoreColor(score);

  $("rUrl").textContent = r.site?.url || "";
  $("rTime").textContent = `${r.started_at || ""} — مدت تحلیل: ${r.duration_sec || 0} ثانیه — ${r.crawl?.crawled ?? 1} صفحه`;

  // امتیاز دسته‌ها
  const cats = Object.values(r.score?.categories || {});
  $("catBars").innerHTML = cats.map((c) => `
    <div class="cat-bar">
      <div class="cb-head"><span>${esc(c.label)}</span><b style="color:${scoreColor(c.score)}">${c.score}٪</b></div>
      <div class="progress"><div class="progress-fill" style="width:${c.score}%;background:${scoreColor(c.score)};box-shadow:none"></div></div>
    </div>`).join("");

  // SERP
  $("serpUrl").textContent = r.serp?.url || "";
  $("serpTitle").textContent = r.serp?.title || "(بدون عنوان)";
  $("serpDesc").textContent = r.serp?.description || "(بدون توضیحات)";
  $("serpTitleSuggest").textContent = r.keywords?.suggested_title || "—";

  // کلمات کلیدی
  const kws = r.keywords || {};
  const mkChip = (t) => `<span class="kw-chip"><button class="x" data-copy="${esc(t)}" title="کپی">⧉</button>${esc(t)}</span>`;
  $("kwPrimary").innerHTML = (kws.primary || []).map(mkChip).join("");
  $("kwSecondary").innerHTML = (kws.secondary || []).map(mkChip).join("");
  $$("[data-copy]").forEach((b) => b.addEventListener("click", () => copyText(b.dataset.copy)));
  $("kwTable").querySelector("tbody").innerHTML = (kws.table || []).map((k) => `
    <tr><td><b>${esc(k.term)}</b></td><td>${k.count}</td><td>${Math.round(k.score)}</td>
    <td>${k.in_title ? "✓" : "—"}</td><td>${k.in_headings ? "✓" : "—"}</td></tr>`).join("");

  // GEO
  const geo = r.geo || {};
  setBadge($("llmsBadge"), "llms.txt", geo.llms_txt);
  setBadge($("faqBadge"), "پرسش‌وپاسخ", geo.faq_like);
  const types = r.structured?.types || [];
  setBadge($("schemaBadge"), "Schema", types.length > 0, types.slice(0, 3).join("، "));
  const stFa = { allowed: ["مجاز ✓", "badge-ok"], blocked: ["مسدود ✗", "badge-bad"], not_mentioned: ["ذکر نشده", "badge-mid"] };
  $("geoBots").querySelector("tbody").innerHTML = (geo.ai_bots || []).map((b) => {
    const [txt, cls] = stFa[b.status] || [b.status, ""];
    return `<tr><td dir="ltr"><b>${esc(b.bot)}</b></td><td>${esc(b.org)}</td><td>${esc(b.purpose)}</td><td><span class="badge ${cls}">${txt}</span></td></tr>`;
  }).join("");

  // بررسی‌ها
  const catFa = { meta: "متا", content: "محتوا", technical: "فنی", geo: "GEO", structure: "ساختار" };
  const stIcon = { pass: ["✓", "st-pass"], warn: ["!", "st-warn"], fail: ["✗", "st-fail"] };
  $("checksTable").querySelector("tbody").innerHTML = (r.checks || []).map((c) => {
    const [ic, cls] = stIcon[c.status] || ["•", ""];
    return `<tr data-cat="${esc(c.category)}"><td><span class="st ${cls}">${ic}</span></td>
      <td><b>${esc(c.label)}</b></td><td class="muted">${esc(c.detail)}</td><td>${catFa[c.category] || esc(c.category)}</td></tr>`;
  }).join("");
  $$("#checkFilter .chip").forEach((ch) => {
    ch.onclick = () => {
      $$("#checkFilter .chip").forEach((x) => x.classList.remove("active"));
      ch.classList.add("active");
      const f = ch.dataset.filter;
      $$("#checksTable tbody tr").forEach((tr) => {
        tr.style.display = (f === "all" || tr.dataset.cat === f) ? "" : "none";
      });
    };
  });

  // توصیه‌ها
  const prCls = { "بالا": "badge-bad", "متوسط": "badge-mid", "پایین": "badge-ok" };
  $("recsList").innerHTML = (r.recommendations || []).map((rec, i) => `
    <div class="rec"><div class="rec-head"><span class="num">${i + 1}</span><b>${esc(rec.title)}</b>
    <span class="badge ${prCls[rec.priority] || ""}">${esc(rec.priority)}</span></div><p>${esc(rec.detail)}</p></div>`).join("")
    || `<p class="empty">موردی یافت نشد — عالی! 🎉</p>`;

  // صفحات خزش‌شده
  $("crawlTable").querySelector("tbody").innerHTML = (r.crawl?.pages || []).map((p) => `
    <tr><td dir="ltr" class="ltr">${esc(p.url.replace(/^https?:\/\//, ""))}</td>
    <td>${p.ok ? "✓ " + p.status : "✗ " + p.status}</td><td>${p.words ?? "—"}</td>
    <td>${p.h1_count ?? "—"}</td><td>${p.has_desc ? "دارد" : "ندارد"}</td>
    <td>${p.no_alt ?? "—"}</td></tr>`).join("");

  // لینک‌های خراب
  const broken = r.links?.broken || [];
  if (broken.length) {
    $("brokenBox").classList.remove("hidden");
    $("brokenList").innerHTML = broken.map((b) => `<li dir="ltr">${esc(b.url)} — ${b.status}</li>`).join("");
  } else $("brokenBox").classList.add("hidden");

  $("mResults").scrollIntoView({ behavior: "smooth", block: "start" });
}

function setBadge(el, label, ok, extra = "") {
  el.textContent = `${label}: ${ok ? "دارد ✓" : "ندارد ✗"}${extra ? " — " + extra : ""}`;
  el.className = `badge ${ok ? "badge-ok" : "badge-bad"}`;
}

/* دکمه‌های خروجی گزارش */
$("btnHtml").addEventListener("click", () => state.taskId && window.open(withToken(`/api/report/html?id=${state.taskId}`), "_blank"));
$("btnJson").addEventListener("click", () => {
  if (!state.analysis) return;
  downloadBlob(JSON.stringify(state.analysis, null, 2), "seo-report.json", "application/json; charset=utf-8");
});
$("btnCsv").addEventListener("click", () => state.taskId && window.open(withToken(`/api/report/csv?id=${state.taskId}`), "_blank"));
$("btnCopy").addEventListener("click", async () => {
  if (!state.taskId) return;
  try {
    const res = await fetch(withToken(`/api/report/text?id=${state.taskId}`));
    copyText(await res.text());
  } catch { toast("دریافت گزارش ناموفق بود", "err"); }
});
$("btnCopyRecs").addEventListener("click", () => {
  const recs = state.analysis?.recommendations || [];
  copyText(recs.map((r, i) => `${i + 1}. (${r.priority}) ${r.title}\n   ${r.detail}`).join("\n"));
});
$("btnCopyKws").addEventListener("click", () => {
  const k = state.analysis?.keywords || {};
  copyText([...(k.primary || []), ...(k.secondary || [])].join("، "));
});
$("btnRerun").addEventListener("click", () => $("runBtn").click());

/* ---------------- سئوی خودکار ---------------- */
function readAutoParams(analyzeOnly) {
  return {
    site_url: $("aSite").value.trim(),
    admin_url: $("aAdmin").value.trim(),
    username: $("aUser").value.trim(),
    password: $("aPass").value,
    limit: parseInt($("aLimit").value, 10),
    blog_desc: $("cBlogDesc").checked,
    meta_desc: $("cMetaDesc").checked,
    focus_kw: $("cFocusKw").checked,
    tags: $("cTags").checked,
    analyze_only: analyzeOnly || $("cOnlyAnalyze").checked,
    verify_ssl: !$("aSsl").checked,
  };
}

function appendAutoLog(s) {
  const ln = document.createElement("div");
  ln.className = "ln";
  ln.innerHTML = `<span class="t">${esc(s.t)}</span><span class="lvl-${esc(s.level)}">${esc(s.msg)}</span>`;
  $("aLog").appendChild(ln);
  $("aLog").scrollTop = $("aLog").scrollHeight;
}

function runAuto(analyzeOnly) {
  const params = readAutoParams(analyzeOnly);
  if (!params.site_url) { toast("آدرس سایت را وارد کنید", "err"); return; }
  if (!params.username || !params.password) { toast("نام کاربری و رمز عبور الزامی است", "err"); return; }

  state.running.auto = true;
  $("autoRunBtn").disabled = true;
  $("testBtn").disabled = true;
  $("autoCancelBtn").classList.remove("hidden");
  $("aProgress").classList.remove("hidden");
  $("autoLogCard").classList.remove("hidden");
  $("autoSummaryCard").classList.add("hidden");
  $("aLog").innerHTML = "";
  $("aBar").style.width = "0%";
  $("aPct").textContent = "0٪";
  $("aStep").textContent = "آماده‌سازی…";
  if (!analyzeOnly) $("testResult").textContent = "";

  api("/api/task/start", { method: "POST", body: JSON.stringify({ type: "auto", params }) })
    .then(({ task_id }) => {
      state.autoTaskId = task_id;
      $("aStep").textContent = "در حال اتصال…";
      pollTask(task_id, {
        onStep: (s) => { appendAutoLog(s); $("aStep").textContent = s.msg.slice(0, 70); },
        onProgress: (task) => { $("aBar").style.width = `${task.progress}%`; $("aPct").textContent = `${task.progress}٪`; },
        onDone: (task) => {
          state.running.auto = false;
          $("autoRunBtn").disabled = false;
          $("testBtn").disabled = false;
          $("autoCancelBtn").classList.add("hidden");
          $("aProgress").classList.add("hidden");
          if (analyzeOnly) {
            $("testResult").textContent = "✓ اتصال موفق — اطلاعات درست است";
            $("testResult").className = "test-result test-ok";
            toast("تست اتصال موفق ✓");
          } else {
            renderAutoSummary(task.result);
            toast("سئوی خودکار کامل شد ✓");
          }
          loadHistory();
        },
        onError: (task) => {
          state.running.auto = false;
          $("autoRunBtn").disabled = false;
          $("testBtn").disabled = false;
          $("autoCancelBtn").classList.add("hidden");
          $("aProgress").classList.add("hidden");
          const msg = task?.error || "اجرای ناموفق — جزئیات در لاگ";
          if (analyzeOnly) {
            $("testResult").textContent = "✗ " + msg;
            $("testResult").className = "test-result test-bad";
          } else toast(msg, "err");
        },
      });
    })
    .catch((e) => {
      state.running.auto = false;
      $("autoRunBtn").disabled = false;
      $("testBtn").disabled = false;
      $("autoCancelBtn").classList.add("hidden");
      toast(e.message, "err");
    });
}

$("testBtn").addEventListener("click", () => runAuto(true));
$("autoRunBtn").addEventListener("click", () => runAuto(false));
$("autoCancelBtn").addEventListener("click", async () => {
  if (state.autoTaskId) { await api("/api/task/cancel", { method: "POST", body: JSON.stringify({ id: state.autoTaskId }) }); toast("درخواست لغو ارسال شد"); }
});
$("aPassToggle").addEventListener("click", () => {
  const inp = $("aPass");
  inp.type = inp.type === "password" ? "text" : "password";
});

function renderAutoSummary(result) {
  $("autoSummaryCard").classList.remove("hidden");
  const s = result.summary || {};
  const stats = [
    { b: s.scanned ?? 0, t: "مطلب بررسی‌شده" },
    { b: s.updated ?? 0, t: "مطلب به‌روزرسانی‌شده" },
    { b: s.failed ?? 0, t: "خطا" },
  ];
  $("autoSummaryStats").innerHTML = stats.map((x) =>
    `<div class="auto-stat"><b style="color:${x.t.includes("خطا") && x.b ? "var(--danger)" : "var(--accent2)"}">${x.b}</b><small>${x.t}</small></div>`).join("");

  const changes = result.changes || [];
  $("autoChanges").innerHTML = changes.length
    ? changes.map((c) => `
      <div class="change-item"><b>${esc(c.title)}</b>
      ${c.fields.map((f) => `<span class="fld">${esc(f.name)}: ${esc(f.value)}</span>`).join("")}
      <span class="fld" dir="ltr">${esc(c.link || "")}</span></div>`).join("")
    : `<p class="empty">تغییری اعمال نشد${result.detection?.seo_plugins?.length ? "" : ""} — مطالب یا قبلاً بهینه بوده‌اند یا گزینه‌ای انتخاب نشده است.</p>`;

  const recs = result.recommendations || [];
  if (recs.length) {
    $("autoChanges").innerHTML += `<div class="note" style="margin-top:12px">📋 <b>قدم‌های بعدی:</b><ul class="bullets">${recs.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>`;
  }
  $("autoSummaryCard").scrollIntoView({ behavior: "smooth", block: "start" });
}

$("btnLogCopy").addEventListener("click", () => {
  copyText([...$("aLog").children].map((ln) => ln.innerText).join("\n"));
});
$("btnLogDownload").addEventListener("click", () => {
  downloadBlob([...$("aLog").children].map((ln) => ln.innerText).join("\n"), "auto-seo-log.txt", "text/plain; charset=utf-8");
});
$("btnAutoHtml").addEventListener("click", () => state.autoTaskId && window.open(withToken(`/api/report/html?id=${state.autoTaskId}`), "_blank"));

/* ---------------- تاریخچه ---------------- */
async function loadHistory() {
  try {
    const { history } = await api("/api/history");
    renderHistory(history || []);
    renderDashRecent(history || []);
  } catch { /* سرور قطع */ }
}

function renderHistory(history) {
  const tb = $("histTable").querySelector("tbody");
  $("histEmpty").style.display = history.length ? "none" : "";
  tb.innerHTML = history.map((h) => {
    const result = h.type === "analyze"
      ? (h.score != null ? `<b style="color:${scoreColor(h.score)}">${h.score}</b> / گرید ${esc(h.grade || "")} — ${h.recommendations} توصیه` : "—")
      : `${h.updated ?? 0} مطلب به‌روزرسانی شد (روش: ${esc(h.method || "—")})`;
    return `<tr>
      <td>${esc(h.time)}</td>
      <td><span class="type-badge type-${esc(h.type)}">${h.type === "analyze" ? "تحلیل دستی" : "سئوی خودکار"}</span></td>
      <td dir="ltr" class="ltr">${esc((h.url || "").replace(/^https?:\/\//, "").slice(0, 40))}</td>
      <td>${result}</td>
      <td><div class="btn-row">
        <button class="btn btn-ghost btn-sm" data-view="${esc(h.id)}">مشاهده</button>
        <button class="btn btn-outline btn-sm" data-html="${esc(h.id)}">گزارش</button>
        <button class="btn btn-danger btn-sm" data-del="${esc(h.id)}">حذف</button>
      </div></td></tr>`;
  }).join("");

  tb.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", async () => {
    try {
      const item = await api(`/api/history/${b.dataset.view}`);
      if (item.report && item.report.type === "analyze") {
        state.taskId = item.entry.id;
        state.analysis = item.report;
        renderReport(item.report);
        switchTab("manual");
      } else if (item.report) {
        renderAutoSummary(item.report);
        switchTab("auto");
      } else {
        toast("گزارش کامل این مورد دیگر در حافظه نیست (سرور ری‌استارت شده). فقط از اجراهای جدید گزارش کامل می‌آید.", "err");
      }
    } catch (e) { toast(e.message, "err"); }
  }));
  tb.querySelectorAll("[data-html]").forEach((b) => b.addEventListener("click", () => window.open(withToken(`/api/report/html?id=${b.dataset.html}`), "_blank")));
  tb.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm("این مورد از تاریخچه حذف شود؟")) return;
    try { await api(`/api/history/${b.dataset.del}`, { method: "DELETE" }); toast("حذف شد ✓"); loadHistory(); }
    catch (e) { toast(e.message, "err"); }
  }));
}

function renderDashRecent(history) {
  const analyze = history.filter((h) => h.type === "analyze");
  const last = analyze[0];
  $("dashScore").textContent = last?.score != null ? last.score : "—";
  $("dashScore").style.color = last?.score != null ? scoreColor(last.score) : "";
  $("dashPages").textContent = last?.pages ?? "—";
  $("dashRecs").textContent = last?.recommendations ?? "—";
  const tb = $("dashRecentTable").querySelector("tbody");
  $("dashRecentEmpty").style.display = analyze.length ? "none" : "";
  tb.innerHTML = analyze.slice(0, 4).map((h) => `
    <tr><td dir="ltr" class="ltr">${esc((h.url || "").replace(/^https?:\/\//, "").slice(0, 32))}</td>
    <td><b style="color:${scoreColor(h.score ?? 0)}">${h.score ?? "—"}</b></td>
    <td class="muted">${esc(h.time)}</td>
    <td><button class="btn btn-ghost btn-sm" data-goto="manual">بازکردن</button></td></tr>`).join("");
}

$("histRefresh").addEventListener("click", loadHistory);
$("histClear").addEventListener("click", async () => {
  if (!confirm("تمام تاریخچه پاک شود؟")) return;
  try { await api("/api/history/clear", { method: "POST" }); toast("تاریخچه پاک شد ✓"); loadHistory(); }
  catch (e) { toast(e.message, "err"); }
});

/* ---------------- شروع ---------------- */
applyTheme();
checkHealth();
loadHistory();
