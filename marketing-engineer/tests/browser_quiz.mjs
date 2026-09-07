// Drives the quiz page in headless Chromium (node playwright). Usage: node tests/browser_quiz.mjs <url>
// Prints one JSON line: request paths made before Start, every request URL, the lead id, the final screen.
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const url = process.argv[2];
const origin = new URL(url).origin;
const browser = await chromium.launch();
const page = await browser.newPage();
const all = [];
let leadId = null;
page.on("request", (r) => all.push(r.url()));
page.on("response", async (r) => {
  if (r.request().method() === "POST" && new URL(r.url()).pathname === "/quiz/start") {
    try { leadId = (await r.json()).lead_id; } catch (e) { /* non-JSON error body */ }
  }
});
await page.goto(url);
await page.waitForSelector("#screen-consent:not([hidden])");
const before = all.filter((u) => u.startsWith(origin)).map((u) => new URL(u).pathname);

await page.check("#consent-tracking");
await page.click("#btn-start");
await page.waitForSelector("#screen-question:not([hidden])");
for (const opt of ["SaaS", "Paid ads", "No idea"]) {
  await page.click(`#question-options button[data-option="${opt}"]`);
}
await page.waitForSelector("#screen-contact:not([hidden])");
await page.fill("#contact-name", "Browser Test");
await page.fill("#contact-email", "browser@example.com");
await page.click("#btn-submit");
await page.waitForSelector("#screen-done:not([hidden])");
const doneState = await page.getAttribute("#quiz", "data-state");
const bookHidden = await page.getAttribute("#btn-book", "hidden");
await browser.close();
console.log(JSON.stringify({ requests_before_start: before, all_requests: all, done_state: doneState, lead_id: leadId, book_link_shown: bookHidden === null }));
