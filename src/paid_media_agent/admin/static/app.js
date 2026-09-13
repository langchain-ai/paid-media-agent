/* Paid Media Agent setup console: a guided wizard plus an advanced view over the same host actions. */
(() => {
  "use strict";
  const LOGOS = window.PMA_LOGOS || {};
  const state = { token: "", view: "wizard", step: null, routeId: "local", status: null, routes: [], processes: [], config: null,
    checks: {}, open: new Set(), results: new Map(), discovered: null, lastRouteId: null, picked: null, direction: "forward",
    session: { modelTested: null, catalog: null, slack: null, db: null } };
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
  function gatewaySlash(spec) {
    return !!(spec && spec.includes("/") && !spec.includes(":"));
  }
  function belongsToPreset(preset, spec) {
    if (!preset || !spec || preset.id === "custom") return false;
    if (preset.id === "langsmith") return spec.startsWith("langsmith:") || gatewaySlash(spec);
    if (preset.base_url) return spec.startsWith(preset.model.split(":")[0] + ":")
      && (state.status.detail.model_key_env === preset.key || state.status.detail.model_base_url === preset.base_url);
    return spec.split(":")[0] === String(preset.model || "").split(":")[0];
  }
  function normalizeModelSpec(preset, spec) {
    if (preset && preset.id === "langsmith" && gatewaySlash(spec)) return `langsmith:${spec}`;
    return spec;
  }
  const RAIL = [
    { id: "welcome", label: "Welcome", note: "What this agent does" },
    { id: "model", label: "Model", note: "Use a provider you trust" },
    { id: "pipeboard", label: "Accounts", note: "Your accounts or sample data" },
    { id: "deployment", label: "Deployment", note: "Put your agent to work" },
  ];
  // Every command is shown the way a fresh checkout runs it, matching README and OPERATIONS.
  // Our own commands run through uv; anything else (docker, open, git) is shown as typed.
  const cli = (command) => el("div", { class: "cli" }, [el("span", { class: "sigil", text: "$" }), el("code", { text: /^(uv run |paid-media-agent |mda )/.test(command) && !command.startsWith("uv run ") ? `uv run ${command}` : command })]);
  const intro = (logoName, title, note, actions = null, cls = "") => el("div", { class: "intro" }, [logo(logoName, cls), el("div", {}, [el("span", { class: "name", text: title }), el("span", { class: "note", text: note }), actions])]);
  const disclose = (summary, open, children) => el("details", { class: "disclose", open: open ? true : null }, [
    el("summary", { text: summary }),
    el("div", { class: "disclose-body" }, children),
  ]);
  const cliDetails = (command) => disclose("CLI equivalent", false, [cli(command)]);
  let dialogKeyHandler = null;
  let dialogTrigger = null;
  function closeDialog() {
    const root = $("#dialog-root");
    if (!root) return;
    root.replaceChildren();
    root.hidden = true;
    dialogTrigger?.focus();
    if (dialogKeyHandler) {
      document.removeEventListener("keydown", dialogKeyHandler);
      dialogKeyHandler = null;
    }
  }
  function showDialog({ title, body, primary }) {
    const root = $("#dialog-root");
    if (!root) return;
    closeDialog();
    dialogTrigger = document.activeElement;
    const close = el("button", { class: "btn btn-ghost btn-block", type: "button", text: "Close", onclick: closeDialog });
    const panel = el("div", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-labelledby": "dialog-title" }, [
      el("h2", { class: "hero-title", id: "dialog-title", text: title }),
      ...[].concat(body || []),
      el("div", { class: "dialog-actions" }, [primary || null, close]),
    ]);
    const backdrop = el("div", { class: "dialog-backdrop" }, [panel]);
    backdrop.addEventListener("click", (ev) => { if (ev.target === backdrop) closeDialog(); });
    dialogKeyHandler = (ev) => {
      if (ev.key === "Escape") { ev.preventDefault(); closeDialog(); }
      if (ev.key === "Tab") {
        const nodes = [...panel.querySelectorAll("a[href], button:not(:disabled), input:not(:disabled)")];
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
        else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", dialogKeyHandler);
    root.replaceChildren(backdrop);
    root.hidden = false;
    close.focus();
  }
  function openGatewayDialog() {
    showDialog({
      title: "LangSmith Gateway",
      body: [
        el("p", { class: "hero-sub", text: "One LangSmith key gives your agent access to the models available in your workspace." }),
        el("p", { class: "hero-sub", text: "LangSmith traces requests and manages provider access and spending limits." }),
      ],
      primary: el("a", { class: "btn btn-primary btn-block", href: "https://smith.langchain.com/settings", target: "_blank", rel: "noopener", text: "Create a LangSmith key" }),
    });
  }
  const hero = (title, why) => el("div", { class: "hero", "data-slot": "step-heading" }, [
    el("h1", { class: "hero-title", tabindex: "-1", text: title }),
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
  function fieldSet(legend, children) {
    return el("div", { class: "field-set", "data-slot": "field-set", role: "group", "aria-label": legend || null }, [
      legend ? el("p", { class: "field-legend", text: legend }) : null,
      ...[].concat(children),
    ]);
  }
  function foot({ skip, primary }) {
    const nodes = [];
    if (primary) {
      nodes.push(el("button", {
        class: "btn btn-primary btn-block", type: "button", text: primary.label,
        disabled: primary.disabled ? true : null, onclick: primary.onclick,
      }));
    }
    if (skip) {
      nodes.push(el("button", {
        class: "btn btn-ghost btn-block", type: "button", text: skip.label || "Skip",
        onclick: skip.onclick || (() => go(skip.step)),
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
    };
  }
  function previousStep(step) {
    if (step === "selfhost") return "deployment";
    const idx = RAIL.findIndex((item) => item.id === step);
    if (idx > 0) return RAIL[idx - 1].id;
    return null;
  }
  function railIndex(step) {
    if (step === "selfhost") return RAIL.length - 1;
    return RAIL.findIndex((item) => item.id === step);
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
    if (state.view !== "advanced") state.view = "wizard";
    if (["path", "mda", "done"].includes(state.step)) state.step = "deployment";
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
    const binary = options.body instanceof Blob;
    const headers = { "X-Admin-Token": state.token, ...(options.body ? { "Content-Type": binary ? options.body.type : "application/json" } : {}) };
    const response = await fetch(path, { ...options, headers, body: binary ? options.body : options.body ? JSON.stringify(options.body) : undefined });
    if (response.status === 401) throw new Error("This page is not authorized. Restart `paid-media-agent setup` and use the printed link.");
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.detail || `request failed (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return data;
  }
  async function loadStatus({ paint = true } = {}) {
    const data = await api("/api/status");
    state.status = data.result; state.routes = data.routes; state.processes = data.processes; state.checks = data.connection_checks || {};
    if (paint) render();
  }
  async function loadConfig() { state.config = await api("/api/config"); }
  const saveConfig = (updates) => api("/api/config", { method: "POST", body: { updates } });
  const runAction = (name, payload = {}) => api(`/api/actions/${name}`, { method: "POST", body: payload });

  // ---- derived setup state
  function derive() {
    const d = state.status?.detail || {};
    const model = d.model || {};
    const modelDone = !!model.package_installed && (d.model_key_env ? !!d.model_key_set : model.provider === "scripted");
    const tokenSet = !!d.pipeboard?.token_set;
    const realAccounts = String(d.accounts_path || "").endsWith("config/accounts.toml") && (d.accounts || []).length > 0;
    return { modelDone, tokenSet, realAccounts };
  }
  function coreDone(id) {
    if (id === "model") return state.checks.model_test?.status === "ok";
    if (id === "pipeboard") return state.status?.detail?.data_mode === "sample" || (derive().realAccounts && state.checks.accounts_discover?.status === "ok");
    return false;
  }

  // ---- render
  function render() {
    $("#brand-mark").innerHTML = LOGOS.langchain || "";
    const advanced = state.view === "advanced";
    $("#wizard").hidden = advanced;
    document.body.classList.toggle("is-welcome", !advanced && (!state.step || state.step === "welcome"));
    $("#advanced").hidden = !advanced;
    const viewLabel = $("#view-toggle-label");
    if (viewLabel) viewLabel.textContent = advanced ? "Setup" : "Advanced";
    $("#view-toggle").setAttribute("aria-pressed", advanced ? "true" : "false");
    $("#view-toggle").setAttribute("aria-label", advanced ? "Back to setup" : "Open advanced");
    document.body.classList.toggle("advanced", advanced);
    writeFragment();
    if (advanced) {
      const back = $("#wizard-back");
      if (back) back.hidden = true;
      renderAdvanced();
      return;
    }
    if (railIndex(state.step) < 0) state.step = "welcome";
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
    const checkSvg = '<svg viewBox="0 0 12 12"><path d="M2.5 6.5l2.4 2.4L9.5 3.7"/></svg>';
    if (mobile) {
      mobile.append(
        el("div", { class: "stepper-compact-row" }, [
          el("span", { class: "step-label", text: active.label }),
          el("span", { class: "step-note", text: `Step ${current + 1} of ${RAIL.length}` }),
        ]),
        el("nav", { class: "stepper-dots", "data-slot": "stepper-nav", "data-orientation": "horizontal", "aria-label": "Onboarding progress" }, RAIL.map((step, i) => {
          const selected = i === current;
          const completed = step.id === "welcome" ? current > 0 : coreDone(step.id);
          const stateName = selected ? "active" : completed ? "completed" : "inactive";
          const mark = completed
            ? el("span", { class: "stepper-indicator", "data-slot": "stepper-indicator", "data-state": "completed", html: checkSvg })
            : el("span", { class: "stepper-indicator", "data-slot": "stepper-indicator", "data-state": stateName, text: String(i + 1) });
          return el("div", { class: "stepper-item", "data-slot": "stepper-item", "data-state": stateName }, [
            el("button", { class: "stepper-dot", type: "button", "data-slot": "stepper-trigger", disabled: i > current ? true : null, "aria-label": `Step ${i + 1}: ${step.label}`, onclick: () => go(step.id) }, [mark]),
            i < RAIL.length - 1 ? el("span", { class: "stepper-separator-h", "data-slot": "stepper-separator", "aria-hidden": "true" }) : null,
          ]);
        })),
      );
    }
    RAIL.forEach((step, i) => {
      const selected = i === current;
      const completed = step.id === "welcome" ? current > 0 : coreDone(step.id);
      const stateName = selected ? "active" : completed ? "completed" : "inactive";
      const mark = completed && !selected
        ? el("span", { class: "stepper-indicator", "data-slot": "stepper-indicator", "data-state": "completed", "aria-hidden": "true", html: checkSvg })
        : el("span", { class: "stepper-indicator", "data-slot": "stepper-indicator", "data-state": stateName, "aria-hidden": "true", text: String(i + 1) });
      nav.append(el("div", { class: "stepper-item", "data-slot": "stepper-item", "data-state": stateName }, [
        el("button", {
          class: "stepper-trigger", type: "button",
          "data-slot": "stepper-trigger",
          "aria-current": selected ? "step" : null,
          disabled: i > current ? true : null,
          onclick: () => go(step.id),
        }, [
          mark,
          el("span", { class: "stepper-copy" }, [
            el("span", { class: "stepper-title step-label", "data-slot": "stepper-title", text: step.label }),
            el("span", { class: "stepper-description step-note", "data-slot": "stepper-description", text: step.note }),
          ]),
        ]),
        i < RAIL.length - 1 ? el("span", { class: "stepper-separator", "data-slot": "stepper-separator", "aria-hidden": "true" }) : null,
      ]));
    });
    if (back) {
      const prev = previousStep(state.step);
      back.hidden = !prev;
      back.onclick = prev ? () => go(prev) : null;
    }
  }

  function go(step) {
    if (step === state.step && state.view === "wizard") return;
    const order = [...RAIL.map((item) => item.id), "selfhost"];
    const from = order.indexOf(state.step);
    const to = order.indexOf(step);
    state.direction = to !== -1 && from !== -1 && to < from ? "back" : "forward";
    state.view = "wizard";
    state.step = step;
    writeFragment();
    render();
    $("#screen h1")?.focus({ preventScroll: true });
  }

  function renderScreen() {
    const host = $("#screen");
    const live = $("#wizard-live");
    processViews.clear();
    const build = { welcome: screenWelcome, model: screenModel, pipeboard: screenPipeboard, deployment: screenDeployment, selfhost: screenSelfHost }[state.step] || screenWelcome;
    const built = build();
    const idx = railIndex(state.step);
    const title = RAIL[idx]?.label || state.step;
    const next = el("section", {
      class: built.scrollBody ? "wizard-step-pane wizard-step-pane-scroll" : state.step === "welcome" ? "wizard-step-pane wizard-step-pane-wide" : "wizard-step-pane",
      "data-slot": "wizard-step-pane",
      "data-onboarding-step": "",
      "data-direction": state.direction,
      role: "region",
      "aria-label": idx >= 0 ? `Step ${idx + 1} of ${RAIL.length}, ${title}` : title,
    }, built.children || built);
    host.closest(".frame-panel").classList.toggle("has-scroll-body", !!built.scrollBody);
    host.replaceChildren(next);
    if (live) live.textContent = idx >= 0 ? `Step ${idx + 1} of ${RAIL.length}, ${title}` : "";
  }
  const refreshScreen = () => {
    const scrollTop = $(".model-step-scroll")?.scrollTop || 0;
    renderProgress(); renderScreen();
    const scroll = $(".model-step-scroll");
    if (scroll) scroll.scrollTop = scrollTop;
  };

  // ---- screens
  function screenWelcome() {
    const miniature = window.createPaidMediaHero({ el, logo });
    return { children: [el("div", { class: "welcome-layout" }, [
      el("div", { class: "welcome-copy" }, [
        el("span", { class: "welcome-badge" }, [
          el("img", { class: "welcome-oss-logo welcome-oss-logo-light", src: "/static/langchain-oss-light.svg", alt: "", width: "22", height: "22" }),
          el("img", { class: "welcome-oss-logo welcome-oss-logo-dark", src: "/static/langchain-oss-dark.svg", alt: "", width: "22", height: "22" }),
          el("span", { text: "LangChain OSS" }),
        ]),
        el("h1", { class: "welcome-title", tabindex: "-1", text: "Set up your\npaid media agent." }),
        el("p", { class: "welcome-description", text: "Compare ad spend, conversions, and cost per lead across channels. Get weekly reports and answers to campaign questions." }),
        el("div", { class: "welcome-actions" }, [
          el("button", { class: "btn btn-primary", type: "button", text: "Get started", onclick: () => go("model") }),
        ]),
      ]), miniature,
    ])] };
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
      const byGateway = gatewaySlash(currentSpec) ? presets.find((p) => p.id === "langsmith") : null;
      state.picked = (byModel || byKey || byProvider || byGateway)?.id || (s.modelDone ? "custom" : null);
    }
    const card = (p) => {
      const choice = el("button", {
      class: "option", type: "button", "data-slot": "choice-card",
      "aria-pressed": state.picked === p.id ? "true" : "false",
      onclick: () => { state.picked = p.id; state.session.modelTested = null; refreshScreen(); },
    }, [
      el("div", { class: "row" }, [
        logo(p.logo, p.logo === "langchain" ? "lc" : ""),
        el("span", { class: "stack" }, [
          el("span", { class: "name", text: p.label }),
          el("span", { class: "note", text: p.id === "anthropic" ? "Use your Anthropic API key" : p.id === "openai" ? "Use your OpenAI API key" : p.note }),
        ]),
      ]),
      ]);
      return p.id === "langsmith" ? el("div", { class: "provider-choice" }, [choice, el("button", {
        class: "btn btn-ghost provider-help", type: "button", "aria-label": "What is LangSmith Gateway?", title: "What is LangSmith Gateway?", onclick: openGatewayDialog,
        html: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5"/><path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 2-2.5 2-2.5 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="12" cy="16.5" r=".8" fill="currentColor"/></svg>',
      })]) : choice;
    };
    const featured = presets.filter((p) => FEATURED_PRESETS.includes(p.id));
    const extra = presets.filter((p) => !FEATURED_PRESETS.includes(p.id));
    const moreOpen = !!(state.picked && extra.some((p) => p.id === state.picked));
    const body = [
      d.model?.error && !gatewaySlash(currentSpec) ? el("div", { class: "status-line" }, [badge("fail", "FAIL"), el("span", { text: `${d.model.error} (currently "${currentSpec}"). Pick a provider and save.` })]) : null,
      el("div", { class: "options featured", "data-slot": "choice-cards" }, featured.map(card)),
      disclose("More providers", moreOpen, [el("div", { class: "options", "data-slot": "choice-cards" }, extra.map(card))]),
    ];
    const preset = presets.find((p) => p.id === state.picked);
    let save = null;
    if (preset) {
      const isCustom = preset.id === "custom";
      const sameProvider = belongsToPreset(preset, currentSpec);
      const selected = sameProvider ? normalizeModelSpec(preset, currentSpec) : "";
      const keyNameInput = el("input", { class: "input", id: "w-keyname", value: isCustom ? (d.model_key_env || "") : preset.key, placeholder: "MY_PROVIDER_API_KEY", spellcheck: "false", disabled: isCustom ? null : true });
      const keyInput = el("input", { class: "input", id: "w-key", type: "password", placeholder: (d.env || {})[isCustom ? d.model_key_env : preset.key] ? "Key already set. Paste to replace." : "API key", autocomplete: "off" });
      const modelInput = isCustom
        ? el("input", { class: "input", id: "w-model", value: s.modelDone ? currentSpec : "", placeholder: "provider:model", spellcheck: "false", autocomplete: "off" })
        : window.createModelPicker({ el, logo, preset, selected,
          loadModels: () => api("/api/models", { method: "POST", body: { provider: preset.id, api_key: keyInput.value } }),
          onChange: () => { state.session.modelTested = null; },
        });
      if (!isCustom) {
        keyInput.addEventListener("change", () => modelInput.refresh());
        if ((d.env || {})[preset.key] || preset.id === "openrouter") requestAnimationFrame(() => { if (modelInput.element.isConnected) modelInput.refresh(); });
      }
      const showBase = isCustom || !!preset.base_url;
      const baseInput = el("input", { class: "input", id: "w-base", value: preset.base_url || (isCustom ? d.model_base_url || "" : ""), placeholder: "https://api.example.com/v1 (optional)", spellcheck: "false" });
      const form = el("form", { class: "form", "data-slot": "form-fields" }, [
        formField("w-key", "API key", keyInput),
        formField("w-model", "Model", isCustom ? modelInput : modelInput.element),
        isCustom ? formField("w-keyname", "Key name in .env", keyNameInput, "Must end with _API_KEY.") : null,
        showBase ? formField("w-base", "Base URL", baseInput) : null,
        preset.url ? el("p", { class: "sub" }, [el("a", { href: preset.url, target: "_blank", rel: "noopener", text: `Get a ${preset.label} key` })]) : null,
      ]);
      const line = el("div", { class: "status-line", id: "model-status", role: "status" });
      if (state.session.modelTested) setLine(line, state.session.modelTested.status, state.session.modelTested.text);
      save = el("button", { class: "btn btn-primary", type: "submit", text: "Test and continue" });
      form.append(line, el("div", { class: "actions" }, [save]));
      form.addEventListener("submit", (ev) => { ev.preventDefault(); busy(save, async () => {
        const keyName = (isCustom ? keyNameInput.value : preset.key).trim();
        if (!/^[A-Z][A-Z0-9_]{1,40}_API_KEY$/.test(keyName)) { setLine(line, "fail", "Key name must look like MY_PROVIDER_API_KEY."); return; }
        if (!modelInput.value.trim()) { setLine(line, "fail", "Select a model or enter its model ID."); return; }
        const updates = { PAID_MEDIA_MODEL: modelInput.value.trim(), PAID_MEDIA_MODEL_API_KEY_ENV: keyName, PAID_MEDIA_MODEL_BASE_URL: showBase ? baseInput.value.trim() : "" };
        if (keyInput.value) updates[keyName] = keyInput.value;
        const saved = await saveConfig(updates);
        if (!saved.ok) { setLine(line, "fail", saved.summary); return; }
        setLine(line, "info", "Saved. Testing the model…");
        const test = await runAction("model_test");
        state.session.modelTested = { status: test.status, text: test.status === "ok" ? `${test.summary}. Tool selection: ${test.detail.selection}.` : test.summary };
        setLine(line, test.status, test.summary);
        await loadStatus({ paint: false });
        if (test.status === "ok") go("pipeboard");
      }); });
      body.push(form);
    }
    return { scrollBody: true, children: [
      el("div", { class: "model-step-header" }, [hero("Choose a model", "Choose a provider and add your key. Available models load directly from its API.")]),
      el("div", { class: "model-step-scroll", tabindex: "0", role: "region", "aria-label": "Model configuration" }, [
        el("div", { class: "model-scroll-inner" }, [
          el("div", { class: "step-stack" }, [...body, cliDetails("paid-media-agent test model")]),
        ]),
      ]),
    ] };
  }

  const DIRECT_PLATFORMS = [
    { id: "x", name: "X Ads", logo: "x", note: "App and access tokens" },
    { id: "openai_ads", name: "OpenAI Ads", logo: "openai", note: "Ads API key" },
  ];
  function openAdvanced(routeId, stepId) {
    state.view = "advanced";
    state.routeId = routeId;
    if (stepId) {
      for (const key of state.open) if (key.startsWith(`${routeId}:`)) state.open.delete(key);
      state.open.add(`${routeId}:${stepId}`);
    }
    render();
    if (stepId) $(`#head-${stepId}`)?.focus();
  }
  function screenPipeboard() {
    const s = derive();
    const pipeboardOpen = !!state.session.pipeboardOpen;
    const connection = el("section", { id: "account-connection", class: "integration-setup", hidden: !pipeboardOpen, "aria-label": "Pipeboard setup" });
    const pipeboard = el("div", { role: "group", "aria-label": "Pipeboard integration" }, [
      el("button", {
        id: "integration-pipeboard", class: "integration-row", type: "button", "aria-label": "Set up Pipeboard",
        "aria-expanded": String(pipeboardOpen), "aria-controls": "account-connection",
        onclick: () => {
          state.session.pipeboardOpen = !pipeboardOpen;
          refreshScreen();
          $("#integration-pipeboard")?.focus();
        },
      }, [logo("pipeboard"), el("span", { class: "stack" }, [
        el("span", { class: "name", text: "Pipeboard" }),
        el("span", { class: "note", text: "Connect your ad platforms and analytics with one token." }),
      ]), el("span", { class: "integration-arrow", "aria-hidden": "true" })]),
      el("div", { class: "integration-platforms", role: "list", "aria-label": "Platforms provided by Pipeboard" }, [
        { name: "Google Ads", logo: "google" }, { name: "Meta Ads", logo: "meta" },
        { name: "TikTok Ads", logo: "tiktok" }, { name: "Pinterest Ads", logo: "pinterest" },
        { name: "Snap Ads", logo: "snapchat" }, { name: "Reddit Ads", logo: "reddit" },
        { name: "LinkedIn Ads", logo: "linkedin" }, { name: "Google Analytics", logo: "googleanalytics" },
      ].map(platform => el("span", { class: "integration-platform", role: "listitem" }, [logo(platform.logo), el("span", { text: platform.name })]))),
      connection,
    ]);
    const direct = el("div", { class: "integration-direct", role: "group", "aria-label": "Direct connections" }, DIRECT_PLATFORMS.map(platform => el("button", {
        id: `integration-${platform.id}`, class: "integration-row", type: "button", "aria-label": `Set up ${platform.name}`,
        onclick: () => openAdvanced("direct", `direct_${platform.id}`),
      }, [logo(platform.logo), el("span", { class: "stack" }, [
        el("span", { class: "name", text: platform.name }), el("span", { class: "note", text: `Direct connection · ${platform.note}` }),
      ]), el("span", { class: "integration-arrow", "aria-hidden": "true" })])));
    const body = [el("div", { class: "integration-list", role: "group", "aria-label": "Ad platform integrations" }, [pipeboard, direct])];
    if (pipeboardOpen) {
      const tokenInput = el("input", { class: "input", id: "w-token", type: "password", placeholder: s.tokenSet ? "Token already set. Paste to replace." : "Pipeboard API token", autocomplete: "off" });
      const connect = el("button", { class: "btn btn-outline", type: "submit", text: s.tokenSet ? "Reconnect" : "Connect" });
      const line = el("div", { class: "status-line", id: "pb-status" });
      if (state.session.catalog) setLine(line, state.session.catalog.status, state.session.catalog.text);
      const form = el("form", { class: "form", "data-slot": "form-fields" }, [
        el("p", { class: "note", text: "Choose your platforms in Pipeboard, then paste your token. You can connect any or all of the platforms above." }),
        el("a", { class: "btn btn-outline", href: "https://pipeboard.co/connections", target: "_blank", rel: "noopener", text: "Connect platforms in Pipeboard ↗" }),
        formField("w-token", "Pipeboard token", tokenInput, [el("a", { href: "https://pipeboard.co/api-tokens", target: "_blank", rel: "noopener", text: "Create a token at Pipeboard" })]),
        line,
        el("div", { class: "actions" }, [connect]),
      ]);
      form.addEventListener("submit", (ev) => { ev.preventDefault(); busy(connect, async () => {
        if (tokenInput.value) { const saved = await saveConfig({ PIPEBOARD_API_TOKEN: tokenInput.value }); if (!saved.ok) { setLine(line, "fail", saved.summary); return; } }
        setLine(line, "info", "Loading the live catalog…");
        const test = await runAction("pipeboard_test");
        state.session.catalog = { status: test.status, text: test.summary };
        if (test.status !== "ok") { setLine(line, test.status, test.summary); return; }
        const disc = await runAction("accounts_discover");
        if (!disc.ok) { setLine(line, disc.status, disc.summary); return; }
        state.discovered = disc.detail.accounts || [];
        await loadStatus();
      }); });
      connection.append(form);
    }
    if (state.discovered?.length) body.push(accountsPicker());
    else if (s.realAccounts) body.push(el("button", { class: "btn btn-outline", type: "button", text: "Review connected accounts", onclick: () => openAdvanced("direct", "direct_accounts") }));
    const useAccounts = mode => async ev => busy(ev.currentTarget, async () => {
      const saved = await saveConfig({ PAID_MEDIA_DATA_MODE: mode });
      if (!saved.ok) throw new Error(saved.summary);
      await loadStatus({ paint: false }); go("deployment");
    });
    const navigation = foot({ primary: {
      label: "Use selected accounts",
      disabled: !(s.realAccounts && state.checks.accounts_discover?.status === "ok"),
      onclick: useAccounts("live"),
    } });
    navigation.append(el("button", { class: "btn btn-ghost btn-block", type: "button", text: "Use sample data", onclick: useAccounts("sample") }));
    return { scrollBody: true, children: [
      el("div", { class: "model-step-header deployment-width" }, [hero("Connect ad accounts", "Connect the platforms you advertise on.")]),
      el("div", { class: "model-step-scroll" }, [el("div", { class: "model-scroll-inner deployment-width step-stack" }, [
        ...body, navigation,
      ])]),
    ] };
  }

  function accountsPicker() {
    const rows = state.discovered;
    const selected = new Set(rows.filter((r) => !r.mapped_alias));
    const list = el("div", { class: "list" });
    const inputs = new Map();
    for (const row of rows) {
      const mapped = !!row.mapped_alias;
      const box = check(mapped || selected.has(row));
      const alias = el("input", { class: "input", "aria-label": `Name for ${row.name}`, value: row.mapped_alias || suggestAlias(row), spellcheck: "false", disabled: mapped ? true : null, onclick: (ev) => ev.stopPropagation() });
      const rowNode = el("div", { class: `list-row${mapped ? " static" : ""}`, role: mapped ? null : "checkbox", "aria-checked": mapped ? null : String(selected.has(row)), tabindex: mapped ? null : "0" }, [
        el("div", { class: "row", style: "display:flex;align-items:center;gap:10px" }, [box, logo(platformLogo(row.platform))]),
        el("div", {}, [el("div", { class: "primary", text: row.name }), el("div", { class: "secondary", text: `${row.platform.replace("_ads", "")} ${row.currency ? " · " + row.currency : ""}` })]),
        mapped ? badge("positive", `mapped as ${row.mapped_alias}`) : alias,
      ]);
      if (!mapped) {
        inputs.set(row, alias);
        const toggle = () => { if (selected.has(row)) selected.delete(row); else selected.add(row); rowNode.setAttribute("aria-checked", String(selected.has(row))); box.dataset.checked = String(selected.has(row)); };
        rowNode.addEventListener("click", toggle);
        rowNode.addEventListener("keydown", (ev) => { if (ev.target === rowNode && (ev.key === " " || ev.key === "Enter")) { ev.preventDefault(); toggle(); } });
      }
      list.append(rowNode);
    }
    const line = el("div", { class: "status-line" });
    const map = el("button", { class: "btn btn-primary", type: "button", text: "Save selected accounts", disabled: inputs.size ? null : true });
    map.addEventListener("click", () => busy(map, async () => {
      let ok = 0;
      for (const row of rows) {
        if (!selected.has(row) || row.mapped_alias) continue;
        const alias = inputs.get(row).value.trim();
        const result = await api("/api/accounts", { method: "POST", body: { alias, platform: row.platform, provider_account_id: row.provider_account_id, currency: row.currency || "USD", timezone: row.timezone || "UTC" } });
        if (!result.ok) { setLine(line, "fail", result.summary); return; }
        ok += 1;
      }
      const disc = await runAction("accounts_discover");
      state.discovered = disc.detail.accounts || [];
      setLine(line, "ok", `${ok} account${ok === 1 ? "" : "s"} mapped.`);
      await loadStatus();
    }));
    return fieldSet("Choose accounts", [list, line, el("div", { class: "actions" }, [map])]);
  }
  const platformLogo = (platform) => ({ google_ads: "google", meta_ads: "meta", reddit_ads: "reddit", tiktok_ads: "tiktok", pinterest_ads: "pinterest", snap_ads: "snapchat", google_analytics: "googleanalytics", linkedin_ads: "linkedin", x_ads: "x", openai_ads: "openai" }[platform] || "custom");
  const suggestAlias = (row) => `${row.platform.replace("_ads", "")}-${(row.name || "main").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "").slice(0, 24) || "main"}`;

  function screenDeployment() {
    const d = state.status.detail;
    const s = derive();
    let keySet = !!d.env?.LANGSMITH_API_KEY || !!d.mda?.langsmith_key_set;
    const cliOk = !!d.mda?.cli_installed;
    const keyInput = el("input", { class: "input", id: "w-ls", type: "password", autocomplete: "off", placeholder: "LangSmith API key" });
    const savedAccess = () => el("p", { class: "deployment-key-status" }, [check(true), el("span", { text: "LangSmith key saved" })]);
    const externalLink = (text, href, className = "") => el("a", { class: className, href, target: "_blank", rel: "noopener", text });
    const access = el("div", { class: "deployment-access" }, [keySet ? savedAccess()
      : formField("w-ls", "LangSmith API key", keyInput, [externalLink("Get an API key ↗", "https://smith.langchain.com/settings")])]);
    const signup = el("div", { class: "deployment-signup" }, [
      el("p", { class: "name", text: "New to LangSmith?" }),
      el("p", { class: "note", text: "Create an account and choose a plan, then return here with your API key." }),
      el("div", { class: "actions" }, [
        externalLink("Create account ↗", "https://smith.langchain.com", "btn btn-outline"),
        externalLink("Choose a plan ↗", "https://www.langchain.com/pricing", "btn btn-ghost"),
      ]),
    ]);
    signup.hidden = keySet;
    state.session.customization ||= {};
    const customization = window.PMA_CUSTOMIZATION({
      el, logo, check, formField, disclose, api, saveConfig, busy, setLine,
      settings: d.customization, draft: state.session.customization, iconSet: d.slack_icon_set,
      onIconChange: (set) => { d.slack_icon_set = set; },
    });
    const prepare = async () => {
      if (!keySet && !keyInput.value.trim()) {
        keyInput.focus();
        throw new Error("Add a LangSmith API key to deploy.");
      }
      await customization.save();
      const updates = { PAID_MEDIA_RUNTIME: "mda" };
      if (keyInput.value.trim()) updates.LANGSMITH_API_KEY = keyInput.value.trim();
      const saved = await saveConfig(updates);
      if (!saved.ok) throw new Error(saved.summary);
      keyInput.value = "";
      keySet = true;
      access.replaceChildren(savedAccess());
      signup.hidden = true;
    };
    const reviewRow = (label, value, step) => el("div", { class: "deployment-review-row" }, [
      el("dt", { text: label }), el("dd", { text: value }),
      el("button", { class: "btn btn-ghost btn-compact", type: "button", text: "Edit", "aria-label": `Edit ${label.toLowerCase()}`, onclick: () => go(step) }),
    ]);
    const accountCount = (d.accounts || []).length;
    const managed = el("section", { id: "deployment-mda", class: "deployment-panel deployment-layout", "aria-labelledby": "choose-mda" }, [
      el("div", { class: "deployment-card", "data-slot": "card" }, [
        el("div", { class: "deployment-card-body deployment-connect", "data-slot": "card-content" }, [
          el("div", { class: "deployment-section-heading" }, [
            el("h2", { text: "Deploy with LangSmith" }),
            el("p", { class: "note", text: "We'll check your setup before deploying." }),
          ]),
          el("dl", { class: "deployment-review" }, [
            reviewRow("Model", s.modelDone ? String(d.model?.spec || "Configured").replace(/^langsmith:/, "") : "Choose a model to continue", "model"),
            reviewRow("Accounts", d.data_mode === "sample" ? "Sample data · synthetic accounts" : s.realAccounts ? `${accountCount} ad account${accountCount === 1 ? "" : "s"}` : "Choose accounts or sample data", "pipeboard"),
            el("div", { class: "deployment-review-row" }, [el("dt", { text: "Sandbox" }), el("dd", { text: d.mda?.sandbox_declared && d.mda?.sandbox_recipe ? "Included · built automatically on deploy" : "Missing sandbox setup files" })]),
          ]),
          signup,
          access,
          el("p", { class: "hint deployment-account-help" }, [
            el("span", { text: "Requires a LangSmith organization with MDA access. " }),
            externalLink("Plans & pricing ↗", "https://www.langchain.com/pricing"),
          ]),
          !cliOk ? el("div", { class: "sub" }, [el("p", { text: "Install the deployment tools, then refresh this page." }), cli("uv sync --all-extras")]) : null,
        ]),
      ]),
      customization.element,
    ]);
    const managedAction = el("div", { id: "deployment-mda-action", class: "deployment-panel deployment-final" }, [
      processControls("mda-deploy", "Deploy agent", !s.modelDone || !cliOk, true, prepare),
      el("p", { class: "deployment-disclosure", text: "Deploying uploads this project and its configuration to LangSmith. Hosting and model usage are billed separately." }),
    ]);
    const selfHosted = el("section", { id: "deployment-self", class: "deployment-card deployment-panel", hidden: true, "aria-labelledby": "choose-self" }, [
      el("div", { class: "deployment-card-body deployment-connect" }, [
        el("p", { class: "deployment-description", text: "Run the same agent on your infrastructure. You manage hosting and connect your own Slack app." }),
        el("div", { class: "deployment-requirements" }, [
          intro("postgres", "Postgres", "Stores conversations and approvals."),
          intro("slack", "Your Slack app", "Create an app and add its credentials."),
          intro("docker", "Docker", "Runs the agent API and database."),
        ]),
      ]),
    ]);
    const selfHostedAction = el("div", { id: "deployment-self-action", class: "deployment-panel deployment-final", hidden: true }, [
      el("button", { class: "btn btn-primary", type: "button", text: "Set up self-hosting", onclick: (ev) => busy(ev.currentTarget, async () => {
        const saved = await saveConfig({ PAID_MEDIA_RUNTIME: "self_hosted" });
        if (!saved.ok) throw new Error(saved.summary);
        await loadStatus({ paint: false }); go("selfhost");
      }) }),
    ]);
    const choice = (id, mark, name, note, recommended) => el("button", {
      id: `choose-${id}`, class: "deployment-choice", type: "button", "aria-controls": `deployment-${id} deployment-${id}-action`, "aria-expanded": "false",
    }, [
      el("span", { class: "deployment-choice-top" }, [logo(mark), el("span", { class: "deployment-chevron", "aria-hidden": "true" })]),
      el("span", { class: "name", text: name }),
      el("span", { class: "note", text: note }),
      badge(recommended ? "positive" : "neutral", recommended ? "Recommended" : "Your infrastructure"),
    ]);
    const mdaChoice = choice("mda", "deepagents", "Managed Deep Agents", "Hosting, Slack and schedules included.", true);
    const selfChoice = choice("self", "postgres", "Self-host", "Docker, Postgres and your Slack app.", false);
    const panels = [["mda", mdaChoice, managed, managedAction], ["self", selfChoice, selfHosted, selfHostedAction]];
    let selected = state.session.deploymentPath === undefined ? "mda" : state.session.deploymentPath;
    const expand = (id, animate = false) => {
      selected = id;
      state.session.deploymentPath = id;
      for (const [key, trigger, panel, action] of panels) {
        const open = key === id;
        trigger.setAttribute("aria-expanded", String(open));
        panel.hidden = !open;
        action.hidden = !open;
        panel.getAnimations().forEach((animation) => animation.cancel());
        if (open && animate && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
          panel.animate([{ opacity: 0, transform: "translateY(-4px)" }, { opacity: 1, transform: "translateY(0)" }], { duration: 180, easing: "ease-out" });
        }
      }
    };
    panels.forEach(([id, trigger]) => trigger.addEventListener("click", (event) => expand(selected === id ? null : id, event.detail > 0)));
    expand(selected);
    const local = disclose("Develop locally", false, [
      el("p", { class: "note", text: "Inspect the agent in Studio or ask a question from your terminal." }),
      processControls("mda-dev", "Start Studio locally", !keySet || !s.modelDone || !cliOk, false),
      cli('paid-media-agent ask "Compare ad spend and conversions over the last two weeks."'),
    ]);
    return { scrollBody: true, children: [
      el("div", { class: "model-step-header deployment-width" }, [hero("Deploy your agent", "Choose where your agent runs.")]),
      el("div", { class: "model-step-scroll" }, [el("div", { class: "model-scroll-inner deployment-width step-stack" }, [
        el("div", { class: "deployment-options", role: "group", "aria-label": "Deployment options" }, [mdaChoice, selfChoice]),
        managed, selfHosted, local, managedAction, selfHostedAction,
      ])]),
    ] };
  }

  function screenSelfHost() {
    const d = state.status.detail;
    const env = d.env || {};
    // Slack
    const bot = el("input", { class: "input", type: "password", placeholder: env.SLACK_BOT_TOKEN ? "Set. Paste to replace." : "xoxb-…", autocomplete: "off" });
    const app = el("input", { class: "input", type: "password", placeholder: env.SLACK_APP_TOKEN ? "Set. Paste to replace." : "xapp-…", autocomplete: "off" });
    const slackLine = el("div", { class: "status-line" });
    if (state.session.slack) setLine(slackLine, state.session.slack.status, state.session.slack.text);
    const slackSave = el("button", { class: "btn btn-outline", type: "submit", text: "Save and test Slack" });
    const slackForm = el("form", { class: "form" }, [
      intro("slack", "Slack", "Create the app from the manifest and install it to your workspace. Enable Socket Mode in its settings, then add the two tokens below.",
        el("div", { class: "actions" }, [el("a", { class: "btn btn-outline btn-compact", href: "https://api.slack.com/apps?new_app=1", target: "_blank", rel: "noopener", text: "Create Slack app" }), el("a", { class: "btn btn-ghost btn-compact", href: "https://api.slack.com/apps", target: "_blank", rel: "noopener", text: "Open your apps ↗" }), el("code", { class: "mono", text: "config/slack-manifest.example.yaml" })])),
      formField("w-bot", "Bot token", bot, slackTokenHelp("SLACK_BOT_TOKEN")),
      formField("w-app", "App-level token", app, slackTokenHelp("SLACK_APP_TOKEN")),
      slackLine,
      el("div", { class: "actions selfhost-actions" }, [slackSave]),
    ]);
    slackForm.addEventListener("submit", (ev) => { ev.preventDefault(); busy(slackSave, async () => {
      const updates = { SLACK_TRANSPORT: "socket_mode" };
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
    const dbSave = el("button", { class: "btn btn-outline", type: "submit", text: "Save and test connection" });
    const gen = el("button", { class: "btn btn-outline", type: "button", text: env.PAID_MEDIA_API_TOKENS && env.PAID_MEDIA_APPROVAL_SIGNING_KEY ? "Regenerate credentials" : "Generate credentials" });
    gen.addEventListener("click", async () => {
      await busy(gen, async () => {
        const result = await runAction("generate_secrets");
        const token = result.detail?.api_token_show_once;
        setLine(dbLine, result.status, token ? `Done. Your API token (shown once): ${token}` : result.summary);
        await loadStatus({ paint: false });
      });
      const savedEnv = state.status.detail.env || {};
      gen.textContent = savedEnv.PAID_MEDIA_API_TOKENS && savedEnv.PAID_MEDIA_APPROVAL_SIGNING_KEY ? "Regenerate credentials" : "Generate credentials";
    });
    const dbForm = el("form", { class: "form" }, [
      intro("postgres", "Storage and access", "Docker includes Postgres for conversations and approvals."),
      el("div", { class: "selfhost-credentials" }, [
        el("div", { class: "stack" }, [el("p", { class: "name", text: "API credentials" }), el("p", { class: "hint", text: "An API token for requests and a signing key for approval links." })]),
        gen,
      ]),
      disclose("Use an existing database", false, [
        formField("w-db", "Database URL", db, "For running the API directly. Docker configures its own database."),
        el("div", { class: "actions selfhost-actions" }, [dbSave]),
      ]),
      dbLine,
    ]);
    dbForm.addEventListener("submit", (ev) => { ev.preventDefault(); busy(dbSave, async () => {
      if (db.value) { const saved = await saveConfig({ DATABASE_URL: db.value }); if (!saved.ok) { setLine(dbLine, "fail", saved.summary); return; } }
      const test = await runAction("database_test");
      state.session.db = { status: test.status, text: test.summary };
      await loadStatus();
    }); });
    const dockerCommand = cli("docker compose up");
    dockerCommand.append(el("button", { class: "btn btn-ghost btn-compact", type: "button", text: "Copy", "aria-label": "Copy Docker command", onclick: ev => copyText("docker compose up", ev.currentTarget) }));
    return { scrollBody: true, children: [
      el("div", { class: "model-step-header deployment-width" }, [hero("Self-host your agent", "Set up access, then run on your infrastructure.")]),
      el("div", { class: "model-step-scroll" }, [el("div", { class: "model-scroll-inner deployment-width step-stack selfhost-layout" }, [
        el("section", { class: "deployment-card", "aria-label": "Storage and access" }, [el("div", { class: "deployment-card-body" }, [dbForm])]),
        el("section", { class: "deployment-card", "aria-label": "Slack connection" }, [el("div", { class: "deployment-card-body" }, [
          disclose("Connect Slack (optional)", false, [slackForm, el("div", { class: "selfhost-run" }, [processControls("slack", "Start Slack adapter", false, false)])]),
        ])]),
        el("section", { class: "deployment-card", "aria-label": "Run your agent" }, [el("div", { class: "deployment-card-body form" }, [
          intro("docker", "Run with Docker", "Starts the API on port 8080 with Postgres."),
          dockerCommand,
          disclose("Run the API directly", false, [
            el("p", { class: "note", text: "Uses your configured database, or in-memory storage when none is set." }),
            cli("paid-media-agent serve"),
            el("div", { class: "selfhost-run" }, [processControls("serve", "Start API", false, false)]),
          ]),
        ])]),
      ])]),
    ] };
  }

  const processViews = new Map();
  function processControls(name, label, disabled, confirm, prepare) {
    const deployment = name === "mda-deploy";
    let pending = false;
    let previousState;
    let authorizationUrls = "";
    const current = () => state.processes.find((p) => p.name === name) || {};
    const line = el("div", { class: "status-line", role: "status", "aria-live": "polite" });
    const action = el("button", { class: "btn btn-primary", type: "button" });
    const resume = el("button", { class: "btn btn-primary", type: "button", text: "Continue deployment" });
    const links = el("div", { class: "actions" });
    const authorization = el("div", { class: "step-stack" }, [
      el("p", { class: "note", text: "Authorize Slack, then continue to finish deployment." }),
      el("div", { class: "process-auth-actions" }, [links, resume]),
    ]);
    const complete = el("div", { class: "form" }, [
      el("p", { class: "name", role: "status", text: "Deployment complete" }),
      el("p", { class: "note", text: "Open your agent's message in Slack to start a conversation." }),
      el("a", { class: "btn btn-primary", href: "https://smith.langchain.com", target: "_blank", rel: "noopener", text: "Open LangSmith ↗" }),
    ]);
    const failed = el("p", { class: "note", role: "alert", text: "Deployment failed. Check the output below, fix the issue, then retry." });
    const status = el("div", { class: "status-line" });
    const log = el("pre", { class: "log mono" });
    const output = disclose(deployment ? "Deployment output" : "Process output", false, [log]);
    const wrap = el("div", { class: "form process-controls" }, [line, complete, failed, authorization, el("div", { class: "actions" }, [action]), status, output]);
    function update() {
      const p = current();
      const displayState = line.textContent ? "failed" : p.state;
      if (!pending) {
        action.textContent = p.running
          ? (deployment ? "Cancel deployment" : `Stop ${label.replace(/^Start /, "")}`)
          : (deployment && { failed: "Retry deployment", completed: "Deploy again" }[displayState]) || label;
        action.disabled = disabled && !p.running;
        action.classList.toggle("btn-outline", deployment && (p.running || displayState === "completed"));
        action.classList.toggle("btn-primary", !deployment || (!p.running && displayState !== "completed"));
      }
      resume.disabled = pending;
      complete.hidden = !deployment || displayState !== "completed";
      failed.hidden = !deployment || p.state !== "failed";
      output.hidden = !!line.textContent || !(p.running || (p.state !== "stopped" && p.log_tail));
      status.hidden = deployment ? !p.running : output.hidden;
      status.replaceChildren(badge(p.running ? "positive" : "info", deployment
        ? (p.state === "waiting_for_authorization" ? "Waiting for Slack authorization" : "Deploying…")
        : p.running ? `Process active · ${p.command}` : `${p.command} · exited ${p.returncode ?? ""}`));
      if (log.textContent !== (p.log_tail || "")) log.textContent = p.log_tail || "";
      if (p.state === "failed" && previousState !== "failed") output.open = true;
      previousState = p.state;
      const authorizationFocused = authorization.contains(document.activeElement);
      authorization.hidden = p.state !== "waiting_for_authorization";
      if (authorization.hidden && authorizationFocused) action.focus();
      if (!authorization.hidden) {
        const urls = [...new Set((p.log_tail || "").match(/https:\/\/[^\s<>"']+/g) || [])].filter((value) => {
          try { const u = new URL(value); return u.hostname === "smith.langchain.com" || u.hostname === "slack.com" || u.hostname.endsWith(".slack.com"); } catch (_) { return false; }
        });
        const signature = urls.join("\n");
        if (signature !== authorizationUrls) {
          links.replaceChildren(...urls.map((href) => el("a", { class: "btn btn-outline", href, target: "_blank", rel: "noopener noreferrer", text: "Authorize Slack ↗" })));
          authorizationUrls = signature;
        }
      }
    }
    async function execute(button, task) {
      if (pending) return;
      const hadFocus = document.activeElement === button;
      pending = true;
      line.replaceChildren();
      action.disabled = resume.disabled = true;
      try {
        await busy(button, async () => { await task(); await loadStatus({ paint: false }); });
      } finally {
        pending = false;
        refreshProcessControls();
        if (hadFocus && wrap.isConnected && [document.body, button].includes(document.activeElement)) {
          (authorization.hidden && authorization.contains(button) ? action : button).focus();
        }
      }
    }
    action.addEventListener("click", () => execute(action, async () => {
      if (current().running) await api(`/api/processes/${name}/stop`, { method: "POST" });
      else {
        if (prepare) await prepare();
        await api(`/api/processes/${name}/start`, { method: "POST", body: { confirm: !!confirm } });
      }
    }));
    resume.addEventListener("click", () => execute(resume, () => api(`/api/processes/${name}/continue`, { method: "POST" })));
    processViews.set(name, update);
    update();
    return wrap;
  }
  function refreshProcessControls() {
    for (const update of processViews.values()) update();
    if (state.view === "advanced") renderProcesses();
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
  function showFatal(error) { const line = $("#global-error"); line.hidden = false; line.replaceChildren(el("span", { text: error.message }), el("button", { class: "btn btn-ghost", type: "button", text: "Dismiss", onclick: () => { line.hidden = true; } })); }
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    const label = $("#theme-toggle-label");
    if (label) label.textContent = theme === "dark" ? "Light" : "Dark";
    $("#theme-toggle").setAttribute("aria-label", theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
    try { localStorage.setItem("pma-admin-theme", theme); } catch (_) { /* ignore */ }
  }

  // ---- advanced settings over the same host actions
  function renderAdvanced() {
    processViews.clear();
    const route = state.routes.find((r) => r.id === state.routeId) || state.routes[0];
    if (!route) return;
    state.routeId = route.id;
    renderRail();
    writeFragment();
    $("#page-title").textContent = route.title;
    $("#page-tagline").textContent = route.description;
    const actions = $("#page-actions");
    actions.hidden = route.id === "org";
    actions.replaceChildren(el("button", { class: "btn btn-outline", type: "button", text: "Check setup", onclick: (ev) => busy(ev.currentTarget, async () => {
      await loadStatus({ paint: false }); renderBanner(true);
    }) }));
    if (route.id === "direct") actions.prepend(el("button", { class: "btn btn-ghost", type: "button", text: "Back to accounts", onclick: () => go("pipeboard") }));
    if (state.lastRouteId !== route.id) $("#canvas").scrollTop = 0;
    renderBanner();
    renderSteps(route);
    renderProcesses();
  }
  function renderRail() {
    const nav = $("#rail-nav");
    nav.replaceChildren();
    for (const [label, ids] of [["Configure", ["local", "pipeboard", "direct"]], ["Run", ["mda", "self_hosted", "slack", "sandbox"]], ["Guides", ["org"]]]) {
      const group = el("div", { class: "rail-group", role: "group", "aria-label": label }, [el("p", { class: "rail-group-label", text: label })]);
      for (const id of ids) {
        const route = state.routes.find(item => item.id === id);
        if (!route) continue;
        group.append(el("button", { class: "rail-item", type: "button", "aria-current": route.id === state.routeId ? "page" : null, text: route.title, onclick: () => { state.routeId = route.id; renderAdvanced(); } }));
      }
      nav.append(group);
    }
  }
  function renderBanner(showHealthy = false) {
    const banner = $("#banner");
    const failing = (state.status?.detail?.checks || []).filter((c) => c.status === "fail");
    const writes = state.status?.detail?.writes || {};
    banner.dataset.tone = "";
    if (writes.kill_switch_engaged) { banner.hidden = false; banner.dataset.tone = "risk"; banner.textContent = "Campaign changes are paused by the kill switch. See the live-write runbook to resume them."; return; }
    if (failing.length) {
      banner.hidden = false;
      banner.replaceChildren(el("p", { class: "name", text: "Some checks need attention" }), el("ul", {}, failing.map(c => el("li", { text: c.detail || c.message || c.name.replaceAll("_", " ") }))));
      return;
    }
    banner.hidden = !showHealthy;
    banner.textContent = showHealthy ? "No blocking configuration issues found." : "";
  }
  function renderSteps(route) {
    const list = $("#steps");
    list.replaceChildren();
    state.lastRouteId = route.id;
    if (route.id === "org") { list.append(renderOrgContext(route)); return; }
    const tpl = $("#tpl-step");
    route.steps.forEach((step, index) => {
      const node = tpl.content.firstElementChild.cloneNode(true);
      node.dataset.step = step.id;
      const key = `${route.id}:${step.id}`;
      $(".step-status", node).dataset.status = step.status;
      const status = $(".step-status", node);
      status.textContent = { done: "Configured", optional: "Optional", blocked: "Needs setup" }[step.status] || "";
      status.hidden = !status.textContent;
      const platform = DIRECT_PLATFORMS.find(item => step.id === `direct_${item.id}`);
      $(".step-marker", node).append(platform ? logo(platform.logo) : el("span", { class: "step-number", text: String(index + 1) }));
      $(".step-title", node).textContent = step.title;
      $(".step-desc", node).textContent = step.description;
      const command = $(".step-command", node);
      command.open = !step.action || step.action.kind === "command";
      $(".step-cli code", node).textContent = step.cli;
      $(".copy", node).addEventListener("click", () => copyText(step.cli, $(".copy", node)));
      const head = $(".step-head", node); const body = $(".step-body", node);
      head.id = `head-${step.id}`;
      body.id = `body-${step.id}`;
      head.setAttribute("aria-controls", body.id);
      body.setAttribute("aria-labelledby", head.id);
      if (step.note) body.append(el("p", { class: "form-note", text: step.note }));
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
  function renderOrgContext() {
    const prompt = "Read .agents/skills/paid-media-org-onboarding/SKILL.md and help me configure this agent for my business. Read existing context, use the briefs I share, ask only for missing facts, and update workspace/skills/company-context/ directly. Keep original sources local and preserve unrelated content.";
    return el("section", { class: "step org-guide", "aria-labelledby": "org-guide-title" }, [
      el("div", { class: "org-guide-section" }, [
        el("h2", { id: "org-guide-title", text: "Set context with your coding agent" }),
        el("p", { class: "note", text: "Open this project in Codex, Claude Code, or Cursor and share a campaign brief. Your coding agent writes the business context and skills your deployed agent will use." }),
        el("div", { class: "actions" }, [el("button", { class: "btn btn-primary", type: "button", text: "Copy instructions", onclick: ev => copyText(prompt, ev.currentTarget) })]),
      ]),
      el("div", { class: "org-guide-section" }, [
        el("h3", { text: "Plain Markdown, in your workspace" }),
        el("p", { class: "note" }, ["Edit ", el("code", { text: "workspace/skills/company-context/SKILL.md" }), " by hand if you prefer. Add conversion definitions, targets, markets, and campaign conventions. Original briefs stay in ", el("code", { text: "workspace/sources/" }), "."]),
        el("p", { class: "hint", text: "Both folders are excluded from Git. Runtime skills are included when you deploy. See docs/customization.md for examples and optional warehouse connections." }),
      ]),
    ]);
  }
  async function renderAction(step, node) {
    const box = $(".step-action", node);
    box.replaceChildren();
    const action = step.action;
    if (!action) return;
    if (step.id === "mda_deploy") {
      box.append(el("button", { class: "btn btn-primary", type: "button", text: "Review and deploy", onclick: () => go("deployment") }));
      return;
    }
    if (action.kind === "form") { if (!state.config) await loadConfig(); box.append(buildForm(action, node)); }
    else if (action.kind === "test" || action.kind === "run") { const b = el("button", { class: "btn btn-primary btn-compact", type: "button", text: action.label }); b.addEventListener("click", () => runInline(b, action.action, action.payload || {}, node)); box.append(b); }
    else if (action.kind === "link") box.append(el("a", { class: "btn btn-outline btn-compact", href: action.href, target: "_blank", rel: "noopener", text: action.label }));
    else if (action.kind === "command") return;
    else if (action.kind === "accounts") box.append(buildAccounts(node));
    else if (action.kind === "process") box.append(processControls(action.action, action.label, false, false));
  }
  const CONFIG_LABELS = {
    PAID_MEDIA_MODEL: "Model", PAID_MEDIA_MODEL_BASE_URL: "Custom API URL",
    PAID_MEDIA_TOOL_SELECTOR_MODEL: "Tool selection model",
    ANTHROPIC_API_KEY: "Anthropic API key", OPENAI_API_KEY: "OpenAI API key", GOOGLE_API_KEY: "Google API key",
    LANGSMITH_API_KEY: "LangSmith API key", PIPEBOARD_API_TOKEN: "Pipeboard API token",
    X_ADS_CONSUMER_KEY: "App API key", X_ADS_CONSUMER_SECRET: "App API secret",
    X_ADS_ACCESS_TOKEN: "Access token", X_ADS_ACCESS_TOKEN_SECRET: "Access token secret",
    OPENAI_ADS_API_KEY: "Ads API key", SLACK_TRANSPORT: "Connection method",
    SLACK_BOT_TOKEN: "Bot token", SLACK_APP_TOKEN: "App-level token",
    SLACK_SIGNING_SECRET: "Signing secret", DATABASE_URL: "Database URL",
  };
  function slackTokenHelp(key) {
    if (key === "SLACK_BOT_TOKEN") return "OAuth & Permissions → Install to Workspace → Bot User OAuth Token. Copy the token starting with xoxb-.";
    if (key === "SLACK_APP_TOKEN") return [
      "Basic Information → App-Level Tokens → Generate Token and Scopes. Add ",
      el("code", { text: "connections:write" }), ", then copy the token starting with xapp-. Requires Socket Mode to be enabled. ",
      el("a", { href: "https://api.slack.com/apps", target: "_blank", rel: "noopener", text: "Open your Slack app ↗" }),
    ];
    if (key === "SLACK_SIGNING_SECRET") return "Basic Information → App Credentials → Signing Secret. Used for HTTP connections.";
    return null;
  }
  function buildForm(action, node) {
    const form = el("form", { class: "form advanced-form" });
    const keys = action.keys.map(name => state.config.detail.keys.find(key => key.name === name)).filter(Boolean);
    for (const key of keys) {
      const input = key.name === "SLACK_TRANSPORT"
        ? el("select", { class: "input schedule-select", name: key.name }, [el("button", { type: "button" }, [el("selectedcontent")]), ...[["socket_mode", "Socket Mode"], ["http", "HTTP"]].map(([value, text]) => el("option", { value, text, selected: key.value === value ? true : null }))])
        : el("input", { class: "input", name: key.name, type: key.secret ? "password" : "text", placeholder: key.is_set && key.secret ? "Saved. Leave blank to keep." : key.example || "", value: key.secret ? "" : key.value, autocomplete: "off", spellcheck: "false" });
      input.id = `f-${key.name}`; input.dataset.initial = key.secret ? "" : key.value;
      const help = key.name === "PAID_MEDIA_MODEL" ? "Use provider:model, such as anthropic:claude-sonnet-4-6."
        : key.name === "PAID_MEDIA_TOOL_SELECTOR_MODEL" ? "Optional smaller model that chooses the tools for each request."
        : key.name === "PAID_MEDIA_MODEL_BASE_URL" ? "Optional endpoint for a compatible model provider." : slackTokenHelp(key.name);
      const field = formField(input.id, CONFIG_LABELS[key.name] || key.description, input, help);
      form.append(field);
    }
    const save = el("button", { class: "btn btn-primary btn-compact", type: "submit", text: action.label });
    form.append(el("div", { class: "form-actions" }, [el("span", { class: "form-note", text: "Saved on this machine." }), save]));
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const updates = {};
      for (const input of form.querySelectorAll("input, select")) {
        if (input.type === "password" && input.value === "") continue;
        if (input.type !== "password" && input.value === (input.dataset.initial ?? "")) continue;
        updates[input.name] = input.value;
      }
      if (!Object.keys(updates).length) return showResult(node, { status: "warn", summary: "Nothing to save.", detail: {} });
      await withBusy(save, async () => {
        const result = await saveConfig(updates);
        showResult(node, result, false);
        if (!result.ok) return;
        state.config = null;
        await loadStatus();
      });
    });
    return form;
  }
  function buildAccounts(node) {
    const wrap = el("div", { class: "form wide" });
    const discover = el("button", { class: "btn btn-primary btn-compact", type: "button", text: "Discover accounts" });
    const list = el("div", { class: "table-scroll" });
    wrap.append(el("div", { class: "form-actions" }, [discover, el("span", { class: "form-note", text: "Find accounts across your connected ad platforms." })]), list);
    discover.addEventListener("click", () => withBusy(discover, async () => { const result = await runAction("accounts_discover"); state.discovered = result.detail.accounts || []; showResult(node, result, false); list.replaceChildren(renderAccountTable(state.discovered, node)); }));
    if (state.discovered) list.replaceChildren(renderAccountTable(state.discovered, node));
    const current = derive().realAccounts ? state.status.detail.accounts : [];
    if (current.length) {
      wrap.append(el("div", { class: "section-title", text: "Saved accounts" }), el("div", { class: "table-scroll", tabindex: "0", role: "region", "aria-label": "Saved accounts" }, [el("table", { class: "data" }, [
        el("thead", {}, el("tr", {}, ["Alias", "Platform", "Provider id", "Currency", "Timezone", ""].map((h) => el("th", { text: h })))),
        el("tbody", {}, current.map((a) => el("tr", {}, [el("td", { class: "mono", text: a.alias }), el("td", { text: a.platform }), el("td", { class: "mono", text: a.provider_account_id_masked }), el("td", { text: a.currency }), el("td", { text: a.timezone }),
          el("td", {}, el("button", { class: "btn btn-ghost btn-compact", type: "button", text: "Remove", onclick: async (ev) => withBusy(ev.currentTarget, async () => { showResult(node, await api(`/api/accounts/${encodeURIComponent(a.alias)}`, { method: "DELETE" })); await loadStatus(); }) }))]))),
      ])]));
    }
    return wrap;
  }
  function renderAccountTable(rows, node) {
    if (!rows.length) return el("p", { class: "form-note", text: "No accounts found. Connect Pipeboard or add direct platform credentials first." });
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
  function renderProcesses() {
    const box = $("#processes");
    box.replaceChildren();
    const running = state.processes.filter((p) => p.running);
    if (!running.length) return;
    box.append(el("h2", { class: "section-title", text: "Running on this machine" }));
    for (const proc of running) {
      const stop = el("button", { class: "btn btn-outline btn-compact", type: "button", text: "Stop" });
      stop.addEventListener("click", () => withBusy(stop, async () => { await api(`/api/processes/${proc.name}/stop`, { method: "POST" }); await loadStatus(); }));
      box.append(el("div", { class: "proc" }, [el("div", {}, [el("div", { class: "label", text: { "mda-dev": "LangSmith Studio", "mda-deploy": "MDA deployment", serve: "Agent API", slack: "Slack connection" }[proc.name] || proc.name }), el("div", { class: "form-note", text: "Running" })]), stop]));
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
    const label = button.textContent;
    if (label === "Copied") return;
    try { await navigator.clipboard.writeText(text); button.textContent = "Copied"; setTimeout(() => (button.textContent = label), 1200); }
    catch (_) { button.textContent = "Select and copy"; }
  }

  // ---- boot
  document.addEventListener("pointerdown", () => { document.body.dataset.input = "pointer"; }, true);
  document.addEventListener("keydown", () => { document.body.dataset.input = "keyboard"; }, true);
  readFragment();
  let theme = "light";
  try { theme = localStorage.getItem("pma-admin-theme") || "light"; } catch (_) { /* ignore */ }
  applyTheme(theme);
  $("#theme-toggle").addEventListener("click", () => applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark"));
  $("#view-toggle").addEventListener("click", () => { state.view = state.view === "advanced" ? "wizard" : "advanced"; render(); });
  window.addEventListener("hashchange", () => { readFragment(); render(); });
  loadStatus().catch(showFatal);
  setInterval(() => { if (state.processes.some((p) => p.running)) loadStatus({ paint: false }).then(refreshProcessControls).catch(() => {}); }, 4000);
})();
