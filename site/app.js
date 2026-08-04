"use strict";

const statusElements = {
  overall: document.querySelector("#overall-status"),
  appVersion: document.querySelector("#app-version"),
  masterVersion: document.querySelector("#master-version"),
  inventoryCount: document.querySelector("#inventory-count"),
  assetCount: document.querySelector("#asset-count"),
  integrity: document.querySelector("#integrity-status"),
  network: document.querySelector("#network-status"),
};

function setNetworkStatus() {
  statusElements.network.textContent = navigator.onLine ? "Online" : "Offline";
}

function toHex(buffer) {
  return Array.from(new Uint8Array(buffer), (value) => value.toString(16).padStart(2, "0")).join("");
}

async function fetchVerifiedJson(path, integrityIndex) {
  const response = await fetch(`./${path}`, { cache: "no-cache" });
  if (!response.ok) {
    throw new Error(`Datei nicht verfügbar: ${path} (${response.status})`);
  }
  const buffer = await response.arrayBuffer();
  const expected = integrityIndex.get(path);
  if (!expected) {
    throw new Error(`Integritätswert fehlt: ${path}`);
  }
  const actual = toHex(await crypto.subtle.digest("SHA-256", buffer));
  if (actual !== expected) {
    throw new Error(`Hashabweichung: ${path}`);
  }
  return JSON.parse(new TextDecoder("utf-8").decode(buffer));
}

async function initialize() {
  setNetworkStatus();
  window.addEventListener("online", setNetworkStatus);
  window.addEventListener("offline", setNetworkStatus);

  const integrityResponse = await fetch("./integrity.json", { cache: "no-cache" });
  if (!integrityResponse.ok) {
    throw new Error(`Integritätsmanifest nicht verfügbar (${integrityResponse.status})`);
  }
  const integrity = await integrityResponse.json();
  const integrityIndex = new Map(integrity.files.map((item) => [item.path, item.sha256]));

  const [version, inventory, assets, metadata] = await Promise.all([
    fetchVerifiedJson("data/version.json", integrityIndex),
    fetchVerifiedJson("data/inventory.json", integrityIndex),
    fetchVerifiedJson("data/assets.json", integrityIndex),
    fetchVerifiedJson("data/export-metadata.json", integrityIndex),
  ]);

  if (inventory.items.length !== metadata.counts.inventoryRecords) {
    throw new Error("Inventaranzahl stimmt nicht mit Exportmetadaten überein");
  }
  if (assets.items.length !== metadata.counts.assetRecords) {
    throw new Error("Assetanzahl stimmt nicht mit Exportmetadaten überein");
  }
  if (version.masterVersion !== inventory.masterVersion || version.masterVersion !== metadata.masterVersion) {
    throw new Error("Masterversion ist inkonsistent");
  }
  if (version.assetVersion !== assets.assetVersion || version.assetVersion !== metadata.assetVersion) {
    throw new Error("Assetversion ist inkonsistent");
  }

  statusElements.appVersion.textContent = version.appVersion;
  statusElements.masterVersion.textContent = `${version.masterVersion} · Assets ${version.assetVersion}`;
  statusElements.inventoryCount.textContent = String(inventory.items.length);
  statusElements.assetCount.textContent = String(assets.items.length);
  statusElements.integrity.textContent = "Bestanden";
  statusElements.overall.textContent = "Technisch bereit";
  statusElements.overall.dataset.state = "ok";
}

window.addEventListener("load", () => {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./service-worker.js", { scope: "./" }).catch((error) => {
      console.error("Service Worker konnte nicht registriert werden", error);
    });
  }
});

initialize().catch((error) => {
  console.error(error);
  statusElements.integrity.textContent = "Fehler";
  statusElements.overall.textContent = "Prüfung fehlgeschlagen";
  statusElements.overall.dataset.state = "error";
});
