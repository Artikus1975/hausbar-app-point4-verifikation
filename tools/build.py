#!/usr/bin/env python3
"""Generate deterministic runtime files and integrity metadata for the public site."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from check_environment import EnvironmentContractError, verify_environment
from validate_public import validate_site

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    try:
        verify_environment(verify_wheels=False, exact_python=False)
    except EnvironmentContractError as exc:
        raise SystemExit(f"ENVIRONMENT_CONTRACT_ERROR: {exc}") from exc
    site = args.site.resolve()

    version_config = json.loads((ROOT / "config/app-version.json").read_text(encoding="utf-8"))
    version_document = {"schemaVersion": 1, **version_config}
    write_json(site / "data/version.json", version_document)

    cache_slug = re.sub(r"[^a-z0-9.-]+", "-", version_config["appVersion"].lower()).strip("-")
    precache_urls = [
        "./",
        "./index.html",
        "./styles.css",
        "./app.js",
        "./manifest.webmanifest",
        "./integrity.json",
        "./data/version.json",
        "./data/inventory.json",
        "./data/assets.json",
        "./data/export-metadata.json",
        "./assets/icons/icon-192.png",
        "./assets/icons/icon-512.png",
        "./assets/icons/apple-touch-icon.png",
    ]
    template = (ROOT / "templates/service-worker.js.tmpl").read_text(encoding="utf-8")
    rendered = template.replace("__CACHE_NAME__", f"hausbar-app-{cache_slug}")
    rendered = rendered.replace("__PRECACHE_URLS__", json.dumps(precache_urls, ensure_ascii=False, indent=2))
    (site / "service-worker.js").write_text(rendered, encoding="utf-8", newline="\n")

    integrity_path = site / "integrity.json"
    if integrity_path.exists():
        integrity_path.unlink()

    validate_site(site, require_integrity=False)

    files = []
    for path in sorted(p for p in site.rglob("*") if p.is_file()):
        relative = path.relative_to(site).as_posix()
        if relative == "integrity.json":
            continue
        files.append({
            "bytes": path.stat().st_size,
            "path": relative,
            "sha256": sha256_file(path),
        })
    write_json(integrity_path, {
        "appVersion": version_config["appVersion"],
        "files": files,
        "schemaVersion": 1,
    })

    result = validate_site(site, require_integrity=True)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
