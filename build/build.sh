#!/bin/bash
# build.sh - Inject this device tree into the twrp51-src Docker volume and
# build the TWRP recovery image in the pinned build-host image.
#
# Modes:
#   (default)        check + inject + build + extract recovery image.
#   --prepare-only   input hash check + device tree injection only.
#   --lunch-only     check + inject + envsetup/lunch, no mka/make.
#
# The kernel and dt.img committed at HEAD are the build inputs. Logs and out/ are
# written to WORK_DIR.
#
# Environment:
#   DOCKER_CONTEXT    passed as --context when set; never switched globally.
#   TWRP_BUILD_IMAGE  build-host image (default twrp51-build:r2).
#   TWRP_SRC_VOLUME   synchronized source volume (default twrp51-src).
#   JOBS              parallel make jobs (default 12).
set -euo pipefail

# --- Constants -------------------------------------------------------------
DOCKER=(docker)
[ -z "${DOCKER_CONTEXT:-}" ] || DOCKER+=(--context "$DOCKER_CONTEXT")
readonly DOCKER
readonly VOLUME="${TWRP_SRC_VOLUME:-twrp51-src}"
readonly IMAGE="${TWRP_BUILD_IMAGE:-twrp51-build:r2}"
readonly PLATFORM=linux/amd64

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
DEVICE_TREE_HOST="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly DEVICE_TREE_HOST
WORK_DIR=
OUT_DIR=

readonly DEVICE_TREE_VOL=/src/device/coolpad/cp3320a

readonly KERNEL_SHA256=21851bee493e95c8b0aa94f1e2eb7ca920552794b25db56aff1016f592cf2c3e
readonly DT_SHA256=e543d6c7cc697db1e7ad9cd79f5eb2f5939f53e31ae899a9354a589b9f16bc4d

JOBS="${JOBS:-12}"
readonly JOBS

extract_cid=
cleanup() {
  if [ -n "$extract_cid" ]; then
    "${DOCKER[@]}" rm -v "$extract_cid" >/dev/null || return "$?"
  fi
}
trap cleanup EXIT

# --- Small helpers ---------------------------------------------------------
die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
usage: build.sh --work-dir DIR [--prepare-only | --lunch-only]

  --work-dir DIR directory for build logs and out/.
  (no mode)      input hash check, inject device tree, build recoveryimage,
                 extract recovery.img and ramdisk-files.txt.
  --prepare-only input hash check and device tree injection only.
  --lunch-only   hash check, injection, envsetup + lunch; no mka/make.
USAGE
}

# --- Step 1: committed-input hash verification -------------------------------
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

verify_input_hashes() {
  local kernel dt
  [ -f "$DEVICE_TREE_HOST/kernel" ] || die "missing $DEVICE_TREE_HOST/kernel"
  [ -f "$DEVICE_TREE_HOST/dt.img" ] || die "missing $DEVICE_TREE_HOST/dt.img"
  kernel="$(sha256_of "$DEVICE_TREE_HOST/kernel")"
  dt="$(sha256_of "$DEVICE_TREE_HOST/dt.img")"
  [ "$kernel" = "$KERNEL_SHA256" ] \
    || die "kernel SHA-256 mismatch: got $kernel expected $KERNEL_SHA256"
  [ "$dt" = "$DT_SHA256" ] \
    || die "dt.img SHA-256 mismatch: got $dt expected $DT_SHA256"
  printf 'Input hashes verified (kernel, dt.img).\n'
}

# --- Step 2: inject device tree into the source volume ---------------------
# Throwaway container; named volume at /src. git archive streams the files of
# HEAD only, so ignored and untracked host files never reach the volume.
inject_device_tree() {
  # Container Bash expands these variables.
  # shellcheck disable=SC2016
  git -C "$DEVICE_TREE_HOST" archive --format=tar HEAD \
  | "${DOCKER[@]}" run --rm -i --platform "$PLATFORM" \
    -v "$VOLUME":/src \
    -e KERNEL_SHA256="$KERNEL_SHA256" \
    -e DT_SHA256="$DT_SHA256" \
    -e DEVICE_TREE_VOL="$DEVICE_TREE_VOL" \
    "$IMAGE" bash -euo pipefail -c '
      set -euo pipefail
      dest="$DEVICE_TREE_VOL"
      rm -rf "$dest"
      mkdir -p "$dest"
      tar -C "$dest" -xf -
      kernel="$(sha256sum "$dest/kernel" | awk "{print \$1}")"
      dt="$(sha256sum "$dest/dt.img" | awk "{print \$1}")"
      [ "$kernel" = "$KERNEL_SHA256" ] || { echo "error: in-volume kernel hash mismatch: $kernel" >&2; exit 1; }
      [ "$dt" = "$DT_SHA256" ] || { echo "error: in-volume dt.img hash mismatch: $dt" >&2; exit 1; }
      echo "Device tree injected at $dest; input hashes re-verified in volume."
    '
  printf 'Device tree injection complete.\n'
}


