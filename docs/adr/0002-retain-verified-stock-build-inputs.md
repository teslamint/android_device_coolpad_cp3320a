# 2. Retain verified Stock build inputs

Date: 2026-10-12

## Status

Accepted

Supersedes the binary-input decision in
[ADR 0001](0001-use-stock-input-extraction-and-android-5-1.md).

## Context

The upstream fork committed a Stock kernel and QCDT image in 2019.
ADR 0001 removed their paths from the branch tip and required local extraction.
The fork still distributed the same objects through its Git history.

The upstream files match the live-tested Stock inputs byte for byte.
Their SHA-256 values are `21851bee493e95c8b0aa94f1e2eb7ca920552794b25db56aff1016f592cf2c3e`
and `e543d6c7cc697db1e7ad9cd79f5eb2f5939f53e31ae899a9354a589b9f16bc4d`.

## Decision

Retain `kernel` and `dt.img` at their upstream paths as the default build inputs.
Keep the Stock extractor and image verifier for independent byte comparison.

Do not restore the obsolete `kernel.mk` include or duplicate recovery fstab.
The current `BoardConfig.mk` and `recovery.fstab` replace those files.

## Consequences

A normal clone contains the inputs required to build the tested recovery.
Builders can still compare them with an exact-model Stock recovery image.
The repository continues to carry binary inputs already present in fork history.
