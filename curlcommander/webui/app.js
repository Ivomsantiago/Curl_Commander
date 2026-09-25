"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  let data;
  try { data = await res.json(); } catch { data = {}; }
  return { ok: res.ok, status: res.status, data };
}

let toastTimer = null;
function toast(msg, isErr) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.toggle("err", !!isErr);
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
}

// ---- navigation -----------------------------------------------------------

function showView(name) {
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("active", v.dataset.view === name));
  try { history.replaceState(null, "", "#" + name); } catch {}
  if (name === "history") loadHistory();
  if (name === "proxy") loadProxy();
  if (name === "scope") loadScope();
}
$$(".nav-item").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));

// request sub-tabs
$$(".ptab").forEach((b) =>
  b.addEventListener("click", () => {
    $$(".ptab").forEach((x) => x.classList.toggle("active", x === b));
    $$(".ptab-panel").forEach((p) => p.classList.toggle("active", p.dataset.ptab === b.dataset.ptab));
    if (b.dataset.ptab === "curl") refreshCurl();
  })
);

// ---- request building -----------------------------------------------------

function parseHeaders(text) {
  const out = {};
  text.split("\n").forEach((line) => {
    const i = line.indexOf(":");
    if (i > 0) {
      const k = line.slice(0, i).trim();
      const v = line.slice(i + 1).trim();
      if (k) out[k] = v;
    }
  });
  return out;
}

function currentRequest() {
  const bodyType = $("#body-type").value;
  const req = {
    method: $("#method").value,
    url: $("#url").value.trim(),
    headers: parseHeaders($("#headers").value),
  };
  const body = $("#body").value;
  if (bodyType !== "none" && body) {
    req.body = body;
    req.body_type = bodyType;
  }
  return req;
}

async function refreshCurl() {
  const req = currentRequest();
  if (!req.url) { $("#curl-preview").textContent = "—"; return; }
  const { data } = await api("POST", "/api/curl", req);
  $("#curl-preview").textContent = data.curl || data.error || "—";
}

function statusClass(code) {
  if (!code) return "";
  return "s" + String(code)[0];
}

