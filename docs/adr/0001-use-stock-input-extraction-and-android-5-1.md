# 1. Use Stock input extraction and the Android 5.1 recovery base

Date: 2026-10-12

## Status

Accepted

## Context

The original 2019 tree stored kernel and QCDT binaries in Git.
It targeted an Android 7.1 recovery base.
The production firmware uses Android 5.1.1.

A source-built TWRP 3.7.0_9 image booted on a Coolpad Rouge 3320A.
It used the Android 5.1 recovery base and exact Stock kernel and QCDT bytes.
The first build rendered correctly but rejected valid zero-major touch reports.

## Decision

Target the pinned Android 5.1 recovery base.
Extract kernel and QCDT inputs from an exact-model Stock recovery outside Git.
Enable `TW_IGNORE_MAJOR_AXIS_0` for the FocalTech touchscreen.

Reject the original Android 7.1 base because it differs from the Stock platform.
Reject committed proprietary binaries because builders can derive them locally.
Reject coordinate transforms because live coordinates were already correct.

## Consequences

The fork preserves the original history, including its legacy binary objects.
The current branch tip removes those binary paths.
Builders must possess a compatible Stock recovery image.
The host verifier can prove byte preservation before a device write.
The battery percentage remains unavailable until a compatible VM-BMS reader exists.
