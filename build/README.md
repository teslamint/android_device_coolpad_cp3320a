# Containerized recovery build

These files rebuild the CP3320A TWRP recovery image from pinned inputs in containers.
The host needs no Android source tree.

| File | Purpose |
|---|---|
| `Dockerfile` | Two `linux/amd64` stages: `repo-host` (source sync) and `build-host` (AOSP 5.1 build). |
| `manifest-pinned.xml` | `repo manifest -r` output of the source tree that built the live-tested image. All 68 projects are pinned by SHA. |
| `sync.sh` | Runs in `repo-host`. Syncs the pinned tree into `/src`, checks every project HEAD, and applies `patches/bootable_recovery/`. |
| `build.sh` | Runs on the host. Injects this device tree, runs `mka recoveryimage`, and extracts the image. |

## Requirements

- Docker that can run `linux/amd64` containers. On Apple Silicon, use Colima with VZ and Rosetta.
- Or, on Linux, rootless Podman with the setup in [Podman hosts](#podman-hosts).
- About 8 GB of container volume space: 6.8 GB of source and 0.5 GB of recovery build output were measured.
- Python 3 on the host, for `tools/`.
- Network access to GitHub, `android.googlesource.com`, `gerrit.googlesource.com`, `storage.googleapis.com`, `cdn.azul.com`, and the Ubuntu archives.
- Git on the host. `build.sh` builds the files committed at `HEAD` and refuses a checkout with uncommitted changes to tracked files.

The committed `kernel` and `dt.img` are the build inputs.
`build.sh` accepts only the SHA-256 values listed in the [top-level README](../README.md#stock-inputs).

Run every command in this file from the repository root.
First choose a work directory. Docker must be able to bind-mount the repository for the sync step; Colima shares only `$HOME` by default.
The ignored `.work/` directory works:

```sh
WORK="$PWD/.work/$(date -u +%Y%m%d)"
mkdir -p "$WORK"
```

## Podman hosts

`build.sh` and the commands below call `docker`. On a Linux host with rootless Podman and no Docker, a `docker` shim is enough.
The steps below keep all Podman settings in `.work/podman/` and change no global configuration.

1. Create the settings and the shim:

   ```sh
   P="$PWD/.work/podman"
   mkdir -p "$P/bin"
   printf '[storage]\ndriver = "vfs"\ngraphroot = "%s/storage"\nrunroot = "%s/run"\n' "$P" "$P" > "$P/storage.conf"
   printf 'unqualified-search-registries = ["docker.io"]\nshort-name-mode = "permissive"\n' > "$P/registries.conf"
   printf '#!/bin/sh\nexec podman "$@"\n' > "$P/bin/docker"
   chmod 755 "$P/bin/docker"
   ```

2. Export the settings in every shell that runs the build:

   ```sh
   export CONTAINERS_STORAGE_CONF="$PWD/.work/podman/storage.conf"
   export CONTAINERS_REGISTRIES_CONF="$PWD/.work/podman/registries.conf"
   export PATH="$PWD/.work/podman/bin:$PATH"
   ```

Notes:

- Rootless overlay storage failed on the tested host, whose home directory is on ZFS. `vfs` storage worked there. On other filesystems, the default driver can work; `vfs` is slower and uses more disk.
- Do not set `DOCKER_CONTEXT` with the shim. `podman` does not accept the `--context` flag that `build.sh` adds.
- The `registries.conf` lines let the unqualified `FROM ubuntu:...` lines resolve to Docker Hub.
- `podman build` mounts the build context with overlayfs, even with `vfs` storage. The running kernel must have the `overlay` module. A kernel package update can remove the modules of the running kernel from `/lib/modules`. The build then fails with `mounting an overlay over build context ... no such device`. Reboot into the installed kernel.
- `JOBS=8` passed on a 14 GB host. The default `JOBS=12` was not tested on that host. Lower `JOBS` if the build runs out of memory.

## Build

Use the same shell, so `WORK` stays set.
To use a non-default Docker context, run `export DOCKER_CONTEXT=<name>` once. The `docker` CLI and `build.sh` both read it.

1. Build both images:

   ```sh
   docker build --platform linux/amd64 --target repo-host -t twrp51-repo:r2 build
   docker build --platform linux/amd64 --target build-host -t twrp51-build:r2 build
   ```

2. Create the source volume and sync it (shallow clones of all 68 projects):

   ```sh
   docker volume create twrp51-src
   docker run --rm --platform linux/amd64 -v twrp51-src:/src \
     --mount type=bind,src="$PWD",dst=/mnt/cp3320a,readonly \
     twrp51-repo:r2 bash /mnt/cp3320a/build/sync.sh
   ```

   A pass prints `68/68 projects at pinned commits` and one `Applied:` line for each patch.
   A repeated run prints `Already applied:` instead.

3. Build the recovery image:

   ```sh
   build/build.sh --work-dir "$WORK"
   ```

   `--lunch-only` stops after `lunch` and checks the environment in a few minutes.
   `--prepare-only` stops after the device tree injection.
   The output is `$WORK/out/recovery.img` and `$WORK/out/ramdisk-files.txt`. The log is `$WORK/build-<UTC time>.log`.

4. Verify the image. The verifier needs inputs extracted from a Stock recovery image.
   The public TwrpBuilder 3.2.3 image uses the same kernel and QCDT. `$WORK/prepared` must not exist yet:

   ```sh
   curl -fsSL -o "$WORK/tb.img" https://github.com/TwrpBuilderTests/android_device_coolpad_cp3320a/releases/download/TWRP-3.2.3-TwrpBuilder-2019-03-21_04-58/TWRP-3.2.3-TwrpBuilder-cp3320a-2019-03-21_04-58.img
   echo "c56645d38c6157b4daaee283faee8ed04cee928aeaafdd2f947fa29a56c0e618  $WORK/tb.img" | shasum -a 256 -c -
   python3 tools/prepare_twrp_inputs.py "$WORK/tb.img" "$WORK/prepared"
   python3 tools/verify_twrp_image.py "$WORK/out/recovery.img" "$WORK/prepared"
   ```

   On Linux, `sha256sum -c -` does the same check as `shasum -a 256 -c -`.
   A dump of your own device's Stock recovery partition can replace `tb.img`.
   This check is static. It does not prove that the image boots.

## Tested hosts

| Date | Host | Engine | Source | Result |
|---|---|---|---|---|
| 2026-10-12 | Apple Silicon Mac, Colima VZ + Rosetta | Docker | earlier private-repository layout, same scripts | `verify_twrp_image` valid |
| 2026-10-13 | x86_64 CachyOS, 16 cores, 14 GB RAM, ZFS home | rootless Podman 6.1.3, `vfs` | earlier private-repository layout, fresh clone, empty volume, `JOBS=8` | all steps passed in about 5 minutes; `verify_twrp_image` valid |
| 2026-10-13 | same CachyOS host | rootless Podman 6.1.3, `vfs` | this layout, fresh clone, new Podman storage, empty volume, `JOBS=8` | all steps passed in about 5 minutes; `68/68 projects at pinned commits`; `verify_twrp_image` valid |

## Limits

- Ubuntu packages are not pinned by version. The 16.04 archive no longer changes; the 22.04 `repo-host` packages can change.
- The output image is not bit-for-bit reproducible. The images from the Mac and the first CachyOS run have the same size, kernel, `dt.img`, command line, and ramdisk file list. File modes, owners, and modification times are identical. Nine ramdisk files differ in content:
  - `default.prop` and `selinux_version` differ only in the build date, time, and container host name.
  - `sbin/busybox` and `sbin/nano` differ only in the build date string.
  - `sbin/adbd`, `sbin/healthd`, and `sbin/linker` contain the same strings in a different order.
  - `init` and `sbin/libc.so` also differ in a small number of strings. `libc.so` is 48 bytes larger on the Mac build.
  - The cause of the binary differences is not confirmed. A possible cause is a different directory listing order on each filesystem, which changes the link order.
  - The header `id` field and the image SHA-256 follow these differences.

## License

The TWRP and AOSP sources are under their own licenses, mostly Apache 2.0 and GPL v2.
A distributed `recovery.img` contains a GPL v2 Linux kernel. If you distribute it, you must meet the GPL source-offer terms for that kernel.
