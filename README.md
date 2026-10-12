# TWRP for Coolpad Rouge 3320A

This fork contains the live-tested device tree for the Coolpad Rouge 3320A.
It builds TWRP 3.7.0_9 on the Android 5.1 recovery base.
It preserves the history of
[`TwrpBuilderTests/android_device_coolpad_cp3320a`](https://github.com/TwrpBuilderTests/android_device_coolpad_cp3320a).

The tested image provides these functions:

- a 480 by 800 graphical interface;
- working FocalTech touch input;
- root Android Debug Bridge access;
- discovery of the named GPT partitions.

## Source base

The tested build used these pinned revisions:

- `minimal-manifest-twrp/platform_manifest_twrp_omni@480e606e8ccf27dfe3c2e8e517a3be3cc911fd44`
- `TeamWin/android_bootable_recovery@90e5d9559065cfa8b2b9a5dbb1c5cb7a88f034fa`

Clone this repository into the source tree:

```sh
git clone https://github.com/teslamint/android_device_coolpad_cp3320a \
  device/coolpad/cp3320a
```

## Stock inputs

The repository includes the upstream Stock kernel and QCDT build inputs.
They match the inputs used by the live-tested image:

- `kernel`: `21851bee493e95c8b0aa94f1e2eb7ca920552794b25db56aff1016f592cf2c3e`
- `dt.img`: `e543d6c7cc697db1e7ad9cd79f5eb2f5939f53e31ae899a9354a589b9f16bc4d`

To compare them with an exact-model Stock recovery, run the extractor outside
the device-tree directory:

```sh
python3 device/coolpad/cp3320a/tools/prepare_twrp_inputs.py \
  stock-recovery.img /tmp/cp3320a-prepared
cmp device/coolpad/cp3320a/kernel /tmp/cp3320a-prepared/kernel
cmp device/coolpad/cp3320a/dt.img /tmp/cp3320a-prepared/dt.img
```

The extractor rejects an image that differs from the CP3320A boot contract.
The comparison succeeds only when both extracted inputs match byte for byte.

The live-tested image had SHA-256
`527c74eabf71f44427e429fca5176a588c5958bfd5543d3c2f950976a4044757`.
This digest is a reference result, not a substitute for local verification.

## Build

Apply the compatibility patch from the Android source-tree root:

```sh
git -C bootable/recovery apply \
  ../../device/coolpad/cp3320a/patches/bootable_recovery/0001-partition-nullptr-to-null.patch
source build/envsetup.sh
lunch omni_cp3320a-eng
mka recoveryimage
```

Verify the image before any device write:

```sh
python3 device/coolpad/cp3320a/tools/verify_twrp_image.py \
  out/target/product/cp3320a/recovery.img \
  /tmp/cp3320a-prepared
```

## Test the host tools

```sh
python3 -m unittest discover -s tests
```

## Known limitation

TWRP displays `0%+` because recovery does not run the Stock VM-BMS reader.
The display does not prove that the battery is empty.
Do not copy the proprietary Stock daemon into a public build.

Read [the build contract](docs/build-contract.md) before changing image geometry.
