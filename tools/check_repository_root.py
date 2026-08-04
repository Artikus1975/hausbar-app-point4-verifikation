#!/usr/bin/env python3
"""Verify that commands are executed from the direct Git repository root."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = '.hausbar-repository-root.json'

class RepositoryRootError(RuntimeError):
    pass

def verify_repository_root(cwd: Path | None = None) -> dict:
    actual = (cwd or Path.cwd()).resolve()
    errors: list[str] = []
    marker_path = actual / MARKER
    if actual != ROOT:
        errors.append(f'Working directory {actual} is not repository root {ROOT}')
    if not marker_path.is_file():
        errors.append(f'Missing root marker: {marker_path}')
        marker = None
    else:
        marker = json.loads(marker_path.read_text(encoding='utf-8'))
        for entry in marker['requiredRootEntries']:
            if not (actual / entry).exists():
                errors.append(f'Missing required root entry: {entry}')
    workflow = actual / '.github/workflows/pages.yml'
    if not workflow.is_file():
        errors.append('GitHub workflow is not located at .github/workflows/pages.yml in repository root')
    if errors:
        raise RepositoryRootError('; '.join(errors))
    return {'status':'PASS','repositoryRoot':str(actual),'marker':marker,'workflow':str(workflow)}

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args=parser.parse_args()
    try:
        result=verify_repository_root(args.root)
    except RepositoryRootError as exc:
        print(f'REPOSITORY_ROOT_ERROR: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