# --- Step 3: full build ------------------------------------------------------
# Returns the build exit code; stdout+stderr are tee'd to the log file.
run_build() {
  local log_file="$1"
  local status
  local -a pipeline_status
  set +e
  # Container Bash, not the host shell, expands the command's variables.
  # shellcheck disable=SC2016
  "${DOCKER[@]}" run --rm --platform "$PLATFORM" \
    -v "$VOLUME":/src \
    -e USER=builder \
    -e HOME=/tmp \
    -e LC_ALL=C \
    -e USE_CCACHE= \
    -e CCACHE_DISABLE=1 \
    -e JOBS="$JOBS" \
    -e BUILD_MODE="$2" \
    "$IMAGE" bash -lc '
      unset USE_CCACHE
      # A login shell can replace the image PATH; restore its pinned tools.
      export PATH="$JAVA_HOME/bin:/opt/make381/usr/bin:$PATH"
      cd /src && source build/envsetup.sh && lunch omni_cp3320a-eng && \
      if [ "$BUILD_MODE" = lunch ]; then
        printf "%s\n" "Lunch-only mode: no build."
      elif type mka >/dev/null 2>&1; then \
        mka recoveryimage -j"$JOBS"; \
      else \
        make -j"$JOBS" recoveryimage; \
      fi
    ' 2>&1 | tee "$log_file"
  pipeline_status=("${PIPESTATUS[@]}")
  status=${pipeline_status[0]}
  set -e
  printf 'Build exit code: %d (log: %s)\n' "$status" "$log_file" | tee -a "$log_file" || return 1
  if [ "${pipeline_status[1]}" -ne 0 ]; then
    printf 'error: tee failed while recording the build log\n' >&2
    [ "$status" -ne 0 ] || return "${pipeline_status[1]}"
  fi
  return "$status"
}

# --- Step 4: extract outputs -------------------------------------------------
# docker create + docker cp for recovery.img; a short --rm run emits the
# ramdisk file listing on stdout. No bind mounts are used for extraction.
extract_outputs() {
  mkdir -p "$OUT_DIR"
  extract_cid="$("${DOCKER[@]}" create --platform "$PLATFORM" -v "$VOLUME":/src "$IMAGE" true)"
  "${DOCKER[@]}" cp "$extract_cid":/src/out/target/product/cp3320a/recovery.img \
    "$OUT_DIR/recovery.img"
  "${DOCKER[@]}" rm -v "$extract_cid" >/dev/null
  extract_cid=

  "${DOCKER[@]}" run --rm --platform "$PLATFORM" \
    -v "$VOLUME":/src \
    "$IMAGE" bash -eo pipefail -c '
      cd /src/out/target/product/cp3320a/recovery/root && find . | sort
    ' > "$OUT_DIR/ramdisk-files.txt"
  test -s "$OUT_DIR/recovery.img"
  test -s "$OUT_DIR/ramdisk-files.txt"
  printf 'Extracted %s and %s\n' \
    "$OUT_DIR/recovery.img" "$OUT_DIR/ramdisk-files.txt"
}

# --- Main --------------------------------------------------------------------
main() {
  local mode=full
  while [ $# -gt 0 ]; do
    case "$1" in
      --work-dir)
        [ $# -ge 2 ] || { usage >&2; die "--work-dir needs a directory"; }
        WORK_DIR="$2"
        shift ;;
      --prepare-only|--lunch-only)
        [ "$mode" = full ] || { usage >&2; die "choose at most one mode flag"; }
        mode="${1#--}"
        mode="${mode%-only}" ;;
      -h|--help) usage; exit 0 ;;
      *) usage >&2; die "unknown flag: $1" ;;
    esac
    shift
  done
  [ -n "$WORK_DIR" ] || { usage >&2; die "--work-dir is required"; }
  [ -d "$WORK_DIR" ] || die "work directory not found: $WORK_DIR"
  WORK_DIR="$(cd "$WORK_DIR" && pwd)"
  OUT_DIR="$WORK_DIR/out"
  readonly WORK_DIR OUT_DIR
  command -v git >/dev/null 2>&1 || die "git not found"
  local dirty
  local toplevel
  toplevel="$(git -C "$DEVICE_TREE_HOST" rev-parse --show-toplevel 2>/dev/null)" \
    || die "device tree is not in a git checkout: $DEVICE_TREE_HOST"
  [ "$(cd "$toplevel" && pwd -P)" = "$(cd "$DEVICE_TREE_HOST" && pwd -P)" ] \
    || die "device tree is not the root of its git checkout: $DEVICE_TREE_HOST"
  dirty="$(git -C "$DEVICE_TREE_HOST" status --porcelain --untracked-files=no)"
  [ -z "$dirty" ] || die "device tree has uncommitted changes:"$'\n'"$dirty"

  verify_input_hashes
  inject_device_tree
  [ "$mode" = prepare ] && { printf '%s\n' 'Prepare-only mode: stopping before build.'; exit 0; }

  local timestamp log_file
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  log_file="$WORK_DIR/build-$timestamp.log"
  local status=0
  run_build "$log_file" "$mode" || status=$?
  if [ "$status" -ne 0 ]; then
    printf 'error: build/lunch failed; see %s\n' "$log_file" >&2
    exit "$status"
  fi
  [ "$mode" != lunch ] || return 0
  extract_outputs
  printf '%s\n' 'Build and extraction complete.'
}

main "$@"
