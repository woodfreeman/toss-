/* Toss 快抛 — 前端逻辑（原生 JS，无 CDN） */
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

function toast(msg, type = "ok", ms = 2200) {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  $("#toastBox").appendChild(el);
  setTimeout(() => el.remove(), ms);
}

function fmtSize(n) {
  if (n == null) return "";
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
  if (n < 1073741824) return (n / 1048576).toFixed(1) + " MB";
  return (n / 1073741824).toFixed(2) + " GB";
}

function fmtTime(ts) {
  const d = new Date(ts * 1000);
  const pad = (x) => String(x).padStart(2, "0");
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (res.status === 401) { showLogin(true); throw new Error("未登录"); }
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}

/* ---------- 登录门 ---------- */
function showLogin(show) { $("#loginMask").style.display = show ? "flex" : "none"; }

$("#btnLogin").addEventListener("click", doLogin);
$("#loginPw").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
async function doLogin() {
  try {
    await api("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: $("#loginPw").value }),
    });
    showLogin(false);
    $("#loginErr").textContent = "";
    boot();
  } catch (e) { $("#loginErr").textContent = e.message; }
}

/* ---------- 选项卡 ---------- */
function selectTab(name) {
  $$(".tab").forEach((x) => x.classList.toggle("active", x.dataset.tab === name));
  $("#paneText").style.display = name === "text" ? "" : "none";
  $("#paneFile").style.display = name === "file" ? "" : "none";
}
$$(".tab").forEach((t) => t.addEventListener("click", () => selectTab(t.dataset.tab)));

/* ---------- 剪贴板粘贴图片（页面级监听） ----------
   剪贴板含图片 → 自动上传（截图工具 Win+Shift+S 后直接 Ctrl+V）；
   纯文本粘贴不拦截，走默认行为（textarea 正常粘贴） */
document.addEventListener("paste", (e) => {
  const files = Array.from((e.clipboardData && e.clipboardData.files) || [])
    .filter((f) => f.type.startsWith("image/"));
  if (!files.length) return;
  e.preventDefault();
  if ($("#loginMask").style.display === "flex") { toast("先输入口令进入", "err"); return; }
  selectTab("file");
  uploadFiles(files);
});

