from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import platform
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from check_environment import EnvironmentContractError, verify_environment  # noqa: E402

class ToolchainContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lock = json.loads((ROOT / "config/toolchain-lock.json").read_text(encoding="utf-8"))

    def test_reference_environment_and_wheels_pass(self) -> None:
        result = verify_environment(verify_wheels=True, exact_python=True)
        self.assertEqual(result["status"], "PASS")

    def test_lock_contains_exact_three_packages(self) -> None:
        actual = {(p["distribution"], p["version"]) for p in self.lock["packages"]}
        self.assertEqual(actual, {("openpyxl", "3.1.5"), ("Pillow", "12.2.0"), ("et_xmlfile", "2.0.0")})

    def test_wheel_hashes_match_lock(self) -> None:
        wheel_dir = ROOT / self.lock["platform"]["wheelDirectory"]
        for item in self.lock["packages"]:
            digest = hashlib.sha256((wheel_dir / item["wheel"]).read_bytes()).hexdigest()
            self.assertEqual(digest, item["sha256"])

    def test_missing_distribution_is_rejected(self) -> None:
        original = metadata.version
        def fake(name: str) -> str:
            if name == "openpyxl":
                raise metadata.PackageNotFoundError(name)
            return original(name)
        with patch("check_environment.metadata.version", side_effect=fake):
            with self.assertRaises(EnvironmentContractError):
                verify_environment(verify_wheels=False, exact_python=False)

    def test_wrong_distribution_version_is_rejected(self) -> None:
        original = metadata.version
        def fake(name: str) -> str:
            return "0.0.0" if name == "Pillow" else original(name)
        with patch("check_environment.metadata.version", side_effect=fake):
            with self.assertRaises(EnvironmentContractError):
                verify_environment(verify_wheels=False, exact_python=False)

    def test_wrong_python_version_is_rejected(self) -> None:
        with patch("check_environment.platform.python_version", return_value="3.13.4"):
            with self.assertRaises(EnvironmentContractError):
                verify_environment(verify_wheels=False, exact_python=True)

    def test_offline_install_contract(self) -> None:
        text = (ROOT / "requirements-lock.txt").read_text(encoding="utf-8")
        self.assertEqual(text.count("--hash=sha256:"), 3)
        self.assertTrue(self.lock["installation"]["networkAllowed"] is False)
        self.assertTrue(self.lock["installation"]["requireHashes"] is True)

if __name__ == "__main__":
    unittest.main()
