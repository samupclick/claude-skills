// Drives the quiz page with a site key configured and Turnstile's api.js served by a local stub (nothing reaches
// Cloudflare). Each widget hands out numbered tokens and a new one on reset, so the test can see which token each
// POST carried. Usage: node tests/browser_turnstile.mjs <url>. Prints one JSON line.
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const STUB = `window.turnstile = {
  widgets: {}, n: 0,
  render: function (selector, opts) {
    var id = "w" + (++this.n); this.widgets[id] = { opts: opts, issued: 0, selector: selector };
    this.issue(id); return id;
  },
  reset: function (id) { this.issue(id); },
  issue: function (id) {
    var w = this.widgets[id]; w.issued += 1; var token = "stub-" + id + "-" + w.issued;
    setTimeout(function () { w.opts.callback(token); }, 20);
  }
};`;

const url = process.argv[2];
const browser = await chromium.launch();
const page = await browser.newPage();
const posts = [];
const external = [];
await page.route("https://challenges.cloudflare.com/**", (route) =>
  route.fulfill({ status: 200, contentType: "application/javascript", body: STUB }));
page.on("request", (r) => {
  const u = new URL(r.url());
  if (u.origin !== new URL(url).origin && !u.href.startsWith("https://challenges.cloudflare.com/")) external.push(u.href);
  if (r.method() === "POST") posts.push({ path: u.pathname, token: JSON.parse(r.postData() || "{}").turnstile_token || null });
});
await page.goto(url);
await page.waitForSelector("#screen-consent:not([hidden])");
await page.waitForFunction(() => window.turnstile && Object.keys(window.turnstile.widgets).length === 1);
await page.waitForTimeout(100);
await page.click("#btn-start");
await page.waitForSelector("#screen-question:not([hidden])");
for (const opt of ["SaaS", "Paid ads", "No idea"]) {
  await page.click(`#question-options button[data-option="${opt}"]`);
}
await page.waitForSelector("#screen-contact:not([hidden])");
const contactWidgetShown = await page.waitForFunction(() => document.querySelector("#turnstile-box-contact") &&
  Object.values(window.turnstile.widgets).some((w) => w.selector === "#turnstile-box-contact")).then(() => true, () => false);
await page.waitForTimeout(100);
await page.fill("#contact-email", "not-an-email");
await page.click("#btn-submit");
await page.waitForSelector("#error-contact:not([hidden])");
await page.waitForTimeout(100);
await page.fill("#contact-email", "turnstile@example.com");
await page.click("#btn-submit");
await page.waitForSelector("#screen-done:not([hidden])");
await browser.close();
console.log(JSON.stringify({ posts, external, contact_widget: contactWidgetShown }));
