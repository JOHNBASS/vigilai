// VigilAI POC 前端：webcam 截圖迴圈 + 規則 CRUD + 即時 log
let PW = "";
let stream = null;
let loopTimer = null;
let busy = false;       // 避免上一次推理還沒回就重送
let rules = [];

const $ = (id) => document.getElementById(id);
const api = async (path, opts = {}) => {
  const res = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json", "X-Access-Password": PW, ...(opts.headers || {}) },
  });
  if (!res.ok) {
    const e = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(e.detail || res.statusText);
  }
  return res.json();
};

// ---- 登入 -----------------------------------------------------------------
$("loginBtn").onclick = async () => {
  PW = $("pw").value;
  try {
    const r = await api("/api/login", { method: "POST", body: JSON.stringify({ password: PW }) });
    $("gate").classList.add("hidden");
    $("app").classList.remove("hidden");
    $("modelBadge").textContent = "model: " + r.model;
    setTgBadge(r.telegram_configured);
    await loadRules();
    refreshHealth();
  } catch (e) {
    $("gateErr").textContent = e.message;
  }
};
$("pw").addEventListener("keydown", (e) => { if (e.key === "Enter") $("loginBtn").click(); });

function setTgBadge(ok) {
  const b = $("tgBadge");
  b.textContent = "Telegram: " + (ok ? "已設定" : "未設定");
  b.className = "badge " + (ok ? "ok" : "bad");
}

async function refreshHealth() {
  try {
    const h = await fetch("/api/health").then((r) => r.json());
    const b = $("ollamaBadge");
    b.textContent = "Ollama: " + (h.ollama === "ok" ? "ok" : "error");
    b.className = "badge " + (h.ollama === "ok" ? "ok" : "bad");
    setTgBadge(h.telegram_configured);
  } catch {}
}

// ---- 攝影機 ---------------------------------------------------------------
$("camBtn").onclick = async () => {
  if (stream) {
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
    $("video").srcObject = null;
    $("camBtn").textContent = "開啟攝影機";
    $("runBtn").disabled = true;
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 960 }, audio: false });
    $("video").srcObject = stream;
    $("camBtn").textContent = "關閉攝影機";
    $("runBtn").disabled = false;
  } catch (e) {
    alert("無法開啟攝影機：" + e.message + "\n（注意：webcam 只能在 localhost 或 https 下使用）");
  }
};

function grabFrame() {
  const v = $("video");
  const canvas = $("canvas");
  const maxEdge = 768;
  let w = v.videoWidth, h = v.videoHeight;
  if (!w || !h) return null;
  const scale = Math.min(1, maxEdge / Math.max(w, h));
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  canvas.getContext("2d").drawImage(v, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.7);
}

// ---- 偵測迴圈 -------------------------------------------------------------
$("runBtn").onclick = () => {
  if (loopTimer) {
    stopLoop();
  } else {
    const sec = Math.max(1, parseInt($("interval").value) || 3);
    $("runBtn").textContent = "停止偵測";
    tick();
    loopTimer = setInterval(tick, sec * 1000);
  }
};
function stopLoop() {
  clearInterval(loopTimer);
  loopTimer = null;
  $("runBtn").textContent = "開始偵測";
}

let busyTimerId = null;
function showBusy(on) {
  const ov = $("busyOverlay");
  if (on) {
    const t0 = performance.now();
    ov.classList.remove("hidden");
    $("busyTimer").textContent = "0.0s";
    busyTimerId = setInterval(() => {
      $("busyTimer").textContent = ((performance.now() - t0) / 1000).toFixed(1) + "s";
    }, 100);
  } else {
    ov.classList.add("hidden");
    clearInterval(busyTimerId);
  }
}

