// Week 12: capture the REAL React UI against disposable, synthetic demo data.
// Install Playwright + Chromium in development tooling before running this script.
const { chromium } = require("playwright");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");
const root = path.resolve(__dirname, "..");
const erp = path.join(root, "services/erp-core");
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "stockpilot-demo-"));
const python = process.env.DEMO_PYTHON ?? path.join(erp, ".venv/bin/python");
const env = { ...process.env, DATABASE_URL: `sqlite:///${temp}/demo.sqlite3`,
  AUTH_MODE: "legacy", DJANGO_DEBUG: "true", STOCKPILOT_PRODUCTION: "false",
  VITE_AUTH_MODE: "legacy", VITE_API_URL: "http://localhost:18000/api/v1",
  CORS_ALLOWED_ORIGINS: "http://localhost:15173", DJANGO_ALLOWED_HOSTS: "localhost,127.0.0.1" };
const output = path.join(root, "docs");
fs.mkdirSync(path.join(output, "screenshots"), { recursive: true });
const children = [];
let browser, context;
async function main() {
  for (const command of ["migrate", "seed_week8"]) {
    const result = spawnSync(python, ["manage.py", command], { cwd: erp, env, encoding: "utf8" });
    if (result.status !== 0) throw new Error(result.stderr || `Failed ${command}`);
  }
  children.push(spawn(python, ["manage.py", "runserver", "127.0.0.1:18000", "--noreload"], { cwd: erp, env, stdio: "ignore" }));
  children.push(spawn("node", ["node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "15173", "--strictPort"], {
    cwd: path.join(root, "apps/web"), env, stdio: "ignore",
  }));
  for (const url of ["http://127.0.0.1:18000/api/v1/health/", "http://127.0.0.1:15173"]) {
    let ready = false;
    for (let i = 0; i < 100; i++) {
      try { if ((await fetch(url)).ok) { ready = true; break; } } catch {}
      await new Promise(resolve => setTimeout(resolve, 200));
    }
    if (!ready) throw new Error("Demo service did not become ready");
  }
  browser = await chromium.launch({ headless: true,
    ...(process.env.DEMO_CHROMIUM ? { executablePath: process.env.DEMO_CHROMIUM } : {}) });
  context = await browser.newContext({ viewport: { width: 1440, height: 1050 },
    recordVideo: { dir: temp, size: { width: 1440, height: 1050 } } });
  const page = await context.newPage();
  await page.goto("http://localhost:15173");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("tab", { name: "Plugins", exact: true }).waitFor();
  await page.screenshot({ path: path.join(output, "screenshots/overview.png"), fullPage: true });
  await page.getByRole("tab", { name: "Plugins", exact: true }).click();
  await page.getByRole("button", { name: "Install", exact: true }).click();
  await page.getByText("Installed 1.0.0, revision 1", { exact: true }).waitFor();
  await page.screenshot({ path: path.join(output, "screenshots/plugin-installed.png"), fullPage: true });
  await page.getByLabel("Catalog version").click();
  await page.getByRole("option", { name: /1.1.0/ }).click();
  await page.getByRole("button", { name: "Update", exact: true }).click();
  await page.getByText("Installed 1.1.0, revision 2", { exact: true }).waitFor();
  await page.screenshot({ path: path.join(output, "screenshots/plugin-updated.png"), fullPage: true });
  await page.getByLabel("Rollback to revision").click();
  await page.getByRole("option", { name: /Revision 1:/ }).click();
  await page.getByRole("button", { name: "Restore selected revision" }).click();
  await page.getByText("Installed 1.0.0, revision 3", { exact: true }).waitFor();
  await page.screenshot({ path: path.join(output, "screenshots/plugin-rollback.png"), fullPage: true });
  const video = page.video();
  await context.close(); context = null;
  await video.saveAs(path.join(output, "plugin-walkthrough.webm"));
  console.log("Browser install/update/rollback passed; real screenshots and recording saved.");
}
main().catch(error => { console.error(error.message); process.exitCode = 1; }).finally(async () => {
  if (context) await context.close();
  if (browser) await browser.close();
  for (const child of children) child.kill("SIGTERM");
  // Only this script's unique temporary directory is removed.
  fs.rmSync(temp, { recursive: true, force: true });
});
