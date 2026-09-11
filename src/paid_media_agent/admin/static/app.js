/* Paid Media Agent setup console: a guided wizard plus an advanced view over the same host actions. */
(() => {
  "use strict";
  const LOGOS = window.PMA_LOGOS || {};
  const state = { token: "", view: "wizard", step: null, routeId: "local", status: null, routes: [], processes: [], config: null,
    open: new Set(), results: new Map(), discovered: null, lastRouteId: null, picked: null, direction: "forward", maxReached: 0,
    session: { modelTested: null, catalog: null, preflight: null, slack: null, db: null, answer: null, skipped: {} } };
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
  const logo = (name, cls = "") => el("span", { class: `well icon ${cls}`, "data-slot": "icon-well", html: LOGOS[name] || "" });
  const check = (checked, large = false) => el("span", { class: `check${large ? " lg" : ""}`, "data-checked": checked ? "true" : "false", "aria-hidden": "true", html: '<svg viewBox="0 0 12 12"><path d="M2.5 6.5l2.4 2.4L9.5 3.7"/></svg>' });
  const badge = (tone, text) => el("span", { class: "badge", "data-tone": tone, text });
  const FEATURED_PRESETS = ["langsmith", "anthropic", "openai"];
  const CORE = [
    { id: "model", label: "Model", note: "Pick a provider and paste a key" },
    { id: "pipeboard", label: "Accounts", note: "Connect or use demo data" },
    { id: "try", label: "Ask", note: "One question through the real graph" },
  ];
  const RAIL = [
    ...CORE,
    { id: "path", label: "Where it lives", note: "Stay local, or deploy" },
  ];
  // Every command is shown the way a fresh checkout runs it, matching README and OPERATIONS.
  // Answers arrive as markdown. Escape everything, then render the small subset the agent uses.
  const escapeHtml = (t) => t.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const inline = (t) => escapeHtml(t).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  function renderMarkdown(text) {
    const lines = String(text || "").split("\n"); const html = []; let list = null; let table = null;
    const flush = () => { if (list) { html.push(`</${list}>`); list = null; } if (table) { html.push("</tbody></table>"); table = null; } };
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (/^\|.*\|$/.test(line)) {
        const cells = line.slice(1, -1).split("|").map((c) => c.trim());
        if (cells.every((c) => /^:?-{2,}:?$/.test(c))) continue;
        if (!table) { if (list) flush(); table = "open"; html.push(`<table><thead><tr>${cells.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>`); continue; }
        html.push(`<tr>${cells.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`); continue;
      }
      if (table) flush();
      const heading = /^(#{1,4})\s+(.*)$/.exec(line);
      if (heading) { flush(); html.push(`<h${heading[1].length + 1}>${inline(heading[2])}</h${heading[1].length + 1}>`); continue; }
      if (/^(-{3,}|\*{3,})$/.test(line)) { flush(); html.push("<hr>"); continue; }
      const bullet = /^\s*[-*]\s+(.*)$/.exec(line); const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
      if (bullet || numbered) { const kind = bullet ? "ul" : "ol"; if (list !== kind) { flush(); list = kind; html.push(`<${kind}>`); } html.push(`<li>${inline((bullet || numbered)[1])}</li>`); continue; }
      if (!line.trim()) { flush(); continue; }
      flush(); html.push(`<p>${inline(line)}</p>`);
    }
    flush(); return html.join("");
  }
  // Our own commands run through uv; anything else (docker, open, git) is shown as typed.
  const cli = (command) => el("div", { class: "cli" }, [el("span", { class: "sigil", text: "$" }), el("code", { text: /^(uv run |paid-media-agent |mda )/.test(command) && !command.startsWith("uv run ") ? `uv run ${command}` : command })]);
  const intro = (logoName, title, note, actions = null, cls = "") => el("div", { class: "intro" }, [logo(logoName, cls), el("div", {}, [el("span", { class: "name", text: title }), el("span", { class: "note", text: note }), actions])]);
  const disclose = (summary, open, children) => el("details", { class: "disclose", open: open ? true : null }, [
    el("summary", { text: summary }),
    el("div", { class: "disclose-body" }, children),
  ]);
  const cliDetails = (command) => disclose("CLI equivalent", false, [cli(command)]);
  const hero = (title, why) => el("div", { class: "hero", "data-slot": "form-section" }, [
    el("h1", { class: "hero-title", text: title }),
    why ? el("p", { class: "hero-sub", text: why }) : null,
  ]);
  function formField(id, label, control, help) {
    if (!control.id) control.id = id;
    const helpNode = help == null ? null
      : typeof help === "string" ? el("p", { class: "hint", id: `${id}-help`, text: help })
      : el("p", { class: "hint", id: `${id}-help` }, [].concat(help));
    if (helpNode) control.setAttribute("aria-describedby", `${id}-help`);
    return el("div", { class: "field", "data-slot": "form-field" }, [
      el("label", { class: "text-label", for: id, text: label }),
      control,
      helpNode,
    ]);
  }
  function foot({ skip, primary }) {
    const nodes = [];
    if (primary) {
      if (primary.node) {
        primary.node.classList.add("btn-block");
        nodes.push(primary.node);
      } else {
        nodes.push(el("button", {
          class: "btn btn-primary btn-block", type: primary.type || "button", text: primary.label,
          disabled: primary.disabled ? true : null,
          onclick: primary.onclick || (primary.step ? () => go(primary.step) : null),
        }));
      }
    }
    if (skip) {
      nodes.push(el("button", {
        class: "btn btn-ghost btn-block", type: "button", text: skip.label || "Skip",
        onclick: skip.onclick || (() => { state.session.skipped[skip.mark || skip.step] = true; go(skip.step); }),
      }));
    }
    return el("div", { class: "onboard-foot" }, nodes);
  }
  function frame(title, why, body, nav, command) {
    return {
      children: [
        el("div", { class: "step-stack" }, [hero(title, why), ...[].concat(body || []), command ? cliDetails(command) : null]),
        nav ? foot(nav) : null,
      ],
      nav,
    };
  }
  function previousStep(step) {
    if (step === "mda" || step === "selfhost" || step === "done") return "path";
    if (step === "welcome") return null;
    const idx = RAIL.findIndex((item) => item.id === step);
    if (idx > 0) return RAIL[idx - 1].id;
    if (idx === 0) return "welcome";
    return null;
  }
  function railIndex(step) {
    if (["mda", "selfhost", "done"].includes(step)) return RAIL.length - 1;
    return RAIL.findIndex((item) => item.id === step);
  }
  function syncReached() {
    const idx = railIndex(state.step);
    if (idx >= 0) state.maxReached = Math.max(state.maxReached, idx);
  }

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
    const approvers = (d.writes?.approvers || []).length > 0;
    const slack = d.slack || {};
    const slackDone = !!slack.bot_token_set && (slack.transport === "socket_mode" ? !!slack.app_token_set : !!slack.signing_secret_set);
    const mdaDone = !!d.mda?.langsmith_key_set && modelDone && approvers;
    const selfDone = slackDone && approvers;
    return { env, model, modelDone, tokenSet, realAccounts, pipeboardDone: tokenSet && realAccounts, runtime, approvers, slackDone, mdaDone, selfDone };
  }
  function coreDone(id, s) {
    const skipped = state.session.skipped || {};
    if (id === "model") return s.modelDone || !!skipped.model;
    if (id === "pipeboard") return s.pipeboardDone || !!skipped.pipeboard;
    if (id === "try") return !!state.session.answer || !!skipped.try;
    return false;
  }
  function stepList() {
    const s = derive();
    const steps = [
      { id: "welcome", label: "Welcome", done: true },
      ...CORE.map((step) => ({ ...step, done: coreDone(step.id, s) })),
      { id: "path", label: "Where it lives", done: s.runtime !== "local" },
    ];
    if (s.runtime === "mda") steps.push({ id: "mda", label: "Deploy", done: s.mdaDone });
    else if (s.runtime === "self_hosted") steps.push({ id: "selfhost", label: "Self-host", done: s.selfDone });
    steps.push({ id: "done", label: "Done", done: false });
    return steps;
  }
  function firstOpenStep() {
    const s = derive();
    const next = CORE.find((step) => !coreDone(step.id, s));
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
    if (!state.step) state.step = firstOpenStep();
    const known = stepList().map((s) => s.id);
    if (!known.includes(state.step)) state.step = firstOpenStep();
    syncReached();
    writeFragment();
    renderProgress();
    renderScreen();
  }

  function renderProgress() {
    const nav = $("#progress");
    const mobile = $("#progress-mobile");
    const back = $("#wizard-back");
    nav.replaceChildren();
    if (mobile) mobile.replaceChildren();
    const current = Math.max(0, railIndex(state.step));
    const active = RAIL[current] || RAIL[0];
    if (mobile) {
      mobile.append(
        el("div", { class: "stepper-compact-row" }, [
          el("span", { class: "step-label", text: state.step === "done" ? "Setup complete" : active.label }),
          el("span", { class: "step-note", text: `Step ${current + 1} of ${RAIL.length}` }),
        ]),
        el("div", { class: "stepper-dots", "aria-hidden": "true" }, RAIL.flatMap((step, i) => {
          const selected = i === current;
          const completed = i < current;
          const mark = completed
            ? el("span", { class: "step-num", "data-done": "true", html: '<svg viewBox="0 0 12 12"><path d="M2.5 6.5l2.4 2.4L9.5 3.7"/></svg>' })
            : el("span", { class: "step-num", "aria-current": selected ? "step" : null, text: String(i + 1) });
          const nodes = [el("button", { class: "stepper-dot", type: "button", disabled: i > current ? true : null, onclick: () => go(step.id) }, [mark])];
          if (i < RAIL.length - 1) nodes.push(el("span", { class: "stepper-dot-rule" }));
          return nodes;
        })),
      );
    }
    RAIL.forEach((step, i) => {
      const selected = i === current && state.step !== "welcome";
      const completed = i < current || (state.step === "done" && i <= current);
      const mark = completed && !selected
        ? el("span", { class: "step-num", "aria-hidden": "true", html: '<svg viewBox="0 0 12 12"><path d="M2.5 6.5l2.4 2.4L9.5 3.7"/></svg>' })
        : el("span", { class: "step-num", "aria-hidden": "true", text: String(i + 1) });
      nav.append(el("button", {
        class: "stepper-item", type: "button",
        "aria-current": selected ? "step" : null,
        "data-done": completed ? "true" : "false",
        disabled: i > current ? true : null,
        onclick: () => go(step.id),
      }, [
        mark,
        el("span", { class: "step-copy" }, [
          el("span", { class: "step-label", text: step.label }),
          el("span", { class: "step-note", text: step.note }),
        ]),
      ]));
    });
    if (back) {
      const prev = previousStep(state.step);
      back.hidden = !prev;
      back.onclick = prev ? () => go(prev) : null;
    }
  }

  let screenToken = 0;
  function go(step) {
    if (step === state.step) return;
    const order = ["welcome", ...RAIL.map((item) => item.id), "mda", "selfhost", "done"];
    const from = order.indexOf(state.step);
    const to = order.indexOf(step);
    state.direction = to !== -1 && from !== -1 && to < from ? "back" : "forward";
    state.step = step;
    syncReached();
    writeFragment();
    renderProgress();
    renderScreen();
  }

  function renderScreen() {
    const host = $("#screen");
    const live = $("#wizard-live");
    const token = ++screenToken;
    const build = { welcome: screenWelcome, model: screenModel, pipeboard: screenPipeboard, try: screenTry, path: screenPath, mda: screenMda, selfhost: screenSelfHost, done: screenDone }[state.step] || screenWelcome;
    const built = build();
    const idx = railIndex(state.step);
    const title = RAIL[idx]?.label || state.step;
    const next = el("section", {
      class: "wizard-step-pane",
      "data-slot": "wizard-step-pane",
      "data-direction": state.direction,
      role: "region",
      "aria-label": idx >= 0 ? `Step ${idx + 1} of ${RAIL.length}, ${title}` : title,
    }, built.children || built);
    if (token !== screenToken) return;
    host.replaceChildren(next);
    if (live) live.textContent = idx >= 0 ? `Step ${idx + 1} of ${RAIL.length}, ${title}` : "";
  }
  const refreshScreen = () => { renderProgress(); renderScreen(); };

  // ---- screens
  const EXAMPLES = [
    "Compare the last 14 days with the prior 14 days.",
    "Where is spend rising while CPA gets worse?",
    "Cut the Performance Max daily budget to 240.",
  ];

  function screenWelcome() {
    const line = el("div", { class: "status-line", id: "welcome-status" });
    const demo = el("button", { class: "btn btn-outline", type: "button", text: "Run the fixture demo", onclick: (ev) => demoInline(ev.currentTarget) });
    return frame(
      "Paid Media Agent",
      "Ask a question about your ads. Code does the math. You approve every change.",
      [
        line,
        disclose("Prove the install first", false, [
          el("p", { class: "sub", text: "Runs the fixture demo with no credentials." }),
          demo,
          cli("paid-media-agent demo --with-proposal"),
        ]),
      ],
      { primary: { label: "Start setup", onclick: () => go(firstOpenStep() === "done" ? "model" : firstOpenStep()) } },
    );
  }

  async function demoInline(button) {
    const line = $("#welcome-status");
    await busy(button, async () => {
      setLine(line, "info", "Running the fixture demo through the real graph…");
      const result = await runAction("demo_run", { with_proposal: true });
      const receipt = result.detail?.receipt?.status;
      setLine(line, result.status, receipt ? `Demo finished. Analysis reconciled and a fake budget change was approved and verified (${receipt}).` : result.summary);
    });
  }

  function screenModel() {
    const d = state.status.detail;
    const s = derive();
    const presets = d.model_presets || [];
    const currentSpec = d.model?.spec || "";
    if (!state.picked) {
      const byModel = presets.find((p) => p.id !== "custom" && currentSpec && p.model === currentSpec);
      const byKey = presets.find((p) => p.id !== "custom" && d.model_key_env && p.key === d.model_key_env && currentSpec.startsWith(p.model.split(":")[0] + ":"));
      // Same provider, different model id or key name (a gateway model, a newer Anthropic id): still that card.
      const byProvider = presets.find((p) => p.id !== "custom" && currentSpec && currentSpec.startsWith(p.model.split(":")[0] + ":"));
      state.picked = (byModel || byKey || byProvider)?.id || (s.modelDone ? "custom" : null);
    }
    const card = (p) => el("button", {
      class: "option", type: "button", "data-slot": "choice-card",
      "aria-pressed": state.picked === p.id ? "true" : "false",
      onclick: () => { state.picked = p.id; state.session.modelTested = null; refreshScreen(); },
    }, [
      el("div", { class: "row" }, [
        logo(p.logo, p.logo === "langchain" ? "lc" : ""),
        el("span", { class: "stack" }, [
          el("span", { class: "name", text: p.label }),
          el("span", { class: "note", text: p.recommended ? `Recommended. ${p.note}` : p.note }),
        ]),
      ]),
    ]);
    const featured = presets.filter((p) => FEATURED_PRESETS.includes(p.id));
    const extra = presets.filter((p) => !FEATURED_PRESETS.includes(p.id));
    const moreOpen = !!(state.picked && extra.some((p) => p.id === state.picked));
    const body = [
      d.model?.error ? el("div", { class: "status-line" }, [badge("fail", "FAIL"), el("span", { text: `${d.model.error} (currently "${currentSpec}"). Pick a provider and save.` })]) : null,
      el("div", { class: "options featured", "data-slot": "choice-cards" }, featured.map(card)),
      disclose("More providers", moreOpen, [el("div", { class: "options", "data-slot": "choice-cards" }, extra.map(card))]),
    ];
    const preset = presets.find((p) => p.id === state.picked);
    let save = null;
    if (preset) {
      const isCustom = preset.id === "custom";
      const sameProvider = currentSpec && preset.model && currentSpec.split(":")[0] === preset.model.split(":")[0];
      const modelInput = el("input", { class: "input", id: "w-model", value: isCustom ? (s.modelDone ? currentSpec : "") : (sameProvider ? currentSpec : preset.model), placeholder: "provider:model", spellcheck: "false", autocomplete: "off" });
      const keyNameInput = el("input", { class: "input", id: "w-keyname", value: isCustom ? (d.model_key_env || "") : preset.key, placeholder: "MY_PROVIDER_API_KEY", spellcheck: "false", disabled: isCustom ? null : true });
      const keyInput = el("input", { class: "input", id: "w-key", type: "password", placeholder: (d.env || {})[isCustom ? d.model_key_env : preset.key] ? "Key already set. Paste to replace." : "API key", autocomplete: "off" });
      const showBase = isCustom || !!preset.base_url;
      const baseInput = el("input", { class: "input", id: "w-base", value: preset.base_url || (isCustom ? d.model_base_url || "" : ""), placeholder: "https://api.example.com/v1 (optional)", spellcheck: "false" });
      const form = el("form", { class: "form", "data-slot": "form-fields" }, [
        formField("w-model", "Model", modelInput),
        formField("w-key", "API key", keyInput, [el("span", { text: "Stored as " }), el("code", { class: "mono", text: isCustom ? "the name you choose" : preset.key })]),
        isCustom ? formField("w-keyname", "Key name in .env", keyNameInput, "Must end with _API_KEY.") : null,
        showBase ? formField("w-base", "Base URL", baseInput) : null,
        preset.url ? el("p", { class: "sub" }, [el("a", { href: preset.url, target: "_blank", rel: "noopener", text: `Create a key at ${preset.label}` })]) : null,
      ]);
      const line = el("div", { class: "status-line", id: "model-status" });
      if (state.session.modelTested) setLine(line, state.session.modelTested.status, state.session.modelTested.text);
      save = el("button", { class: "btn btn-primary", type: "submit", text: "Save and test" });
      form.append(line, el("div", { class: "actions" }, [save]));
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
        await loadStatus();
      }); });
      body.push(form);
    }
    return frame(
      "Choose a model",
      s.modelDone ? `${currentSpec} is saved on this machine.` : "Pick a provider and paste a key. We write it to .env here.",
      body,
      {
        back: { step: "welcome" },
        primary: { label: "Continue", step: "pipeboard" },
      },
      "paid-media-agent test model",
    );
  }

  function screenPipeboard() {
    const s = derive();
    const tokenInput = el("input", { class: "input", id: "w-token", type: "password", placeholder: s.tokenSet ? "Token already set. Paste to replace." : "Pipeboard API token", autocomplete: "off" });
    const connect = el("button", { class: "btn btn-primary", type: "submit", text: s.tokenSet ? "Reconnect" : "Connect" });
    const line = el("div", { class: "status-line", id: "pb-status" });
    if (state.session.catalog) setLine(line, state.session.catalog.status, state.session.catalog.text);
    const form = el("form", { class: "form", "data-slot": "form-fields" }, [
      formField("w-token", "API token", tokenInput, [el("a", { href: "https://pipeboard.co/api-tokens", target: "_blank", rel: "noopener", text: "Create a token at Pipeboard" })]),
      line,
      el("div", { class: "actions" }, [connect]),
    ]);
    form.addEventListener("submit", (ev) => { ev.preventDefault(); busy(connect, async () => {
      if (tokenInput.value) { const saved = await saveConfig({ PIPEBOARD_API_TOKEN: tokenInput.value }); if (!saved.ok) { setLine(line, "fail", saved.summary); return; } }
      setLine(line, "info", "Loading the live catalog…");
      const test = await runAction("pipeboard_test");
      state.session.catalog = { status: test.status, text: test.summary };
      const disc = await runAction("accounts_discover");
      state.discovered = disc.detail.accounts || [];
      await loadStatus();
    }); });
    if (state.discovered === null && s.tokenSet) {
      runAction("accounts_discover").then((disc) => { state.discovered = disc.detail.accounts || []; refreshScreen(); }).catch(() => {});
    }
    const body = [form];
    if (state.discovered && state.discovered.length) body.push(accountsPicker());
    else if (!s.tokenSet) body.push(el("p", { class: "sub", text: "Skip to use the demo accounts." }));
    body.push(disclose("LinkedIn, X, and OpenAI Ads", false, [
      el("p", { class: "sub" }, [
        el("a", { href: "#", text: "Direct platforms", onclick: (ev) => { ev.preventDefault(); state.view = "advanced"; state.routeId = "direct"; render(); } }),
        el("span", { text: " takes those credentials in Advanced." }),
      ]),
    ]));
    return frame(
      "Connect ad accounts",
      "A Pipeboard token loads Google, Meta, and Reddit. Or skip and use demo data.",
      body,
      {
        back: { step: "model" },
        skip: { label: "Skip with demo data", mark: "pipeboard", step: "try" },
        primary: { label: "Continue", step: "try" },
      },
      "paid-media-agent accounts discover",
    );
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
      await loadStatus();
    }));
    return el("div", { class: "form" }, [el("h2", { class: "section-title", text: "Choose the accounts to use" }), list, line, el("div", { class: "actions" }, [map])]);
  }
  const platformLogo = (platform) => ({ google_ads: "google", meta_ads: "langchain", reddit_ads: "langchain" }[platform] || "langchain");
  const suggestAlias = (row) => `${row.platform.replace("_ads", "")}-${(row.name || "main").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "").slice(0, 24) || "main"}`;

  function screenTry() {
    const d = state.status.detail;
    const s = derive();
    const question = el("textarea", { class: "input", id: "w-q", rows: "3", placeholder: "Ask something about the connected accounts…" });
    question.value = state.session.draft || EXAMPLES[0];
    const ask = el("button", { class: "btn btn-primary", type: "submit", text: "Ask", disabled: s.modelDone ? null : true });
    const line = el("div", { class: "status-line", id: "ask-status" });
    const answerBox = el("div", { class: "answer md", hidden: state.session.answer ? null : true });
    if (state.session.answer) answerBox.innerHTML = renderMarkdown(state.session.answer);
    const form = el("form", { class: "form", "data-slot": "form-fields" }, [
      formField("w-q", "Question", question),
      el("div", { class: "prompts" }, EXAMPLES.slice(0, 2).map((q) => el("button", { class: "prompt", type: "button", text: q, onclick: () => { question.value = q; } }))),
      line, answerBox,
      el("div", { class: "actions" }, [ask]),
      el("p", { class: "mini", text: s.modelDone ? (s.tokenSet ? "Runs against your accounts." : "Runs against the demo accounts.") : "Add a model first." }),
    ]);
    form.addEventListener("submit", (ev) => { ev.preventDefault(); busy(ask, async () => {
      setLine(line, "info", "Thinking…");
      const result = await runAction("ask", { question: question.value });
      if (!result.ok) { setLine(line, "fail", result.summary); return; }
      state.session.answer = result.detail.answer;
      answerBox.hidden = false; answerBox.innerHTML = renderMarkdown(result.detail.answer);
      setLine(line, "ok", `Answered with ${d.model?.spec}.`);
      renderProgress();
    }); });
    return frame(
      "Ask a question",
      "This is the product. One question through the same profile a deploy runs.",
      [form],
      {
        back: { step: "pipeboard" },
        skip: { label: "Skip", mark: "try", step: "path" },
        primary: { label: "Continue", step: "path" },
      },
      'paid-media-agent ask "How did spend move week over week?"',
    );
  }

  function screenPath() {
    const s = derive();
    const choose = async (button, runtime) => busy(button, async () => { await saveConfig({ PAID_MEDIA_RUNTIME: runtime }); await loadStatus(); go(runtime === "mda" ? "mda" : "selfhost"); });
    const card = (id, logoNode, title, note, pressed, recommended) => el("button", {
      class: "option", type: "button", "data-slot": "choice-card",
      "aria-pressed": pressed ? "true" : "false",
      onclick: (ev) => choose(ev.currentTarget, id),
    }, [
      el("div", { class: "row" }, [
        logoNode,
        el("span", { class: "stack" }, [
          el("span", { class: "name", text: title }),
          el("span", { class: "note" }, [recommended ? el("b", { class: "rec", text: "Recommended. " }) : null, el("span", { text: note })]),
        ]),
      ]),
    ]);
    return frame(
      "Where it lives",
      "Same agent either way. You can stay local.",
      [el("div", { class: "options two", "data-slot": "choice-cards" }, [
        card("mda", logo("langchain", "lc"), "Managed Deep Agents", "One command on LangSmith Cloud. Threads, sandbox, Slack.", s.runtime === "mda", true),
        card("self_hosted", logo("slack"), "Self-host", "Your API, Postgres, and Slack app.", s.runtime === "self_hosted", false),
      ])],
      { back: { step: "try" }, primary: { label: "Stay local", step: "done" } },
    );
  }

  function screenMda() {
    const d = state.status.detail;
    const s = derive();
    const keyInput = el("input", { class: "input", id: "w-ls", type: "password", placeholder: d.env?.LANGSMITH_API_KEY ? "Key already set. Paste to replace." : "LangSmith API key", autocomplete: "off" });
    const approvers = el("input", { class: "input", id: "w-approvers", value: (d.writes?.approvers || []).join(", "), placeholder: "the identity refs allowed to approve, comma-separated", spellcheck: "false" });
    const save = el("button", { class: "btn btn-primary", type: "submit", text: "Save and run preflight" });
    const line = el("div", { class: "status-line" });
    const preflight = state.session.preflight;
    // [label, done, optional]: optional rows inform, they never block the deploy.
    const items = preflight ? [["mda CLI installed", preflight.cli_installed], ["LangSmith key", preflight.langsmith_key_set], ["agent.py imports", preflight.import_smoke === "ok"], ["Model package and key", preflight.model_package && preflight.provider_key_set], ["Slack channel and identity declared", preflight.slack_channel && preflight.identity], ["Approvers named", s.approvers], ["Sandbox snapshot declared (PDF reports; optional)", preflight.sandbox_declared, true]] : [];
    const form = el("form", { class: "form", "data-slot": "form-fields" }, [
      formField("w-ls", "LangSmith API key", keyInput, [el("a", { href: "https://smith.langchain.com/settings", target: "_blank", rel: "noopener", text: "Create a key in LangSmith" })]),
      formField("w-approvers", "Who can approve changes", approvers),
      line,
      el("div", { class: "actions" }, [save]),
    ]);
    form.addEventListener("submit", (ev) => { ev.preventDefault(); busy(save, async () => {
      const updates = { PAID_MEDIA_APPROVER_IDS: approvers.value.trim() };
      if (keyInput.value) updates.LANGSMITH_API_KEY = keyInput.value;
      const saved = await saveConfig(updates);
      if (!saved.ok) { setLine(line, "fail", saved.summary); return; }
      setLine(line, "info", "Running preflight…");
      const result = await runAction("mda_check");
      state.session.preflight = result.detail;
      state.session.preflightSummary = result.summary;
      await loadStatus();
    }); });
    const body = [form];
    if (preflight) {
      body.push(el("ul", { class: "checklist" }, items.map(([label, done]) => el("li", { "data-done": done ? "true" : "false" }, [check(!!done), el("span", { text: label })]))));
      const ready = items.filter(([, , optional]) => !optional).every(([, done]) => done);
      body.push(processControls("mda-deploy", ready ? "Deploy" : "Deploy (blocked)", !ready, true, "mda-dev", "Run locally with Studio"));
    }
    return frame(
      "Deploy",
      "LangSmith key and who may approve changes. Then preflight.",
      body,
      { back: { step: "path" }, skip: { label: "Switch to self-host", step: "path" }, primary: { label: "Continue", step: "done" } },
      "mda deploy .",
    );
  }

  function screenSelfHost() {
    const d = state.status.detail;
    const env = d.env || {};
    // Slack
    const bot = el("input", { class: "input", type: "password", placeholder: env.SLACK_BOT_TOKEN ? "Set. Paste to replace." : "xoxb-…", autocomplete: "off" });
    const app = el("input", { class: "input", type: "password", placeholder: env.SLACK_APP_TOKEN ? "Set. Paste to replace." : "xapp-…", autocomplete: "off" });
    const approvers = el("input", { class: "input", value: (d.writes?.approvers || []).join(", "), placeholder: "slack:T0123:U0456, operator", spellcheck: "false" });
    const slackLine = el("div", { class: "status-line" });
    if (state.session.slack) setLine(slackLine, state.session.slack.status, state.session.slack.text);
    const slackSave = el("button", { class: "btn btn-primary", type: "submit", text: "Save and test Slack" });
    const slackForm = el("form", { class: "form" }, [
      intro("slack", "Slack", "Create the app from the manifest, install it to your workspace, then paste the bot token and the app-level token. Socket Mode needs no public URL.",
        el("div", { class: "actions" }, [el("a", { class: "btn btn-outline btn-compact", href: "https://api.slack.com/apps?new_app=1", target: "_blank", rel: "noopener", text: "Create Slack app" }), el("code", { class: "mono", text: "config/slack-manifest.example.yaml" })])),
      el("div", { class: "field-row" }, [formField("w-bot", "Bot token", bot), formField("w-app", "App-level token", app)]),
      formField("w-approvers-sh", "Who can approve changes", approvers, "Slack refs look like slack:<team_id>:<user_id>; API callers use the name from PAID_MEDIA_API_TOKENS. Where a card is posted is never authorization."),
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
    // Storage and API
    const db = el("input", { class: "input", type: "password", placeholder: env.DATABASE_URL ? "Set. Paste to replace." : "postgresql://user:pass@host/db (optional; compose sets it)", autocomplete: "off" });
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
      intro("postgres", "Storage and API", "Postgres keeps threads, proposals, approvals, and receipts across restarts; docker compose brings one up for you. Leave it empty to run in memory."),
      formField("w-db", "Database URL", db),
      dbLine,
      el("div", { class: "actions" }, [dbSave, gen]),
    ]);
    dbForm.addEventListener("submit", (ev) => { ev.preventDefault(); busy(dbSave, async () => {
      if (db.value) { const saved = await saveConfig({ DATABASE_URL: db.value }); if (!saved.ok) { setLine(dbLine, "fail", saved.summary); return; } }
      const test = await runAction("database_test");
      state.session.db = { status: test.status, text: test.summary };
      await loadStatus();
    }); });
    return frame(
      "Self-host",
      "Slack first. Database and API can wait.",
      [
        slackForm,
        disclose("Storage, API, and run", false, [
          dbForm,
          processControls("serve", "Start API", false, false, "slack", "Start Slack adapter"),
          cli("docker compose up  # API on :8080 with Postgres"),
        ]),
      ],
      { back: { step: "path" }, skip: { label: "Switch to managed", step: "path" }, primary: { label: "Continue", step: "done" } },
      "paid-media-agent serve",
    );
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
    const runtimeLabel = s.runtime === "mda" ? "Managed Deep Agents" : s.runtime === "self_hosted" ? "Self-hosted" : "local only";
    const items = [["Model", s.modelDone, d.model?.spec], ["Ad accounts", s.pipeboardDone, s.tokenSet ? `${(d.accounts || []).length} alias(es)` : "demo accounts"], ["Approvers", s.approvers, (d.writes?.approvers || []).length ? `${(d.writes?.approvers || []).length} ref(s)` : "none"], ["Where it lives", s.runtime !== "local", runtimeLabel]];
    if (s.runtime === "mda") items.push(["Deploy", s.mdaDone, s.mdaDone ? "ready: uv run mda deploy ." : "LangSmith key or approvers missing"]);
    if (s.runtime === "self_hosted") items.push(["Slack", s.slackDone, s.slackDone ? d.slack?.transport : "not connected"]);
    return frame(
      "Ready",
      "Catalog, write gates, and running processes live in Advanced.",
      [el("ul", { class: "checklist stagger" }, items.map(([label, done, meta]) => el("li", { "data-done": done ? "true" : "false" }, [check(done), el("span", { text: label }), el("span", { class: "mini", text: meta || "" })])))],
      {
        back: { step: "path" },
        primary: { label: "Open Advanced", onclick: () => { state.view = "advanced"; render(); } },
      },
      "paid-media-agent doctor",
    );
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
    catch (error) { const line = button.closest("form, .form, [data-slot='wizard-step-pane']")?.querySelector(".status-line"); if (line) setLine(line, "fail", error.message); else showFatal(error); }
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