async function tick() {
  if (busy) return;             // 上一輪還在跑，跳過（避免推理塞車）
  const img = grabFrame();
  if (!img) return;
  busy = true;
  showBusy(true);
  try {
    const r = await api("/api/analyze", { method: "POST", body: JSON.stringify({ image: img }) });
    renderResults(r);
  } catch (e) {
    addLog({ head: "錯誤", reason: e.message, fire: true });
  } finally {
    busy = false;
    showBusy(false);
  }
}

function renderResults(r) {
  const map = {};
  for (const res of r.results) {
    map[res.rule_id] = res;
    // log
    let head, fire = false;
    if (res.cooled_down) head = `[冷卻] ${res.name}`;
    else if (res.vlm_error) head = `[VLM錯誤] ${res.name}`;
    else if (res.triggered) { head = `🔔 觸發：${res.name}`; fire = true; }
    else head = `[正常] ${res.name}`;
    const detail = [];
    if (res.value !== null && res.value !== undefined) detail.push(`值=${res.value}`);
    if (res.detected !== null && res.detected !== undefined) detail.push(`detected=${res.detected}`);
    if (res.confidence !== null && res.confidence !== undefined) detail.push(`conf=${res.confidence}`);
    if (res.inference_ms) detail.push(`${(res.inference_ms / 1000).toFixed(1)}s`);
    if (res.triggered) detail.push(res.notified ? "已通知✅" : "通知失敗❌");
    addLog({ head, reason: (res.reason || res.vlm_error || "") + (detail.length ? "  [" + detail.join(" ") + "]" : ""), fire });
  }
  // 更新規則狀態燈
  document.querySelectorAll(".rule").forEach((el) => {
    const res = map[el.dataset.id];
    const dot = el.querySelector(".dot");
    if (!res) return;
    dot.className = "dot " + (res.triggered ? "fire" : res.cooled_down ? "cool" : "on");
  });
}

function addLog({ head, reason, fire }) {
  const log = $("log");
  const div = document.createElement("div");
  div.className = "log-entry" + (fire ? " fire" : "");
  const t = new Date().toLocaleTimeString();
  // 用 esc() 轉義：head/reason 含使用者規則名稱與 VLM 輸出，避免 XSS
  div.innerHTML = `<span class="t">${esc(t)}</span> <span class="head">${esc(head)}</span><br>${esc(reason || "")}`;
  log.prepend(div);
  while (log.children.length > 200) log.lastChild.remove();
}
$("clearLogBtn").onclick = () => ($("log").innerHTML = "");

