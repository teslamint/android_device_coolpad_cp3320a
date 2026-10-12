"""Generated-image CLI tests.

Set TWRP_VERIFICATION_ARTIFACT to retain the success JSON outside the temporary
fixture directory. The artifact contains only synthetic-fixture measurements.
"""

import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest

from test_prepare_twrp_inputs import (
    DT_SIZE, FSTAB, KERNEL_SIZE, LIMIT, PAGE, align, cli, image, newc, ramdisk,
)


class VerifyTwrpImageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="verify-twrp-")
        self.root = Path(self.temp.name)
        self.source = self.root / "stock.img"
        self.prepared = self.root / "prepared"
        self.candidate = self.root / "candidate.img"
        self.source.write_bytes(image())

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self):
        result = cli("prepare_twrp_inputs", self.source, self.prepared)
        self.assertEqual(result.returncode, 0, result.stderr)

    def verify(self, payload):
        if not self.prepared.exists():
            self.prepare()
        self.candidate.write_bytes(payload)
        return cli("verify_twrp_image", self.candidate, self.prepared)

    def reject(self, payload, message):
        result = self.verify(payload)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(message, result.stderr.lower())
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_success_writes_repeatable_verification_artifact(self):
        payload = image(os_version=0x0E04111B)
        result = self.verify(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        artifact = Path(os.environ.get("TWRP_VERIFICATION_ARTIFACT",
                                       str(self.root / "verification.json")))
        artifact.write_text(result.stdout)
        report = json.loads(artifact.read_bytes())
        self.assertTrue(report["valid"])
        self.assertEqual(report["image_size"], len(payload))
        self.assertEqual(report["image_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(report["os_version"], 0x0E04111B)
        self.assertEqual(report["kernel"]["sha256"],
                         hashlib.sha256(b"K" * KERNEL_SIZE).hexdigest())
        self.assertEqual(report["ramdisk"]["sha256"], hashlib.sha256(ramdisk()).hexdigest())
        again = cli("verify_twrp_image", self.candidate, self.prepared)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(artifact.read_bytes(), again.stdout.encode())
        self.assertEqual(report["fstab_mounts"],
                         ["/boot", "/cache", "/data", "/external_sd", "/misc", "/recovery", "/system"])

    def test_magic(self):
        payload = image()
        payload[:8] = b"BADMAGIC"
        self.reject(payload, "magic")

    def test_fixed_headers(self):
        for offset, value in [(12, 0), (20, 0), (28, 0), (32, 0),
                              (36, 4096), (24, 1)]:
            with self.subTest(offset=offset):
                payload = image()
                struct.pack_into("<I", payload, offset, value)
                self.reject(payload, "header")

    def test_kernel_bytes_differ(self):
        payload = image()
        payload[PAGE + 100] ^= 1
        self.reject(payload, "kernel")

    def test_qcdt_bytes_differ(self):
        payload = image()
        dt_offset = PAGE + align(KERNEL_SIZE) + align(len(ramdisk()))
        payload[dt_offset + PAGE + 100] ^= 1
        self.reject(payload, "qcdt")

    def test_partition_ceiling(self):
        self.reject(image() + bytes(LIMIT), "partition")

    def test_truncated_layout(self):
        self.reject(image()[:-PAGE], "size")

    def test_non_gzip_and_non_newc(self):
        self.reject(image(b"not gzip"), "gzip")
        self.reject(image(gzip.compress(b"not cpio", mtime=0)), "newc")

    def test_gzip_expansion_limit(self):
        expanded = b"X" * (32 * 1024 * 1024 + 1)
        self.reject(image(gzip.compress(expanded, compresslevel=9, mtime=0)),
                    "uncompressed")

    def test_malformed_newc(self):
        valid = newc([("sbin/recovery", b"X", 0o100755),
                      ("etc/recovery.fstab", FSTAB, 0o100644)])
        cases = [valid[:-100], valid[:110], valid[:-124],
                 valid[:54] + b"ffffffff" + valid[62:],
                 valid[:94] + b"00000000" + valid[102:],
                 valid[:6] + b"zzzzzzzz" + valid[14:]]
        for data in cases:
            with self.subTest(length=len(data)):
                self.reject(image(gzip.compress(data, mtime=0)), "newc")

    def test_missing_required_files(self):
        for entries, message in [
            ([("etc/recovery.fstab", FSTAB, 0o100644)], "sbin/recovery"),
            ([("sbin/recovery", b"X", 0o100755)], "etc/recovery.fstab"),
        ]:
            self.reject(image(ramdisk(entries)), message)

    def test_required_files_must_be_real_files(self):
        for mode, data in [(0o120777, b"/bin/false"), (0o040755, b""),
                           (0o100644, b""), (0o100644, b"X")]:
            entries = [("sbin/recovery", data, mode),
                       ("etc/recovery.fstab", FSTAB, 0o100644)]
            self.reject(image(ramdisk(entries)), "sbin/recovery")

    def test_fstab_missing_or_wrong_partition(self):
        for content in [b"# /system ext4 /dev/block/bootdevice/by-name/system\n",
                        FSTAB.replace(b"/cache ext4", b"/other ext4"),
                        FSTAB.replace(b"by-name/userdata", b"by-name/system"),
                        FSTAB.replace(b"/system ext4", b"/system vfat")]:
            entries = [("sbin/recovery", b"X", 0o100755),
                       ("etc/recovery.fstab", content, 0o100644)]
            self.reject(image(ramdisk(entries)), "fstab")

    def test_duplicate_or_traversal_archive_entries(self):
        for name in ["etc/recovery.fstab", "../sbin/recovery"]:
            entries = [("sbin/recovery", b"X", 0o100755),
                       ("etc/recovery.fstab", FSTAB, 0o100644),
                       (name, b"X", 0o100755)]
            self.reject(image(ramdisk(entries)), "newc")

    def test_absolute_and_hardlinked_archive_entries(self):
        entries = [("/sbin/recovery", b"X", 0o100755),
                   ("etc/recovery.fstab", FSTAB, 0o100644)]
        self.reject(image(ramdisk(entries)), "newc")

        archive = bytearray(newc([("sbin/recovery", b"X", 0o100755),
                                  ("etc/recovery.fstab", FSTAB, 0o100644)]))
        archive[38:46] = b"00000002"
        self.reject(image(gzip.compress(archive, mtime=0)), "newc")

    def test_signature_overlap_and_unknown_trailer(self):
        attrs = b"\x30\x10\x13\x09/recovery\x02\x03\x00\x10\x00"
        signature = b"\x02\x01\x01\x30\x00\x30\x00" + attrs + b"\x04\x01X"
        self.reject(image() + b"\x30" + bytes([len(signature)]) + signature, "signature")
        self.reject(image() + b"unrecognized nonzero trailer", "signature")

    def test_valid_signature_extent_and_partition_padding(self):
        payload = image()
        length = len(payload).to_bytes(4, "big")
        attrs = b"\x30\x11\x13\x09/recovery\x02\x04" + length
        signature = b"\x02\x01\x01\x30\x00\x30\x00" + attrs + b"\x04\x01X"
        payload.extend(b"\x30" + bytes([len(signature)]) + signature)
        payload.extend(bytes(LIMIT - len(payload)))
        result = self.verify(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["signature_authenticated"])

    def test_missing_prepared_inputs(self):
        self.candidate.write_bytes(image())
        result = cli("verify_twrp_image", self.candidate, self.prepared)
        self.assertEqual(result.returncode, 1)
        self.assertIn("prepared", result.stderr.lower())
        self.assertNotIn("Traceback", result.stderr)

    def test_prepared_receipt_does_not_override_changed_bytes(self):
        self.prepare()
        (self.prepared / "kernel").write_bytes(b"K" * (KERNEL_SIZE - 1) + b"M")
        result = self.verify(image())
        self.assertEqual(result.returncode, 1)
        self.assertIn("prepared", result.stderr.lower())

    def test_prepared_directory_symlink_is_rejected(self):
        actual = self.root / "actual"
        result = cli("prepare_twrp_inputs", self.source, actual)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.prepared.symlink_to(actual, target_is_directory=True)
        self.candidate.write_bytes(image())
        result = cli("verify_twrp_image", self.candidate, self.prepared)
        self.assertEqual(result.returncode, 1)
        self.assertIn("symlink", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
