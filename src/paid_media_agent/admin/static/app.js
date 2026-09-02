/* Paid Media Agent setup console: a guided wizard plus an advanced view over the same host actions. */
(() => {
  "use strict";
  const LOGOS = window.PMA_LOGOS || {};
  const state = { token: "", view: "wizard", step: null, routeId: "local", status: null, routes: [], processes: [], config: null,
    open: new Set(), results: new Map(), discovered: null, lastRouteId: null, picked: null, moreProviders: false,
    session: { modelTested: null, catalog: null, preflight: null, slack: null, db: null, answer: null, demo: null, draft: null } };
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
  const logo = (name, cls = "") => el("span", { class: `well ${cls}`, html: LOGOS[name] || "" });
  const check = (checked, large = false) => el("span", { class: `check${large ? " lg" : ""}`, "data-checked": checked ? "true" : "false", "aria-hidden": "true", html: '<svg viewBox="0 0 12 12"><path d="M2.5 6.5l2.4 2.4L9.5 3.7"/></svg>' });
  const badge = (tone, text) => el("span", { class: "badge", "data-tone": tone, text });
  const tick = () => el("span", { class: "tick", "aria-hidden": "true", html: '<svg viewBox="0 0 12 12"><path d="M2.5 6.5l2.4 2.4L9.5 3.7"/></svg>' });
  const facts = (items) => el("div", { class: "facts" }, items.map((t) => el("span", { class: "fact", text: t })));
  const cli = (command) => el("div", { class: "cli" }, [el("span", { class: "sigil", text: "$" }), el("code", { text: command })]);
  const intro = (logoName, title, note, actions = null, cls = "") => el("div", { class: "intro" }, [logo(logoName, cls), el("div", {}, [el("span", { class: "name", text: title }), el("span", { class: "note", text: note }), actions])]);
  const receipt = (tone, title, body) => el("div", { class: "receipt", "data-tone": tone }, [
    el("div", { class: "receipt-kicker" }, [badge(tone, (tone || "info").toUpperCase()), el("span", { class: "receipt-title", text: title })]),
    body ? el("p", { class: "receipt-body", text: body }) : null,
  ]);
  const quiet = (text, onclick) => el("button", { class: "link-quiet", type: "button", onclick, text });

  // ---- fragment: #token=...&view=...&step=...&route=...
  function readFragment() {
    const params = new URLSearchParams(location.hash.replace(/^#/, ""));
    const token = params.get("token");
    if (token) { state.token = token; try { sessionStorage.setItem("pma-admin-token", token); } catch (_) { /* private mode */ } }
    else { try { state.token = sessionStorage.getItem("pma-admin-token") || ""; } catch (_) { state.token = ""; } }
    state.view = params.get("view") || state.view;
    state.step = params.get("step") || state.step;
    state.routeId = params.get("route") || state.routeId;
  }
  function writeFragment() {
    const params = new URLSearchParams();
    if (state.token) params.set("token", state.token);
    params.set("view", state.view);
    if (state.view === "wizard" && state.step) params.set("step", state.step);
    if (state.view === "advanced") params.set("route", state.routeId);
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
    state.status = data.result; state.routes = data.routes; state.processes = data.processes;
    render();
  }
  async function loadConfig() { state.config = await api("/api/config"); }
  const saveConfig = (updates) => api("/api/config", { method: "POST", body: { updates } });
  const runAction = (name, payload = {}) => api(`/api/actions/${name}`, { method: "POST", body: payload });

  // ---- derived setup state
  function derive() {
    const d = state.status?.detail || {};
    const env = d.env || {};
    const model = d.model || {};
    const modelDone = !!model.package_installed && (d.model_key_env ? !!d.model_key_set : model.provider === "scripted");
    const tokenSet = !!d.pipeboard?.token_set;
    const realAccounts = String(d.accounts_path || "").endsWith("config/accounts.toml") && (d.accounts || []).length > 0;
    const runtime = d.runtime || "local";
    const slack = d.slack || {};
    const slackDone = !!slack.bot_token_set && (slack.transport === "socket_mode" ? !!slack.app_token_set : !!slack.signing_secret_set);
    const approvers = (d.writes?.approvers || []).length > 0;
    const mdaDone = !!d.mda?.langsmith_key_set && modelDone;
    const selfDone = slackDone && approvers;
    return { env, model, modelDone, tokenSet, realAccounts, pipeboardDone: tokenSet && realAccounts, runtime, slackDone, approvers, mdaDone, selfDone,
      pathDone: runtime === "mda" ? mdaDone : runtime === "self_hosted" ? selfDone : false };
  }
  function stepList() {
    const s = derive();
    const steps = [
      { id: "welcome", label: "Welcome", done: true },
      { id: "model", label: "Model", done: s.modelDone },
      { id: "pipeboard", label: "Ad accounts", done: s.pipeboardDone },
      { id: "try", label: "Try it", done: !!state.session.answer },
      { id: "path", label: "Where it lives", done: s.runtime !== "local" },
    ];
    if (s.runtime === "mda") steps.push({ id: "mda", label: "Deploy", done: s.mdaDone });
    else if (s.runtime === "self_hosted") steps.push({ id: "selfhost", label: "Slack & storage", done: s.selfDone });
    steps.push({ id: "done", label: "Done", done: false });
    return steps;
  }
  function firstOpenStep() {
    const steps = stepList();
    const next = steps.find((s) => !s.done && s.id !== "welcome" && s.id !== "done");
    return next ? next.id : "done";
  }

  // ---- render
  function render() {
    $("#brand-mark").innerHTML = LOGOS.langchain || "";
    const advanced = state.view === "advanced";
    $("#wizard").hidden = advanced;
    $("#advanced").hidden = !advanced;
    $("#view-toggle").textContent = advanced ? "Setup" : "Advanced";
    document.body.classList.toggle("advanced", advanced);
    writeFragment();
    if (advanced) { renderAdvanced(); return; }
    if (!state.step) state.step = "welcome";
    const known = stepList().map((s) => s.id);
    if (!known.includes(state.step)) state.step = firstOpenStep();
    writeFragment();
    renderProgress();
    renderScreen(false);
  }

  function renderProgress() {
    const nav = $("#progress");
    nav.replaceChildren();
    const steps = stepList();
    const currentIdx = Math.max(0, steps.findIndex((s) => s.id === state.step));
    const track = el("div", { class: "meter-track" });
    for (const [index, step] of steps.entries()) {
      const current = step.id === state.step;
      const ahead = !step.done && !current && index > currentIdx;
      track.append(el("button", {
        class: "chip", type: "button", "aria-current": current ? "step" : null,
        "aria-label": step.label,
        "data-done": step.done ? "true" : "false", "data-ahead": ahead ? "true" : "false",
        onclick: () => go(step.id),
      }, [el("span", { class: "seg", "aria-hidden": "true" }), el("span", { class: "chip-label", text: step.label })]));
    }
    nav.append(
      el("div", { class: "meter-head" }, [
        el("span", { class: "kicker", text: "Setup" }),
        el("span", { class: "step-switch", text: `${currentIdx + 1} of ${steps.length} · ${steps[currentIdx]?.label || ""}` }),
      ]),
      track,
    );
  }

  let screenToken = 0;
  function go(step) {
    if (step === state.step) return;
    state.step = step;
    writeFragment();
    renderProgress();
    renderScreen(true);
  }

  function renderScreen(animate = true) {
    const host = $("#screen");
    const token = ++screenToken;
    const build = { welcome: screenWelcome, model: screenModel, pipeboard: screenPipeboard, try: screenTry, path: screenPath, mda: screenMda, selfhost: screenSelfHost, done: screenDone }[state.step] || screenWelcome;
    const nodes = [].concat(build()).filter(Boolean);
    const swap = () => {
      if (token !== screenToken) return;
      host.replaceChildren(...nodes);
      if (animate) {
        host.setAttribute("data-enter", "");
        requestAnimationFrame(() => requestAnimationFrame(() => host.removeAttribute("data-enter")));
      }
    };
    if (animate && host.childElementCount) {
      host.setAttribute("data-exit", "");
      setTimeout(() => { host.removeAttribute("data-exit"); swap(); }, 90);
    } else swap();
  }
  const refreshScreen = () => { renderProgress(); renderScreen(false); };

  // ---- screens
  const EXAMPLES = [
    "Compare the last 14 days with the prior 14 days.",
    "Where is spend rising while CPA gets worse?",
    "Cut the Performance Max daily budget to 240.",
  ];

  function screenWelcome() {
    const demo = state.session.demo;
    const start = () => go(firstOpenStep() === "done" ? "model" : firstOpenStep());
    const actions = demo && demo.status === "ok"
      ? [el("button", { class: "btn btn-primary btn-block", type: "button", text: "Start setup", onclick: start })]
      : [
        el("button", { class: "btn btn-primary btn-block", type: "button", text: "Run the fixture demo", onclick: (ev) => demoInline(ev.currentTarget) }),
        el("button", { class: "link-quiet", type: "button", text: "Start setup", onclick: start }),
      ];
    return [
      el("div", { class: "hero" }, [
        el("h1", { class: "hero-title", text: "Paid Media Agent" }),
        el("p", { class: "hero-sub", text: "Run it locally with fixture data. Connect a model and ad accounts when you want live reads. Every write still waits for a signed approval." }),
      ]),
      el("div", { class: "pair" }, [
        stat("Reads", "Fixture data"),
        stat("Writes", "Need approval"),
      ]),
      el("div", { class: "break" }, [
        el("span", { class: "kicker", text: "Capabilities" }),
        el("div", { class: "break-track", "aria-hidden": "true" }, [
          el("span", { class: "break-seg", "data-tone": "info" }),
          el("span", { class: "break-seg", "data-tone": "positive" }),
          el("span", { class: "break-seg", "data-tone": "primary" }),
        ]),
        el("div", { class: "cap-row" }, [
          cap("Analyze", "Period comparison in Decimal, per platform."),
          cap("Change", "One mutation, bounded readback, honest receipt."),
          cap("Report", "HTML and PDF from a versioned payload."),
        ]),
      ]),
      el("div", { class: "form" }, [
        el("span", { class: "kicker", text: "Ask it things like" }),
        el("div", { class: "prompts" }, EXAMPLES.slice(0, 2).map((q) => el("button", { class: "prompt", type: "button", text: q, onclick: () => { state.session.draft = q; go("try"); } }))),
      ]),
      demo ? receipt(demo.status, demo.title, demo.body) : el("div", { class: "status-line", id: "welcome-status" }),
      el("div", { class: "actions stack" }, actions),
      cli("paid-media-agent demo --with-proposal"),
    ];
  }

  const cap = (name, note) => el("div", { class: "cap" }, [
    el("span", { class: "name", text: name }),
    el("span", { class: "note", text: note }),
  ]);
  const stat = (label, value) => el("div", { class: "stat" }, [
    el("span", { class: "kicker", text: label }),
    el("span", { class: "stat-value", text: value }),
  ]);

  async function demoInline(button) {
    const line = $("#welcome-status");
    await busy(button, async () => {
      if (line) setLine(line, "info", "Running the fixture demo through the real graph…");
      const result = await runAction("demo_run", { with_proposal: true });
      const status = result.detail?.receipt?.status;
      state.session.demo = {
        status: result.status,
        title: result.status === "ok" ? "Demo finished" : (result.summary || "Demo failed"),
        body: status
          ? `Analysis reconciled. A fake budget change was approved and verified (${status}).`
          : result.summary,
      };
      refreshScreen();
    });
  }

  function providerCard(p, { featured = false } = {}) {
    const lead = featured || p.id === "anthropic";
    return el("button", {
      class: `option${featured ? " lead" : " compact"}`, type: "button",
      "aria-pressed": state.picked === p.id ? "true" : "false",
      onclick: () => { state.picked = p.id; state.session.modelTested = null; if (p.id !== "anthropic") state.moreProviders = true; refreshScreen(); },
    }, [
      el("div", { class: "row" }, [logo(p.logo, p.logo === "langchain" ? "lc" : ""), el("span", { class: "name", text: p.label })]),
      el("span", { class: "note", text: p.note }),
      lead ? el("span", { class: "flag" }, [badge("info", "Recommended")]) : null,
    ]);
  }

  function screenModel() {
    const d = state.status.detail;
    const s = derive();
    const presets = d.model_presets || [];
    const currentSpec = d.model?.spec || "";
    const featured = presets.find((p) => p.id === "anthropic") || presets.find((p) => p.recommended) || presets[0];
    const rest = presets.filter((p) => p !== featured);
    if (!state.picked) {
      const byModel = presets.find((p) => p.id !== "custom" && currentSpec && p.model === currentSpec);
      const byKey = presets.find((p) => p.id !== "custom" && d.model_key_env && p.key === d.model_key_env && currentSpec.startsWith(p.model.split(":")[0] + ":"));
      state.picked = (byModel || byKey)?.id || (s.modelDone ? "custom" : (featured?.id || "anthropic"));
    }
    if (state.picked && featured && state.picked !== featured.id) state.moreProviders = true;
    const picker = el("div", { class: "provider-picker" }, [
      featured ? el("div", { class: "options lead stagger" }, [providerCard(featured, { featured: true })]) : null,
      rest.length ? el("button", {
        class: "more-toggle", type: "button", "aria-expanded": state.moreProviders ? "true" : "false",
        onclick: () => { state.moreProviders = !state.moreProviders; refreshScreen(); },
        text: state.moreProviders ? "Fewer providers" : `More providers (${rest.length})`,
      }) : null,
      state.moreProviders && rest.length ? el("div", { class: "options stagger" }, rest.map((p) => providerCard(p))) : null,
    ]);
    const nodes = [
      el("div", { class: "hero" }, [
        el("h1", { class: "hero-title", text: "Model" }),
        el("p", { class: "hero-sub", text: s.modelDone
          ? `${currentSpec} is saved in .env. Anthropic and OpenAI use native tool search; everything else uses the portable selector.`
          : "Pick a provider, paste a key, we test one call. The key stays in .env on this machine." }),
      ]),
      picker,
    ];
    const preset = presets.find((p) => p.id === state.picked);
    if (preset) {
      const isCustom = preset.id === "custom";
      const sameProvider = currentSpec && preset.model && currentSpec.split(":")[0] === preset.model.split(":")[0];
      const modelInput = el("input", { class: "input", id: "w-model", value: isCustom ? (s.modelDone ? currentSpec : "") : (sameProvider ? currentSpec : preset.model), placeholder: "provider:model", spellcheck: "false", autocomplete: "off" });
      const keyNameInput = el("input", { class: "input", id: "w-keyname", value: isCustom ? (d.model_key_env || "") : preset.key, placeholder: "MY_PROVIDER_API_KEY", spellcheck: "false", disabled: isCustom ? null : true });
      const keyInput = el("input", { class: "input", id: "w-key", type: "password", placeholder: (d.env || {})[isCustom ? d.model_key_env : preset.key] ? "Key already set. Paste to replace." : "API key", autocomplete: "off" });
      const showBase = isCustom || !!preset.base_url;
      const baseInput = el("input", { class: "input", id: "w-base", value: preset.base_url || (isCustom ? d.model_base_url || "" : ""), placeholder: "https://api.example.com/v1 (optional)", spellcheck: "false" });
      const form = el("form", { class: "form" }, [
        el("div", { class: "field-row" }, [
          el("div", { class: "field" }, [el("label", { for: "w-model", text: "Model" }), modelInput, el("span", { class: "hint", text: "provider:model. Edit the id to what your account allows." })]),
          el("div", { class: "field" }, [el("label", { for: "w-key", text: "API key" }), keyInput, el("span", { class: "hint" }, [el("span", { text: "Stored as " }), el("code", { class: "mono", text: isCustom ? "the name you choose" : preset.key })])]),
        ]),
        el("div", { class: "field-row" }, [
          isCustom ? el("div", { class: "field" }, [el("label", { for: "w-keyname", text: "Key name in .env" }), keyNameInput, el("span", { class: "hint", text: "Must end with _API_KEY." })]) : null,
          showBase ? el("div", { class: "field" }, [el("label", { for: "w-base", text: "Base URL" }), baseInput, el("span", { class: "hint", text: "For OpenAI-compatible endpoints. Native tool search is off through a proxy." })]) : null,
        ]),
        preset.url ? el("p", { class: "sub" }, [el("a", { href: preset.url, target: "_blank", rel: "noopener", text: `Create a key at ${preset.label}` })]) : null,
        preset.extra && !isCustom ? el("p", { class: "mini" }, [el("span", { text: "Needs the provider package: " }), el("code", { class: "mono", text: `uv sync --extra ${preset.extra}` })]) : null,
      ]);
      const line = el("div", { class: "status-line", id: "model-status" });
      if (state.session.modelTested) setLine(line, state.session.modelTested.status, state.session.modelTested.text);
      const save = el("button", { class: "btn btn-primary", type: "submit", text: "Save and test" });
      form.append(
        line,
        el("div", { class: "actions" }, [
          save,
          el("button", { class: "btn btn-outline", type: "button", text: "Continue", onclick: () => go("pipeboard") }),
          quiet("Skip for now", () => go("pipeboard")),
        ]),
        cli("paid-media-agent test model"),
      );
      form.addEventListener("submit", (ev) => { ev.preventDefault(); busy(save, async () => {
        const keyName = (isCustom ? keyNameInput.value : preset.key).trim();
        if (!/^[A-Z][A-Z0-9_]{1,40}_API_KEY$/.test(keyName)) { setLine(line, "fail", "Key name must look like MY_PROVIDER_API_KEY."); return; }
        const updates = { PAID_MEDIA_MODEL: modelInput.value.trim(), PAID_MEDIA_MODEL_API_KEY_ENV: keyName, PAID_MEDIA_MODEL_BASE_URL: showBase ? baseInput.value.trim() : "" };
        if (keyInput.value) updates[keyName] = keyInput.value;
        const saved = await saveConfig(updates);
        if (!saved.ok) { setLine(line, "fail", saved.summary); return; }
        setLine(line, "info", "Saved. Testing the model…");
        const test = await runAction("model_test");
        state.session.modelTested = { status: test.status, text: test.status === "ok" ? `${test.summary}. Tool selection: ${test.detail.selection}.` : test.summary };
        if (test.status === "ok") state.step = "pipeboard";
        await loadStatus();
      }); });
      nodes.push(form);
    }
    return nodes;
  }

  function screenPipeboard() {
    const d = state.status.detail;
    const s = derive();
    const nodes = [el("div", { class: "hero" }, [
      el("h1", { class: "hero-title", text: "Ad accounts" }),
      el("p", { class: "hero-sub", text: "Connect Pipeboard when you have live accounts. Until then the fixture catalog works." }),
    ])];
    const introNode = intro("pipeboard", "Pipeboard", "Google, Meta, and Reddit logins live there. Create a scoped read-only token and paste it here.",
      el("div", { class: "actions" }, [el("a", { class: "btn btn-outline btn-compact", href: "https://pipeboard.co/api-tokens", target: "_blank", rel: "noopener", text: "Open Pipeboard" })]));
    const tokenInput = el("input", { class: "input", id: "w-token", type: "password", placeholder: s.tokenSet ? "Token already set. Paste to replace." : "Pipeboard API token", autocomplete: "off" });
    const connect = el("button", { class: "btn btn-primary", type: "submit", text: s.tokenSet ? "Reconnect" : "Connect" });
    const line = el("div", { class: "status-line", id: "pb-status" });
    if (state.session.catalog) setLine(line, state.session.catalog.status, state.session.catalog.text);
    const form = el("form", { class: "form" }, [el("div", { class: "field" }, [el("label", { for: "w-token", text: "API token" }), tokenInput]), line, el("div", { class: "actions" }, [connect])]);
    form.addEventListener("submit", (ev) => { ev.preventDefault(); busy(connect, async () => {
      if (tokenInput.value) { const saved = await saveConfig({ PIPEBOARD_API_TOKEN: tokenInput.value }); if (!saved.ok) { setLine(line, "fail", saved.summary); return; } }
      setLine(line, "info", "Loading the live catalog…");
      const test = await runAction("pipeboard_test");
      state.session.catalog = { status: test.status, text: test.summary };
      const disc = await runAction("accounts_discover");
      state.discovered = disc.detail.accounts || [];
      await loadStatus();
    }); });
    nodes.push(introNode, form);
    if (state.discovered === null && s.tokenSet) {
      runAction("accounts_discover").then((disc) => { state.discovered = disc.detail.accounts || []; refreshScreen(); }).catch(() => {});
    }
    if (state.discovered && state.discovered.length) nodes.push(accountsPicker());
    else if (!s.tokenSet) nodes.push(el("p", { class: "sub", text: `No token yet. Reads use the fixture aliases: ${(d.accounts || []).map((a) => a.alias).join(", ") || "demo accounts"}.` }));
    nodes.push(el("p", { class: "sub" }, [
      el("span", { text: "LinkedIn Ads, X Ads, and OpenAI Ads are not on Pipeboard. " }),
      el("a", { href: "#", text: "Direct platforms", onclick: (ev) => { ev.preventDefault(); state.view = "advanced"; state.routeId = "direct"; render(); } }),
      el("span", { text: " takes their credentials and adds them to the same catalog." }),
    ]));
    nodes.push(
      el("div", { class: "actions" }, [
        el("button", { class: "btn btn-outline", type: "button", text: "Continue", onclick: () => go("try") }),
        quiet("Skip for now", () => go("try")),
      ]),
      cli("paid-media-agent accounts discover"),
    );
    return nodes;
  }

  function accountsPicker() {
    const rows = state.discovered;
    const selected = new Set(rows.filter((r) => !r.mapped_alias).map((r) => r.provider_account_id));
    const list = el("div", { class: "list" });
    const inputs = new Map();
    const paint = () => { for (const [id, node] of inputs) { node.box.dataset.checked = selected.has(id) ? "true" : "false"; } };
    for (const row of rows) {
      const mapped = !!row.mapped_alias;
      const box = check(mapped || selected.has(row.provider_account_id));
      const alias = el("input", { class: "input", value: row.mapped_alias || suggestAlias(row), spellcheck: "false", disabled: mapped ? true : null, onclick: (ev) => ev.stopPropagation() });
      const rowNode = el("div", { class: `list-row${mapped ? " static" : ""}`, role: mapped ? null : "checkbox", "aria-checked": mapped ? null : String(selected.has(row.provider_account_id)), tabindex: mapped ? null : "0" }, [
        el("div", { class: "row", style: "display:flex;align-items:center;gap:10px" }, [box, logo(platformLogo(row.platform))]),
        el("div", {}, [el("div", { class: "primary", text: row.name }), el("div", { class: "secondary", text: `${row.platform} · ${row.provider_account_id}${row.currency ? " · " + row.currency : ""}` })]),
        mapped ? badge("positive", `mapped as ${row.mapped_alias}`) : alias,
      ]);
      if (!mapped) {
        inputs.set(row.provider_account_id, { box, alias });
        const toggle = () => { if (selected.has(row.provider_account_id)) selected.delete(row.provider_account_id); else selected.add(row.provider_account_id); rowNode.setAttribute("aria-checked", String(selected.has(row.provider_account_id))); paint(); };
        rowNode.addEventListener("click", toggle);
        rowNode.addEventListener("keydown", (ev) => { if (ev.key === " " || ev.key === "Enter") { ev.preventDefault(); toggle(); } });
      }
      list.append(rowNode);
    }
    const line = el("div", { class: "status-line" });
    const map = el("button", { class: "btn btn-primary", type: "button", text: "Map selected", disabled: inputs.size ? null : true });
    map.addEventListener("click", () => busy(map, async () => {
      let ok = 0;
      for (const row of rows) {
        if (!selected.has(row.provider_account_id) || row.mapped_alias) continue;
        const entry = inputs.get(row.provider_account_id);
        const result = await api("/api/accounts", { method: "POST", body: { alias: entry.alias.value.trim(), platform: row.platform, provider_account_id: row.provider_account_id, currency: row.currency || "USD", timezone: row.timezone || "UTC" } });
        if (!result.ok) { setLine(line, "fail", result.summary); return; }
        ok += 1;
      }
      const disc = await runAction("accounts_discover");
      state.discovered = disc.detail.accounts || [];
      setLine(line, "ok", `${ok} account${ok === 1 ? "" : "s"} mapped.`);
      if (ok > 0) state.step = "try";
      await loadStatus();
    }));
    return el("div", { class: "form" }, [el("h2", { class: "section-title", text: "Choose the accounts to use" }), list, line, el("div", { class: "actions" }, [map])]);
  }
  const platformLogo = (platform) => ({ google_ads: "google", meta_ads: "langchain", reddit_ads: "langchain" }[platform] || "langchain");
  const suggestAlias = (row) => `${row.platform.replace("_ads", "")}-${(row.name || "main").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "").slice(0, 24) || "main"}`;

  function screenTry() {
    const d = state.status.detail;
    const s = derive();
    const studio = d.studio || {};
    const question = el("textarea", { class: "input", id: "w-q", rows: "3", placeholder: "Ask something about the connected accounts…" });
    question.value = state.session.draft || EXAMPLES[0];
    const ask = el("button", { class: "btn btn-primary", type: "submit", text: "Ask", disabled: s.modelDone ? null : true });
    const line = el("div", { class: "status-line", id: "ask-status" });
    const answerBox = el("div", { class: "answer", hidden: state.session.answer ? null : true }, [
      el("div", { class: "receipt-kicker" }, [badge("ok", "OK"), el("span", { class: "receipt-title", text: "Answer" })]),
      el("pre", { class: "answer-body", text: state.session.answer || "" }),
    ]);
    const form = el("form", { class: "form" }, [
      el("div", { class: "field" }, [el("label", { for: "w-q", text: "Ask the agent" }), question]),
      el("div", { class: "prompts" }, EXAMPLES.map((q) => el("button", { class: "prompt", type: "button", text: q, onclick: () => { question.value = q; } }))),
      line, answerBox,
      el("div", { class: "actions" }, [ask, el("span", { class: "mini", text: s.modelDone ? (s.tokenSet ? "Runs against your live catalog." : "Runs against the demo accounts until Pipeboard is connected.") : "Add a model first." })]),
    ]);
    form.addEventListener("submit", (ev) => { ev.preventDefault(); busy(ask, async () => {
      setLine(line, "info", "Thinking…");
      const result = await runAction("ask", { question: question.value });
      if (!result.ok) { setLine(line, "fail", result.summary); return; }
      state.session.answer = result.detail.answer;
      answerBox.hidden = false;
      const body = answerBox.querySelector(".answer-body");
      if (body) body.textContent = result.detail.answer;
      setLine(line, "ok", `Answered with ${d.model?.spec} (${result.detail.selection} tool selection).`);
      renderProgress();
    }); });
    const studioBlock = el("div", { class: "block" }, [
      intro("langchain", "LangGraph Studio", "Optional. Starts a local server on 127.0.0.1:2024 so you can watch tool calls and the approval interrupt.",
        el("div", { class: "actions" }, [
          ...(studio.installed ? [processButton("studio", "Start Studio", true, false, !s.modelDone), el("a", { class: "btn btn-outline", href: studio.url, target: "_blank", rel: "noopener", text: "Open Studio" })] : [el("code", { class: "mono", text: "uv sync --extra studio" }), el("span", { class: "mini", text: "installs the local server" })]),
        ]), "lc"),
      processStatus("studio"),
    ]);
    return [
      el("div", { class: "hero" }, [
        el("h1", { class: "hero-title", text: "Try it" }),
        el("p", { class: "hero-sub", text: "One question through the same compiled graph your deploy will run." }),
      ]),
      form,
      studioBlock,
      el("div", { class: "actions" }, [el("button", { class: "btn btn-outline", type: "button", text: "Continue", onclick: () => go("path") })]),
      cli("langgraph dev  # http://127.0.0.1:2024"),
    ];
  }

  function processButton(name, label, isPrimary, needsConfirm, disabled) {
    const p = state.processes.find((x) => x.name === name) || {};
    const running = !!p.running;
    const b = el("button", { class: `btn ${isPrimary ? "btn-primary" : "btn-outline"}`, type: "button", text: running ? "Stop" : label, disabled: disabled && !running ? true : null });
    b.addEventListener("click", () => busy(b, async () => {
      if (running) await api(`/api/processes/${name}/stop`, { method: "POST" });
      else { if (needsConfirm && !window.confirm("Deploy to LangSmith Cloud now? This is an outward-facing action.")) return; await api(`/api/processes/${name}/start`, { method: "POST", body: { confirm: !!needsConfirm } }); }
      await loadStatus();
    }));
    return b;
  }
  function processStatus(name) {
    const p = state.processes.find((x) => x.name === name) || {};
    // Show the log while it runs, or when it failed. A finished run leaves no clutter behind.
    if (!p.running && !p.returncode) return null;
    return el("div", { class: "form" }, [el("div", { class: "status-line" }, [badge(p.running ? "positive" : "info", p.running ? `running · ${p.command}` : `${p.command} · exited ${p.returncode ?? ""}`)]), el("pre", { class: "log mono", text: p.log_tail || "" })]);
  }

  function screenPath() {
    const s = derive();
    const choose = async (button, runtime) => busy(button, async () => { await saveConfig({ PAID_MEDIA_RUNTIME: runtime }); await loadStatus(); go(runtime === "mda" ? "mda" : "selfhost"); });
    const card = (id, logoNode, title, note, bullets, pressed, recommended) => el("button", { class: "option", type: "button", "aria-pressed": pressed ? "true" : "false", onclick: (ev) => choose(ev.currentTarget, id) }, [
      el("div", { class: "row" }, [logoNode, el("span", { class: "name", text: title })]),
      el("span", { class: "note", text: note }),
      el("ul", {}, bullets.map((b) => el("li", {}, [tick(), el("span", { text: b })]))),
      recommended ? el("span", { class: "pick" }, [badge("info", "Recommended")]) : null,
    ]);
    return [
      el("div", { class: "hero" }, [
        el("h1", { class: "hero-title", text: "Where it lives" }),
        el("p", { class: "hero-sub", text: "Same agent either way. Managed hosts threads and Slack. Self-host keeps Postgres and the Slack app yours." }),
      ]),
      el("div", { class: "options two stagger" }, [
        card("mda", logo("langchain", "lc"), "Managed Deep Agents", "One command deploy on LangSmith Cloud.", ["mda dev runs it locally with Studio", "Slack app provisioned on first deploy", "Managed threads, sandbox, and schedules", "Secrets forwarded from your .env"], s.runtime === "mda", true),
        card("self_hosted", logo("slack"), "Self-host with Slack", "Your Postgres, your Slack app, your API.", ["Block Kit review cards with edits", "Socket Mode, no public URL needed", "Full control of data and auth"], s.runtime === "self_hosted", false),
      ]),
      el("div", { class: "actions" }, [quiet("Stay local", () => go("done"))]),
    ];
  }

  function screenMda() {
    const d = state.status.detail;
    const s = derive();
    const keyInput = el("input", { class: "input", id: "w-ls", type: "password", placeholder: d.env?.LANGSMITH_API_KEY ? "Key already set. Paste to replace." : "LangSmith API key", autocomplete: "off" });
    const save = el("button", { class: "btn btn-primary", type: "submit", text: "Save and run preflight" });
    const line = el("div", { class: "status-line" });
    const preflight = state.session.preflight;
    const items = preflight ? [["mda CLI installed", preflight.cli_installed], ["LangSmith key", preflight.langsmith_key_set], ["agent.py imports", preflight.import_smoke === "ok"], ["Model package and key", preflight.model_package && preflight.provider_key_set], ["Slack channel declared", preflight.slack_channel]] : [];
    const form = el("form", { class: "form" }, [
      el("div", { class: "field" }, [el("label", { for: "w-ls", text: "LangSmith API key" }), keyInput, el("span", { class: "hint" }, [el("a", { href: "https://smith.langchain.com/settings", target: "_blank", rel: "noopener", text: "Create a key in LangSmith" })])]),
      line,
      el("div", { class: "actions" }, [save]),
    ]);
    form.addEventListener("submit", (ev) => { ev.preventDefault(); busy(save, async () => {
      if (keyInput.value) { const saved = await saveConfig({ LANGSMITH_API_KEY: keyInput.value }); if (!saved.ok) { setLine(line, "fail", saved.summary); return; } }
      setLine(line, "info", "Running preflight…");
      const result = await runAction("mda_check");
      state.session.preflight = result.detail;
      state.session.preflightSummary = result.summary;
      await loadStatus();
    }); });
    const nodes = [el("div", { class: "hero" }, [
      el("h1", { class: "hero-title", text: "Managed Deep Agents" }),
      el("p", { class: "hero-sub", text: "Deploy compiles agent.py, skills, and the Slack channel. Non-reserved .env values become deployment secrets." }),
    ]), form];
    if (preflight) {
      nodes.push(el("ul", { class: "checklist" }, items.map(([label, done]) => el("li", { "data-done": done ? "true" : "false" }, [check(!!done), el("span", { text: label })]))));
      const ready = items.every(([, done]) => done);
      nodes.push(processControls("mda-deploy", ready ? "Deploy" : "Deploy (blocked)", !ready, true, "mda-dev", "Run locally with Studio"));
    }
    nodes.push(
      el("div", { class: "actions" }, [
        el("button", { class: "btn btn-outline", type: "button", text: "Continue", onclick: () => go("done") }),
        el("button", { class: "btn btn-ghost", type: "button", text: "Switch to self-host", onclick: () => go("path") }),
      ]),
      cli("mda deploy ."),
    );
    return nodes;
  }

  function screenSelfHost() {
    const d = state.status.detail;
    const s = derive();
    const env = d.env || {};
    // Slack
    const bot = el("input", { class: "input", type: "password", placeholder: env.SLACK_BOT_TOKEN ? "Set. Paste to replace." : "xoxb-…", autocomplete: "off" });
    const app = el("input", { class: "input", type: "password", placeholder: env.SLACK_APP_TOKEN ? "Set. Paste to replace." : "xapp-…", autocomplete: "off" });
    const approvers = el("input", { class: "input", value: (d.writes?.approvers || []).join(", "), placeholder: "slack:T0123:U0456, slack:T0123:U0789", spellcheck: "false" });
    const slackLine = el("div", { class: "status-line" });
    if (state.session.slack) setLine(slackLine, state.session.slack.status, state.session.slack.text);
    const slackSave = el("button", { class: "btn btn-primary", type: "submit", text: "Save and test Slack" });
    const slackForm = el("form", { class: "form" }, [
      intro("slack", "Slack", "Create the app from the manifest, install it, then paste the bot token and the app-level token (Socket Mode).",
        el("div", { class: "actions" }, [el("a", { class: "btn btn-outline btn-compact", href: "https://api.slack.com/apps?new_app=1", target: "_blank", rel: "noopener", text: "Create Slack app" }), el("code", { class: "mono", text: "config/slack-manifest.example.yaml" })])),
      el("div", { class: "field-row" }, [el("div", { class: "field" }, [el("label", { text: "Bot token" }), bot]), el("div", { class: "field" }, [el("label", { text: "App-level token" }), app])]),
      el("div", { class: "field" }, [el("label", { text: "Who can approve changes" }), approvers, el("span", { class: "hint", text: "Slack user refs. Card location is never authorization." })]),
      slackLine,
      el("div", { class: "actions" }, [slackSave]),
    ]);
    slackForm.addEventListener("submit", (ev) => { ev.preventDefault(); busy(slackSave, async () => {
      const updates = { SLACK_TRANSPORT: "socket_mode", PAID_MEDIA_APPROVER_IDS: approvers.value.trim() };
      if (bot.value) updates.SLACK_BOT_TOKEN = bot.value;
      if (app.value) updates.SLACK_APP_TOKEN = app.value;
      const saved = await saveConfig(updates);
      if (!saved.ok) { setLine(slackLine, "fail", saved.summary); return; }
      setLine(slackLine, "info", "Testing Slack…");
      const test = await runAction("slack_test");
      state.session.slack = { status: test.status, text: test.summary };
      await loadStatus();
    }); });
    // Storage
    const db = el("input", { class: "input", type: "password", placeholder: env.DATABASE_URL ? "Set. Paste to replace." : "postgresql://user:pass@host/db (optional)", autocomplete: "off" });
    const dbLine = el("div", { class: "status-line" });
    if (state.session.db) setLine(dbLine, state.session.db.status, state.session.db.text);
    const dbSave = el("button", { class: "btn btn-primary", type: "submit", text: "Save and test" });
    const gen = el("button", { class: "btn btn-outline", type: "button", text: env.PAID_MEDIA_API_TOKENS && env.PAID_MEDIA_APPROVAL_SIGNING_KEY ? "Regenerate API token and signing key" : "Generate API token and signing key" });
    gen.addEventListener("click", () => busy(gen, async () => {
      const result = await runAction("generate_secrets");
      const token = result.detail?.api_token_show_once;
      setLine(dbLine, result.status, token ? `Done. Your API token (shown once): ${token}` : result.summary);
      await loadStatus();
    }));
    const dbForm = el("form", { class: "form" }, [
      intro("postgres", "Storage and API", "Postgres keeps threads, proposals, and receipts across restarts. Leave it empty to run in memory."),
      el("div", { class: "field" }, [el("label", { text: "Database URL" }), db]),
      dbLine,
      el("div", { class: "actions" }, [dbSave, gen]),
    ]);
    dbForm.addEventListener("submit", (ev) => { ev.preventDefault(); busy(dbSave, async () => {
      if (db.value) { const saved = await saveConfig({ DATABASE_URL: db.value }); if (!saved.ok) { setLine(dbLine, "fail", saved.summary); return; } }
      const test = await runAction("database_test");
      state.session.db = { status: test.status, text: test.summary };
      await loadStatus();
    }); });
    return [
      el("div", { class: "hero" }, [
        el("h1", { class: "hero-title", text: "Slack and storage" }),
        el("p", { class: "hero-sub", text: "Socket Mode needs no public URL. Postgres keeps threads and receipts across restarts; skip it to stay in memory." }),
      ]),
      slackForm,
      el("div", { class: "block" }, [dbForm]),
      el("div", { class: "block" }, [el("h2", { class: "section-title", text: "Run it" }), processControls("serve", "Start API", false, false, "slack", "Start Slack adapter")]),
      el("div", { class: "actions" }, [
        el("button", { class: "btn btn-outline", type: "button", text: "Continue", onclick: () => go("done") }),
        el("button", { class: "btn btn-ghost", type: "button", text: "Switch to managed", onclick: () => go("path") }),
      ]),
      cli("paid-media-agent serve"),
    ];
  }

  function processControls(name, label, disabled, confirm, secondName, secondLabel) {
    const proc = (n) => state.processes.find((p) => p.name === n) || {};
    const button = (n, text, isPrimary, needsConfirm) => {
      const p = proc(n);
      const running = !!p.running;
      const b = el("button", { class: `btn ${isPrimary ? "btn-primary" : "btn-outline"}`, type: "button", text: running ? `Stop ${text.replace(/^Start |^Deploy.*$/, "") || text}` : text, disabled: disabled && !running ? true : null });
      b.addEventListener("click", () => busy(b, async () => {
        if (running) { await api(`/api/processes/${n}/stop`, { method: "POST" }); }
        else {
          if (needsConfirm && !window.confirm("Deploy to LangSmith Cloud now? This is an outward-facing action.")) return;
          await api(`/api/processes/${n}/start`, { method: "POST", body: { confirm: !!needsConfirm } });
        }
        await loadStatus();
      }));
      return b;
    };
    const wrap = el("div", { class: "form" }, [el("div", { class: "actions" }, [button(name, label, true, confirm), secondName ? button(secondName, secondLabel, false, false) : null])]);
    for (const n of [name, secondName].filter(Boolean)) {
      const p = proc(n);
      if (p.running || p.log_tail) wrap.append(el("div", { class: "status-line" }, [badge(p.running ? "positive" : "info", p.running ? `running · ${p.command}` : `${p.command} · exited ${p.returncode ?? ""}`)]), el("pre", { class: "log mono", text: p.log_tail || "" }));
    }
    return wrap;
  }

  function screenDone() {
    const s = derive();
    const d = state.status.detail;
    const items = [["Model", s.modelDone, d.model?.spec], ["Ad accounts", s.pipeboardDone, s.tokenSet ? `${(d.accounts || []).length} alias(es)` : "demo accounts"], ["Where it lives", s.runtime !== "local", s.runtime === "mda" ? "Managed Deep Agents" : s.runtime === "self_hosted" ? "Self-hosted" : "local"], ["Slack", s.slackDone, s.slackDone ? d.slack?.transport : "not connected"]];
    const doctor = el("button", { class: "btn btn-outline btn-block", type: "button", text: "Run doctor" });
    const doctorLine = el("div", { class: "status-line", id: "done-doctor" });
    doctor.addEventListener("click", () => busy(doctor, async () => {
      const result = await runAction("status");
      setLine(doctorLine, result.status, result.summary || "Doctor finished.");
    }));
    return [
      el("div", { class: "hero" }, [
        el("h1", { class: "hero-title", text: "You're set" }),
        el("p", { class: "hero-sub", text: "Local setup is on this machine. Advanced holds the catalog, write policy, and running processes." }),
      ]),
      el("div", { class: "pair" }, [
        stat("Model", s.modelDone ? (d.model?.spec || "Saved") : "Not set"),
        stat("Accounts", s.tokenSet ? `${(d.accounts || []).length} alias(es)` : "Fixture data"),
      ]),
      el("ul", { class: "checklist stagger" }, items.map(([label, done, meta]) => el("li", { "data-done": done ? "true" : "false" }, [check(done), el("span", { text: label }), el("span", { class: "sub mono", text: meta || "" })]))),
      doctorLine,
      el("div", { class: "actions stack" }, [
        el("button", { class: "btn btn-primary btn-block", type: "button", text: "Open Advanced", onclick: () => { state.view = "advanced"; render(); } }),
        doctor,
        el("button", { class: "btn btn-line btn-block", type: "button", text: s.runtime === "mda" ? "Back to deploy" : "Where it lives", onclick: () => go(s.runtime === "mda" ? "mda" : s.runtime === "self_hosted" ? "selfhost" : "path") }),
      ]),
      cli("paid-media-agent doctor"),
    ];
  }

  // ---- helpers
  function setLine(line, status, text) {
    line.replaceChildren(badge(status === "ok" ? "ok" : status === "warn" ? "warn" : status === "fail" ? "fail" : "info", (status || "info").toUpperCase()), el("span", { text }));
    line.setAttribute("data-enter", "");
    requestAnimationFrame(() => requestAnimationFrame(() => line.removeAttribute("data-enter")));
  }
  async function busy(button, fn) {
    const label = button.textContent;
    button.disabled = true; button.textContent = "Working…";
    try { await fn(); }
    catch (error) { const line = button.closest("form, .form, .screen")?.querySelector(".status-line"); if (line) setLine(line, "fail", error.message); else showFatal(error); }
    finally { button.disabled = false; button.textContent = label; }
  }
  function showFatal(error) { $("#foot").textContent = error.message; }
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    $("#theme-toggle").textContent = theme === "dark" ? "Light" : "Dark";
    try { localStorage.setItem("pma-admin-theme", theme); } catch (_) { /* ignore */ }
  }

  // ---- advanced view (dense routes over the same actions)
  function renderAdvanced() {
    renderRail();
    const route = state.routes.find((r) => r.id === state.routeId) || state.routes[0];
    if (!route) return;
    state.routeId = route.id;
    writeFragment();
    $("#page-title").textContent = route.title;
    $("#page-tagline").textContent = route.tagline;
    $("#page-desc").textContent = route.description;
    const actions = $("#page-actions");
    actions.replaceChildren(el("button", { class: "btn btn-outline btn-compact", type: "button", text: "Run doctor", onclick: (ev) => runInline(ev.currentTarget, "status") }));
    renderBanner();
    renderSteps(route);
    renderProcesses();
  }
  function renderRail() {
    const nav = $("#rail-nav");
    nav.replaceChildren();
    for (const route of state.routes) {
      const done = route.steps.filter((s) => s.status === "done").length;
      const total = route.steps.filter((s) => s.status !== "optional").length;
      nav.append(el("button", { class: "rail-item", type: "button", "aria-current": route.id === state.routeId ? "page" : null, onclick: () => { state.routeId = route.id; renderAdvanced(); } }, [el("span", { text: route.title }), el("span", { class: "progress-count", text: `${done}/${total}` })]));
    }
  }
  function renderBanner() {
    const banner = $("#banner");
    const failing = (state.status?.detail?.checks || []).filter((c) => c.status === "fail");
    const writes = state.status?.detail?.writes || {};
    if (writes.kill_switch_engaged) { banner.hidden = false; banner.dataset.tone = "risk"; banner.textContent = "Kill switch engaged: every write execution is refused until it is cleared from the Write gates route."; return; }
    if (failing.length) { banner.hidden = false; banner.dataset.tone = ""; banner.textContent = `Doctor reports failing checks: ${failing.map((c) => c.name).join(", ")}.`; return; }
    banner.hidden = true; banner.textContent = "";
  }
  function renderSteps(route) {
    const list = $("#steps");
    list.replaceChildren();
    list.classList.toggle("stagger", state.lastRouteId !== route.id);
    state.lastRouteId = route.id;
    const tpl = $("#tpl-step");
    route.steps.forEach((step, index) => {
      const node = tpl.content.firstElementChild.cloneNode(true);
      node.dataset.step = step.id;
      const key = `${route.id}:${step.id}`;
      $(".step-status", node).dataset.status = step.status;
      $(".step-status-text", node).textContent = step.status;
      $(".step-title", node).textContent = `${index + 1}. ${step.title}`;
      $(".step-desc", node).textContent = step.description;
      const note = $(".step-note", node);
      if (step.note && step.note.length <= 24) { note.hidden = false; note.textContent = step.note; }
      else if (step.note) { $(".step-main", node).append(el("span", { class: "step-meta", text: step.note })); }
      $(".step-cli code", node).textContent = step.cli;
      $(".copy", node).addEventListener("click", () => copyText(step.cli, $(".copy", node)));
      const head = $(".step-head", node); const body = $(".step-body", node);
      const open = state.open.has(key);
      node.dataset.open = open ? "true" : "false"; head.setAttribute("aria-expanded", open ? "true" : "false"); body.hidden = !open;
      head.addEventListener("click", () => {
        const next = !state.open.has(key);
        if (next) state.open.add(key); else state.open.delete(key);
        node.dataset.open = next ? "true" : "false"; head.setAttribute("aria-expanded", next ? "true" : "false"); body.hidden = !next;
        if (next) renderAction(step, node);
      });
      if (open) renderAction(step, node);
      const stored = state.results.get(key);
      if (stored) paintResult(node, stored.result, stored.includeDetail, stored.extraRender, false);
      list.append(node);
    });
  }
  async function renderAction(step, node) {
    const box = $(".step-action", node);
    box.replaceChildren();
    const action = step.action;
    if (!action) return;
    if (action.kind === "form") { if (!state.config) await loadConfig(); box.append(buildForm(action, node)); }
    else if (action.kind === "test" || action.kind === "run") { const b = el("button", { class: "btn btn-primary btn-compact", type: "button", text: action.label }); b.addEventListener("click", () => runInline(b, action.action, action.payload || {}, node)); box.append(b); }
    else if (action.kind === "link") box.append(el("a", { class: "btn btn-outline btn-compact", href: action.href, target: "_blank", rel: "noopener", text: action.label }));
    else if (action.kind === "command") box.append(el("span", { class: "form-note", text: "Copy the command above and run it in your terminal." }));
    else if (action.kind === "accounts") box.append(buildAccounts(node));
    else if (action.kind === "policy") { const b = el("button", { class: "btn btn-primary btn-compact", type: "button", text: action.label }); b.addEventListener("click", () => runInline(b, "policy_validate", action.payload || {}, node, renderPolicy)); box.append(b); }
    else if (action.kind === "process") box.append(buildProcess(action, node));
    else if (action.kind === "kill_switch") box.append(buildKillSwitch(node));
  }
  function buildForm(action, node) {
    const form = el("form", { class: "form" });
    const keys = state.config.detail.keys.filter((k) => action.keys.includes(k.name));
    for (const key of keys) {
      const input = key.name === "SLACK_TRANSPORT"
        ? el("select", { class: "input", name: key.name }, ["socket_mode", "http"].map((v) => el("option", { value: v, text: v, selected: key.value === v ? true : null })))
        : el("input", { class: "input", name: key.name, type: key.secret ? "password" : "text", placeholder: key.is_set && key.secret ? "set (leave blank to keep)" : key.example || "", value: key.secret ? "" : key.value, autocomplete: "off", spellcheck: "false" });
      input.id = `f-${key.name}`; input.dataset.initial = key.secret ? "" : key.value;
      form.append(el("div", { class: "field" }, [el("label", { for: `f-${key.name}` }, [el("span", { text: key.name }), el("span", { class: "hint", text: key.description + (key.is_set ? " · set" : "") })]), input]));
    }
    const save = el("button", { class: "btn btn-primary btn-compact", type: "submit", text: action.label });
    form.append(el("div", { class: "form-actions" }, [save, el("span", { class: "form-note", text: "Written to .env on this machine. Secrets are never displayed." })]));
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const updates = {};
      for (const input of form.querySelectorAll("input, select")) {
        if (input.type === "password" && input.value === "") continue;
        if (input.type !== "password" && input.value === (input.dataset.initial ?? "")) continue;
        updates[input.name] = input.value;
      }
      if (!Object.keys(updates).length) return showResult(node, { status: "warn", summary: "Nothing to save.", detail: {} });
      await withBusy(save, async () => { showResult(node, await saveConfig(updates)); state.config = null; await loadStatus(); });
    });
    return form;
  }
  function buildAccounts(node) {
    const wrap = el("div", { class: "form wide" });
    const discover = el("button", { class: "btn btn-primary btn-compact", type: "button", text: "Discover accounts" });
    const list = el("div");
    wrap.append(el("div", { class: "form-actions" }, [discover, el("span", { class: "form-note", text: "Host-side listing through Pipeboard. Ids stay in config/accounts.toml." })]), list);
    discover.addEventListener("click", () => withBusy(discover, async () => { const result = await runAction("accounts_discover"); state.discovered = result.detail.accounts || []; showResult(node, result, false); list.replaceChildren(renderAccountTable(state.discovered, node)); }));
    if (state.discovered) list.replaceChildren(renderAccountTable(state.discovered, node));
    const current = state.status?.detail?.accounts || [];
    if (current.length) {
      wrap.append(el("div", { class: "caps", text: "Mapped aliases" }), el("table", { class: "data" }, [
        el("thead", {}, el("tr", {}, ["Alias", "Platform", "Provider id", "Currency", "Timezone", ""].map((h) => el("th", { text: h })))),
        el("tbody", {}, current.map((a) => el("tr", {}, [el("td", { class: "mono", text: a.alias }), el("td", { text: a.platform }), el("td", { class: "mono", text: a.provider_account_id_masked }), el("td", { text: a.currency }), el("td", { text: a.timezone }),
          el("td", {}, el("button", { class: "btn btn-ghost btn-compact", type: "button", text: "Remove", onclick: async (ev) => withBusy(ev.currentTarget, async () => { showResult(node, await api(`/api/accounts/${encodeURIComponent(a.alias)}`, { method: "DELETE" })); await loadStatus(); }) }))]))),
      ]));
    }
    return wrap;
  }
  function renderAccountTable(rows, node) {
    if (!rows.length) return el("p", { class: "form-note", text: "No accounts returned. Connect platforms in Pipeboard first." });
    return el("table", { class: "data" }, [
      el("thead", {}, el("tr", {}, ["Platform", "Account", "Provider id", "Alias", ""].map((h) => el("th", { text: h })))),
      el("tbody", {}, rows.map((row) => {
        const alias = el("input", { class: "input", value: row.mapped_alias || suggestAlias(row), disabled: row.mapped_alias ? true : null });
        const add = row.mapped_alias ? badge("positive", `mapped as ${row.mapped_alias}`) : el("button", { class: "btn btn-primary btn-compact", type: "button", text: "Map" });
        if (!row.mapped_alias) add.addEventListener("click", () => withBusy(add, async () => {
          showResult(node, await api("/api/accounts", { method: "POST", body: { alias: alias.value.trim(), platform: row.platform, provider_account_id: row.provider_account_id, currency: row.currency || "USD", timezone: row.timezone || "UTC" } }));
          const refreshed = await runAction("accounts_discover"); state.discovered = refreshed.detail.accounts || state.discovered; await loadStatus();
        }));
        return el("tr", {}, [el("td", { text: row.platform }), el("td", { text: row.name }), el("td", { class: "mono", text: row.provider_account_id }), el("td", {}, alias), el("td", {}, add)]);
      })),
    ]);
  }
  function renderPolicy(result) {
    const box = el("div", { class: "form" });
    const admitted = result.detail.admitted || []; const issues = result.detail.issues || [];
    box.append(el("div", { class: "caps", text: `Admitted (${admitted.length})` }), el("code", { class: "mono", text: admitted.join(", ") || "none" }));
    if (issues.length) box.append(el("div", { class: "caps", text: "Rows with issues" }), el("table", { class: "data" }, [el("tbody", {}, issues.map((i) => el("tr", {}, [el("td", { class: "mono", text: i.tool }), el("td", { text: i.reason })])))]));
    return box;
  }
  function buildProcess(action, node) {
    const wrap = el("div", { class: "form" });
    const proc = state.processes.find((p) => p.name === action.action) || {};
    const running = !!proc.running;
    const start = el("button", { class: "btn btn-primary btn-compact", type: "button", text: action.label, disabled: running ? true : null });
    const stop = el("button", { class: "btn btn-outline btn-compact", type: "button", text: "Stop", disabled: running ? null : true });
    const status = badge(running ? "positive" : "info", running ? `running · pid ${proc.pid}` : (proc.returncode !== null && proc.returncode !== undefined ? `exited ${proc.returncode}` : "stopped"));
    const log = el("pre", { class: "proc-log mono", text: proc.log_tail || "No log yet." });
    start.addEventListener("click", () => withBusy(start, async () => { const confirm = !!(action.payload && action.payload.confirm); if (confirm && !window.confirm("Deploy to LangSmith Cloud now? This is an outward-facing action.")) return; await api(`/api/processes/${action.action}/start`, { method: "POST", body: { confirm } }); await loadStatus(); }));
    stop.addEventListener("click", () => withBusy(stop, async () => { await api(`/api/processes/${action.action}/stop`, { method: "POST" }); await loadStatus(); }));
    const refresh = el("button", { class: "btn btn-ghost btn-compact", type: "button", text: "Refresh log", onclick: async () => { const view = await api(`/api/processes/${action.action}/log`); log.textContent = view.log_tail || "No log yet."; } });
    wrap.append(el("div", { class: "form-actions" }, [start, stop, refresh, status]), log);
    return wrap;
  }
  function buildKillSwitch(node) {
    const engaged = !!state.status?.detail?.writes?.kill_switch_engaged;
    const wrap = el("div", { class: "form" });
    const engage = el("button", { class: "btn btn-risk btn-compact", type: "button", text: "Engage kill switch", disabled: engaged ? true : null });
    const clear = el("button", { class: "btn btn-outline btn-compact", type: "button", text: "Clear kill switch", disabled: engaged ? null : true });
    engage.addEventListener("click", () => withBusy(engage, async () => { showResult(node, await api("/api/kill-switch", { method: "POST", body: { engaged: true } })); await loadStatus(); }));
    clear.addEventListener("click", () => withBusy(clear, async () => { if (!window.confirm("Clear the kill switch? Only do this after the incident review.")) return; showResult(node, await api("/api/kill-switch", { method: "POST", body: { engaged: false, confirm: true } })); await loadStatus(); }));
    wrap.append(el("div", { class: "form-actions" }, [engage, clear, badge(engaged ? "risk" : "positive", engaged ? "engaged" : "clear")]));
    return wrap;
  }
  function renderProcesses() {
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
  async function runInline(button, action, payload = {}, node = null, extraRender = null) {
    await withBusy(button, async () => {
      const result = await runAction(action, payload);
      if (node) showResult(node, result, true, extraRender); else { const first = $("#steps .step"); if (first) showResult(first, result); }
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
    box.replaceChildren(); box.hidden = false;
    if (animate) box.setAttribute("data-entering", "");
    box.append(el("div", { class: "result-head" }, [badge(result.status || "info", (result.status || "info").toUpperCase()), el("span", { class: "result-summary", text: result.summary || "" })]));
    if (result.command) box.append(el("code", { class: "mono", text: result.command }));
    if (extraRender) box.append(extraRender(result));
    else if (includeDetail && result.detail && Object.keys(result.detail).length) {
      const detail = { ...result.detail };
      for (const k of ["answer", "receipt_message"]) if (detail[k]) { box.append(el("pre", { class: "result-detail mono", text: detail[k] })); delete detail[k]; }
      for (const k of ["api_token_show_once", "show_once"]) if (detail[k]) { box.append(el("div", { class: "kv" }, [el("dt", { text: "Token (shown once)" }), el("dd", { text: detail[k] })])); delete detail[k]; }
      if (detail.usage) { box.append(el("div", { class: "kv" }, [el("dt", { text: "Use as" }), el("dd", { text: detail.usage })])); delete detail.usage; }
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
    catch (error) { const step = button.closest(".step"); if (step) showResult(step, { status: "fail", summary: error.message, detail: {} }); else { const banner = $("#banner"); banner.hidden = false; banner.textContent = error.message; } }
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
  $("#view-toggle").addEventListener("click", () => { state.view = state.view === "advanced" ? "wizard" : "advanced"; render(); });
  window.addEventListener("hashchange", () => { readFragment(); render(); });
  loadStatus().catch(showFatal);
  setInterval(() => { if (state.processes.some((p) => p.running)) loadStatus().catch(() => {}); }, 4000);
})();
