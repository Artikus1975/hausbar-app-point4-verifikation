#!/usr/bin/env python3
"""Create and verify an offline clean-room environment for the private Phase-1 tools."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(command: list[str], cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    venv = args.venv.resolve()
    if venv.exists():
        if not args.replace:
            raise SystemExit(f"Target exists: {venv}; use --replace")
        shutil.rmtree(venv)
    run([sys.executable, "-m", "venv", str(venv)])
    python = venv / "bin/python"
    wheel_dir = ROOT / "vendor/wheels/cp313-linux-x86_64"
    run([
        str(python), "-m", "pip", "install", "--no-index", "--no-deps", "--require-hashes",
        "--find-links", str(wheel_dir), "-r", str(ROOT / "requirements-lock.txt"),
    ])
    completed = subprocess.run(
        [str(python), str(ROOT / "tools/check_environment.py")],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    result = {"status": "PASS", "venv": str(venv), "environment": json.loads(completed.stdout)}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
