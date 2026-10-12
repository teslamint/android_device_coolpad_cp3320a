"""Repository-level contract for the committed CP3320A build inputs."""

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "kernel": "21851bee493e95c8b0aa94f1e2eb7ca920552794b25db56aff1016f592cf2c3e",
    "dt.img": "e543d6c7cc697db1e7ad9cd79f5eb2f5939f53e31ae899a9354a589b9f16bc4d",
}


class RepositoryInputsTest(unittest.TestCase):
    def test_committed_inputs_match_live_tested_stock_bytes(self):
        for name, expected in EXPECTED.items():
            with self.subTest(name=name):
                payload = (ROOT / name).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), expected)

    def test_board_config_uses_committed_inputs(self):
        config = (ROOT / "BoardConfig.mk").read_text()
        self.assertIn("TARGET_PREBUILT_KERNEL := $(LOCAL_PATH)/kernel", config)
        self.assertIn("--dt $(LOCAL_PATH)/dt.img", config)
        self.assertNotIn("$(LOCAL_PATH)/prebuilt/", config)


if __name__ == "__main__":
    unittest.main()
