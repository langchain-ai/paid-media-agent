/* Paid Media Agent setup console. Vanilla JS; every action mirrors a CLI command. */
(() => {
  "use strict";

  const state = { token: "", routeId: "local", status: null, routes: [], processes: [], config: null, open: new Set(), results: new Map(), discovered: null, lastRouteId: null };
  const $ = (sel, root = document) => root.querySelector(sel);
  const el = (tag, attrs = {}, children = []) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k === "html") node.innerHTML = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v === true ? "" : v);
    }
    for (const child of [].concat(children)) if (child) node.append(child);
    return node;
  };

  // ---- fragment: #token=...&route=...
  function readFragment() {
    const params = new URLSearchParams(location.hash.replace(/^#/, ""));
    const token = params.get("token");
    if (token) {
      state.token = token;
      try { sessionStorage.setItem("pma-admin-token", token); } catch (_) { /* private mode */ }
    } else {
      try { state.token = sessionStorage.getItem("pma-admin-token") || ""; } catch (_) { state.token = ""; }
    }
    state.routeId = params.get("route") || state.routeId;
  }
  function writeFragment() {
    const params = new URLSearchParams();
    if (state.token) params.set("token", state.token);
    params.set("route", state.routeId);
    history.replaceState(null, "", `#${params.toString()}`);
  }

  // ---- api
  async function api(path, options = {}) {
    const headers = { "X-Admin-Token": state.token, ...(options.body ? { "Content-Type": "application/json" } : {}) };
    const response = await fetch(path, { ...options, headers, body: options.body ? JSON.stringify(options.body) : undefined });
    if (response.status === 401) throw new Error("This page is not authorized. Restart `paid-media-agent setup` and use the printed link.");
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `request failed (${response.status})`);
    return data;
  }

  async function loadStatus() {
    const data = await api("/api/status");
    state.status = data.result;
    state.routes = data.routes;
    state.processes = data.processes;
    render();
  }
  async function loadConfig() {
    state.config = await api("/api/config");
  }

  // ---- theme
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    $("#theme-toggle").textContent = theme === "dark" ? "Light theme" : "Dark theme";
    try { localStorage.setItem("pma-admin-theme", theme); } catch (_) { /* ignore */ }
  }

  // ---- rendering
  function render() {
    renderRail();
    const route = state.routes.find((r) => r.id === state.routeId) || state.routes[0];
    if (!route) return;
    state.routeId = route.id;
    writeFragment();
    $("#page-title").textContent = route.title;
    $("#page-tagline").textContent = route.tagline;
    $("#page-desc").textContent = route.description;
    renderPageActions(route);
    renderBanner();
    renderSteps(route);
    renderProcesses(route);
  }

  function renderRail() {
    const nav = $("#rail-nav");
    nav.replaceChildren();
    for (const route of state.routes) {
      const done = route.steps.filter((s) => s.status === "done").length;
      const total = route.steps.filter((s) => s.status !== "optional").length;
      const item = el("button", { class: "rail-item", type: "button", "aria-current": route.id === state.routeId ? "page" : null, onclick: () => { state.routeId = route.id; render(); } }, [
        el("span", { text: route.title }),
        el("span", { class: "progress", text: `${done}/${total}` }),
      ]);
      nav.append(item);
    }
  }

  function renderPageActions(route) {
    const box = $("#page-actions");
    box.replaceChildren();
    const doctor = el("button", { class: "btn btn-outline btn-compact", type: "button", text: "Run doctor", onclick: () => runInline(doctor, "status") });
    box.append(doctor);
    if (route.id === "writes") {
      const link = el("a", { class: "btn btn-ghost btn-compact", href: "https://github.com/amal-irgashev/paid-media-agent-open-source/blob/main/docs/operations/live-write-runbook.md", target: "_blank", rel: "noopener", text: "Runbook" });
      box.append(link);
    }
  }

  function renderBanner() {
    const banner = $("#banner");
    const failing = (state.status?.detail?.checks || []).filter((c) => c.status === "fail");
    const writes = state.status?.detail?.writes || {};
    if (writes.kill_switch_engaged) {
      banner.hidden = false; banner.dataset.tone = "risk";
      banner.textContent = "Kill switch engaged: every write execution is refused until it is cleared from the Write gates route.";
      return;
    }
    if (failing.length) {
      banner.hidden = false; banner.dataset.tone = "";
      banner.textContent = `Doctor reports failing checks: ${failing.map((c) => c.name).join(", ")}.`;
      return;
    }
    banner.hidden = true;
    banner.textContent = "";
  }

  function renderSteps(route) {
    const list = $("#steps");
    list.replaceChildren();
    // Entrance motion only when the route changes; refreshes must not replay it.
    list.classList.toggle("stagger", state.lastRouteId !== route.id);
    state.lastRouteId = route.id;
    const tpl = $("#tpl-step");
    route.steps.forEach((step, index) => {
      const node = tpl.content.firstElementChild.cloneNode(true);
      node.dataset.step = step.id;
      const key = `${route.id}:${step.id}`;
      const status = $(".step-status", node);
      status.dataset.status = step.status;
      $(".step-status-text", node).textContent = step.status;
      $(".step-title", node).textContent = `${index + 1}. ${step.title}`;
      $(".step-desc", node).textContent = step.description;
      const note = $(".step-note", node);
      if (step.note && step.note.length <= 24) { note.hidden = false; note.textContent = step.note; }
      else if (step.note) { $(".step-main", node).append(el("span", { class: "step-meta", text: step.note })); }
      $(".step-cli code", node).textContent = step.cli;
      $(".copy", node).addEventListener("click", () => copyText(step.cli, $(".copy", node)));
      const head = $(".step-head", node);
      const body = $(".step-body", node);
      const open = state.open.has(key);
      node.dataset.open = open ? "true" : "false";
      head.setAttribute("aria-expanded", open ? "true" : "false");
      body.hidden = !open;
      head.addEventListener("click", () => {
        const next = !state.open.has(key);
        if (next) state.open.add(key); else state.open.delete(key);
        node.dataset.open = next ? "true" : "false";
        head.setAttribute("aria-expanded", next ? "true" : "false");
        body.hidden = !next;
        if (next) renderAction(step, node);
      });
      if (open) renderAction(step, node);
      const stored = state.results.get(key);
      if (stored) paintResult(node, stored.result, stored.includeDetail, stored.extraRender, false);
      list.append(node);
    });
  }

  // ---- step actions
  async function renderAction(step, node) {
    const box = $(".step-action", node);
    box.replaceChildren();
    const action = step.action;
    if (!action) return;
    if (action.kind === "form") {
      if (!state.config) await loadConfig();
      box.append(buildForm(action, node));
    } else if (action.kind === "test" || action.kind === "run") {
      const button = el("button", { class: "btn btn-primary btn-compact", type: "button", text: action.label });
      button.addEventListener("click", () => runInline(button, action.action, action.payload || {}, node));
      box.append(button);
    } else if (action.kind === "link") {
      box.append(el("a", { class: "btn btn-outline btn-compact", href: action.href, target: "_blank", rel: "noopener", text: action.label }));
    } else if (action.kind === "command") {
      box.append(el("span", { class: "form-note", text: "Copy the command above and run it in your terminal." }));
    } else if (action.kind === "accounts") {
      box.append(buildAccounts(node));
    } else if (action.kind === "policy") {
      const button = el("button", { class: "btn btn-primary btn-compact", type: "button", text: action.label });
      button.addEventListener("click", () => runInline(button, "policy_validate", action.payload || {}, node, renderPolicy));
      box.append(button);
    } else if (action.kind === "process") {
      box.append(buildProcess(action, node));
    } else if (action.kind === "kill_switch") {
      box.append(buildKillSwitch(node));
    }
  }

  function buildForm(action, node) {
    const form = el("form", { class: "form" });
    const keys = state.config.detail.keys.filter((k) => action.keys.includes(k.name));
    for (const key of keys) {
      const input = key.name === "SLACK_TRANSPORT"
        ? el("select", { class: "input", name: key.name }, ["socket_mode", "http"].map((v) => el("option", { value: v, text: v, selected: key.value === v ? true : null })))
        : el("input", { class: "input", name: key.name, type: key.secret ? "password" : "text", placeholder: key.is_set && key.secret ? "set (leave blank to keep)" : key.example || "", value: key.secret ? "" : key.value, autocomplete: "off", spellcheck: "false" });
      const label = el("label", { for: `f-${key.name}` }, [el("span", { text: key.name }), el("span", { class: "hint", text: key.description + (key.is_set ? " · set" : "") })]);
      input.id = `f-${key.name}`;
      input.dataset.initial = key.secret ? "" : key.value;
      form.append(el("div", { class: "field" }, [label, input]));
    }
    const save = el("button", { class: "btn btn-primary btn-compact", type: "submit", text: action.label });
    form.append(el("div", { class: "form-actions" }, [save, el("span", { class: "form-note", text: "Written to .env on this machine. Secrets are never displayed." })]));
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const updates = {};
      for (const input of form.querySelectorAll("input, select")) {
        if (input.type === "password" && input.value === "") continue;
        const before = input.dataset.initial ?? "";
        if (input.type !== "password" && input.value === before) continue;
        updates[input.name] = input.value;
      }
      if (!Object.keys(updates).length) return showResult(node, { status: "warn", summary: "Nothing to save.", detail: {} });
      await withBusy(save, async () => {
        const result = await api("/api/config", { method: "POST", body: { updates } });
        showResult(node, result);
        state.config = null;
        await loadStatus();
      });
    });
    return form;
  }

  function buildAccounts(node) {
    const wrap = el("div", { class: "form wide" });
    const discover = el("button", { class: "btn btn-primary btn-compact", type: "button", text: "Discover accounts" });
    const list = el("div");
    wrap.append(el("div", { class: "form-actions" }, [discover, el("span", { class: "form-note", text: "Host-side listing through Pipeboard. Ids stay in config/accounts.toml." })]), list);
    discover.addEventListener("click", () => withBusy(discover, async () => {
      const result = await api("/api/actions/accounts_discover", { method: "POST", body: {} });
      state.discovered = result.detail.accounts || [];
      showResult(node, result, false);
      list.replaceChildren(renderAccountTable(state.discovered, node));
    }));
    if (state.discovered) list.replaceChildren(renderAccountTable(state.discovered, node));
    const current = state.status?.detail?.accounts || [];
    if (current.length) {
      const table = el("table", { class: "data" }, [
        el("thead", {}, el("tr", {}, ["Alias", "Platform", "Provider id", "Currency", "Timezone", ""].map((h) => el("th", { text: h })))),
        el("tbody", {}, current.map((a) => el("tr", {}, [
          el("td", { class: "mono", text: a.alias }), el("td", { text: a.platform }), el("td", { class: "mono", text: a.provider_account_id_masked }),
          el("td", { text: a.currency }), el("td", { text: a.timezone }),
          el("td", {}, el("button", { class: "btn btn-ghost btn-compact", type: "button", text: "Remove", onclick: async (ev) => withBusy(ev.currentTarget, async () => { showResult(node, await api(`/api/accounts/${encodeURIComponent(a.alias)}`, { method: "DELETE" })); await loadStatus(); }) })),
        ]))),
      ]);
      wrap.append(el("div", { class: "caps", text: "Mapped aliases" }), table);
    }
    return wrap;
  }

  function renderAccountTable(rows, node) {
    if (!rows.length) return el("p", { class: "form-note", text: "No accounts returned. Connect platforms in Pipeboard first." });
    const table = el("table", { class: "data" }, [
      el("thead", {}, el("tr", {}, ["Platform", "Account", "Provider id", "Alias", ""].map((h) => el("th", { text: h })))),
      el("tbody", {}, rows.map((row) => {
        const alias = el("input", { class: "input", placeholder: `${row.platform.replace("_ads", "")}-main`, value: `${row.platform.replace("_ads", "")}-${row.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "").slice(0, 24) || "main"}` });
        const add = row.mapped_alias
          ? el("span", { class: "badge", "data-tone": "positive", text: `mapped as ${row.mapped_alias}` })
          : el("button", { class: "btn btn-primary btn-compact", type: "button", text: "Map" });
        if (!row.mapped_alias) add.addEventListener("click", () => withBusy(add, async () => {
          const result = await api("/api/accounts", { method: "POST", body: { alias: alias.value.trim(), platform: row.platform, provider_account_id: row.provider_account_id, currency: row.currency || "USD", timezone: row.timezone || "UTC" } });
          showResult(node, result);
          const refreshed = await api("/api/actions/accounts_discover", { method: "POST", body: {} });
          state.discovered = refreshed.detail.accounts || state.discovered;
          await loadStatus();
        }));
        return el("tr", {}, [el("td", { text: row.platform }), el("td", { text: row.name }), el("td", { class: "mono", text: row.provider_account_id }), el("td", {}, alias), el("td", {}, add)]);
      })),
    ]);
    return table;
  }

  function renderPolicy(result) {
    const box = el("div", { class: "form" });
    const admitted = result.detail.admitted || [];
    const issues = result.detail.issues || [];
    box.append(el("div", { class: "caps", text: `Admitted (${admitted.length})` }));
    box.append(el("code", { class: "mono", text: admitted.join(", ") || "none" }));
    if (issues.length) {
      box.append(el("div", { class: "caps", text: "Rows with issues" }));
      box.append(el("table", { class: "data" }, [el("tbody", {}, issues.map((i) => el("tr", {}, [el("td", { class: "mono", text: i.tool }), el("td", { text: i.reason })])))]));
    }
    return box;
  }

  function buildProcess(action, node) {
    const wrap = el("div", { class: "form" });
    const proc = state.processes.find((p) => p.name === action.action) || {};
    const running = !!proc.running;
    const start = el("button", { class: "btn btn-primary btn-compact", type: "button", text: action.label, disabled: running ? true : null });
    const stop = el("button", { class: "btn btn-outline btn-compact", type: "button", text: "Stop", disabled: running ? null : true });
    const badge = el("span", { class: "badge badge-quiet", "data-tone": running ? "positive" : null, text: running ? `running · pid ${proc.pid}` : (proc.returncode !== null && proc.returncode !== undefined ? `exited ${proc.returncode}` : "stopped") });
    const log = el("pre", { class: "proc-log mono", text: proc.log_tail || "No log yet." });
    start.addEventListener("click", () => withBusy(start, async () => {
      const confirm = !!(action.payload && action.payload.confirm);
      if (confirm && !window.confirm("Deploy to LangSmith Cloud now? This is an outward-facing action. Preflight must be green.")) return;
      await api(`/api/processes/${action.action}/start`, { method: "POST", body: { confirm } });
      await loadStatus();
    }));
    stop.addEventListener("click", () => withBusy(stop, async () => { await api(`/api/processes/${action.action}/stop`, { method: "POST" }); await loadStatus(); }));
    const refresh = el("button", { class: "btn btn-ghost btn-compact", type: "button", text: "Refresh log", onclick: async () => { const view = await api(`/api/processes/${action.action}/log`); log.textContent = view.log_tail || "No log yet."; } });
    wrap.append(el("div", { class: "form-actions" }, [start, stop, refresh, badge]), log);
    return wrap;
  }

  function buildKillSwitch(node) {
    const engaged = !!state.status?.detail?.writes?.kill_switch_engaged;
    const wrap = el("div", { class: "form" });
    const badge = el("span", { class: "badge badge-quiet", "data-tone": engaged ? "risk" : "positive", text: engaged ? "engaged" : "clear" });
    const engage = el("button", { class: "btn btn-risk btn-compact", type: "button", text: "Engage kill switch", disabled: engaged ? true : null });
    const clear = el("button", { class: "btn btn-outline btn-compact", type: "button", text: "Clear kill switch", disabled: engaged ? null : true });
    engage.addEventListener("click", () => withBusy(engage, async () => { showResult(node, await api("/api/kill-switch", { method: "POST", body: { engaged: true } })); await loadStatus(); }));
    clear.addEventListener("click", () => withBusy(clear, async () => {
      if (!window.confirm("Clear the kill switch? Only do this after the incident review.")) return;
      showResult(node, await api("/api/kill-switch", { method: "POST", body: { engaged: false, confirm: true } }));
      await loadStatus();
    }));
    wrap.append(el("div", { class: "form-actions" }, [engage, clear, badge]));
    return wrap;
  }

  function renderProcesses(route) {
    const box = $("#processes");
    box.replaceChildren();
    const running = state.processes.filter((p) => p.running);
    if (!running.length) return;
    box.append(el("div", { class: "caps", text: "Running" }));
    for (const proc of running) {
      const stop = el("button", { class: "btn btn-outline btn-compact", type: "button", text: "Stop" });
      stop.addEventListener("click", () => withBusy(stop, async () => { await api(`/api/processes/${proc.name}/stop`, { method: "POST" }); await loadStatus(); }));
      box.append(el("div", { class: "proc" }, [el("div", {}, [el("div", { class: "label", text: proc.command }), el("div", { class: "meta", text: `pid ${proc.pid} · log ${proc.log_path}` })]), stop]));
    }
  }

  // ---- results
  async function runInline(button, action, payload = {}, node = null, extraRender = null) {
    await withBusy(button, async () => {
      const result = await api(`/api/actions/${action}`, { method: "POST", body: payload });
      if (node) showResult(node, result, true, extraRender);
      else {
        const first = $("#steps .step");
        if (first) showResult(first, result);
      }
      await loadStatus();
    });
  }

  function showResult(node, result, includeDetail = true, extraRender = null) {
    const key = `${state.routeId}:${node.dataset.step}`;
    state.results.set(key, { result, includeDetail, extraRender });
    paintResult(node, result, includeDetail, extraRender);
  }

  function paintResult(node, result, includeDetail = true, extraRender = null, animate = true) {
    const box = $(".step-result", node);
    box.replaceChildren();
    box.hidden = false;
    // Entrance motion only for a fresh result; a repaint after refresh must be steady.
    if (animate) box.setAttribute("data-entering", "");
    const badge = el("span", { class: "badge", "data-tone": result.status || "info", text: (result.status || "info").toUpperCase() });
    box.append(el("div", { class: "result-head" }, [badge, el("span", { class: "result-summary", text: result.summary || "" })]));
    if (result.command) box.append(el("code", { class: "mono", text: result.command }));
    if (extraRender) box.append(extraRender(result));
    else if (includeDetail && result.detail && Object.keys(result.detail).length) {
      const detail = { ...result.detail };
      if (detail.answer) { box.append(el("pre", { class: "result-detail mono", text: detail.answer })); delete detail.answer; }
      if (detail.receipt_message) { box.append(el("pre", { class: "result-detail mono", text: detail.receipt_message })); delete detail.receipt_message; }
      if (detail.api_token_show_once) { box.append(el("div", { class: "kv" }, [el("dt", { text: "API token (shown once)" }), el("dd", { text: detail.api_token_show_once })])); delete detail.api_token_show_once; }
      if (detail.show_once) { box.append(el("div", { class: "kv" }, [el("dt", { text: "Token (shown once)" }), el("dd", { text: detail.show_once })])); delete detail.show_once; }
      const flat = Object.entries(detail).filter(([, v]) => ["string", "number", "boolean"].includes(typeof v));
      if (flat.length) box.append(el("dl", { class: "kv" }, flat.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", { text: String(v) })])));
      const nested = Object.fromEntries(Object.entries(detail).filter(([, v]) => v && typeof v === "object"));
      if (Object.keys(nested).length) box.append(el("pre", { class: "result-detail mono", text: JSON.stringify(nested, null, 2) }));
    }
    requestAnimationFrame(() => box.removeAttribute("data-entering"));
  }

  async function withBusy(button, fn) {
    const label = button.textContent;
    button.disabled = true; button.textContent = "Working…";
    try { await fn(); }
    catch (error) { const step = button.closest(".step"); if (step) showResult(step, { status: "fail", summary: error.message, detail: {} }); else $("#banner").hidden = false, $("#banner").textContent = error.message; }
    finally { button.disabled = false; button.textContent = label; }
  }

  async function copyText(text, button) {
    try { await navigator.clipboard.writeText(text); button.textContent = "Copied"; setTimeout(() => (button.textContent = "Copy"), 1200); }
    catch (_) { button.textContent = "Select and copy"; }
  }

  // ---- boot
  readFragment();
  let theme = "light";
  try { theme = localStorage.getItem("pma-admin-theme") || "light"; } catch (_) { /* ignore */ }
  applyTheme(theme);
  $("#theme-toggle").addEventListener("click", () => applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark"));
  $("#refresh").addEventListener("click", () => loadStatus().catch(showFatal));
  window.addEventListener("hashchange", () => { readFragment(); render(); });
  loadStatus().catch(showFatal);
  setInterval(() => { if (state.processes.some((p) => p.running)) loadStatus().catch(() => {}); }, 4000);

  function showFatal(error) {
    $("#page-title").textContent = "Setup console";
    const banner = $("#banner"); banner.hidden = false; banner.dataset.tone = "risk"; banner.textContent = error.message;
  }
})();
