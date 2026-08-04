#!/usr/bin/env python3
"""Verify every public site file against the immutable Phase-1 reference lock."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LOCK=ROOT/'config/public-site-lock.json'

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def verify_public_tree(site: Path) -> dict:
    lock=json.loads(LOCK.read_text(encoding='utf-8'))
    actual={p.relative_to(site).as_posix():sha256_file(p) for p in sorted(site.rglob('*')) if p.is_file()}
    expected=lock['files']
    missing=sorted(set(expected)-set(actual))
    extra=sorted(set(actual)-set(expected))
    changed=sorted(k for k in set(expected)&set(actual) if expected[k]!=actual[k])
    tree=hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest()
    errors=[]
    if len(actual)!=lock['fileCount']: errors.append(f"fileCount {len(actual)} != {lock['fileCount']}")
    if missing: errors.append(f'missing={missing}')
    if extra: errors.append(f'extra={extra}')
    if changed: errors.append(f'changed={changed}')
    if tree!=lock['treeSha256']: errors.append(f"treeSha256 {tree} != {lock['treeSha256']}")
    result={'status':'PASS' if not errors else 'FAIL','fileCount':len(actual),'treeSha256':tree,'missing':missing,'extra':extra,'changed':changed,'errors':errors}
    if errors:
        raise RuntimeError('; '.join(errors))
    return result

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--site', type=Path, default=ROOT/'site'); args=parser.parse_args()
    try: result=verify_public_tree(args.site.resolve())
    except Exception as exc:
        print(f'PUBLIC_TREE_ERROR: {exc}', file=sys.stderr); return 3
    print(json.dumps(result,ensure_ascii=False,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