// ---- 規則 CRUD ------------------------------------------------------------
async function loadRules() {
  rules = await api("/api/rules");
  renderRules();
}
function renderRules() {
  const list = $("rulesList");
  list.innerHTML = "";
  if (!rules.length) { list.innerHTML = '<p class="muted">尚無規則，點右上「+ 新增」</p>'; return; }
  for (const r of rules) {
    const el = document.createElement("div");
    el.className = "rule";
    el.dataset.id = r.id;
    const cond = r.condition.type === "numeric"
      ? `數值 ${r.condition.operator} ${r.condition.value}`
      : `布林 (信心≥${r.confidence_threshold})`;
    el.innerHTML = `
      <div class="rule-top">
        <span class="dot ${r.enabled ? "on" : ""}"></span>
        <span class="rule-name">${esc(r.name)}</span>
        <div class="rule-actions">
          <button class="ghost" data-act="toggle">${r.enabled ? "停用" : "啟用"}</button>
          <button class="ghost" data-act="edit">編輯</button>
          <button class="ghost" data-act="del">刪除</button>
        </div>
      </div>
      <div class="rule-meta">${esc(r.prompt)}</div>
      <div class="rule-meta">條件：${cond} ｜ cooldown ${r.cooldown_sec}s</div>`;
    el.querySelector('[data-act="toggle"]').onclick = async () => {
      r.enabled = !r.enabled; await api("/api/rules", { method: "POST", body: JSON.stringify(r) }); loadRules();
    };
    el.querySelector('[data-act="edit"]').onclick = () => openModal(r);
    el.querySelector('[data-act="del"]').onclick = async () => {
      if (confirm(`刪除規則「${r.name}」？`)) { await api("/api/rules/" + r.id, { method: "DELETE" }); loadRules(); }
    };
    list.appendChild(el);
  }
}
const esc = (s) => (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

// modal
$("addRuleBtn").onclick = () => openModal(null);
$("ruleCancel").onclick = () => $("ruleModal").classList.add("hidden");
$("r_type").onchange = syncTypeRows;
function syncTypeRows() {
  const numeric = $("r_type").value === "numeric";
  $("numericRow").classList.toggle("hidden", !numeric);
  $("boolRow").classList.toggle("hidden", numeric);
}
function openModal(r) {
  $("ruleModalTitle").textContent = r ? "編輯規則" : "新增規則";
  $("r_id").value = r ? r.id : "";
  $("r_name").value = r ? r.name : "";
  $("r_prompt").value = r ? r.prompt : "";
  $("r_type").value = r ? r.condition.type : "boolean";
  $("r_operator").value = r ? r.condition.operator : ">=";
  $("r_value").value = r && r.condition.value != null ? r.condition.value : "";
  $("r_conf").value = r ? r.confidence_threshold : 60;
  $("r_cooldown").value = r ? r.cooldown_sec : 60;
  $("r_notify").value = r ? r.notify_text : "";
  syncTypeRows();
  $("ruleModal").classList.remove("hidden");
}
$("ruleSave").onclick = async () => {
  const type = $("r_type").value;
  const body = {
    name: $("r_name").value.trim() || "未命名規則",
    enabled: true,
    prompt: $("r_prompt").value.trim(),
    condition: {
      type,
      operator: $("r_operator").value,
      value: type === "numeric" ? parseFloat($("r_value").value) : null,
    },
    confidence_threshold: parseInt($("r_conf").value) || 60,
    cooldown_sec: parseInt($("r_cooldown").value) || 0,
    notify_text: $("r_notify").value.trim(),
  };
  if (!body.prompt) { alert("請填寫 Prompt"); return; }
  const id = $("r_id").value;
  if (id) body.id = id;
  // 保留原 enabled 狀態
  if (id) { const old = rules.find((x) => x.id === id); if (old) body.enabled = old.enabled; }
  await api("/api/rules", { method: "POST", body: JSON.stringify(body) });
  $("ruleModal").classList.add("hidden");
  loadRules();
};

// ---- Telegram -------------------------------------------------------------
$("probeBtn").onclick = async () => {
  $("tgInfo").textContent = "撈取中…";
  try {
    const r = await api("/api/telegram/probe");
    if (r.ok) {
      $("tgInfo").textContent = `chat_id=${r.chat_id} (${r.chat_name || ""})`;
      addLog({ head: "Telegram", reason: `已取得 chat_id=${r.chat_id} (${r.chat_name || ""})` });
      refreshHealth();
    } else {
      $("tgInfo").textContent = r.error;
      addLog({ head: "Telegram 撈取失敗", reason: r.error, fire: true });
    }
  } catch (e) { $("tgInfo").textContent = e.message; addLog({ head: "Telegram 撈取失敗", reason: e.message, fire: true }); }
};
$("tgTestBtn").onclick = async () => {
  $("tgInfo").textContent = "傳送測試…";
  try {
    const r = await api("/api/telegram/test", { method: "POST" });
    if (r.ok) { $("tgInfo").textContent = "測試通知已送出 ✅"; addLog({ head: "Telegram", reason: "測試通知已送出 ✅，請查看手機" }); }
    else { const msg = "失敗：" + (r.error || r.body); $("tgInfo").textContent = msg; addLog({ head: "Telegram 測試失敗", reason: r.error || r.body, fire: true }); }
  } catch (e) { $("tgInfo").textContent = e.message; addLog({ head: "Telegram 測試失敗", reason: e.message, fire: true }); }
};
