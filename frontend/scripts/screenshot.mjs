/**
 * Headless-Chrome screenshot harness (raw CDP, no puppeteer dependency).
 *
 * Launches the system Chrome with remote debugging, logs in through the real
 * login form (typed + submitted via CDP), waits for the dashboard, then
 * captures every main page plus the rooms create modal.
 *
 * Requires: backend on :8000 (CORS covers :3000/:3001), this frontend running.
 *
 * Usage:
 *   node scripts/screenshot.mjs [out-dir]
 */
import { spawn } from "child_process";
import { mkdirSync, writeFileSync } from "fs";
import { resolve } from "path";

const FRONT = process.env.FRONT_URL || "http://localhost:3001";
const API = process.env.API_URL || "http://localhost:8000";
const EMAIL = process.env.ADMIN_EMAIL || "admin@example.com";
const PASSWORD = process.env.ADMIN_PASSWORD || "admin123";
const CHROME = process.env.CHROME_PATH || "/usr/bin/google-chrome-stable";
const CDP_PORT = 9222;

const OUT = resolve(process.argv[2] || "/tmp/opencode/shots");
mkdirSync(OUT, { recursive: true });

const PAGES = [
  ["dashboard", "/dashboard"],
  ["rooms", "/rooms"],
  ["faculty", "/faculty"],
  ["groups", "/groups"],
  ["subjects", "/subjects"],
  ["assignments", "/assignments"],
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const chrome = spawn(CHROME, [
    "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
    "--window-size=1440,900", "--remote-debugging-port=" + CDP_PORT,
    "--user-data-dir=/tmp/opencode/chrome-profile", "about:blank",
  ], { stdio: "ignore" });
  await sleep(2500);

  const targets = await (await fetch(`http://localhost:${CDP_PORT}/json`)).json();
  const page = targets.find((t) => t.type === "page");
  if (!page) throw new Error("no page target");

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let msgId = 0;
  const pending = new Map();
  const send = (method, params = {}) => {
    const id = ++msgId;
    ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolveMsg) => pending.set(id, resolveMsg));
  };
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); }
  };
  await new Promise((r) => { ws.onopen = r; });

  const evalJs = async (expression) => {
    const res = await send("Runtime.evaluate", { expression, returnByValue: true });
    return res && res.result ? res.result.value : undefined;
  };

  await send("Page.enable");

  // --- login page ---
  await send("Page.navigate", { url: `${FRONT}/login` });
  await sleep(3500);
  {
    const shot = await send("Page.captureScreenshot", { format: "png" });
    writeFileSync(resolve(OUT, "login.png"), Buffer.from(shot.data, "base64"));
    console.log("saved login");
  }

  // --- real login via form ---
  await send("Page.navigate", { url: `${FRONT}/login` });
  await sleep(3000);
  await evalJs(`
    (() => {
      const set = (sel, v) => {
        const el = document.querySelector(sel);
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, v);
        el.dispatchEvent(new Event('input', { bubbles: true }));
      };
      set('input[type=email]', ${JSON.stringify(EMAIL)});
      set('input[type=password]', ${JSON.stringify(PASSWORD)});
      document.querySelector('button[type=submit]').click();
      return 'submitted';
    })()
  `);
  // wait for dashboard (client-side redirect)
  for (let i = 0; i < 30; i++) {
    await sleep(500);
    const url = await evalJs("window.location.pathname");
    if (url === "/dashboard") break;
  }
  await sleep(1500);
  console.log("logged in ->", await evalJs("window.location.pathname"));

  const shot = async (name) => {
    await sleep(2500); // let client-side fetch settle
    const res = await send("Page.captureScreenshot", { format: "png" });
    writeFileSync(resolve(OUT, `${name}.png`), Buffer.from(res.data, "base64"));
    console.log("saved", name);
  };

  for (const [name, path] of PAGES) {
    await send("Page.navigate", { url: `${FRONT}${path}` });
    await shot(name);
  }

  // scheduling pages — need a seeded generation/instances to be meaningful
  const instList = await fetch(`${API}/api/v1/instances?limit=3`, {
    headers: { Authorization: `Bearer ${await evalJs("localStorage.getItem('timetable_token')")}` },
  }).then((r) => r.json()).catch(() => []);
  if (Array.isArray(instList) && instList.length >= 2) {
    await send("Page.navigate", { url: `${FRONT}/instances` });
    await shot("instances");
    await send("Page.navigate", { url: `${FRONT}/instances/${instList[0].id}` });
    await shot("instance-detail");
    await send("Page.navigate", { url: `${FRONT}/instances/compare?a=${instList[0].id}&b=${instList[1].id}` });
    await shot("instance-compare");
  } else {
    console.log("no instances to capture; skip scheduling pages");
  }
  await send("Page.navigate", { url: `${FRONT}/exports` });
  await shot("exports");

  // rooms modal
  await send("Page.navigate", { url: `${FRONT}/rooms` });
  await sleep(2500);
  const clicked = await evalJs(`
    (() => {
      const b = Array.from(document.querySelectorAll('button')).find(
        (x) => x.textContent && x.textContent.trim().includes('Add room'));
      if (b) { b.click(); return true; }
      return false;
    })()
  `);
  if (clicked) {
    await sleep(1000);
    await shot("rooms-modal");
  } else {
    console.log("no Add-room button");
  }

  ws.close();
  chrome.kill();
  console.log("done");
}

main().catch((e) => { console.error(e); process.exit(1); });