/* ---------- 文本发送 ---------- */
$("#btnPaste").addEventListener("click", async () => {
  try { $("#textContent").value = await navigator.clipboard.readText(); }
  catch (_) { toast("浏览器没给剪贴板权限，手动 Ctrl+V 吧", "err"); }
});
$("#btnSendText").addEventListener("click", sendText);
$("#textContent").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.ctrlKey) sendText();
});
async function sendText() {
  const content = $("#textContent").value.trim();
  if (!content) return toast("先写点内容", "err");
  try {
    await api("/api/text", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    $("#textContent").value = "";
    toast("已发送 ✓");
    loadItems();
  } catch (e) { toast(e.message, "err"); }
}

/* ---------- 文件上传 ---------- */
const dz = $("#dropzone");
dz.addEventListener("click", () => $("#fileInput").click());
dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
dz.addEventListener("drop", (e) => {
  e.preventDefault(); dz.classList.remove("drag");
  uploadFiles(e.dataTransfer.files);
});
$("#fileInput").addEventListener("change", (e) => uploadFiles(e.target.files));

async function uploadFiles(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  $("#uploadStatus").textContent = `⏳ 正在传 ${files.length} 个文件…`;
  try {
    const r = await api("/api/files", { method: "POST", body: fd });
    $("#uploadStatus").textContent = "";
    $("#fileInput").value = "";
    toast(`已收 ${r.saved.length} 个文件 ✓`);
    loadItems();
  } catch (e) {
    $("#uploadStatus").textContent = "";
    toast(e.message, "err");
  }
}

/* ---------- 列表（记录 / 回收站双视图） ---------- */
let pollIds = null; // 轮询基线：上次渲染的 id 串
let view = "main";  // main = 传输记录 | trash = 回收站

function setView(v) {
  view = v;
  $("#listTitle").textContent = v === "trash" ? "🗑 回收站" : "📦 传输记录";
  $("#btnTrashView").textContent = v === "trash" ? "← 返回记录" : "🗑 回收站";
  $("#btnEmptyTrash").style.display = v === "trash" ? "" : "none";
  pollIds = null;
  loadItems();
}
$("#btnTrashView").addEventListener("click", () => setView(view === "main" ? "trash" : "main"));

$("#btnEmptyTrash").addEventListener("click", async () => {
  if (!confirm("清空回收站？所有条目和文件将被彻底删除，无法恢复。")) return;
  try {
    const r = await api("/api/trash/empty", { method: "POST" });
    toast(`已清空 ${r.removed} 条`);
    loadItems();
  } catch (e) { toast(e.message, "err"); }
});

async function loadItems() {
  try {
    const items = await api(view === "main" ? "/api/items?limit=100" : "/api/trash?limit=100");
    renderItems(items);
  } catch (e) { /* 401 已由 api() 处理 */ }
}

function renderItems(items) {
  const box = $("#itemList");
  pollIds = items.map((x) => x.id).join(",");
  if (!items.length) {
    box.innerHTML = `<div class="empty">${view === "main" ? "还没有记录" : "回收站是空的"}</div>`;
    $("#listMeta").textContent = "";
    return;
  }
  const totalSize = items.reduce((s, x) => s + (x.size || 0), 0);
  renderRetentionFooter();
  $("#listMeta").textContent =
    `${items.length} 条 · 共 ${fmtSize(totalSize)}${view === "trash" ? " · 过期自动清空" : ""}`;
  box.innerHTML = "";
  items.forEach((it) => box.appendChild(renderItem(it)));
}

/* 自动刷新：5s 轮询（仅记录视图），页面不可见跳过；有新增才重渲染 + 提示 */
setInterval(async () => {
  if (document.hidden || view !== "main" || $("#loginMask").style.display === "flex") return;
  try {
    const items = await api("/api/items?limit=100");
    const ids = items.map((x) => x.id).join(",");
    if (ids === pollIds) return;
    const prevSet = new Set((pollIds || "").split(",").filter(Boolean));
    const added = items.filter((x) => !prevSet.has(x.id)).length;
    renderItems(items);
    if (added > 0) { toast(`有 ${added} 条新记录`); checkUpdate(); }
  } catch (_) {}
}, 5000);

function renderItem(it) {
  const div = document.createElement("div");
  div.className = view === "trash" ? "item trash" : "item";
  const isImg = it.kind === "file" && it.is_image;
  const left = isImg
    ? `<img class="item-img" loading="lazy" src="/api/items/${it.id}/raw" alt="">`
    : `<div class="item-icon">${it.kind === "text" ? "📝" : "📎"}</div>`;
  // 备注名优先显示；设置过备注时保留原文件名的浅色引用行
  const nameShown = it.memo ? it.memo : it.orig_name;
  const origLine = it.kind === "text"
    ? ""
    : (it.memo ? `<div class="item-orig" title="${esc(it.orig_name || "")}">原名：${esc(it.orig_name || "")}</div>` : "");
  const body = it.kind === "text"
    ? `<div class="item-kind">文本</div>${it.memo ? `<div class="item-memo">✎ ${esc(it.memo)}</div>` : ""}
       <div class="item-text">${esc(it.content)}</div>`
    : `<div class="item-kind">文件</div><div class="item-name">${esc(nameShown)}</div>
       ${origLine}
       <div class="item-size">${fmtSize(it.size)}</div>`;
  const ops = [];
  if (view === "trash") {
    ops.push(`<button class="btn small primary" data-act="restore">↩ 还原</button>`);
    ops.push(`<button class="btn small danger" data-act="purge">彻底删除</button>`);
  } else {
    if (it.kind === "text") ops.push(`<button class="btn small primary" data-act="copy">📋 复制</button>`);
    if (it.kind === "file") ops.push(`<button class="btn small primary" data-act="dl">⬇ 下载</button>`);
    ops.push(`<button class="btn small" data-act="memo" title="备注 / 重命名">✏️</button>`);
    if (isImg) ops.push(`<button class="btn small" data-act="view">🔍 查看</button>`);
    ops.push(`<button class="btn small danger" data-act="del" title="移入回收站">🗑</button>`);
  }
  const timeLine = view === "trash" && it.deleted_at
    ? `发送 ${fmtTime(it.created_at)} · 删除于 ${fmtTime(it.deleted_at)}`
    : fmtTime(it.created_at);
  div.innerHTML = `${left}
    <div class="item-body">${body}<div class="item-time">${timeLine}</div></div>
    <div class="item-ops">${ops.join("")}</div>`;
  div.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => act(b.dataset.act, it, b)));
  if (it.kind === "text" && view !== "trash") {
    /* 渲染后实测高度：超过折叠线才给展开按钮 */
    const txtEl = div.querySelector(".item-text");
    requestAnimationFrame(() => {
      if (txtEl.scrollHeight > 126) {
        const btn = document.createElement("button");
        btn.className = "btn small link";
        btn.dataset.act = "toggle";
        btn.textContent = "展开 ▾";
        div.querySelector(".item-ops").prepend(btn);
        btn.addEventListener("click", () => act("toggle", it, btn));
      }
    });
  }
  return div;
}

