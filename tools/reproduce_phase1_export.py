#!/usr/bin/env python3
"""Reproduce the Phase-1 public export in an isolated work directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def tree_manifest(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha256_file(p) for p in sorted(root.rglob("*")) if p.is_file()}

def run(command: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    source = args.source_dir.resolve()
    work = args.work_dir.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    generated_site = work / "site"
    shutil.copytree(ROOT / "site", generated_site)

    run([sys.executable, str(TOOLS / "check_environment.py")])
    export_command = [
        sys.executable, str(TOOLS / "export_public_data.py"),
        "--master-csv", str(source / "v7.66.csv"),
        "--master-xlsx", str(source / "v7.66.xlsx"),
        "--asset-package-zip", str(source / "04_v7.66_assetpaket_stabil.zip"),
        "--asset-mapping-csv", str(source / "v7.66_bildmapping_stabil.csv"),
        "--asset-manifest-json", str(source / "v7.66_assetmanifest_stabil.json"),
        "--asset-dir", str(source / "v7.66_bild_und_assetpaket_stabil"),
        "--phase0-matrix", str(source / "Hausbar_App_Phase0_Uebernahmematrix_v2.00_kandidat_01.csv"),
        "--phase0-audit-summary", str(source / "Hausbar_App_Phase0_Audit_Summary_v2.00_kandidat_01.json"),
        "--manifest-v200", str(source / "Hausbar_App_Manifest_v2.00.md"),
        "--historical-app-zip", str(source / "HausbarNext-main 2.zip"),
        "--site", str(generated_site),
    ]
    run(export_command)
    run([sys.executable, str(TOOLS / "build.py"), "--site", str(generated_site)])
    run([sys.executable, str(TOOLS / "validate_public.py"), "--site", str(generated_site)])
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    if shutil.which("node"):
        run(["node", "tests/runtime_contract.mjs"])

    reference = tree_manifest(ROOT / "site")
    generated = tree_manifest(generated_site)
    missing = sorted(set(reference) - set(generated))
    extra = sorted(set(generated) - set(reference))
    changed = sorted(path for path in set(reference) & set(generated) if reference[path] != generated[path])
    result = {
        "status": "PASS" if not (missing or extra or changed) else "FAIL",
        "referenceFiles": len(reference),
        "generatedFiles": len(generated),
        "missing": missing,
        "extra": extra,
        "changed": changed,
        "referenceTreeSha256": hashlib.sha256(json.dumps(reference, sort_keys=True).encode()).hexdigest(),
        "generatedTreeSha256": hashlib.sha256(json.dumps(generated, sort_keys=True).encode()).hexdigest(),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 3

if __name__ == "__main__":
    raise SystemExit(main())
