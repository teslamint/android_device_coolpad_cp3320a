"""Contract between the container build scripts and this repository."""

import re
import subprocess
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from test_repository_inputs import EXPECTED


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"


class BuildScriptsTest(unittest.TestCase):
    def test_build_script_pins_the_committed_input_hashes(self):
        script = (BUILD / "build.sh").read_text()
        self.assertIn(f"KERNEL_SHA256={EXPECTED['kernel']}", script)
        self.assertIn(f"DT_SHA256={EXPECTED['dt.img']}", script)

    def test_shell_scripts_parse(self):
        for name in ("build.sh", "sync.sh"):
            with self.subTest(name=name):
                subprocess.run(["bash", "-n", str(BUILD / name)], check=True)

    def test_manifest_pins_every_project_by_commit(self):
        projects = ET.parse(BUILD / "manifest-pinned.xml").getroot().findall("project")
        self.assertEqual(len(projects), 68)
        for project in projects:
            with self.subTest(project=project.get("name")):
                self.assertRegex(project.get("revision") or "", r"^[0-9a-f]{40}$")

    def test_sync_script_pins_the_documented_recovery_commit(self):
        script = (BUILD / "sync.sh").read_text()
        recovery = re.search(r"RECOVERY_COMMIT=([0-9a-f]{40})", script).group(1)
        self.assertIn(f"TeamWin/android_bootable_recovery@{recovery}", (ROOT / "README.md").read_text())
        projects = ET.parse(BUILD / "manifest-pinned.xml").getroot().findall("project")
        revisions = {p.get("path") or p.get("name"): p.get("revision") for p in projects}
        self.assertEqual(revisions["bootable/recovery"], recovery)

    def test_sync_script_reads_patches_from_this_tree(self):
        script = (BUILD / "sync.sh").read_text()
        self.assertIn('"$TREE"/patches/bootable_recovery/*.patch', script)
        self.assertTrue(list((ROOT / "patches" / "bootable_recovery").glob("*.patch")))


if __name__ == "__main__":
    unittest.main()
