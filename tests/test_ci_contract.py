from __future__ import annotations
import hashlib
import json
import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'tools'
sys.path.insert(0,str(TOOLS))
from check_repository_root import RepositoryRootError, verify_repository_root  # noqa: E402
from verify_public_tree import verify_public_tree  # noqa: E402

class CiContractTests(unittest.TestCase):
    def setUp(self):
        self.lock=json.loads((ROOT/'config/ci-toolchain-lock.json').read_text(encoding='utf-8'))
        self.workflow=(ROOT/'.github/workflows/pages.yml').read_text(encoding='utf-8')

    def test_repository_root_passes(self):
        self.assertEqual(verify_repository_root(ROOT)['status'],'PASS')

    def test_wrong_nested_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            wrapper=Path(td)/'v0.1.0-preview.3'; shutil_target=wrapper/'app'; shutil_target.mkdir(parents=True)
            with self.assertRaises(RepositoryRootError): verify_repository_root(wrapper)

    def test_exact_runtime_versions_are_declared(self):
        self.assertEqual((ROOT/'.python-version').read_text().strip(),'3.13.5')
        self.assertEqual((ROOT/'.node-version').read_text().strip(),'22.16.0')
        self.assertEqual(self.lock['runner']['label'],'ubuntu-24.04')

    def test_actions_are_full_sha_pinned(self):
        for action in self.lock['actions']:
            needle=f"uses: {action['repository']}@{action['commitSha']}"
            self.assertIn(needle,self.workflow)
            self.assertEqual(len(action['commitSha']),40)
        self.assertNotIn('ubuntu-latest',self.workflow)

    def test_offline_installation_is_enforced(self):
        bootstrap=(ROOT/'tools/bootstrap_clean_environment.py').read_text(encoding='utf-8')
        for flag in ('--no-index','--no-deps','--require-hashes'):
            self.assertIn(flag,bootstrap)
        self.assertNotIn('pip install -U',self.workflow)
        self.assertNotIn('pip install --upgrade',self.workflow)

    def test_public_tree_is_byte_identical(self):
        result=verify_public_tree(ROOT/'site')
        self.assertEqual(result['fileCount'],172)
        self.assertEqual(result['treeSha256'],'ed6da5035e0a0943b35fd183e6ffd84771b8abd73d5a3133ecc0c806575b37c4')

    def test_workflow_hash_matches_lock(self):
        actual=hashlib.sha256((ROOT/'.github/workflows/pages.yml').read_bytes()).hexdigest()
        self.assertEqual(actual,self.lock['workflow']['sha256'])

    def test_point5_tests_are_not_added(self):
        self.assertFalse((ROOT/'tests/inventory_contract.mjs').exists())
        self.assertFalse((ROOT/'tests/inventory_ui_contract.mjs').exists())
        self.assertFalse((ROOT/'tests/recipe_contract.mjs').exists())
        self.assertFalse((ROOT/'tests/recipe_ui_contract.mjs').exists())

if __name__=='__main__': unittest.main()
