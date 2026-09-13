/* Slack appearance and report timing. The .env settings are shared with the MDA declarations. */
window.PMA_CUSTOMIZATION = ({ el, logo, check, formField, disclose, api, saveConfig, busy, setLine, settings, draft: changes, iconSet, onIconChange }) => {
  const draft = { ...settings, ...changes };
  const fields = new Map();
  const line = el("div", { class: "status-line", role: "status", "aria-live": "polite" });
  const previewName = el("strong");
  const previewDescription = el("p", { class: "note" });
  const previewCaption = el("p", { class: "hint" });
  const avatar = el("div", { class: "slack-preview-avatar" });
  let iconData = "";
  let iconBusy = false;
  const change = (name, value) => {
    draft[name] = value;
    if (value === settings[name]) delete changes[name];
    else changes[name] = value;
    if (Object.keys(changes).length) setLine(line, "info", "Unsaved changes");
    else line.replaceChildren();
  };
  const paintPreview = () => {
    previewName.textContent = draft.slack_name || "Agent name";
    previewCaption.textContent = iconSet ? "Slack preview" : "Slack preview · MDA will generate your icon.";
    previewDescription.textContent = draft.slack_description || "Your Slack app description";
    avatar.style.backgroundColor = /^#[0-9a-f]{6}$/i.test(draft.slack_background_color) ? draft.slack_background_color : "";
    avatar.replaceChildren(iconData ? el("img", { src: iconData, width: "40", height: "40", alt: "Custom Slack icon" }) : logo("deepagents"));
  };
  const input = (name, label, attrs = {}, help) => {
    const control = el("input", { class: "input", ...attrs, id: `custom-${name}`, value: attrs.type === "time" ? String(draft[name]).slice(0, 5) : draft[name] ?? "" });
    fields.set(name, control);
    control.addEventListener("input", () => {
      change(name, attrs.type === "number" ? Number(control.value) : control.value);
      paintPreview();
    });
    return formField(control.id, label, control, help);
  };
  const toggle = (name, label, help) => {
    const id = `custom-${name}`;
    const control = el("input", { type: "checkbox", class: "sr-only", checked: draft[name], id, "aria-labelledby": `${id}-label`, "aria-describedby": `${id}-help` });
    const mark = check(draft[name]);
    control.addEventListener("change", () => { mark.dataset.checked = String(control.checked); change(name, control.checked); });
    return el("label", { class: "customization-toggle", for: control.id }, [control,
      el("span", { class: "customization-toggle-copy" }, [el("span", { class: "name", id: `${id}-label`, text: label }), el("span", { class: "note", id: `${id}-help`, text: help })]),
      mark,
    ]);
  };
  const reportSelect = (name, label, options, parse = Number) => {
    const control = el("select", { class: "input schedule-select", id: `custom-${name}`, required: true }, [
      el("button", { type: "button" }, [el("selectedcontent")]),
      ...options.map(([value, text]) => el("option", { value, text })),
    ]);
    control.value = name === "report_time" ? String(draft[name]).slice(0, 5) : String(draft[name]);
    fields.set(name, control);
    control.addEventListener("change", () => change(name, parse(control.value)));
    return formField(control.id, label, control);
  };
  const responses = el("div", { class: "customization-section" }, [
    el("h3", { class: "customization-section-title", text: "When the agent responds" }),
    el("p", { class: "note", text: "By default, mentions and direct messages start runs. Replies continue active threads." }),
    el("div", { class: "customization-options" }, [
      toggle("slack_trigger_on_all_messages", "Every channel message", "In channels the app has joined. More messages mean more model usage."),
      toggle("slack_allow_bot_triggers", "Messages from other bots", "Can create repeated runs when bots reply to one another."),
    ]),
  ]);
  // Keep an existing minute-specific schedule alongside the quarter-hour choices.
  const times = new Set(Array.from({ length: 96 }, (_, i) => `${String(Math.floor(i / 4)).padStart(2, "0")}:${String((i % 4) * 15).padStart(2, "0")}`));
  const currentTime = String(draft.report_time).slice(0, 5);
  times.add(currentTime);
  // Keep saved IANA aliases even when the browser lists only their canonical names.
  const timezones = new Set(["UTC", draft.report_timezone, ...Intl.supportedValuesOf("timeZone")]);
  const timezoneOptions = [...timezones].filter(zone => zone && zone !== "UTC").sort();
  timezoneOptions.unshift("UTC");
  const reports = el("div", { class: "customization-section" }, [
    el("h3", { class: "customization-section-title", text: "Scheduled reports" }),
    el("div", { class: "customization-schedule" }, [
      el("div", { class: "field-row" }, [
        reportSelect("weekly_report_day", "Weekly report", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((day, i) => [i, day])),
        reportSelect("monthly_report_day", "Monthly report day", Array.from({ length: 28 }, (_, i) => [i + 1, `Day ${i + 1}`])),
      ]),
      el("div", { class: "field-row" }, [
        reportSelect("report_time", "Run at", [...times].sort().map(time => [time, time]), String),
        reportSelect("report_timezone", "Timezone", timezoneOptions.map(zone => [zone, zone.replaceAll("_", " ")]), String),
      ]),
    ]),
    el("p", { class: "hint", text: "Weekly and monthly reports run at this time on Managed Deep Agents." }),
  ]);
  const upload = el("input", { type: "file", accept: "image/png", id: "custom-slack-icon", class: "customization-file" });
  const uploadLabel = el("label", { class: "btn btn-outline btn-compact", for: upload.id, text: "Upload icon" });
  const remove = el("button", { class: "btn btn-ghost btn-compact", type: "button", text: "Remove", hidden: !iconSet });
  const iconNote = el("p", { class: "hint", text: "512 × 512 PNG, up to 1 MB." });
  const iconActions = el("div", { class: "actions" }, [upload, uploadLabel, remove]);
  upload.addEventListener("change", async () => {
    const file = upload.files?.[0];
    if (!file) return;
    iconBusy = true; upload.disabled = true; remove.disabled = true;
    try {
      if (file.size > 1024 * 1024) throw new Error("Choose a PNG no larger than 1 MB");
      setLine(line, "info", "Saving icon…");
      await api("/api/slack/icon", { method: "POST", body: file });
      iconSet = true; onIconChange(true); remove.hidden = false;
      iconData = (await api("/api/slack/icon")).data_url;
      paintPreview();
      setLine(line, "ok", "Icon saved. Deploy to apply it to Slack.");
    } catch (error) { setLine(line, "fail", error.message); }
    finally { iconBusy = false; upload.disabled = false; remove.disabled = false; upload.value = ""; }
  });
  remove.addEventListener("click", () => busy(remove, async () => {
    iconBusy = true; upload.disabled = true;
    try {
      await api("/api/slack/icon", { method: "DELETE" });
      iconSet = false; onIconChange(false); iconData = ""; remove.hidden = true;
      paintPreview(); setLine(line, "ok", "Custom icon removed. MDA will generate one on deployment.");
    } finally { iconBusy = false; upload.disabled = false; }
  }));
  const appearance = disclose("Slack appearance", false, [
    el("div", { class: "customization-identity" }, [avatar, el("div", { class: "stack" }, [iconActions, iconNote])]),
    input("slack_name", "Name in Slack", { required: true, maxlength: "35", pattern: "[a-zA-Z0-9_.][a-zA-Z0-9_. \\-]*[a-zA-Z0-9_.]|[a-zA-Z0-9_.]" }),
    input("slack_description", "Description", { maxlength: "139" }),
    input("slack_background_color", "Icon background", { placeholder: "Default", pattern: "#[0-9a-fA-F]{6}", maxlength: "7" }, "Optional hex color, such as #1d4ed8."),
    el("div", { class: "customization-preview" }, [
      previewCaption,
      el("div", { class: "slack-preview", "aria-label": "Slack appearance preview" }, [el("div", { class: "stack" }, [
        el("div", { class: "slack-preview-name" }, [previewName, el("span", { class: "badge badge-quiet", text: "APP" })]), previewDescription,
      ])]),
    ]),
  ]);
  const form = el("form", { class: "form customization-form", novalidate: true }, [
    responses, reports, appearance,
    line,
  ]);
  const element = el("section", { class: "deployment-card deployment-customization", "aria-labelledby": "customization-heading" }, [
    el("div", { class: "deployment-card-body" }, [
      el("div", { class: "deployment-section-heading" }, [
        el("h2", { id: "customization-heading", text: "Agent settings" }),
        el("p", { class: "note", text: "Set when your agent responds and sends reports. Saved when you deploy." }),
      ]),
      form,
    ]),
  ]);
  const save = async () => {
    if (iconBusy) throw new Error("Wait for the icon to finish saving.");
    const invalid = [...fields.values()].find(control => !control.checkValidity());
    if (invalid) {
      if (appearance.contains(invalid)) appearance.open = true;
      invalid.reportValidity(); invalid.focus();
      throw new Error("Check the highlighted setting.");
    }
    if (!Object.keys(changes).length) return;
    const result = await saveConfig(Object.fromEntries(Object.entries(changes).map(([key, value]) => [`PAID_MEDIA_${key.toUpperCase()}`, String(value)])));
    if (!result.ok) throw new Error(result.summary);
    Object.assign(settings, draft);
    Object.keys(changes).forEach(key => delete changes[key]);
    setLine(line, "ok", "Settings saved. Deploy to apply them.");
  };
  form.addEventListener("submit", event => event.preventDefault());
  paintPreview();
  if (iconSet) api("/api/slack/icon").then(result => { iconData = result.data_url; paintPreview(); }).catch(error => setLine(line, "fail", error.message));
  return { element, save };
};
