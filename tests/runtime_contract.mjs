import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const site = path.join(root, "site");
const baseUrl = new URL("https://example.test/hausbar/");

function bytesFor(relativePath) {
  return fs.readFileSync(path.join(site, relativePath));
}

function normalizeRequest(input) {
  const raw = typeof input === "string" ? input : input.url;
  return new URL(raw, baseUrl).href;
}

function responseFor(input, networkOnline = true) {
  if (!networkOnline) {
    return Promise.reject(new Error("offline"));
  }
  const url = new URL(normalizeRequest(input));
  let relative = url.pathname.replace("/hausbar/", "");
  if (relative === "" || relative.endsWith("/")) {
    relative += "index.html";
  }
  const filePath = path.join(site, relative);
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    return Promise.resolve(new Response("not found", { status: 404 }));
  }
  return Promise.resolve(new Response(bytesFor(relative), { status: 200 }));
}

async function waitFor(predicate, timeoutMs = 5000) {
  const started = Date.now();
  while (!predicate()) {
    if (Date.now() - started > timeoutMs) {
      throw new Error("timeout waiting for runtime state");
    }
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

async function testAppRuntime() {
  const elements = new Map();
  for (const selector of [
    "#overall-status", "#app-version", "#master-version", "#inventory-count",
    "#asset-count", "#integrity-status", "#network-status",
  ]) {
    elements.set(selector, { textContent: "", dataset: {} });
  }
  const loadCallbacks = [];
  const context = {
    TextDecoder,
    console,
    crypto: crypto.webcrypto,
    document: { querySelector: (selector) => elements.get(selector) },
    fetch: async (request) => {
      const response = await responseFor(request, true);
      return response;
    },
    navigator: {
      onLine: true,
      serviceWorker: { register: async () => ({ scope: baseUrl.href }) },
    },
    setTimeout,
    clearTimeout,
    window: {
      addEventListener: (event, callback) => {
        if (event === "load") loadCallbacks.push(callback);
      },
    },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(site, "app.js"), "utf8"), context, { filename: "app.js" });
  for (const callback of loadCallbacks) callback();
  await waitFor(() => elements.get("#overall-status").textContent === "Technisch bereit");
  assert.equal(elements.get("#app-version").textContent, "v0.1.0-preview.1");
  assert.match(elements.get("#master-version").textContent, /^v7\.66/);
  assert.equal(elements.get("#inventory-count").textContent, "142");
  assert.equal(elements.get("#asset-count").textContent, "154");
  assert.equal(elements.get("#integrity-status").textContent, "Bestanden");
}

async function testServiceWorkerOfflineContract() {
  const handlers = new Map();
  const cacheStores = new Map();
  let networkOnline = true;

  const normalize = (input) => normalizeRequest(input);
  const cachesMock = {
    async open(name) {
      if (!cacheStores.has(name)) cacheStores.set(name, new Map());
      const store = cacheStores.get(name);
      return {
        async addAll(urls) {
          for (const url of urls) {
            const response = await responseFor(url, networkOnline);
            if (!response.ok) throw new Error(`precache failed: ${url}`);
            store.set(normalize(url), response.clone());
          }
        },
        async put(request, response) {
          store.set(normalize(request), response.clone());
        },
      };
    },
    async keys() { return [...cacheStores.keys()]; },
    async delete(name) { return cacheStores.delete(name); },
    async match(request) {
      const key = normalize(request);
      for (const store of cacheStores.values()) {
        if (store.has(key)) return store.get(key).clone();
      }
      return undefined;
    },
  };

  const context = {
    URL,
    caches: cachesMock,
    fetch: (request) => responseFor(request, networkOnline),
    self: {
      location: { origin: baseUrl.origin },
      addEventListener: (event, callback) => handlers.set(event, callback),
      skipWaiting: async () => undefined,
      clients: { claim: async () => undefined },
    },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(site, "service-worker.js"), "utf8"), context, { filename: "service-worker.js" });

  let installPromise;
  handlers.get("install")({ waitUntil: (promise) => { installPromise = promise; } });
  await installPromise;

  let activatePromise;
  handlers.get("activate")({ waitUntil: (promise) => { activatePromise = promise; } });
  await activatePromise;

  const inventory = JSON.parse(fs.readFileSync(path.join(site, "data/inventory.json"), "utf8"));
  const imagePath = inventory.items[0].bilder.haupt;
  const onlineImageRequest = { method: "GET", mode: "no-cors", url: new URL(imagePath, baseUrl).href };
  let imageResponsePromise;
  handlers.get("fetch")({ request: onlineImageRequest, respondWith: (promise) => { imageResponsePromise = promise; } });
  const onlineImageResponse = await imageResponsePromise;
  assert.equal(onlineImageResponse.status, 200);

  networkOnline = false;
  let offlineImagePromise;
  handlers.get("fetch")({ request: onlineImageRequest, respondWith: (promise) => { offlineImagePromise = promise; } });
  const offlineImageResponse = await offlineImagePromise;
  assert.equal(offlineImageResponse.status, 200);

  const navigationRequest = { method: "GET", mode: "navigate", url: new URL("missing-route", baseUrl).href };
  let navigationPromise;
  handlers.get("fetch")({ request: navigationRequest, respondWith: (promise) => { navigationPromise = promise; } });
  const navigationResponse = await navigationPromise;
  assert.equal(navigationResponse.status, 200);
  assert.match(await navigationResponse.text(), /Murats Hausbar/);
}

await testAppRuntime();
await testServiceWorkerOfflineContract();
console.log(JSON.stringify({ status: "PASS", tests: ["app-runtime-integrity", "service-worker-offline"] }));