/* 复制兼容：navigator.clipboard 仅在 HTTPS/localhost 可用，
   局域网 http 场景 fallback 到 execCommand 隐藏 textarea */
function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }
  return new Promise((resolve, reject) => {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0";
    document.body.appendChild(ta);
    ta.focus(); ta.select();
    try {
      const ok = document.execCommand("copy");
      ok ? resolve() : reject(new Error("execCommand copy failed"));
    } catch (e) { reject(e); } finally { ta.remove(); }
  });
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function act(a, it, btn) {
  if (a === "copy") {
    try { await copyText(it.content); toast("已复制 ✓"); }
    catch (_) { toast("复制失败，请展开后手动选择复制", "err"); }
  } else if (a === "toggle") {
    const txt = btn.closest(".item").querySelector(".item-text");
    const open = txt.classList.toggle("expanded");
    btn.textContent = open ? "收起 ▴" : "展开 ▾";
  } else if (a === "dl") {
    location.href = `/api/items/${it.id}/download`;
  } else if (a === "view") {
    window.open(`/api/items/${it.id}/raw`, "_blank");
  } else if (a === "del") {
    try { await api(`/api/items/${it.id}`, { method: "DELETE" }); toast("已移入回收站（7 天内可还原）"); loadItems(); }
    catch (e) { toast(e.message, "err"); }
  } else if (a === "restore") {
    try { await api(`/api/items/${it.id}/restore`, { method: "POST" }); toast("已还原 ✓"); loadItems(); }
    catch (e) { toast(e.message, "err"); }
  } else if (a === "purge") {
    if (!confirm("彻底删除后无法恢复，确定？")) return;
    try { await api(`/api/trash/${it.id}`, { method: "DELETE" }); toast("已彻底删除"); loadItems(); }
    catch (e) { toast(e.message, "err"); }
  } else if (a === "memo") {
    openMemo(it);
  }
}

/* ---------- 备注 / 重命名（v0.1.6） ---------- */
let memoTarget = null;
function openMemo(it) {
  memoTarget = it;
  $("#memoInput").value = it.memo || "";
  $("#memoMask").style.display = "flex";
  $("#memoInput").focus();
}
function closeMemo() {
  $("#memoMask").style.display = "none";
  memoTarget = null;
}
function promptMemo() {
  return $("#memoInput").value.trim();
}
$("#btnMemoSave").addEventListener("click", async () => {
  if (!memoTarget) return;
  try {
    await api(`/api/items/${memoTarget.id}/memo`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ memo: promptMemo() }),
    });
    closeMemo();
    toast("备注已保存 ✓");
    loadItems();
  } catch (e) { toast(e.message, "err"); }
});
$("#btnMemoClear").addEventListener("click", async () => {
  if (!memoTarget) return;
  try {
    await api(`/api/items/${memoTarget.id}/memo`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ memo: "" }),
    });
    closeMemo();
    toast("备注已清除 ✓");
    loadItems();
  } catch (e) { toast(e.message, "err"); }
});
$("#btnMemoCancel").addEventListener("click", closeMemo);
$("#memoMask").addEventListener("click", (e) => { if (e.target === $("#memoMask")) closeMemo(); });
$("#memoInput").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#btnMemoSave").click(); });

/* ---------- 设置 ---------- */
let retentionInfo = { days: 30, min: 1, max: 90 };
async function renderRetentionFooter() {
  try { retentionInfo = await api("/api/settings/retention"); } catch (_) {}
  $("#retentionFoot").textContent = retentionInfo.days;
  return retentionInfo;
}
$("#btnSettings").addEventListener("click", openSettings);
async function openSettings() {
  $("#peerUrl").value = localStorage.getItem("toss_peer") || "";
  $("#pwMsg").textContent = "";
  $("#retMsg").textContent = "";
  try {
    const info = await renderRetentionFooter();
    $("#retentionInput").value = info.days;
    $("#infoLine").textContent = `v${info.version} · ${info.item_count} 条记录 · 共 ${fmtSize(info.total_size)} · ${info.retention_days} 天自动清理`;
  } catch (_) {}
  $("#setMask").style.display = "flex";
}
$("#setMask").addEventListener("click", (e) => { if (e.target === $("#setMask")) $("#setMask").style.display = "none"; });

