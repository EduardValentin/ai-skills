import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const CACHE_EXECUTABLES = new Set([
  "chrome-headless-shell",
  "headless_shell",
  "Chromium",
  "Google Chrome for Testing",
  "chrome",
  "chrome.exe",
  "chrome-headless-shell.exe",
]);

function playwrightCacheRoots() {
  const home = os.homedir();
  return [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    path.join(home, "Library", "Caches", "ms-playwright"),
    path.join(home, ".cache", "ms-playwright"),
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, "ms-playwright"),
  ].filter(Boolean);
}

function findInCache(directory, depth = 0) {
  if (depth > 6) return null;
  let entries;
  try {
    entries = fs.readdirSync(directory, { withFileTypes: true });
  } catch {
    return null;
  }
  const newestFirst = entries.sort((x, y) => y.name.localeCompare(x.name, undefined, { numeric: true }));
  for (const entry of newestFirst) {
    const full = path.join(directory, entry.name);
    if (entry.isFile() && CACHE_EXECUTABLES.has(entry.name)) return full;
    if (entry.isDirectory() && (depth > 0 || entry.name.startsWith("chromium"))) {
      const found = findInCache(full, depth + 1);
      if (found) return found;
    }
  }
  return null;
}

function systemBrowsers() {
  if (process.platform === "darwin") {
    return ["Google Chrome", "Chromium", "Microsoft Edge", "Brave Browser"].map(
      (name) => `/Applications/${name}.app/Contents/MacOS/${name}`,
    );
  }
  if (process.platform === "win32") {
    return [process.env.PROGRAMFILES, process.env["PROGRAMFILES(X86)"], process.env.LOCALAPPDATA]
      .filter(Boolean)
      .flatMap((root) => [
        path.join(root, "Google", "Chrome", "Application", "chrome.exe"),
        path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
      ]);
  }
  return ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"]
    .map((name) => spawnSync("which", [name], { encoding: "utf8" }).stdout.trim())
    .filter(Boolean);
}

export function findBrowser() {
  const explicit = process.env.UX_AUDIT_BROWSER || process.env.CHROME_PATH;
  if (explicit) return explicit;
  const system = systemBrowsers().find((candidate) => fs.existsSync(candidate));
  if (system) return system;
  for (const root of playwrightCacheRoots()) {
    const cached = findInCache(root);
    if (cached) return cached;
  }
  throw new Error(
    "no Chromium-based browser found: install Chrome, run `npx playwright install chromium`, or set UX_AUDIT_BROWSER",
  );
}

