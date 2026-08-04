#!/usr/bin/env python3
"""Verify the locked private Phase-1 toolchain using only the standard library."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "config/toolchain-lock.json"

class EnvironmentContractError(RuntimeError):
    pass

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_lock() -> dict:
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))

def verify_environment(*, verify_wheels: bool = True, exact_python: bool = True) -> dict:
    lock = load_lock()
    errors: list[str] = []
    actual_version = platform.python_version()
    actual_impl = platform.python_implementation()
    if actual_impl != lock["python"]["implementation"]:
        errors.append(f"Python implementation {actual_impl!r} != {lock['python']['implementation']!r}")
    if exact_python and actual_version != lock["python"]["exactReferenceVersion"]:
        errors.append(f"Python version {actual_version!r} != {lock['python']['exactReferenceVersion']!r}")
    if not exact_python and ".".join(actual_version.split(".")[:2]) != lock["python"]["majorMinor"]:
        errors.append(f"Python major/minor {actual_version!r} != {lock['python']['majorMinor']!r}")
    if platform.system() != lock["platform"]["system"]:
        errors.append(f"Platform system {platform.system()!r} != {lock['platform']['system']!r}")
    if platform.machine() != lock["platform"]["machine"]:
        errors.append(f"Platform machine {platform.machine()!r} != {lock['platform']['machine']!r}")

    package_results = []
    for package in lock["packages"]:
        try:
            actual = metadata.version(package["distribution"])
        except metadata.PackageNotFoundError:
            errors.append(f"Missing distribution: {package['distribution']}=={package['version']}")
            actual = None
        if actual is not None and actual != package["version"]:
            errors.append(f"Distribution {package['distribution']} version {actual!r} != {package['version']!r}")
        package_results.append({"distribution": package["distribution"], "expected": package["version"], "actual": actual})

    wheel_results = []
    if verify_wheels:
        wheel_dir = ROOT / lock["platform"]["wheelDirectory"]
        expected_names = {item["wheel"] for item in lock["packages"]}
        actual_names = {path.name for path in wheel_dir.glob("*.whl")}
        if actual_names != expected_names:
            errors.append(f"Wheel set mismatch: missing={sorted(expected_names-actual_names)}, extra={sorted(actual_names-expected_names)}")
        for package in lock["packages"]:
            path = wheel_dir / package["wheel"]
            actual_hash = sha256_file(path) if path.is_file() else None
            if actual_hash != package["sha256"]:
                errors.append(f"Wheel hash mismatch: {package['wheel']}")
            wheel_results.append({"wheel": package["wheel"], "expectedSha256": package["sha256"], "actualSha256": actual_hash})

    result = {
        "status": "PASS" if not errors else "FAIL",
        "python": {"implementation": actual_impl, "version": actual_version},
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "packages": package_results,
        "wheels": wheel_results,
        "errors": errors,
    }
    if errors:
        raise EnvironmentContractError("; ".join(errors))
    return result

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-wheel-check", action="store_true")
    parser.add_argument("--allow-python-patch-difference", action="store_true")
    args = parser.parse_args()
    try:
        result = verify_environment(verify_wheels=not args.skip_wheel_check, exact_python=not args.allow_python_patch_difference)
    except EnvironmentContractError as exc:
        print(f"ENVIRONMENT_CONTRACT_ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
