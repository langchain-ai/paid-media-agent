// Offline first-run walkthrough. Run only against the throwaway console described in README.
// Usage: node tests/e2e/console_walkthrough.mjs "<console URL>" <screenshot directory>
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";
const [url, out] = process.argv.slice(2);
if (!url || !out) throw new Error("Pass the throwaway console URL and screenshot directory.");
await mkdir(out, { recursive: true });
const errors = [];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 900 }, reducedMotion: "reduce" });
page.on("pageerror", (error) => errors.push(String(error)));
try {
  await page.goto(url);
  await page.getByRole("button", { name: "Get started", exact: true }).waitFor();
  assert.equal(await page.getByRole("button", { name: /Try sample/ }).count(), 0);
  await page.screenshot({ path: `${out}/01-welcome.png`, fullPage: true });
  await page.getByRole("button", { name: "Get started", exact: true }).click();
  await page.getByRole("heading", { name: "Choose a model", exact: true }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Try the sample first", exact: true }).count(), 0);
  // A fresh throwaway project has no key. This must fail before any provider request.
  await page.getByRole("button", { name: "Test and continue", exact: true }).click();
  await page.locator("#model-status").getByText(/is not set/).waitFor();
  assert.match(page.url(), /step=model/);
  assert.equal(await page.getByRole("button", { name: "Continue", exact: true }).count(), 0);
  await page.screenshot({ path: `${out}/04-missing-key.png`, fullPage: true });
  // Reach deployment with fixture data; no real keys or deploy request are sent.
  const accounts = new URL(url);
  accounts.hash = "view=wizard&step=pipeboard";
  await page.goto(accounts.href);
  assert.equal(await page.getByRole("group", { name: "Ad platform integrations" }).getByRole("button").count(), 3);
  assert.deepEqual(await page.getByRole("list", { name: "Platforms provided by Pipeboard" }).getByRole("listitem").allTextContents(), ["Google Ads", "Meta Ads", "TikTok Ads", "Pinterest Ads", "Snap Ads", "Reddit Ads", "LinkedIn Ads", "Google Analytics"]);
  assert.equal(await page.getByRole("group", { name: "Direct connections", exact: true }).getByRole("button").count(), 2);
  // A direct platform returns to Accounts even when it is already the saved wizard step.
  await page.getByRole("button", { name: "Set up OpenAI Ads", exact: true }).click();
  await page.locator("#head-direct_openai_ads[aria-expanded='true']").waitFor();
  await page.getByRole("button", { name: "Back to accounts", exact: true }).click();
  await page.getByRole("heading", { name: "Connect ad accounts", exact: true }).waitFor();
  assert.match(page.url(), /view=wizard&step=pipeboard/);
  assert.equal(await page.getByRole("group", { name: "Ad platform integrations" }).getByRole("button").count(), 3);
  await page.getByRole("button", { name: "Use sample data", exact: true }).click();
  await page.getByRole("heading", { name: "Deploy your agent", exact: true }).waitFor();
  assert.match(page.url(), /step=deployment/);
  await page.getByRole("button", { name: /Managed Deep Agents/ }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Deploy agent", exact: true }).isEnabled(), false);
  assert.equal(await page.getByRole("button", { name: "Set up self-hosting", exact: true }).isVisible(), false);
  await page.getByRole("button", { name: /^Self-host Docker/ }).click();
  await page.getByRole("button", { name: "Set up self-hosting", exact: true }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Deploy agent", exact: true }).isVisible(), false);
  await page.getByRole("button", { name: /Managed Deep Agents/ }).click();
  // Switching paths keeps the mounted customization draft and live preview intact.
  await page.getByRole("heading", { name: "Agent settings", exact: true }).waitFor();
  assert.equal(await page.locator("#deployment-mda-action").evaluate(node => {
    const visible = [...node.parentElement.children].filter(child => !child.hidden);
    return visible.at(-1) === node;
  }), true);
  assert.equal(await page.getByRole("link", { name: "Create account ↗", exact: true }).getAttribute("href"), "https://smith.langchain.com");
  assert.equal(await page.getByRole("link", { name: "Choose a plan ↗", exact: true }).getAttribute("target"), "_blank");
  await page.getByText("Slack appearance", { exact: true }).click();
  await page.getByLabel("Name in Slack", { exact: true }).fill("Campaign Analyst");
  await page.getByRole("button", { name: /^Self-host Docker/ }).click();
  await page.getByRole("button", { name: /Managed Deep Agents/ }).click();
  assert.equal(await page.getByLabel("Name in Slack", { exact: true }).inputValue(), "Campaign Analyst");
  assert.match(await page.locator(".slack-preview").textContent(), /Campaign Analyst/);
  assert.equal(await page.getByRole("button", { name: "Save settings", exact: true }).count(), 0);
  // Polling must preserve focus and output disclosure while updating the action.
  let processState = { name: "mda-deploy", running: false, state: "stopped", command: "mda deploy", log_tail: "Old deployment output" };
  const processRequests = [];
  await page.route("**/api/status", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.result.detail.model = { provider: "scripted", package_installed: true };
    data.result.detail.model_key_env = null;
    data.result.detail.mda = { cli_installed: true, langsmith_key_set: true };
    data.processes = [processState];
    await route.fulfill({ json: data });
  });
  await page.route("**/api/processes/**", async (route) => {
    processRequests.push(new URL(route.request().url()).pathname);
    if (route.request().url().endsWith("/start")) {
      await route.fulfill({ status: 409, json: { detail: "Fixture preflight rejected" } });
      return;
    }
    processState = { ...processState, running: false, state: "completed", returncode: 0, log_tail: "Fixture deployment complete" };
    await route.fulfill({ json: { ok: true } });
  });
  await page.reload();
  await page.getByRole("button", { name: "Deploy agent", exact: true }).waitFor();
  assert.equal(await page.getByText("Deployment output", { exact: true }).isVisible(), false);
  processState = { ...processState, running: true, state: "active", log_tail: "Starting fixture deployment" };
  await page.reload();
  const controls = page.locator(".process-controls").filter({ has: page.getByRole("button", { name: "Cancel deployment", exact: true }) });
  await controls.locator("summary").click();
  await page.getByRole("button", { name: "Cancel deployment", exact: true }).focus();
  processState = { ...processState, state: "waiting_for_authorization", log_tail: "Authorize at https://slack.com/fixture" };
  await page.getByRole("button", { name: "Continue deployment", exact: true }).waitFor();
  assert.equal(await page.locator(":focus").textContent(), "Cancel deployment");
  assert.equal(await controls.locator("details").getAttribute("open"), "");
  await page.getByRole("button", { name: "Continue deployment", exact: true }).click();
  await page.getByRole("button", { name: "Deploy again", exact: true }).waitFor();
  assert.equal(await page.locator(":focus").textContent(), "Deploy again");
  await page.getByText("Slack appearance", { exact: true }).click();
  await page.getByLabel("Name in Slack", { exact: true }).fill("Campaign Analyst");
  await page.getByLabel("Weekly report", { exact: true }).selectOption("2");
  await page.getByLabel("Monthly report day", { exact: true }).selectOption("15");
  await page.getByLabel("Run at", { exact: true }).selectOption("09:15");
  const customizationSaved = page.waitForResponse((response) => response.url().endsWith("/api/config") && response.request().postDataJSON()?.updates?.PAID_MEDIA_SLACK_NAME === "Campaign Analyst");
  await Promise.all([
    page.waitForResponse((response) => response.url().endsWith("/api/processes/mda-deploy/start")),
    page.getByRole("button", { name: "Deploy again", exact: true }).click(),
  ]);
  const savedCustomization = await customizationSaved;
  assert.equal((await savedCustomization.json()).ok, true);
  assert.equal(savedCustomization.request().postDataJSON().updates.PAID_MEDIA_WEEKLY_REPORT_DAY, "2");
  assert.equal(savedCustomization.request().postDataJSON().updates.PAID_MEDIA_MONTHLY_REPORT_DAY, "15");
  assert.equal(savedCustomization.request().postDataJSON().updates.PAID_MEDIA_REPORT_TIME, "09:15");
  await page.getByRole("button", { name: "Retry deployment", exact: true }).waitFor();
  assert.equal(await page.locator("#deployment-mda-action").getByText("Deployment complete", { exact: true }).isVisible(), false);
  assert.deepEqual(processRequests, ["/api/processes/mda-deploy/continue", "/api/processes/mda-deploy/start"]);

  // Equal provider IDs on different platforms must remain independent rows.
  const discovered = [
    { platform: "google_ads", provider_account_id: "123", name: "Google fixture" },
    { platform: "meta_ads", provider_account_id: "123", name: "Meta fixture" },
  ];
  const mapped = [];
  await page.route("**/api/actions/pipeboard_test", (route) => route.fulfill({ json: { ok: true, status: "ok", summary: "Fixture connection" } }));
  await page.route("**/api/actions/accounts_discover", (route) => route.fulfill({ json: { ok: true, detail: { accounts: discovered } } }));
  await page.route("**/api/accounts", async (route) => { mapped.push(route.request().postDataJSON()); await route.fulfill({ json: { ok: true } }); });
  await page.goto(accounts.href);
  await page.getByRole("button", { name: "Set up Pipeboard", exact: true }).click();
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("checkbox", { name: /Google fixture/ }).click();
  const meta = page.getByRole("checkbox", { name: /Meta fixture/ });
  assert.equal(await meta.getAttribute("aria-checked"), "true");
  await page.getByLabel("Name for Meta fixture", { exact: true }).press("End");
  await page.getByLabel("Name for Meta fixture", { exact: true }).press("Space");
  assert.equal(await meta.getAttribute("aria-checked"), "true");
  await Promise.all([
    page.waitForResponse((response) => response.url().endsWith("/api/accounts")),
    page.getByRole("button", { name: "Save selected accounts", exact: true }).click(),
  ]);
  assert.equal(mapped.length, 1);
  assert.equal(mapped[0].platform, "meta_ads");
  assert.equal(mapped[0].alias, "meta-meta-fixture");
  await page.locator("#theme-toggle").click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${out}/05-mobile.png`, fullPage: true });
  assert.deepEqual(errors, []);
  console.log("Guided setup, missing key, deployment controls, independent accounts, and mobile layout passed.");
} finally {
  await browser.close();
}
