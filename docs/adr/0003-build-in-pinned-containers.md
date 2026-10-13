# 3. Build in pinned containers

Date: 2026-10-13

## Status

Accepted

## Context

The live-tested image was built in an Android 5.1 source tree prepared by hand.
That tree needs an old toolchain: OpenJDK 7, GNU make 3.81, and Ubuntu 16.04 packages.
A builder without that setup could not rebuild the image from this repository alone.

## Decision

Add `build/` with a two-stage `linux/amd64` Dockerfile, a pinned `repo` manifest, a sync script, and a build script.
Pin base images by digest and downloaded tools by SHA-256.
Pin all 68 source projects by commit.
Inject this checkout into the source volume and use the committed `kernel` and `dt.img`.

Rejected: document the manual source setup only. A manual setup drifts and was not reproduced on a second host.
Rejected: commit a built `recovery.img`. A built image does not show how to rebuild it.

## Consequences

A fresh clone of this repository built and verified on a Linux host with rootless Podman.
The Docker path was tested on an Apple Silicon Mac with the same scripts in an earlier repository layout.
The output is not bit-for-bit reproducible; `build/README.md` lists the known differences.
Ubuntu packages are not pinned by version.