function renderFindings(el, findings) {
  el.innerHTML = "";
  if (!findings || !findings.length) {
    el.innerHTML = '<div class="hint">Nenhum achado passivo.</div>';
    return;
  }
  findings.forEach((f) => {
    const d = document.createElement("div");
    d.className = "finding " + f.severity;
    d.innerHTML =
      `<div class="f-title"><span class="sev ${f.severity}">${f.severity}</span>${escapeHtml(f.title)}</div>` +
      `<div class="f-detail">${escapeHtml(f.detail || "")}</div>`;
    el.appendChild(d);
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

async function sendRequest() {
  const req = currentRequest();
  if (!req.url) { toast("Informe a URL", true); return; }
  $("#resp-meta").textContent = "enviando…";
  $("#resp-content").textContent = "";
  $("#resp-headers").textContent = "";
  $("#resp-findings").innerHTML = "";
  const { data } = await api("POST", "/api/send", req);
  if (data.error) { $("#resp-meta").textContent = ""; toast(data.error, true); return; }
  const r = data.response || {};
  const cls = statusClass(r.status_code);
  $("#resp-meta").innerHTML =
    `<span class="${cls}">${r.status_code ?? "ERR"} ${escapeHtml(r.reason || "")}</span> · ` +
    `${r.duration_ms ?? 0} ms · ${r.size_bytes ?? 0} B`;
  $("#resp-headers").textContent = Object.entries(r.headers || {}).map(([k, v]) => `${k}: ${v}`).join("\n");
  $("#resp-content").textContent = r.body || (r.error ? "Erro: " + r.error : "");
  if (data.curl) $("#curl-preview").textContent = data.curl;
  window._lastSendReq = req;
}

async function scanCurrent() {
  const req = window._lastSendReq || currentRequest();
  if (!req.url) { toast("Envie ou informe uma URL primeiro", true); return; }
  const { data } = await api("POST", "/api/passive", req);
  if (data.error) { toast(data.error, true); return; }
  renderFindings($("#resp-findings"), data.findings);
  toast(`${(data.findings || []).length} achado(s) passivo(s)`);
}

async function activeScanCurrent() {
  const req = window._lastSendReq || currentRequest();
  if (!req.url) { toast("Informe a URL primeiro", true); return; }
  if (!req.url.includes("?") && !(req.body_type === "form" && req.body)) {
    toast("Scan ativo precisa de parâmetros (query ?a=1 ou body form)", true);
    return;
  }
  $("#resp-findings").innerHTML = '<div class="hint">Scan ativo em andamento…</div>';
  const { data } = await api("POST", "/api/active", req);
  if (data.error) { $("#resp-findings").innerHTML = ""; toast(data.error, true); return; }
  renderFindings($("#resp-findings"), data.findings);
  toast(`Scan ativo: ${(data.findings || []).length} achado(s)`);
}

async function importCurl() {
  const cmd = $("#body").value.trim();
  if (!cmd) { toast("Cole um comando curl no corpo", true); return; }
  const { data } = await api("POST", "/api/import-curl", { command: cmd });
  if (data.error) { toast(data.error, true); return; }
  const c = data.config;
  $("#method").value = c.method || "GET";
  $("#url").value = c.url || "";
  const hs = (c.headers || []).map(([k, v]) => `${k}: ${v}`).join("\n");
  $("#headers").value = hs;
  if (c.body) { $("#body").value = c.body; $("#body-type").value = c.body_type || "raw"; }
  else { $("#body").value = ""; }
  toast("curl importado");
  refreshCurl();
}

// ---- history / proxy ------------------------------------------------------

function fillTable(tbody, entries, onClick, cols) {
  tbody.innerHTML = "";
  entries.forEach((e) => {
    const tr = document.createElement("tr");
    tr.innerHTML = cols(e);
    tr.addEventListener("click", () => onClick(e));
    tbody.appendChild(tr);
  });
}

async function loadHistory() {
  const { data } = await api("GET", "/api/history");
  fillTable(
    $("#history-table tbody"),
    data.entries || [],
    loadEntryIntoRequest,
    (e) =>
      `<td>${e.id}</td><td>${e.method}</td><td class="url">${escapeHtml(e.url)}</td>` +
      `<td class="${statusClass(e.status_code)}">${e.status_code ?? "—"}</td><td>${Math.round(e.duration_ms || 0)}</td><td>${e.origin || ""}</td>`
  );
}

let interceptTimer = null;
let currentHeld = null;

async function loadProxy() {
  await refreshProxyStatus();
  const { data } = await api("GET", "/api/history");
  const captured = (data.entries || []).filter((e) => (e.origin || "").startsWith("proxy") || (e.origin || "").startsWith("mcp"));
  fillTable(
    $("#proxy-table tbody"),
    captured,
    loadEntryIntoRequest,
    (e) =>
      `<td>${e.id}</td><td>${e.method}</td><td class="url">${escapeHtml(e.url)}</td>` +
      `<td class="${statusClass(e.status_code)}">${e.status_code ?? "—"}</td><td>${e.origin || ""}</td>`
  );
}

async function refreshProxyStatus() {
  const { data } = await api("GET", "/api/proxy/status");
  const st = data || {};
  if (!st.available) {
    $("#proxy-status").innerHTML = '<span class="s4">mitmproxy ausente</span> — instale: <code>curlcmd setup --proxy</code>';
  } else {
    $("#proxy-status").innerHTML = st.running
      ? `<span class="s2">rodando :${st.port}</span> · fila ${st.queued} · intercept ${st.intercept ? "ON" : "off"}`
      : "<span class='muted'>parado</span>";
  }
  if (st.ca_cert) $("#proxy-ca").innerHTML = `CA: <code>${escapeHtml(st.ca_cert)}</code> — confie só para testes e remova depois.`;
  if (st.error) toast(st.error, true);
  $("#intercept-toggle").checked = !!st.intercept;
  if (st.running && st.intercept) startInterceptPoll(); else stopInterceptPoll();
}

async function proxyStart() {
  const port = parseInt($("#proxy-port").value, 10) || 8080;
  const { data } = await api("POST", "/api/proxy/start", { port });
  if (data.error) toast(data.error, true); else toast("Proxy iniciado");
  refreshProxyStatus();
}
async function proxyStop() {
  await api("POST", "/api/proxy/stop", {});
  toast("Proxy parado");
  refreshProxyStatus();
}
async function interceptToggle() {
  const on = $("#intercept-toggle").checked;
  await api("POST", "/api/intercept/toggle", { on });
  refreshProxyStatus();
}
async function browserLaunch() {
  const engine = $("#browser-engine").value;
  const channel = $("#browser-channel").value.trim() || undefined;
  const { data } = await api("POST", "/api/browser/launch", { engine, channel });
  if (data.error) toast(data.error, true); else toast("Navegador aberto pelo proxy");
}

function startInterceptPoll() {
  if (interceptTimer) return;
  interceptTimer = setInterval(pollIntercept, 900);
  pollIntercept();
}
function stopInterceptPoll() {
  if (interceptTimer) { clearInterval(interceptTimer); interceptTimer = null; }
}
async function pollIntercept() {
  const { data } = await api("GET", "/api/intercept/queue");
  const q = (data && data.queue) || [];
  const panel = $("#intercept-panel");
  if (!q.length) { panel.style.display = "none"; currentHeld = null; return; }
  const held = q[0];
  panel.style.display = "flex";
  if (!currentHeld || currentHeld.id !== held.id) {
    currentHeld = held;
    const dir = held.direction === "request" ? "Requisição" : "Resposta";
    $("#intercept-label").textContent = `Interceptado (${dir}) — ${held.method || held.status || ""} ${held.url}  · fila ${q.length}`;
    $("#intercept-body").value = held.body || "";
  }
}
async function resolveIntercept(action) {
  if (!currentHeld) return;
  // Send the edited body only when it actually changed; otherwise null so the
  // backend forwards the original bytes untouched (binary uploads/images).
  let body = null;
  if (action !== "drop") {
    const edited = $("#intercept-body").value;
    body = edited === (currentHeld.body || "") ? null : edited;
  }
  await api("POST", "/api/intercept/resolve", { id: currentHeld.id, action, body });
  currentHeld = null;
  pollIntercept();
}

async function loadEntryIntoRequest(e) {
  const { data } = await api("GET", "/api/history/" + e.id);
  if (data.error) { toast(data.error, true); return; }
  const c = data.config;
  $("#method").value = c.method || "GET";
  $("#url").value = c.url || "";
  $("#headers").value = (c.headers || []).map(([k, v]) => `${k}: ${v}`).join("\n");
  if (c.body) { $("#body").value = c.body; $("#body-type").value = c.body_type || "raw"; }
  showView("request");
  refreshCurl();
  toast("Carregado no Repeater (#" + e.id + ")");
}

// ---- scan / scope ---------------------------------------------------------

async function runScan() {
  const url = $("#scan-url").value.trim();
  if (!url) { toast("Informe a URL", true); return; }
  $("#scan-findings").innerHTML = '<div class="hint">Analisando…</div>';
  const { data } = await api("POST", "/api/passive", { url });
  if (data.error) { $("#scan-findings").innerHTML = ""; toast(data.error, true); return; }
  renderFindings($("#scan-findings"), data.findings);
}

async function loadScope() {
  const { data } = await api("GET", "/api/scope");
  $("#scope-text").value = (data.scope || []).join("\n");
}

async function saveScope() {
  const entries = $("#scope-text").value.split("\n").map((s) => s.trim()).filter(Boolean);
  const { data } = await api("POST", "/api/scope", { entries });
  $("#scope-status").textContent = `Escopo salvo: ${(data.scope || []).length} host(s).`;
  toast("Escopo atualizado");
}

// ---- wire-up --------------------------------------------------------------

$("#send").addEventListener("click", sendRequest);
$("#scan-this").addEventListener("click", scanCurrent);
$("#active-this").addEventListener("click", activeScanCurrent);
$("#import-curl").addEventListener("click", importCurl);
$("#copy-curl").addEventListener("click", () => {
  navigator.clipboard?.writeText($("#curl-preview").textContent || "").then(() => toast("curl copiado"));
});
$("#history-refresh").addEventListener("click", loadHistory);
$("#proxy-start").addEventListener("click", proxyStart);
$("#proxy-stop").addEventListener("click", proxyStop);
$("#intercept-toggle").addEventListener("change", interceptToggle);
$("#browser-launch").addEventListener("click", browserLaunch);
$("#intercept-forward").addEventListener("click", () => resolveIntercept("forward"));
$("#intercept-drop").addEventListener("click", () => resolveIntercept("drop"));
$("#intercept-forward-all").addEventListener("click", async () => { await api("POST", "/api/intercept/forward-all", {}); currentHeld = null; pollIntercept(); });
$("#scan-run").addEventListener("click", runScan);
$("#scope-save").addEventListener("click", saveScope);
$("#url").addEventListener("keydown", (e) => { if (e.key === "Enter") sendRequest(); });
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") sendRequest();
});

(async function init() {
  const { data } = await api("GET", "/api/info");
  if (data.version) $("#brand-version").textContent = "v" + data.version + " · GUI";
  const tag = $("#engagement-tag");
  if (data.engagement) { tag.textContent = "engagement: " + data.engagement; tag.classList.add("eng"); }
  else { tag.textContent = "sem engagement"; }
  const initial = (location.hash || "").replace("#", "");
  if (["request", "history", "proxy", "scan", "scope"].includes(initial)) showView(initial);
})();
