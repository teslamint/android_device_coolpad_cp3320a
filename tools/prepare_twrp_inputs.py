#!/usr/bin/env python3
"""Extract CP3320A kernel/QCDT inputs; never verify or alter acquisition evidence.

Usage: python3 -m tools.prepare_twrp_inputs IMAGE OUTPUT_DIRECTORY
An existing directory is allowed only when all three output names are absent.
The deterministic receipt is published last. No acquisition manifest is read.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

PARTITION_SIZE = 16777216
PAGE_SIZE = 2048
KERNEL_SIZE = 6509208
DT_SIZE = 149504
MAX_RAMDISK = 10112575


def align(size, boundary=PAGE_SIZE):
    return (size + boundary - 1) // boundary * boundary


def read_image(path):
    with path.open("rb") as stream:
        data = stream.read(PARTITION_SIZE + 1)
    if len(data) > PARTITION_SIZE:
        raise ValueError(f"image exceeds {PARTITION_SIZE}-byte recovery partition")
    return data


def der_element(data, cursor, tag):
    """Read a definite-length DER element without escaping its enclosing bytes."""
    if cursor + 2 > len(data) or data[cursor] != tag:
        raise ValueError("signature has an invalid DER field")
    first = data[cursor + 1]
    start = cursor + 2
    if first < 128:
        length = first
    else:
        count = first & 127
        if not 1 <= count <= 4 or start + count > len(data):
            raise ValueError("signature DER length is invalid")
        length = int.from_bytes(data[start:start + count], "big")
        if length < 128 or data[start] == 0:
            raise ValueError("signature DER length is not canonical")
        start += count
    end = start + length
    if end > len(data):
        raise ValueError("signature exceeds image size")
    return data[start:end], end


def signature_extent(data, unsigned_end):
    trailer = data[unsigned_end:]
    if not any(trailer):
        return None
    sequence, end = der_element(trailer, 0, 0x30)
    version, cursor = der_element(sequence, 0, 0x02)
    if version != b"\x01":
        raise ValueError("signature format version must be 1")
    _, cursor = der_element(sequence, cursor, 0x30)  # certificate
    _, cursor = der_element(sequence, cursor, 0x30)  # algorithm
    attrs, cursor = der_element(sequence, cursor, 0x30)
    _, finish = der_element(sequence, cursor, 0x04)
    target, attribute_cursor = der_element(attrs, 0, 0x13)
    length, attribute_end = der_element(attrs, attribute_cursor, 0x02)
    if (target not in (b"/boot", b"/recovery") or attribute_end != len(attrs)
            or not length or length[0] & 128 or len(length) > 5
            or int.from_bytes(length, "big") != unsigned_end):
        raise ValueError("signature authenticated length overlaps or differs from image layout")
    if finish != len(sequence) or any(trailer[end:]):
        raise ValueError("signature has unexpected trailing bytes")
    # Structural extent only. No certificate trust or cryptographic claim.
    return {"offset": unsigned_end, "size": end}


def validate_qcdt(dt):
    if len(dt) != DT_SIZE or dt[:4] != b"QCDT":
        raise ValueError("QCDT magic or size differs from CP3320A contract")
    version, count = struct.unpack_from("<2I", dt, 4)
    if (version, count) != (3, 1):
        raise ValueError("QCDT must contain one version-3 entry")
    # Version 3: platform, variant, subtype, soc_rev, pmic_rev[4], offset, size.
    entry = struct.unpack_from("<10I", dt, 12)
    offset, size = entry[8:10]
    if entry[:2] != (0x103, 8):
        raise ValueError("QCDT platform/variant must be 0x103/0x8")
    if offset < 52 or size == 0 or offset + size > len(dt):
        raise ValueError("QCDT entry overlaps its header or exceeds container size")
    if size < 8 or dt[offset:offset + 4] != b"\xd0\x0d\xfe\xed":
        raise ValueError("QCDT entry does not contain an FDT")
    total_size = struct.unpack_from(">I", dt, offset + 4)[0]
    if total_size < 40 or total_size > size:
        raise ValueError("FDT total size exceeds its QCDT entry")


def parse_image(data):
    if data[:8] != b"ANDROID!":
        raise ValueError("Android boot magic must be ANDROID!")
    if len(data) < PAGE_SIZE:
        raise ValueError("Android v0 header is truncated")
    fields = struct.unpack_from("<10I", data, 8)
    kernel_size, kernel_addr, ram_size, ram_addr, second_size, second_addr, tags, page, dt_size, os_version = fields
    fixed = {"kernel_size": (kernel_size, KERNEL_SIZE),
             "kernel_addr": (kernel_addr, 0x80008000),
             "ramdisk_addr": (ram_addr, 0x81000000),
             "second_size": (second_size, 0),
             "second_addr": (second_addr, 0x80F00000),
             "tags_addr": (tags, 0x80000100), "page_size": (page, PAGE_SIZE),
             "dt_size": (dt_size, DT_SIZE)}
    for name, (actual, expected) in fixed.items():
        if actual != expected:
            raise ValueError(f"header {name}: expected {expected:#x}, found {actual:#x}")
    if not 0 < ram_size <= MAX_RAMDISK:
        raise ValueError(f"ramdisk size must be 1..{MAX_RAMDISK} bytes")
    ram_offset = PAGE_SIZE + align(kernel_size)
    dt_offset = ram_offset + align(ram_size)
    unsigned_end = dt_offset + align(dt_size)
    if unsigned_end > PARTITION_SIZE:
        raise ValueError("image sections overlap recovery partition boundary")
    if unsigned_end > len(data):
        raise ValueError("image size is smaller than declared page-aligned sections")
    sections = {"kernel": {"offset": PAGE_SIZE, "size": kernel_size},
                "ramdisk": {"offset": ram_offset, "size": ram_size},
                "dt": {"offset": dt_offset, "size": dt_size}}
    for name, section in sections.items():
        start, size = section["offset"], section["size"]
        end = start + size
        if any(data[end:start + align(size)]):
            raise ValueError(f"{name} padding overlaps signature or contains nonzero bytes")
        section["sha256"] = hashlib.sha256(memoryview(data)[start:end]).hexdigest()
    validate_qcdt(data[dt_offset:dt_offset + dt_size])
    return {"page_size": page, "os_version": os_version, **sections,
            "unsigned_size": unsigned_end,
            "signature": signature_extent(data, unsigned_end)}


def prepare(source, output):
    try:
        data = read_image(source)
    except OSError as error:
        raise ValueError(f"cannot read input image: {error}") from error
    parsed = parse_image(data)
    receipt = {"format": "cp3320a-twrp-inputs-v1", "page_size": PAGE_SIZE,
               "os_version": parsed["os_version"],
               "kernel": parsed["kernel"], "dt": parsed["dt"]}
    names = ("kernel", "dt.img", "receipt.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        output.mkdir(mode=0o700)
    except FileExistsError as error:
        raise ValueError("output directory must not already exist") from error

    directory_fd = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    published = []
    try:
        payloads = []
        for key, filename in (("kernel", "kernel"), ("dt", "dt.img")):
            section = parsed[key]
            content = memoryview(data)[section["offset"]:section["offset"] + section["size"]]
            payloads.append((filename, content))
        payloads.append(("receipt.json",
                         (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()))
        for filename, content in payloads:
            descriptor = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                 0o600, dir_fd=directory_fd)
            try:
                view = memoryview(content)
                while view:
                    view = view[os.write(descriptor, view):]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            published.append(filename)
        os.fsync(directory_fd)
    except OSError:
        for filename in reversed(published):
            try:
                os.unlink(filename, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        raise
    finally:
        os.close(directory_fd)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    try:
        receipt = prepare(args.image, args.output_directory)
    except (OSError, ValueError) as error:
        print(f"prepare_twrp_inputs: {error}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
