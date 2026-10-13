#!/bin/bash
# sync.sh - Fetch the pinned twrp-5.1 source tree into /src and patch it.
#
# Runs inside the repo-host image, not on the host:
#   docker run --rm --platform linux/amd64 -v twrp51-src:/src \
#     --mount type=bind,src="$PWD",dst=/mnt/cp3320a,readonly \
#     twrp51-repo:r2 bash /mnt/cp3320a/build/sync.sh
#
# manifest-pinned.xml fixes every project at a commit SHA. It is the
# `repo manifest -r` output of the 2026-10-12 source tree that built the
# accepted image. The manifest repository commit only seeds the .repo client.
set -euxo pipefail
readonly TREE=/mnt/cp3320a
readonly MANIFEST_COMMIT=480e606e8ccf27dfe3c2e8e517a3be3cc911fd44
readonly REPO_REV=v2.68.1
readonly RECOVERY_COMMIT=90e5d9559065cfa8b2b9a5dbb1c5cb7a88f034fa

cd /src
export GIT_TERMINAL_PROMPT=0
uname -m
python3 --version
df -h /src
git config --global user.name 'TWRP source preparation'
git config --global user.email 'twrp-build@localhost'
repo init -u https://github.com/minimal-manifest-twrp/platform_manifest_twrp_omni \
  -b twrp-5.1 --depth=1 --repo-rev="$REPO_REV"
# A second init pins repo's manifest revision, not only the worktree HEAD.
repo init -b "$MANIFEST_COMMIT" --manifest-upstream-branch refs/heads/twrp-5.1 \
  --depth=1 --repo-rev="$REPO_REV"
test "$(git -C .repo/manifests rev-parse HEAD)" = "$MANIFEST_COMMIT"
repo --version
# The pinned manifest already contains the recovery override.
rm -f .repo/local_manifests/recovery-pin.xml

sync_status=1
for attempt in 1 2 3; do
  printf '\nSource sync attempt %s\n' "$attempt"
  if repo sync -c -j8 --no-tags --no-clone-bundle -m "$TREE/build/manifest-pinned.xml"; then
    sync_status=0
    break
  else
    sync_status=$?
    printf '\nSource sync attempt %s failed: exit %s\n' "$attempt" "$sync_status"
  fi
done
if [ "$sync_status" -ne 0 ]; then
  exit "$sync_status"
fi

# Every checked-out project must be at its pinned commit.
python3 - "$TREE/build/manifest-pinned.xml" <<'PY'
import subprocess, sys, xml.etree.ElementTree as ET
projects = ET.parse(sys.argv[1]).getroot().findall("project")
bad = []
for project in projects:
    path = project.get("path") or project.get("name")
    head = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    if head != project.get("revision"):
        bad.append(f"{path}: {head or 'missing'} != {project.get('revision')}")
print(f"{len(projects) - len(bad)}/{len(projects)} projects at pinned commits")
sys.exit("\n".join(bad) if bad else 0)
PY
test -f build/target/product/full_base.mk
test -f vendor/omni/config/common.mk
test "$(git -C bootable/recovery rev-parse HEAD)" = "$RECOVERY_COMMIT"

# Apply each recovery patch once. A patch that reverses cleanly is present.
for patch in "$TREE"/patches/bootable_recovery/*.patch; do
  [ -e "$patch" ] || continue
  if git -C bootable/recovery apply --reverse --check "$patch" 2>/dev/null; then
    printf 'Already applied: %s\n' "${patch##*/}"
  else
    git -C bootable/recovery apply "$patch"
    printf 'Applied: %s\n' "${patch##*/}"
  fi
done

df -h /src
printf '\nPinned source synchronization, patches, and required-path checks complete.\n'
