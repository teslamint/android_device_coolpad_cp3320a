# CP3320A TWRP build contract

## Scope

This tree builds TWRP 3.7.0_9 on the Android 5.1 recovery base.
It targets only the Coolpad Rouge 3320A, device name `cp3320a`.

## Required inputs

The current branch does not include a kernel, device tree, or recovery image.
The inherited fork history still contains the original 2019 binary inputs.
The builder must supply an exact-model Stock recovery image.

`tools/prepare_twrp_inputs.py` extracts these local build inputs:

- `prebuilt/kernel`
- `prebuilt/dt.img`
- an extraction receipt

The extractor rejects incompatible headers, QCDT metadata, and partition sizes.
The build must preserve the extracted kernel and QCDT bytes.

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
