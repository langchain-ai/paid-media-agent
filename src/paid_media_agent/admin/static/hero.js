/* Onboarding illustration: an isometric view of the agent's supported tools. */
window.createPaidMediaHero = ({ el, logo }) => {
  const svg = (tag, attrs = {}, children = []) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
    for (const child of children) node.append(child);
    return node;
  };
  const cosine = Math.cos(Math.PI / 6);
  const cell = 56;
  const projection = `matrix(${cosine} -.5 ${cosine} .5 0 0)`;
  const point = (column, row) => [360 + (column + row) * cell * cosine, 304 + (row - column) * cell / 2];
  const integrations = [
    ["pipeboard", "Pipeboard", "Ad account connection", 4, -2],
    ["google", "Google Ads", "Ad platform", 2, -2],
    ["anthropic", "Anthropic", "Model provider", 0, -3],
    ["deepagents", "Managed Deep Agents", "Managed hosting", 4, 1],
    ["x", "X Ads", "Ad platform", 2, 0],
    ["meta", "Meta Ads", "Ad platform", 0, -1],
    ["langchain", "LangChain", "Agent framework", -2, -2],
    ["linkedin", "LinkedIn Ads", "Ad platform", 1, 1],
    ["openai", "OpenAI", "Model provider", -1, 1],
    ["slack", "Slack", "Optional team interface", -3, -1],
    ["reddit", "Reddit Ads", "Ad platform", -2, 1],
  ];
  const defs = svg("defs", {}, [
    svg("pattern", { id: "hero-grid", width: cell, height: cell, patternUnits: "userSpaceOnUse" }, [
      svg("path", { d: `M ${cell} 0 H 0 V ${cell}`, fill: "none", stroke: "currentColor", "stroke-width": ".7" }),
    ]),
    svg("radialGradient", { id: "hero-grid-fade" }, [
      svg("stop", { offset: ".2", "stop-color": "white" }),
      svg("stop", { offset: "1", "stop-color": "black" }),
    ]),
    svg("mask", { id: "hero-grid-mask" }, [
      svg("rect", { width: "720", height: "620", fill: "url(#hero-grid-fade)" }),
    ]),
  ]);
  const floor = svg("g", { class: "integration-floor", mask: "url(#hero-grid-mask)" }, [
    svg("g", { transform: `translate(360 304) ${projection}` }, [
      svg("rect", { x: "-504", y: "-504", width: "1008", height: "1008", fill: "url(#hero-grid)" }),
    ]),
  ]);
  for (const [column, row, direction] of [[3, -4, 1], [-4, -1, 0], [2, 2, 1], [0, -2, 0], [-1, 3, 1]]) {
    const [x, y] = point(column, row);
    const [endX, endY] = point(column + (direction ? 1 : 0), row + (direction ? 0 : 1));
    floor.append(svg("path", { class: "integration-signal", d: `M ${x} ${y} L ${endX} ${endY}` }));
  }
  const drawing = svg("svg", { class: "integration-scene", viewBox: "0 0 720 620", role: "group", "aria-label": "Tools supported by Paid Media Agent. These are available integrations, not connected accounts." }, [defs, floor]);
  const caption = svg("text", { class: "integration-caption", transform: `translate(478 447) ${projection}`, "text-anchor": "middle" });
  caption.textContent = "Your paid media stack";
  drawing.append(caption);
  integrations.forEach(([mark, name, description, column, row], index) => {
    const [x, y] = point(column, row);
    const tile = svg("g", { class: "integration-tile", transform: `translate(${x} ${y - 34})`, tabindex: "0", role: "img", "aria-label": `${name}: ${description}`, style: `--tile-delay: ${index * 60}ms; --float-delay: ${index * -710}ms; --float-duration: ${7 + index % 4}s` });
    const float = svg("g", { class: "integration-float" });
    const width = cell * cosine;
    float.append(
      svg("path", { class: "integration-side", d: `M ${-width} 0 L 0 28 L 0 44 L ${-width} 16 Z` }),
      svg("path", { class: "integration-side integration-side-front", d: `M 0 28 L ${width} 0 L ${width} 16 L 0 44 Z` }),
      svg("rect", { class: "integration-face", x: "-28", y: "-28", width: cell, height: cell, rx: "6", transform: projection }),
    );
    const markBox = svg("foreignObject", { x: "-17", y: "-17", width: "34", height: "34", transform: projection, "aria-hidden": "true" });
    markBox.append(logo(mark, "integration-mark"));
    float.append(markBox);
    const tooltip = svg("g", { class: "integration-callout", "aria-hidden": "true" }, [
      svg("path", { d: "M 0 -32 V -72" }),
      svg("circle", { cx: "0", cy: "-32", r: "2" }),
    ]);
    const labelBox = svg("foreignObject", { x: "-150", y: "-104", width: "300", height: "32" });
    labelBox.append(el("div", { class: "integration-label" }, [el("span", { text: name }), el("span", { class: "note", text: description })]));
    tooltip.append(labelBox);
    tile.append(float, tooltip);
    drawing.append(tile);
  });
  return el("div", { class: "integration-visual" }, [drawing]);
};
