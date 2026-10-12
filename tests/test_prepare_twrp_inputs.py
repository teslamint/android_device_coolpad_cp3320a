"""Generated-image CLI tests; no acquisition or device access."""

import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PAGE = 2048
KERNEL_SIZE = 6509208
DT_SIZE = 149504
LIMIT = 16777216
FSTAB = b"""/system ext4 /dev/block/bootdevice/by-name/system
/cache ext4 /dev/block/bootdevice/by-name/cache
/data ext4 /dev/block/bootdevice/by-name/userdata flags=length=-16384
/external_sd vfat /dev/block/mmcblk1p1
/boot emmc /dev/block/bootdevice/by-name/boot
/recovery emmc /dev/block/bootdevice/by-name/recovery
/misc emmc /dev/block/bootdevice/by-name/misc
"""


def align(n, boundary=PAGE):
    return (n + boundary - 1) // boundary * boundary


def newc(entries):
    result = bytearray()
    for number, (name, data, mode) in enumerate(entries + [("TRAILER!!!", b"", 0)]):
        fields = [number, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0,
                  len(name.encode()) + 1, 0]
        result.extend(b"070701" + "".join(f"{n:08x}" for n in fields).encode())
        result.extend(name.encode() + b"\0")
        result.extend(bytes(align(len(result), 4) - len(result)))
        result.extend(data)
        result.extend(bytes(align(len(result), 4) - len(result)))
    return bytes(result)


def ramdisk(entries=None):
    if entries is None:
        entries = [("sbin/recovery", b"synthetic executable", 0o100755),
                   ("etc/recovery.fstab", FSTAB, 0o100644)]
    return gzip.compress(newc(entries), mtime=0)


def image(ram=None, os_version=0):
    if ram is None:
        ram = ramdisk()
    kernel = b"K" * KERNEL_SIZE
    dt = bytearray(DT_SIZE)
    # QCDT v3 adds four PMIC revision words before offset and size.
    struct.pack_into("<13I", dt, 0, 0x54444351, 3, 1, 0x103, 8, 0, 0,
                     0, 0, 0, 0, PAGE, DT_SIZE - PAGE)
    dt[PAGE:PAGE + 8] = b"\xd0\x0d\xfe\xed" + struct.pack(">I", DT_SIZE - PAGE)
    header = bytearray(PAGE)
    header[:8] = b"ANDROID!"
    struct.pack_into("<10I", header, 8, KERNEL_SIZE, 0x80008000, len(ram),
                     0x81000000, 0, 0x80f00000, 0x80000100, PAGE, DT_SIZE,
                     os_version)
    result = bytearray(header)
    for part in (kernel, ram, dt):
        result.extend(part)
        result.extend(bytes(align(len(part)) - len(part)))
    return result


def cli(module, *args):
    return subprocess.run([sys.executable, "-m", "tools." + module,
                           *map(str, args)], cwd=ROOT, capture_output=True,
                          text=True, timeout=30,
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))


class PrepareTwrpInputsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="prepare-twrp-")
        self.root = Path(self.temp.name)
        self.source = self.root / "source.img"
        self.output = self.root / "prepared"

    def tearDown(self):
        self.temp.cleanup()

    def fail_image(self, payload, message):
        self.source.write_bytes(payload)
        result = cli("prepare_twrp_inputs", self.source, self.output)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(message, result.stderr.lower())
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.output.exists())

    def test_exact_extraction_and_repeatable_receipt(self):
        payload = image(os_version=0x0E04111B)
        self.source.write_bytes(payload)
        first = cli("prepare_twrp_inputs", self.source, self.output)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.root / "second"
        result = cli("prepare_twrp_inputs", self.source, second)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt_bytes = (self.output / "receipt.json").read_bytes()
        self.assertEqual(receipt_bytes, (second / "receipt.json").read_bytes())
        receipt = json.loads(receipt_bytes)
        self.assertEqual(receipt["os_version"], 0x0E04111B)
        expected_dt = PAGE + align(KERNEL_SIZE) + align(len(ramdisk()))
        for name, offset, size in [("kernel", PAGE, KERNEL_SIZE),
                                    ("dt", expected_dt, DT_SIZE)]:
            content = payload[offset:offset + size]
            filename = "kernel" if name == "kernel" else "dt.img"
            self.assertEqual((self.output / filename).read_bytes(), content)
            self.assertEqual(receipt[name], {"offset": offset, "size": size,
                                             "sha256": hashlib.sha256(content).hexdigest()})

    def test_missing_input(self):
        result = cli("prepare_twrp_inputs", self.source, self.output)
        self.assertEqual(result.returncode, 1)
        self.assertIn("input", result.stderr.lower())
        self.assertFalse(self.output.exists())

    def test_existing_output_is_never_modified(self):
        self.source.write_bytes(image())
        self.output.mkdir()
        sentinel = self.output / "kernel"
        sentinel.write_bytes(b"another agent's bytes")
        result = cli("prepare_twrp_inputs", self.source, self.output)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(sentinel.read_bytes(), b"another agent's bytes")
        self.assertEqual(list(self.output.iterdir()), [sentinel])

    def test_existing_empty_or_symlink_output_is_rejected(self):
        self.source.write_bytes(image())
        self.output.mkdir()
        result = cli("prepare_twrp_inputs", self.source, self.output)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(list(self.output.iterdir()), [])

        self.output.rmdir()
        target = self.root / "foreign"
        target.mkdir()
        self.output.symlink_to(target, target_is_directory=True)
        result = cli("prepare_twrp_inputs", self.source, self.output)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(list(target.iterdir()), [])

    def test_magic(self):
        payload = image()
        payload[:8] = b"BADMAGIC"
        self.fail_image(payload, "magic")

    def test_short_header(self):
        self.fail_image(b"ANDROID!", "header")

    def test_fixed_header_fields(self):
        for offset, value in [(12, 0), (20, 0), (28, 0), (32, 0),
                              (36, 4096), (8, KERNEL_SIZE - 1),
                              (40, DT_SIZE - 1), (24, 1)]:
            with self.subTest(offset=offset):
                payload = image()
                struct.pack_into("<I", payload, offset, value)
                self.fail_image(payload, "header")

    def test_zero_or_oversize_ramdisk(self):
        for size in (0, 10112576):
            payload = image()
            struct.pack_into("<I", payload, 16, size)
            self.fail_image(payload, "ramdisk")

    def test_truncation_and_partition_ceiling(self):
        self.fail_image(image()[:-PAGE], "size")
        self.fail_image(image() + bytes(LIMIT), "partition")

    def test_qcdt_contract_and_entry_bounds(self):
        for relative, value in [(0, 0), (4, 2), (8, 2), (12, 0),
                                (16, 0), (44, 12), (48, DT_SIZE)]:
            with self.subTest(relative=relative):
                payload = image()
                dt_offset = PAGE + align(KERNEL_SIZE) + align(len(ramdisk()))
                struct.pack_into("<I", payload, dt_offset + relative, value)
                self.fail_image(payload, "qcdt")

    def test_qcdt_entry_must_contain_bounded_fdt(self):
        payload = image()
        dt_offset = PAGE + align(KERNEL_SIZE) + align(len(ramdisk()))
        payload[dt_offset + PAGE:dt_offset + PAGE + 4] = b"BAD!"
        self.fail_image(payload, "fdt")

        payload = image()
        struct.pack_into(">I", payload, dt_offset + PAGE + 4, DT_SIZE)
        self.fail_image(payload, "fdt")

    def test_signature_overlaps_declared_layout(self):
        payload = image()
        # DER BootSignature with authenticated length shorter than the sections.
        attrs = b"\x30\x10\x13\x09/recovery\x02\x03\x00\x10\x00"
        signature = b"\x02\x01\x01\x30\x00\x30\x00" + attrs + b"\x04\x01X"
        payload.extend(b"\x30" + bytes([len(signature)]) + signature)
        self.fail_image(payload, "signature")


if __name__ == "__main__":
    unittest.main()
