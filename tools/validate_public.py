#!/usr/bin/env python3
"""Validate the generated public Hausbar site with the locked private toolchain."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from check_environment import EnvironmentContractError, verify_environment

try:
    from PIL import Image
except ModuleNotFoundError:
    Image = None

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"

PRODUCT_KEYS = {
    "alkohol", "beschreibung", "bestand", "bilder", "flasche",
    "geschmacksTags", "herkunft", "hersteller", "id", "kategorie",
    "logik", "name", "nr", "nutzungsTags", "unterkategorie",
}
ALCOHOL_KEYS = {"prozent", "status"}
STOCK_KEYS = {"aktiv", "anzahl", "einheit", "fuellstand", "mengeText", "oeffnungsstatus", "statusCode"}
IMAGE_KEYS = {"haupt", "zusatz"}
BOTTLE_KEYS = {"groesseMl"}
LOGIC_KEYS = {
    "appFilterPrimaer", "appFilterSekundaer", "cocktailRelevanz", "cocktailrolle",
    "empfohleneCocktailtypen", "flavorPrimaer", "flavorSekundaer",
    "gastmodusRelevanz", "mixerGarnishSirupAbgrenzung", "produktart",
}
ASSET_KEYS = {"breitePixel", "dateigroesseByte", "hoehePixel", "id", "mimeTyp", "pfad", "rolle", "sha256"}
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^csv-\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*$")
SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


class ValidationError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValidationError(f"{label} keys mismatch: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")


def nested_get(value: dict[str, Any], dotted: str) -> Any:
    current: Any = value
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ValidationError(f"Missing protected path {dotted}")
        current = current[part]
    return current


def recursive_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            found.add(key)
            found.update(recursive_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(recursive_keys(child))
    return found


def validate_runtime_files(site: Path) -> None:
    required = [
        "index.html", "styles.css", "app.js", "manifest.webmanifest", "service-worker.js", ".nojekyll",
        "data/version.json", "data/inventory.json", "data/assets.json", "data/export-metadata.json",
        "assets/icons/icon-192.png", "assets/icons/icon-512.png", "assets/icons/apple-touch-icon.png",
        "schemas/inventory.schema.json", "schemas/assets.schema.json", "schemas/export-metadata.schema.json", "schemas/version.schema.json",
    ]
    missing = [path for path in required if not (site / path).is_file()]
    if missing:
        raise ValidationError(f"Missing public files: {missing}")


def validate_version(site: Path) -> dict[str, Any]:
    config = load_json(CONFIG_DIR / "app-version.json")
    version = load_json(site / "data/version.json")
    expected = {"schemaVersion": 1, **config}
    if version != expected:
        raise ValidationError("Public version.json differs from the single version source")
    cache_slug = re.sub(r"[^a-z0-9.-]+", "-", config["appVersion"].lower()).strip("-")
    service_worker = (site / "service-worker.js").read_text(encoding="utf-8")
    expected_cache = f'const CACHE_NAME = "hausbar-app-{cache_slug}";'
    if expected_cache not in service_worker:
        raise ValidationError("Service worker cache version is not derived from app-version.json")
    return version


def validate_inventory(site: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    inventory = load_json(site / "data/inventory.json")
    assets = load_json(site / "data/assets.json")
    metadata = load_json(site / "data/export-metadata.json")
    regression = load_json(CONFIG_DIR / "regression-cases.json")
    allowlist = load_json(CONFIG_DIR / "public-field-allowlist.json")

    assert_exact_keys(inventory, {"items", "masterVersion", "schemaVersion"}, "inventory root")
    assert_exact_keys(assets, {"assetVersion", "items", "schemaVersion"}, "assets root")
    if inventory["schemaVersion"] != 1 or assets["schemaVersion"] != 1:
        raise ValidationError("Unexpected public schema version")

    expected = regression["expected"]
    products = inventory["items"]
    asset_items = assets["items"]
    if len(products) != expected["inventoryRecords"]:
        raise ValidationError(f"Inventory count mismatch: {len(products)}")
    if len(asset_items) != expected["assetRecords"]:
        raise ValidationError(f"Asset count mismatch: {len(asset_items)}")
    if metadata["counts"] != {
        "additionalAssets": expected["additionalAssets"],
        "assetRecords": expected["assetRecords"],
        "inventoryRecords": expected["inventoryRecords"],
        "primaryAssets": expected["primaryAssets"],
    }:
        raise ValidationError("Export metadata counts mismatch")
    if metadata["historicalAppUsedAsInput"] is not False:
        raise ValidationError("Historical app must not be used as Phase-1 input")
    if metadata["policy"]["mode"] != "DENY_BY_DEFAULT" or metadata["policy"]["privateFieldsSerialized"] != 0:
        raise ValidationError("Public export policy is not deny-by-default")

    product_ids: set[str] = set()
    product_numbers: set[int] = set()
    product_names: set[str] = set()
    by_id: dict[str, dict[str, Any]] = {}
    previous_nr = 0
    all_public_keys: set[str] = set()

    asset_by_path = {item["pfad"]: item for item in asset_items}
    if len(asset_by_path) != len(asset_items):
        raise ValidationError("Duplicate public asset path")

    for index, product in enumerate(products):
        assert_exact_keys(product, PRODUCT_KEYS, f"product[{index}]")
        assert_exact_keys(product["alkohol"], ALCOHOL_KEYS, f"product[{index}].alkohol")
        assert_exact_keys(product["bestand"], STOCK_KEYS, f"product[{index}].bestand")
        assert_exact_keys(product["bilder"], IMAGE_KEYS, f"product[{index}].bilder")
        assert_exact_keys(product["flasche"], BOTTLE_KEYS, f"product[{index}].flasche")
        assert_exact_keys(product["logik"], LOGIC_KEYS, f"product[{index}].logik")
        all_public_keys.update(recursive_keys(product))

        product_id = product["id"]
        if not ID_RE.fullmatch(product_id):
            raise ValidationError(f"Invalid product ID: {product_id}")
        if product_id in product_ids:
            raise ValidationError(f"Duplicate product ID: {product_id}")
        product_ids.add(product_id)
        by_id[product_id] = product

        nr = product["nr"]
        if not isinstance(nr, int) or nr <= previous_nr:
            raise ValidationError("Inventory is not strictly ordered by visible number")
        previous_nr = nr
        if nr in product_numbers:
            raise ValidationError(f"Duplicate visible number: {nr}")
        product_numbers.add(nr)
        if product["name"] in product_names:
            raise ValidationError(f"Duplicate product name: {product['name']}")
        product_names.add(product["name"])

        if not product["beschreibung"].strip():
            raise ValidationError(f"Missing visible description: {product_id}")
        if product["kategorie"] == "Whiskey" or "Whiskey" in product["kategorie"]:
            raise ValidationError(f"Non-canonical whisky category: {product_id}")
        if not isinstance(product["geschmacksTags"], list) or not product["geschmacksTags"]:
            raise ValidationError(f"Missing visible flavor tags: {product_id}")
        if not isinstance(product["nutzungsTags"], list) or not product["nutzungsTags"]:
            raise ValidationError(f"Missing visible usage tags: {product_id}")

        main_path = product["bilder"]["haupt"]
        if main_path not in asset_by_path or asset_by_path[main_path]["rolle"] != "haupt":
            raise ValidationError(f"Primary image mismatch for {product_id}")
        if asset_by_path[main_path]["id"] != product_id:
            raise ValidationError(f"Primary image ID mismatch for {product_id}")
        if not Path(main_path).name.startswith(product_id + "__"):
            raise ValidationError(f"Primary image path is not ID-based for {product_id}")
        for additional_path in product["bilder"]["zusatz"]:
            if additional_path not in asset_by_path or asset_by_path[additional_path]["rolle"] != "zusatz":
                raise ValidationError(f"Additional image mismatch for {product_id}: {additional_path}")
            if asset_by_path[additional_path]["id"] != product_id:
                raise ValidationError(f"Additional image ID mismatch for {product_id}")

    if len(product_ids) != expected["uniqueProductIds"]:
        raise ValidationError("Unique product ID count mismatch")
    if not any(product["kategorie"] == "Whisky" for product in products):
        raise ValidationError("Canonical category Whisky is missing")

    forbidden_keys = set(allowlist["sourceFieldsForbiddenInPublicBuild"])
    if forbidden_keys & all_public_keys:
        raise ValidationError(f"Forbidden private keys in public products: {sorted(forbidden_keys & all_public_keys)}")
    legacy_forbidden = {"tags", "barrolle", "bestUse", "servieren", "sourceLinks", "korrekturNotiz"}
    lowered = {key.casefold() for key in all_public_keys}
    if {key.casefold() for key in legacy_forbidden} & lowered:
        raise ValidationError("Forbidden legacy or internal public key detected")

    for index, asset in enumerate(asset_items):
        assert_exact_keys(asset, ASSET_KEYS, f"asset[{index}]")
        if asset["id"] not in product_ids:
            raise ValidationError(f"Asset references unknown product: {asset['id']}")
        if asset["rolle"] not in {"haupt", "zusatz"}:
            raise ValidationError(f"Invalid asset role: {asset['rolle']}")
        if asset["mimeTyp"] != "image/jpeg" or not HEX64_RE.fullmatch(asset["sha256"]):
            raise ValidationError(f"Invalid asset metadata: {asset['pfad']}")
        file_path = site / asset["pfad"]
        if not file_path.is_file():
            raise ValidationError(f"Missing physical asset: {asset['pfad']}")
        if file_path.stat().st_size != asset["dateigroesseByte"]:
            raise ValidationError(f"Asset byte size mismatch: {asset['pfad']}")
        if sha256_file(file_path) != asset["sha256"]:
            raise ValidationError(f"Asset hash mismatch: {asset['pfad']}")
        with Image.open(file_path) as image:
            if image.format != "JPEG" or image.size != (asset["breitePixel"], asset["hoehePixel"]):
                raise ValidationError(f"Asset image metadata mismatch: {asset['pfad']}")
        if not Path(asset["pfad"]).name.startswith(asset["id"] + "__"):
            raise ValidationError(f"Asset filename is not ID-based: {asset['pfad']}")

    physical_assets = sorted(
        path.relative_to(site).as_posix()
        for path in (site / "assets/images/inventory").glob("*.jpg")
    )
    if physical_assets != sorted(asset_by_path):
        raise ValidationError("Physical asset set differs from public asset manifest")

    primary_count = sum(item["rolle"] == "haupt" for item in asset_items)
    additional_count = sum(item["rolle"] == "zusatz" for item in asset_items)
    if primary_count != expected["primaryAssets"] or additional_count != expected["additionalAssets"]:
        raise ValidationError("Primary/additional asset count mismatch")

    for case in regression["protectedCases"]:
        product = by_id.get(case["id"])
        if product is None:
            raise ValidationError(f"Protected product missing: {case['id']}")
        for dotted, expected_value in case["assert"].items():
            actual = nested_get(product, dotted)
            if actual != expected_value:
                raise ValidationError(
                    f"Protected case mismatch {case['id']} {dotted}: expected {expected_value!r}, got {actual!r}"
                )

    return inventory, assets, metadata


def validate_privacy(site: Path) -> None:
    allowlist = load_json(CONFIG_DIR / "public-field-allowlist.json")
    private_terms = allowlist["sourceFieldsForbiddenInPublicBuild"] + allowlist["assetFieldsForbiddenInPublicBuild"]
    data_text = "\n".join(
        (site / relative).read_text(encoding="utf-8")
        for relative in ["data/inventory.json", "data/assets.json", "data/export-metadata.json"]
    )
    leaked = [term for term in private_terms if f'"{term}"' in data_text]
    if leaked:
        raise ValidationError(f"Private source fields leaked into public data: {leaked}")
    if "http://" in data_text or "https://" in data_text:
        raise ValidationError("Public runtime data contains external URLs")

    forbidden_names = {
        "v7.66.csv", "v7.66.xlsx", "sourceLinks", "originaldateiname", "quellarchiv",
        "beschreibung_intern_nicht_sichtbar", "servieren_intern_nicht_sichtbar",
    }
    for path in site.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".ico"}:
            continue
        text = path.read_text(encoding="utf-8")
        low = text.casefold()
        hits = sorted(term for term in forbidden_names if term.casefold() in low)
        if hits:
            raise ValidationError(f"Forbidden private marker in {path.relative_to(site)}: {hits}")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                raise ValidationError(f"Secret-like value in {path.relative_to(site)}")

    runtime_files = ["index.html", "app.js", "styles.css", "manifest.webmanifest", "service-worker.js"]
    for relative in runtime_files:
        text = (site / relative).read_text(encoding="utf-8")
        if re.search(r"(?:src|href)=[\"']/", text):
            raise ValidationError(f"Absolute root path breaks GitHub project pages: {relative}")
        if "https://" in text or "http://" in text:
            raise ValidationError(f"External runtime dependency in {relative}")


def validate_pwa(site: Path) -> None:
    manifest = load_json(site / "manifest.webmanifest")
    required = {"name", "short_name", "icons", "start_url", "scope", "display", "background_color", "theme_color"}
    if not required.issubset(manifest):
        raise ValidationError(f"Manifest missing members: {sorted(required - set(manifest))}")
    if manifest["start_url"] != "./" or manifest["scope"] != "./" or manifest["display"] != "standalone":
        raise ValidationError("Manifest is not safe for GitHub project subpaths")
    icon_sizes = {item["sizes"] for item in manifest["icons"]}
    if not {"192x192", "512x512"}.issubset(icon_sizes):
        raise ValidationError("PWA manifest lacks 192x192 and 512x512 icons")
    for item in manifest["icons"]:
        icon_path = site / item["src"].removeprefix("./")
        if not icon_path.is_file():
            raise ValidationError(f"Manifest icon missing: {item['src']}")
        expected_size = tuple(int(part) for part in item["sizes"].split("x"))
        with Image.open(icon_path) as image:
            if image.size != expected_size:
                raise ValidationError(f"Manifest icon dimensions mismatch: {item['src']}")
    index = (site / "index.html").read_text(encoding="utf-8")
    if '<link rel="manifest" href="./manifest.webmanifest">' not in index:
        raise ValidationError("index.html does not reference the web app manifest relatively")
    app_js = (site / "app.js").read_text(encoding="utf-8")
    if 'navigator.serviceWorker.register("./service-worker.js", { scope: "./" })' not in app_js:
        raise ValidationError("Service worker registration is missing or not subpath-safe")
    service_worker = (site / "service-worker.js").read_text(encoding="utf-8")
    for required_url in ["./index.html", "./data/inventory.json", "./data/assets.json", "./data/version.json", "./integrity.json"]:
        if required_url not in service_worker:
            raise ValidationError(f"Service worker precache is missing {required_url}")


def validate_integrity(site: Path, required: bool) -> None:
    path = site / "integrity.json"
    if not path.exists():
        if required:
            raise ValidationError("integrity.json is missing")
        return
    manifest = load_json(path)
    assert_exact_keys(manifest, {"appVersion", "files", "schemaVersion"}, "integrity root")
    listed = {item["path"]: item for item in manifest["files"]}
    if "integrity.json" in listed:
        raise ValidationError("integrity.json must not hash itself")
    actual_paths = sorted(
        p.relative_to(site).as_posix()
        for p in site.rglob("*")
        if p.is_file() and p.relative_to(site).as_posix() != "integrity.json"
    )
    if sorted(listed) != actual_paths:
        missing = sorted(set(actual_paths) - set(listed))
        extra = sorted(set(listed) - set(actual_paths))
        raise ValidationError(f"Integrity file set mismatch: missing={missing}, extra={extra}")
    for relative, item in listed.items():
        file_path = site / relative
        if set(item) != {"bytes", "path", "sha256"}:
            raise ValidationError(f"Integrity entry keys invalid: {relative}")
        if item["bytes"] != file_path.stat().st_size or item["sha256"] != sha256_file(file_path):
            raise ValidationError(f"Integrity mismatch: {relative}")


def validate_schemas(site: Path) -> None:
    for path in sorted((site / "schemas").glob("*.json")):
        document = load_json(path)
        if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise ValidationError(f"Unexpected schema dialect: {path.name}")


def validate_site(site: Path, require_integrity: bool = True) -> dict[str, Any]:
    try:
        verify_environment(verify_wheels=False, exact_python=False)
    except EnvironmentContractError as exc:
        raise ValidationError(f"Environment contract failed: {exc}") from exc
    if Image is None:
        raise ValidationError("Environment contract failed: Pillow import is unavailable")
    site = site.resolve()
    if not site.is_dir():
        raise ValidationError(f"Site directory does not exist: {site}")
    validate_runtime_files(site)
    version = validate_version(site)
    inventory, assets, metadata = validate_inventory(site)
    validate_privacy(site)
    validate_pwa(site)
    validate_schemas(site)
    validate_integrity(site, required=require_integrity)
    return {
        "appVersion": version["appVersion"],
        "assetRecords": len(assets["items"]),
        "inventoryRecords": len(inventory["items"]),
        "masterVersion": metadata["masterVersion"],
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    parser.add_argument("--allow-missing-integrity", action="store_true")
    args = parser.parse_args()
    result = validate_site(args.site, require_integrity=not args.allow_missing_integrity)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"VALIDATION_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
