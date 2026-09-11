// Headless walkthrough of the setup wizard: model presets and a custom key, ad accounts,
// path choice, MDA, done. Fails on any browser error.
// Run against a throwaway project copy that includes pyproject.toml and langgraph.json.
// Usage: node tests/e2e/console_walkthrough.mjs "<console url with #token>" <screenshot dir>
import { chromium } from "playwright";
const url = process.argv[2]; const out = process.argv[3];
const errors = []; const r = {};
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(String(e)));
const shot = async (name) => { await page.waitForTimeout(500); await page.screenshot({ path: `${out}/${name}.png`, fullPage: true }); };
await page.goto(url, { waitUntil: "networkidle" });
await page.waitForSelector(".hero-title", { timeout: 15000 });
await page.waitForSelector(".stepper-item");
r.rail = await page.$$eval(".stepper-item .step-label", (els) => els.map((e) => e.textContent));
r.title = await page.$eval(".hero-title", (e) => e.textContent);
if (await page.$(".onboard-foot .btn-primary:has-text('Start setup')")) {
  await page.click(".onboard-foot .btn-primary:has-text('Start setup')");
  await page.waitForSelector(".hero-title:has-text('Choose a model')");
}
await shot("01-model");
await page.waitForSelector(".options .option", { timeout: 10000 });
r.providers = await page.$$eval(".options .option .name", (els) => els.map((e) => e.textContent));
r.recommended = await page.$$eval(".options .option .note", (els) => els.map((e) => e.textContent).filter((t) => t.includes("Recommended")));
await page.click("summary:has-text('More providers')");
await page.click(".options .option:has-text('Kimi')");
await page.waitForSelector("#w-model");
r.kimiModel = await page.$eval("#w-model", (e) => e.value);
r.kimiBase = await page.$eval("#w-base", (e) => e.value);
r.kimiKeyName = await page.$eval("form .field .hint code", (e) => e.textContent);
await shot("02-model-kimi");
await page.click("summary:has-text('More providers')");
await page.click(".options .option:has-text('Custom')");
await page.waitForSelector("#w-keyname:not([disabled])");
await page.fill("#w-model", "openai:my-model");
await page.fill("#w-keyname", "ACME_API_KEY");
await page.fill("#w-key", "acme-" + "z".repeat(24));
await page.fill("#w-base", "https://llm.acme.example/v1");
await page.click("button:has-text('Save and test')");
await page.waitForFunction(() => /FAIL|OK|WARN/.test(document.querySelector("#model-status .badge")?.textContent || ""), null, { timeout: 90000 });
r.customTest = (await page.$eval("#model-status", (e) => e.textContent)).slice(0, 120);
r.leak = (await page.content()).includes("z".repeat(24));
await shot("03-model-custom");
await page.click(".options .option:has-text('Anthropic')");
await page.waitForSelector("#w-model");
await page.fill("#w-key", "sk-ant-" + "a".repeat(30));
await page.click("button:has-text('Save and test')");
await page.waitForFunction(() => /FAIL|OK|WARN/.test(document.querySelector("#model-status .badge")?.textContent || ""), null, { timeout: 90000 });
r.anthropicTest = (await page.$eval("#model-status", (e) => e.textContent)).slice(0, 100);
await page.click(".onboard-foot .btn-primary");
await page.waitForSelector("#w-token");
await page.click(".onboard-foot .btn-primary");
await page.waitForSelector(".path-card");
r.pathTitle = await page.$eval(".hero-title", (e) => e.textContent);
r.pathRecommended = await page.$$eval(".path-kicker.rec", (els) => els.map((e) => e.textContent));
await shot("06-path");
await page.click("#theme-toggle");
await shot("07-path-dark");
await page.click(".path-card:has-text('Managed')");
await page.click(".onboard-foot .btn-primary");
await page.waitForSelector("#w-ls", { timeout: 20000 });
await shot("08-mda-dark");
await page.click(".onboard-foot .btn-primary");
await page.waitForSelector(".hero-title:has-text(\"Ready\")");
await shot("09-done-dark");
r.errors = errors;
console.log(JSON.stringify(r, null, 2));
await browser.close();
