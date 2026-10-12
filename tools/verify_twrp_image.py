#!/usr/bin/env python3
"""Statically verify a CP3320A TWRP image against prepared kernel/QCDT bytes.

Usage: python3 -m tools.verify_twrp_image IMAGE PREPARED_DIRECTORY
Success emits deterministic JSON. Failure emits stderr and exits 1.
Signature checks cover extent only, not authenticity or live boot acceptance.
"""

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import zlib

if __package__:
    from .prepare_twrp_inputs import (
        DT_SIZE, KERNEL_SIZE, PAGE_SIZE, align, parse_image, read_image, validate_qcdt,
    )
else:
    from prepare_twrp_inputs import (
        DT_SIZE, KERNEL_SIZE, PAGE_SIZE, align, parse_image, read_image, validate_qcdt,
    )

FSTAB = {"/system": ("ext4", "/dev/block/bootdevice/by-name/system"),
         "/cache": ("ext4", "/dev/block/bootdevice/by-name/cache"),
         "/data": ("ext4", "/dev/block/bootdevice/by-name/userdata"),
         "/external_sd": ("vfat", "/dev/block/mmcblk1p1"),
         "/boot": ("emmc", "/dev/block/bootdevice/by-name/boot"),
         "/recovery": ("emmc", "/dev/block/bootdevice/by-name/recovery"),
         "/misc": ("emmc", "/dev/block/bootdevice/by-name/misc")}
MAX_UNCOMPRESSED_RAMDISK = 32 * 1024 * 1024


def prepared_inputs(directory):
    try:
        if directory.is_symlink():
            raise ValueError("prepared directory must not be a symlink")
        for name in ("receipt.json", "kernel", "dt.img"):
            metadata = os.lstat(directory / name)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"prepared {name} must be a regular file, not a symlink")
        receipt = json.loads((directory / "receipt.json").read_text())
        if (not isinstance(receipt, dict)
                or receipt.get("format") != "cp3320a-twrp-inputs-v1"
                or receipt.get("page_size") != PAGE_SIZE):
            raise ValueError("invalid extraction receipt format")
        hashes = {}
        for key, name, size in (("kernel", "kernel", KERNEL_SIZE), ("dt", "dt.img", DT_SIZE)):
            with (directory / name).open("rb") as stream:
                content = stream.read(size + 1)
            section = receipt.get(key)
            digest = hashlib.sha256(content).hexdigest()
            if (len(content) != size or not isinstance(section, dict)
                    or section.get("size") != size or section.get("sha256") != digest
                    or type(section.get("offset")) is not int
                    or section["offset"] < PAGE_SIZE or section["offset"] % PAGE_SIZE):
                raise ValueError(f"{name} differs from its extraction receipt")
            if key == "dt":
                validate_qcdt(content)
            hashes[key] = digest
        return hashes
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot validate prepared inputs: {error}") from error


def parse_newc(archive):
    entries = {}
    cursor = 0
    while cursor < len(archive):
        if cursor + 110 > len(archive) or archive[cursor:cursor + 6] != b"070701":
            raise ValueError(f"newc header missing or truncated at {cursor}")
        header = archive[cursor + 6:cursor + 110]
        if any(value not in b"0123456789abcdefABCDEF" for value in header):
            raise ValueError("newc header contains a non-hexadecimal field")
        fields = [int(header[start:start + 8], 16) for start in range(0, 104, 8)]
        mode, nlink, size, namesize = fields[1], fields[4], fields[6], fields[11]
        start = cursor + 110
        if not namesize or start + namesize > len(archive):
            raise ValueError("newc name size exceeds archive bounds")
        raw_name = archive[start:start + namesize]
        if raw_name[-1:] != b"\0" or b"\0" in raw_name[:-1]:
            raise ValueError("newc entry name is not NUL-terminated")
        try:
            name = raw_name[:-1].decode("utf-8")
        except UnicodeError as error:
            raise ValueError("newc entry name is not UTF-8") from error
        data_start = align(start + namesize, 4)
        cursor = align(data_start + size, 4)
        if cursor > len(archive):
            raise ValueError("newc file size exceeds archive bounds")
        if name == "TRAILER!!!":
            if size or any(archive[cursor:]):
                raise ValueError("newc trailer has data or nonzero trailing bytes")
            return entries
        if name.startswith("/") or (nlink != 1 and not stat.S_ISDIR(mode)):
            raise ValueError("newc entry has an absolute path or hardlink")
        if ".." in name.split("/"):
            raise ValueError("newc path traverses outside ramdisk")
        name = name.lstrip("/")
        while name.startswith("./"):
            name = name[2:]
        if not name or name in entries:
            raise ValueError(f"newc empty or duplicate path: {name!r}")
        entries[name] = (mode, archive[data_start:data_start + size])
    raise ValueError("newc archive lacks TRAILER!!!")


def validate_ramdisk(compressed):
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            archive = stream.read(MAX_UNCOMPRESSED_RAMDISK + 1)
    except (OSError, EOFError, zlib.error) as error:
        raise ValueError(f"ramdisk is not valid gzip: {error}") from error
    if len(archive) > MAX_UNCOMPRESSED_RAMDISK:
        raise ValueError(f"uncompressed ramdisk exceeds {MAX_UNCOMPRESSED_RAMDISK} bytes")
    entries = parse_newc(archive)
    for name in ("sbin/recovery", "etc/recovery.fstab"):
        if name not in entries:
            raise ValueError(f"ramdisk lacks {name}")
        mode, content = entries[name]
        if not stat.S_ISREG(mode) or not content or (name == "sbin/recovery" and not mode & 0o111):
            raise ValueError(f"{name} must be a nonempty regular file; recovery must be executable")
    try:
        text = entries["etc/recovery.fstab"][1].decode("utf-8")
    except UnicodeError as error:
        raise ValueError("recovery.fstab must be UTF-8") from error
    mounts = {}
    for line in text.splitlines():
        tokens = line.split("#", 1)[0].split()
        if not tokens:
            continue
        if len(tokens) < 3 or tokens[0] in mounts:
            raise ValueError("recovery.fstab has a malformed or duplicate mount entry")
        mounts[tokens[0]] = tuple(tokens[1:3])
    for mount, expected in FSTAB.items():
        if mounts.get(mount) != expected:
            raise ValueError(f"recovery.fstab requires {mount} {expected[0]} {expected[1]}")
    return sorted(mounts)


def verify(candidate, directory):
    hashes = prepared_inputs(directory)
    data = read_image(candidate)
    parsed = parse_image(data)
    for key, label in (("kernel", "kernel"), ("dt", "QCDT")):
        if parsed[key]["sha256"] != hashes[key]:
            raise ValueError(f"{label} bytes differ from prepared inputs; rebuild with the extracted prebuilt")
    section = parsed["ramdisk"]
    mounts = validate_ramdisk(data[section["offset"]:section["offset"] + section["size"]])
    return {"valid": True, "image_size": len(data),
            "image_sha256": hashlib.sha256(data).hexdigest(), **parsed,
            "fstab_mounts": mounts, "signature_authenticated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("prepared_directory", type=Path)
    args = parser.parse_args()
    try:
        report = verify(args.image, args.prepared_directory)
    except (OSError, ValueError) as error:
        print(f"verify_twrp_image: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
