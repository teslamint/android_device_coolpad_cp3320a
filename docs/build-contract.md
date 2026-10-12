# CP3320A TWRP build contract

## Scope

This tree builds TWRP 3.7.0_9 on the Android 5.1 recovery base.
It targets only the Coolpad Rouge 3320A, device name `cp3320a`.

## Required inputs

The current branch includes the live-tested Stock kernel and QCDT inputs:

- `kernel` with SHA-256
  `21851bee493e95c8b0aa94f1e2eb7ca920552794b25db56aff1016f592cf2c3e`;
- `dt.img` with SHA-256
  `e543d6c7cc697db1e7ad9cd79f5eb2f5939f53e31ae899a9354a589b9f16bc4d`.

`tools/prepare_twrp_inputs.py` extracts independent copies and a receipt from
an exact-model Stock recovery image. The extractor rejects incompatible
headers, QCDT metadata, and partition sizes. Builders can compare these copies
with the committed inputs before building.

## Build interfaces

Clone this repository at `device/coolpad/cp3320a`.
Apply `patches/bootable_recovery/0001-partition-nullptr-to-null.patch` to the
pinned TWRP recovery source before building.

The product name is `omni_cp3320a`.
The target uses 32-bit ARM and Qualcomm MSM8909 hardware.
The recovery partition limit is 16,777,216 bytes.

## Verification

`tools/verify_twrp_image.py` must accept the built image before any device write.
It checks the boot header, partition ceiling, kernel, QCDT, ramdisk, and fstab.

The live acceptance checks are:

1. TWRP renders at 480 by 800 pixels.
2. Touch input selects controls.
3. ADB starts in recovery mode.
4. TWRP discovers the named GPT partitions.

The battery percentage is unavailable without the Stock VM-BMS userspace reader.
The `0%+` display does not prove that the battery is empty.
