/* The GTM CORE combobox anatomy, adapted to the console's dependency-free DOM. */
window.createModelPicker = ({ el, logo, preset, selected, loadModels, onChange }) => {
  let value = selected;
  let models = [];
  let filtered = [];
  let active = -1;
  let requested = false;
  let requestId = 0;
  const providerLogos = { google: "gemini", "google-genai": "gemini", google_genai: "gemini", moonshotai: "moonshot", "x-ai": "xai", mistralai: "mistral", "z-ai": "zhipu", "meta-llama": "meta" };
  const modelId = spec => spec.slice(spec.indexOf(":") + 1);
  const modelLogo = item => {
    const provider = item?.provider || (["langsmith", "openrouter"].includes(preset.id) ? modelId(value).split("/")[0] : preset.logo);
    const key = providerLogos[provider] || provider;
    return logo(window.PMA_LOGOS[key] ? key : "custom", "model-mini-logo");
  };
  const triggerLabel = el("span", { class: "model-picker-value" });
  const trigger = el("button", { id: "w-model", class: "input model-picker-trigger", type: "button", role: "combobox", "aria-haspopup": "listbox", "aria-controls": "w-model-options", "aria-expanded": "false" }, [triggerLabel, el("span", { class: "model-picker-chevron", "aria-hidden": "true", text: "⌄" })]);
  const list = el("div", { id: "w-model-options", class: "model-picker-list", role: "listbox", "aria-label": "Available models" });
  const search = el("input", { class: "model-picker-search", placeholder: "Search models…", "aria-label": "Search models", role: "combobox", "aria-controls": list.id, "aria-autocomplete": "list", "aria-expanded": "false", autocomplete: "off", spellcheck: "false" });
  const status = el("p", { class: "model-picker-status", role: "status" });
  const refresh = el("button", { class: "btn btn-ghost btn-compact", type: "button", text: "Refresh", onclick: () => load() });
  const manual = el("button", { class: "btn btn-ghost btn-compact", type: "button", text: "Enter model ID", onclick: () => {
    popup.hidePopover(); manualField.hidden = false; manualInput.focus();
  } });
  const popup = el("div", { id: "w-model-popup", class: "model-picker-popup", popover: "auto", "data-slot": "combobox-content" }, [
    el("div", { class: "model-picker-search-row" }, [search]), list, status,
    el("div", { class: "model-picker-footer" }, [manual, refresh]),
  ]);
  const manualInput = el("input", { id: "w-model-id", class: "input", placeholder: "Model ID from your provider", "aria-label": "Model ID", autocomplete: "off", spellcheck: "false", value: selected ? modelId(selected) : "" });
  const manualField = el("div", { class: "field model-picker-manual", hidden: true }, [el("label", { class: "text-label", for: "w-model-id", text: "Model ID" }), manualInput]);
  const element = el("div", { id: "w-model-field", class: "model-picker" }, [trigger, popup, manualField]);
  const paintValue = () => {
    const item = models.find(item => item.id === value);
    triggerLabel.replaceChildren(...(value ? [modelLogo(item), el("span", { text: item?.name || modelId(value) })] : [el("span", { class: "sub", text: "Select a model" })]));
  };
  const setValue = next => { value = next; paintValue(); onChange(); };
  manualInput.addEventListener("input", () => {
    const id = manualInput.value.trim();
    const prefix = `${preset.model.split(":")[0]}:`;
    setValue(id ? (id.startsWith(prefix) ? id : `${prefix}${id}`) : "");
  });
  const highlight = index => {
    active = index;
    [...list.children].forEach((row, i) => row.dataset.active = String(i === active));
    if (active < 0) search.removeAttribute("aria-activedescendant");
    else {
      const row = list.children[active];
      search.setAttribute("aria-activedescendant", row.id);
      if (row.offsetTop < list.scrollTop) list.scrollTop = row.offsetTop;
      else if (row.offsetTop + row.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = row.offsetTop + row.offsetHeight - list.clientHeight;
    }
  };
  const choose = item => { setValue(item.id); manualInput.value = modelId(item.id); manualField.hidden = true; popup.hidePopover(); trigger.focus(); };
  const filter = () => {
    const query = search.value.trim().toLowerCase();
    filtered = models.filter(item => `${item.id} ${item.name}`.toLowerCase().includes(query));
    list.replaceChildren(...filtered.map((item, index) => el("div", {
      id: `w-model-option-${index}`, class: "model-picker-option", role: "option", "aria-selected": String(item.id === value),
      onpointermove: () => highlight(index), onmousedown: ev => ev.preventDefault(), onclick: () => choose(item),
    }, [modelLogo(item), el("span", { class: "model-option-name", text: item.name }), item.id === value ? el("span", { class: "model-option-check", "aria-hidden": "true", text: "✓" }) : null])));
    if (models.length) status.textContent = filtered.length ? `${models.length} models from ${preset.label}` : "No matching models.";
    highlight(filtered.length ? Math.max(0, filtered.findIndex(item => item.id === value)) : -1);
    if (popup.matches(":popover-open")) place();
  };
  const place = () => {
    const bounds = trigger.getBoundingClientRect();
    const below = window.innerHeight - bounds.bottom - 18;
    const above = bounds.top - 18;
    const opensBelow = below >= 280 || below >= above;
    popup.style.width = `${Math.min(bounds.width, window.innerWidth - 24)}px`;
    popup.style.maxHeight = `${Math.max(120, Math.min(400, opensBelow ? below : above))}px`;
    popup.style.left = `${Math.max(12, Math.min(bounds.left, window.innerWidth - popup.offsetWidth - 12))}px`;
    popup.style.top = `${opensBelow ? bounds.bottom + 6 : Math.max(12, bounds.top - popup.offsetHeight - 6)}px`;
  };
  async function load() {
    const id = ++requestId;
    requested = true;
    models = []; filter();
    refresh.disabled = true;
    status.textContent = "Loading models from the provider…";
    list.setAttribute("aria-busy", "true");
    try {
      const result = await loadModels();
      if (id !== requestId || !element.isConnected) return;
      if (!result.ok) { status.textContent = result.summary; return; }
      models = result.detail.models;
      status.textContent = models.length ? "" : "No chat models returned. You can enter a model ID.";
      filter(); paintValue();
    } catch (error) {
      if (id === requestId) status.textContent = error.message;
    } finally {
      if (id === requestId) { refresh.disabled = false; list.removeAttribute("aria-busy"); if (popup.matches(":popover-open")) place(); }
    }
  }
  search.addEventListener("input", filter);
  search.addEventListener("keydown", ev => {
    if (["ArrowDown", "ArrowUp", "Enter"].includes(ev.key)) ev.preventDefault();
    if (ev.key === "ArrowDown" && filtered.length) highlight(Math.min(active + 1, filtered.length - 1));
    if (ev.key === "ArrowUp" && filtered.length) highlight(Math.max(0, active - 1));
    if (ev.key === "Enter" && active >= 0) choose(filtered[active]);
    if (ev.key === "Escape") { ev.preventDefault(); popup.hidePopover(); trigger.focus(); }
  });
  const onScroll = ev => { if (!popup.contains(ev.target)) popup.hidePopover(); };
  const open = () => {
    popup.showPopover(); place(); search.value = ""; filter(); search.focus();
    if (!requested) load();
  };
  trigger.addEventListener("click", () => popup.matches(":popover-open") ? popup.hidePopover() : open());
  trigger.addEventListener("keydown", ev => { if (["ArrowDown", "ArrowUp"].includes(ev.key)) { ev.preventDefault(); open(); } });
  popup.addEventListener("toggle", ev => {
    const expanded = ev.newState === "open";
    trigger.setAttribute("aria-expanded", String(expanded)); search.setAttribute("aria-expanded", String(expanded));
    if (expanded) { window.addEventListener("resize", place); document.addEventListener("scroll", onScroll, true); }
    else { window.removeEventListener("resize", place); document.removeEventListener("scroll", onScroll, true); }
  });
  popup.addEventListener("focusout", ev => { if (ev.relatedTarget && !element.contains(ev.relatedTarget)) popup.hidePopover(); });
  paintValue();
  return { element, get value() { return value; }, refresh: load };
};
