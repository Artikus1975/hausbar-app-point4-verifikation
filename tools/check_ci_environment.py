#!/usr/bin/env python3
"""Verify exact CI runtime, repository root, action pins, locks and public reference."""
from __future__ import annotations
import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from check_repository_root import verify_repository_root, RepositoryRootError  # noqa: E402
from check_environment import verify_environment, EnvironmentContractError  # noqa: E402

LOCK=ROOT/'config/ci-toolchain-lock.json'

def sha256_file(path: Path) -> str:
    h=hashlib.sha256(); h.update(path.read_bytes()); return h.hexdigest()

def node_version() -> str:
    return subprocess.run(['node','--version'],check=True,capture_output=True,text=True).stdout.strip().removeprefix('v')

def verify_ci_environment() -> dict:
    lock=json.loads(LOCK.read_text(encoding='utf-8'))
    errors=[]
    try: root_result=verify_repository_root(ROOT)
    except RepositoryRootError as exc: errors.append(str(exc)); root_result=None
    try: py_result=verify_environment(verify_wheels=True,exact_python=True)
    except EnvironmentContractError as exc: errors.append(str(exc)); py_result=None
    actual_node=node_version()
    if actual_node!=lock['node']['version']: errors.append(f"Node version {actual_node} != {lock['node']['version']}")
    workflow=ROOT/lock['workflow']['path']
    if sha256_file(workflow)!=lock['workflow']['sha256']: errors.append('Workflow SHA-256 mismatch')
    protected={
      'toolchainLockSha256':ROOT/'config/toolchain-lock.json',
      'requirementsLockSha256':ROOT/'requirements-lock.txt',
      'wheelProvenanceSha256':ROOT/'vendor/wheels/wheel-provenance.json',
      'rootMarkerSha256':ROOT/'.hausbar-repository-root.json',
      'publicSiteLockSha256':ROOT/'config/public-site-lock.json',
    }
    for key,path in protected.items():
        if sha256_file(path)!=lock['protectedFiles'][key]: errors.append(f'{key} mismatch')
    text=workflow.read_text(encoding='utf-8')
    if 'ubuntu-latest' in text: errors.append('ubuntu-latest is forbidden')
    if text.count('runs-on: ubuntu-24.04')!=2: errors.append('Both jobs must use ubuntu-24.04')
    bootstrap=(ROOT/'tools/bootstrap_clean_environment.py').read_text(encoding='utf-8')
    if any(flag not in bootstrap for flag in ('--no-index','--no-deps','--require-hashes')):
        errors.append('Offline installation flags incomplete')
    if 'tools/bootstrap_clean_environment.py --venv "$HAUSBAR_CI_VENV" --replace' not in text:
        errors.append('Workflow does not invoke the locked offline bootstrap')
    if 'HAUSBAR_CI_VENV: ${{ runner.temp }}/hausbar-ci-venv' not in text:
        errors.append('Workflow does not place the CI environment in runner.temp')
    actual_uses=dict(re.findall(r'uses:\s+([^@\s]+)@([0-9a-f]{40})',text))
    expected={a['repository']:a['commitSha'] for a in lock['actions']}
    if actual_uses!=expected: errors.append(f'Action pins mismatch: actual={actual_uses} expected={expected}')
    result={'status':'PASS' if not errors else 'FAIL','python':platform.python_version(),'node':actual_node,'repositoryRoot':root_result,'pythonToolchain':py_result,'actionPins':actual_uses,'errors':errors}
    if errors: raise RuntimeError('; '.join(errors))
    return result

def main() -> int:
    try: result=verify_ci_environment()
    except Exception as exc:
        print(f'CI_ENVIRONMENT_ERROR: {exc}',file=sys.stderr); return 4
    print(json.dumps(result,ensure_ascii=False,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