export function toPageUrl(input) {
  if (/^https?:\/\//i.test(input) || input.startsWith("file://")) return input;
  const resolved = path.resolve(input);
  if (!fs.existsSync(resolved)) throw new Error(`input not found: ${input}`);
  return pathToFileURL(resolved).href;
}

class Page {
  constructor(connection, sessionId) {
    this.connection = connection;
    this.sessionId = sessionId;
  }

  send(method, params = {}) {
    return this.connection.send(method, params, this.sessionId);
  }

  setViewport(width, height) {
    return this.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
  }

  async navigate(url, wait = "networkidle", timeoutMs = 30000) {
    const awaited = wait === "networkidle" ? "networkIdle" : "load";
    let navigation = null;
    const settled = this.connection.waitForEvent(
      this.sessionId,
      (event) =>
        event.method === "Page.lifecycleEvent" &&
        event.params.name === awaited &&
        navigation !== null &&
        event.params.loaderId === navigation.loaderId,
      timeoutMs,
    );
    settled.catch(() => {});
    navigation = await this.send("Page.navigate", { url });
    if (navigation.errorText) throw new Error(`navigation failed for ${url}: ${navigation.errorText}`);
    await settled;
    if (typeof wait === "number") await new Promise((resolve) => setTimeout(resolve, wait));
  }

  async evaluate(pageFunction, argument) {
    const expression = `(${pageFunction})(${JSON.stringify(argument ?? null)})`;
    const { result, exceptionDetails } = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (exceptionDetails) {
      throw new Error(`page evaluation failed: ${exceptionDetails.exception?.description ?? exceptionDetails.text}`);
    }
    return result.value;
  }

  async accessibleName(elementExpression) {
    const { result } = await this.send("Runtime.evaluate", { expression: elementExpression });
    if (!result.objectId) return "";
    const { nodes } = await this.send("Accessibility.getPartialAXTree", {
      objectId: result.objectId,
      fetchRelatives: false,
    });
    return nodes?.[0]?.name?.value ?? "";
  }
}

class Connection {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Set();
    socket.addEventListener("message", (message) => this.receive(JSON.parse(message.data)));
  }

  receive(payload) {
    if (payload.id === undefined) {
      for (const listener of this.listeners) listener(payload);
      return;
    }
    const waiter = this.pending.get(payload.id);
    this.pending.delete(payload.id);
    if (payload.error) waiter.reject(new Error(`${waiter.method}: ${payload.error.message}`));
    else waiter.resolve(payload.result);
  }

  send(method, params, sessionId) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject, method });
      this.socket.send(JSON.stringify({ id, method, params, sessionId }));
    });
  }

  waitForEvent(sessionId, matches, timeoutMs) {
    return new Promise((resolve, reject) => {
      const listener = (event) => {
        if (event.sessionId !== sessionId || !matches(event)) return;
        clearTimeout(timer);
        this.listeners.delete(listener);
        resolve(event);
      };
      const timer = setTimeout(() => {
        this.listeners.delete(listener);
        reject(new Error(`timed out after ${timeoutMs} ms waiting for the page`));
      }, timeoutMs);
      this.listeners.add(listener);
    });
  }
}

function debuggerEndpoint(child) {
  return new Promise((resolve, reject) => {
    let stderr = "";
    const timer = setTimeout(() => reject(new Error(`browser did not start: ${stderr.slice(-400)}`)), 20000);
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
      const match = stderr.match(/DevTools listening on (ws:\/\/\S+)/);
      if (!match) return;
      clearTimeout(timer);
      resolve(match[1]);
    });
    child.once("error", reject);
    child.once("exit", (code) => reject(new Error(`browser exited with code ${code}: ${stderr.slice(-400)}`)));
  });
}

export async function launchBrowser() {
  if (typeof WebSocket === "undefined") throw new Error("Node.js 22 or newer is required");
  const executable = findBrowser();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "ux-audit-"));
  const flags = [
    "--headless",
    "--remote-debugging-port=0",
    `--user-data-dir=${profile}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-gpu",
    "--hide-scrollbars",
    "--allow-file-access-from-files",
  ];
  if (process.getuid?.() === 0) flags.push("--no-sandbox");
  const child = spawn(executable, [...flags, "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
  let socket;
  try {
    socket = new WebSocket(await debuggerEndpoint(child));
    await new Promise((resolve, reject) => {
      socket.addEventListener("open", resolve, { once: true });
      socket.addEventListener("error", () => reject(new Error("could not connect to the browser")), { once: true });
    });
  } catch (error) {
    child.kill("SIGKILL");
    fs.rmSync(profile, { recursive: true, force: true });
    throw error;
  }
  const connection = new Connection(socket);
  const { product } = await connection.send("Browser.getVersion", {});

  return {
    product,
    async newPage() {
      const { targetId } = await connection.send("Target.createTarget", { url: "about:blank" });
      const { sessionId } = await connection.send("Target.attachToTarget", { targetId, flatten: true });
      const page = new Page(connection, sessionId);
      await page.send("Page.enable");
      await page.send("Page.setLifecycleEventsEnabled", { enabled: true });
      await page.send("Runtime.enable");
      await page.send("DOM.enable");
      await page.send("Accessibility.enable");
      await page.send("Emulation.setFocusEmulationEnabled", { enabled: true });
      return page;
    },
    async close() {
      child.removeAllListeners("exit");
      socket.close();
      child.kill();
      await new Promise((resolve) => child.once("exit", resolve));
      fs.rmSync(profile, { recursive: true, force: true, maxRetries: 3 });
    },
  };
}