$("#btnSaveRetention").addEventListener("click", async () => {
  const v = parseInt($("#retentionInput").value, 10);
  if (!Number.isFinite(v)) { $("#retMsg").textContent = "✗ 请输入有效数字"; return; }
  try {
    const r = await api("/api/settings/retention", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ days: v }),
    });
    retentionInfo.days = r.days;
    $("#retentionInput").value = r.days;
    $("#retentionFoot").textContent = r.days;
    $("#retMsg").textContent = `✓ 已设为 ${r.days} 天（1~${r.max}，超期条目将在下次清理时删除）`;
    toast(`保留期已设为 ${r.days} 天 ✓`);
  } catch (e) { $("#retMsg").textContent = "✗ " + e.message; }
});

$("#btnSavePeer").addEventListener("click", () => {
  let url = $("#peerUrl").value.trim().replace(/\/+$/, "");
  if (url && !/^https?:\/\//.test(url)) url = "http://" + url;
  localStorage.setItem("toss_peer", url);
  $("#peerUrl").value = url;
  toast("已保存 ✓"); renderPeer();
});

$("#btnSetPw").addEventListener("click", async () => {
  try {
    await api("/api/auth/setpw", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_password: $("#oldPw").value, new_password: $("#newPw").value }),
    });
    $("#oldPw").value = $("#newPw").value = "";
    $("#pwMsg").textContent = "✓ 口令已生效（下次打开需先登录）";
    toast("口令已设置 ✓");
  } catch (e) { $("#pwMsg").textContent = "✗ " + e.message; }
});

$("#btnClearPw").addEventListener("click", async () => {
  if (!confirm("确定清除口令？清除后局域网内任何人都能打开。")) return;
  try { await api("/api/auth/clearpw", { method: "POST" }); $("#pwMsg").textContent = "✓ 已清除"; toast("口令已清除"); }
  catch (e) { $("#pwMsg").textContent = "✗ " + e.message; }
});

$("#btnLogout").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" }).catch(() => {});
  location.reload();
});

/* ---------- 对方实例 / 本机地址 ---------- */
$("#btnPeer").addEventListener("click", () => {
  const peer = localStorage.getItem("toss_peer");
  if (peer) window.open(peer, "_blank");
  else { openSettings(); toast("先在设置里填对方 Toss 地址", "err"); }
});
function renderPeer() {
  const peer = localStorage.getItem("toss_peer");
  $("#btnPeer").textContent = peer ? `↔ ${peer.replace(/^https?:\/\//, "")}` : "↔ 对方 Toss";
}

$("#selfAddr").addEventListener("click", async () => {
  try { await copyText($("#selfAddr").dataset.addr || ""); toast("本机地址已复制 ✓"); }
  catch (_) { toast($("#selfAddr").dataset.addr || "", "ok", 5000); }
});
async function renderSelfAddr() {
  try {
    const info = await api("/api/info");
    const addr = info.ips.length ? `http://${info.ips[0]}:${info.port}` : `http://127.0.0.1:${info.port}`;
    $("#selfAddr").textContent = `📍 ${addr}`;
    $("#selfAddr").dataset.addr = addr;
  } catch (_) { $("#selfAddr").textContent = "📍 本机地址（登录后显示）"; }
}

/* ---------- 版本与更新说明 ----------
   CHANGELOG：升级后首次打开自动弹「本次更新内容」；
   对比 localStorage.toss_seen_ver 与服务端版本号 */
