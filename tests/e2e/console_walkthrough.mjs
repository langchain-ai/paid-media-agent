// Headless walkthrough of the setup console. Run against a throwaway project copy; it writes
// .env and config/accounts.toml in the project the console serves.
// Usage: node tests/e2e/console_walkthrough.mjs "<console url with #token>" <screenshot dir>
import { chromium } from "playwright";
const url = process.argv[2]; const out = process.argv[3];
const errors = []; const results = {};
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1360, height: 900 } });
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(String(e)));
const shot = async (name) => page.waitForTimeout(350).then(() => page.screenshot({ path: `${out}/${name}.png`, fullPage: true }));
await page.goto(url, { waitUntil: "networkidle" });
await page.waitForSelector(".step", { timeout: 15000 });
results.title = await page.title();
results.rail = await page.$$eval(".rail-item", (els) => els.map((e) => e.textContent.trim()));
await shot("01-local-light");
// Local route: run the demo from step 2
await page.click(".step[data-step='demo'] .step-head");
await page.click(".step[data-step='demo'] .step-action button");
await page.waitForFunction(() => document.querySelector(".step[data-step='demo'] .step-result .badge")?.textContent, null, { timeout: 120000 });
results.demoBadge = await page.$eval(".step[data-step='demo'] .step-result .badge", (e) => e.textContent);
results.demoAnswer = (await page.$eval(".step[data-step='demo'] .step-result", (e) => e.textContent)).slice(0, 240);
await shot("02-local-demo-result");
// Save a model setting through the form (throwaway project only)
await page.click(".step[data-step='model'] .step-head");
await page.waitForSelector("#f-PAID_MEDIA_MODEL");
await page.fill("#f-PAID_MEDIA_MODEL", "anthropic:claude-sonnet-4-6");
await page.fill("#f-ANTHROPIC_API_KEY", "sk-ant-" + "x".repeat(30));
await page.click(".step[data-step='model'] form button[type=submit]");
await page.waitForFunction(() => document.querySelector(".step[data-step='model'] .step-result .badge")?.textContent, null, { timeout: 30000 });
results.modelSave = await page.$eval(".step[data-step='model'] .step-result .result-summary", (e) => e.textContent);
await page.waitForTimeout(600);
results.modelStatusAfter = await page.$eval(".step[data-step='model'] .step-status-text", (e) => e.textContent);
results.secretLeak = (await page.content()).includes("x".repeat(30));
await shot("03-local-model-saved");
// Pipeboard route: discover fixture accounts and map one
await page.click("text=Connect Pipeboard");
await page.waitForSelector(".step[data-step='pb_accounts']");
await page.click(".step[data-step='pb_accounts'] .step-head");
await page.click(".step[data-step='pb_accounts'] .step-action button");
await page.waitForSelector(".step[data-step='pb_accounts'] table.data", { timeout: 30000 });
results.discoveredRows = await page.$$eval(".step[data-step='pb_accounts'] table.data tbody tr", (rows) => rows.length);
results.mappedButtons = await page.$$eval(".step[data-step='pb_accounts'] table.data tbody button", (b) => b.map((x) => x.textContent));
await shot("04-pipeboard-accounts");
// Write gates: validate policy + kill switch
await page.click("text=Write gates");
await page.waitForSelector(".step[data-step='w_policy']");
await page.click(".step[data-step='w_policy'] .step-head");
await page.click(".step[data-step='w_policy'] .step-action button");
await page.waitForSelector(".step[data-step='w_policy'] .step-result .badge", { timeout: 30000 });
results.policy = await page.$eval(".step[data-step='w_policy'] .step-result .result-summary", (e) => e.textContent);
await page.click(".step[data-step='w_kill'] .step-head");
await page.click(".step[data-step='w_kill'] .btn-risk");
await page.waitForFunction(() => document.querySelector("#banner")?.textContent.includes("Kill switch engaged"), null, { timeout: 30000 });
results.killBanner = await page.$eval("#banner", (e) => e.textContent);
await shot("05-writes-kill-switch");
page.once("dialog", (d) => d.accept());
await page.click(".step[data-step='w_kill'] .btn-outline");
await page.waitForFunction(() => document.querySelector("#banner")?.hidden === true, null, { timeout: 30000 });
// MDA and self-host routes, dark theme
await page.click("text=Deploy to MDA");
await page.waitForSelector(".step[data-step='mda_check']");
await page.click(".step[data-step='mda_check'] .step-head");
await page.click(".step[data-step='mda_check'] .step-action button");
await page.waitForSelector(".step[data-step='mda_check'] .step-result .badge", { timeout: 120000 });
results.mda = await page.$eval(".step[data-step='mda_check'] .step-result .result-summary", (e) => e.textContent);
await page.click("#theme-toggle");
await shot("06-mda-dark");
await page.click("text=Self-host");
await page.waitForSelector(".step[data-step='sh_serve']");
await page.click(".step[data-step='sh_serve'] .step-head");
await shot("07-selfhost-dark");
results.processButtons = await page.$$eval(".step[data-step='sh_serve'] .form-actions button", (b) => b.map((x) => x.textContent));
await page.click("text=Slack (rich adapter)");
await page.waitForSelector(".step[data-step='sl_tokens']");
await page.click(".step[data-step='sl_tokens'] .step-head");
await page.waitForSelector("#f-SLACK_TRANSPORT");
await shot("08-slack-dark");
results.errors = errors;
console.log(JSON.stringify(results, null, 2));
await browser.close();
