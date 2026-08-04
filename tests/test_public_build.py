from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from validate_public import validate_site  # noqa: E402


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


class PublicBuildTests(unittest.TestCase):
    def test_complete_public_validation(self) -> None:
        result = validate_site(ROOT / "site", require_integrity=True)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["inventoryRecords"], 142)
        self.assertEqual(result["assetRecords"], 154)

    def test_build_is_reproducible(self) -> None:
        before = tree_digest(ROOT / "site")
        subprocess.run(
            [sys.executable, str(TOOLS / "build.py"), "--site", str(ROOT / "site")],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        after = tree_digest(ROOT / "site")
        self.assertEqual(before, after)

    def test_single_version_source(self) -> None:
        config = json.loads((ROOT / "config/app-version.json").read_text(encoding="utf-8"))
        public = json.loads((ROOT / "site/data/version.json").read_text(encoding="utf-8"))
        self.assertEqual(public["appVersion"], config["appVersion"])
        self.assertEqual(public["masterVersion"], config["masterVersion"])
        self.assertEqual(public["assetVersion"], config["assetVersion"])

    def test_phase_scope_is_not_expanded(self) -> None:
        site = ROOT / "site"
        self.assertFalse((site / "data/recipes.json").exists())
        html = (site / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('id="inventory-list"', html)
        self.assertNotIn('id="recipe-list"', html)

    def test_private_sources_are_not_packaged(self) -> None:
        forbidden_suffixes = {".xlsx"}
        forbidden_names = {"v7.66.csv", "v7.66.xlsx", "sourceLinks.csv"}
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            self.assertNotIn(path.name, forbidden_names)
            self.assertNotIn(path.suffix.lower(), forbidden_suffixes)


if __name__ == "__main__":
    unittest.main()