const CHANGELOG = {
  "0.1.7": [
    "🗓️ 记录保留天数可配置（默认 30 天）：⚙️ 设置里随时改为 1~90 天，改动立即生效，无需重启",
  ],
  "0.1.6": [
    "✏️ 传输记录可备注 / 重命名：给图片、文件、文本加一句注释（如「最新版UI草稿」），列表优先显示备注名，原名保留；一键清除",
  ],
  "0.1.5": [
    "📌 点页头版本徽章 v0.1.5，可随时查看完整更新说明（不用再等升级弹卡）",
  ],
  "0.1.4": [
    "⚡ 一键更新：新版本包推送进来后，页面点一下自动换包重启，不再手动下载覆盖",
    "🚫 静态资源不再强缓存，升级后普通刷新即是新版，无需 Ctrl+F5",
    "🗑 回收站（0.1.3）：删除 7 天内可还原、彻底删除、一键清空",
  ],
  "0.1.3": [
    "🗑 回收站：删除不再直接消失，7 天内可还原",
    "回收站支持「彻底删除」和「一键清空」",
    "回收站条目显示发送时间 + 删除时间",
  ],
  "0.1.2": [
    "📋 粘贴截图：Win+Shift+S 截图后直接 Ctrl+V 即上传",
  ],
  "0.1.1": [
    "📋 复制按钮兼容局域网 HTTP（不再频繁复制失败）",
    "📄 长文本折叠 / 展开",
    "🔄 列表 5 秒自动刷新，新记录自动提示",
  ],
};

function updListHtml(vers) {
  return vers.map((v) =>
    `<div class="upd-ver">v${v}</div><ul class="upd-list">${CHANGELOG[v].map((n) => `<li>${n}</li>`).join("")}</ul>`
  ).join("");
}

function showUpdateCard(title, hint, vers) {
  $("#updTitle").textContent = title;
  $("#updHint").textContent = hint;
  $("#updList").innerHTML = updListHtml(vers);
  $("#updMask").style.display = "flex";
}

function maybeShowUpdate(version) {
  const seen = localStorage.getItem("toss_seen_ver");
  if (seen === version) return; // 已看过这个版本的更新说明
  localStorage.setItem("toss_seen_ver", version);
  if (!CHANGELOG[version]) return;
  showUpdateCard(`🎉 已更新到 v${version}`, "本次更新内容：", [version]);
}

/* 点版本徽章随时回看完整更新说明（新→旧全版本） */
$("#verChip").addEventListener("click", () => {
  showUpdateCard("📜 更新说明", "全部版本（新 → 旧）：", Object.keys(CHANGELOG));
});
$("#verChip").style.cursor = "pointer";
$("#verChip").title = "点击查看更新说明";

$("#btnUpdOk").addEventListener("click", () => { $("#updMask").style.display = "none"; });
$("#updMask").addEventListener("click", (e) => { if (e.target === $("#updMask")) $("#updMask").style.display = "none"; });

/* ---------- 应用内一键更新 ----------
   后端 /api/update/check 发现 Toss-vX.Y.Z.exe 版本包 → 横条提示；
   /api/update/apply 换包重启（旧进程退出，新 exe 自动拉起）→ 前端等服务回来后刷新 */
let pendingUpdate = null;

async function checkUpdate() {
  try {
    const u = await api("/api/update/check");
    pendingUpdate = u.available ? u : null;
    $("#updBannerVer").textContent = u.update_version || "";
    $("#updBanner").style.display = u.available ? "flex" : "none";
  } catch (_) {}
}

$("#btnApplyUpdate").addEventListener("click", async () => {
  if (!pendingUpdate) return;
  const target = pendingUpdate.update_version;
  if (!confirm(`更新到 v${target}？服务会短暂重启（几秒），其他正在用的人会掉线一次。`)) return;
  try {
    await api("/api/update/apply", { method: "POST" });
  } catch (e) { toast(e.message, "err"); return; }
  $("#updBanner").innerHTML = "<span>⏳ 更新中，服务重启后自动刷新，请稍候…</span>";
  const t0 = Date.now();
  let sawDown = false;
  const timer = setInterval(async () => {
    if (Date.now() - t0 > 60000) {
      clearInterval(timer);
      toast("更新等待超时，请手动刷新页面确认", "err", 5000);
      return;
    }
    try {
      await api("/api/health");
      if (sawDown || Date.now() - t0 > 5000) { clearInterval(timer); location.reload(); }
    } catch (_) { sawDown = true; }
  }, 1000);
});

/* ---------- 启动 ---------- */
async function boot() {
  try {
    const h = await api("/api/health");
    $("#ver").textContent = h.version;
    $("#verChip").textContent = "v" + h.version;
    if (h.need_password && !h.authed) { showLogin(true); return; }
    maybeShowUpdate(h.version);
    await Promise.all([loadItems(), renderSelfAddr(), renderRetentionFooter()]);
    checkUpdate();
  } catch (_) { showLogin(true); }
}
renderPeer();
boot();
