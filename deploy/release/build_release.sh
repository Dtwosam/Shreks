#!/usr/bin/env bash
set -euo pipefail

SOURCE_SHA="${1:-${SOURCE_SHA:-}}"
PLATFORM="x86_64-unknown-linux-gnu"
RELEASE_OUT="${RELEASE_OUT:-dist/release}"
WHEEL_OUT="dist/release-wheel"
STAGING="$RELEASE_OUT/staging"

if [[ ! "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "SOURCE_SHA must be exactly 40 lowercase hex characters" >&2
  exit 2
fi

ACTUAL_SHA="$(git rev-parse HEAD)"
if [[ "$ACTUAL_SHA" != "$SOURCE_SHA" ]]; then
  echo "checked-out source SHA does not match requested release SHA" >&2
  exit 2
fi

rm -rf "$RELEASE_OUT"
rm -rf "$WHEEL_OUT"
mkdir -p \
  "$STAGING/target/release" \
  "$STAGING/deploy/systemd" \
  "$STAGING/wheelhouse" \
  "$WHEEL_OUT"

cargo build --release --bin shreks-observe --bin shreks-paper-evidence
python -m pip wheel ./python --no-deps -w "$WHEEL_OUT"

mapfile -t WHEELS < <(find "$WHEEL_OUT" -maxdepth 1 -type f -name 'shreks_brain-*.whl' -print | sort)
if [[ "${#WHEELS[@]}" -ne 1 ]]; then
  echo "expected exactly one shreks_brain wheel" >&2
  exit 2
fi

cp target/release/shreks-observe "$STAGING/target/release/shreks-observe"
cp target/release/shreks-paper-evidence "$STAGING/target/release/shreks-paper-evidence"
cp deploy/systemd/shreks-observe.service "$STAGING/deploy/systemd/shreks-observe.service"
cp deploy/systemd/shreks-paper-evidence.service "$STAGING/deploy/systemd/shreks-paper-evidence.service"
cp deploy/systemd/shreks-paper-campaign.service "$STAGING/deploy/systemd/shreks-paper-campaign.service"
cp deploy/systemd/shreks.target "$STAGING/deploy/systemd/shreks.target"
cp "${WHEELS[0]}" "$STAGING/wheelhouse/$(basename "${WHEELS[0]}")"

python deploy/release/release_bundle.py build \
  --staging "$STAGING" \
  --source-sha "$SOURCE_SHA" \
  --platform "$PLATFORM" \
  --out-dir "$RELEASE_OUT"

ARCHIVE="$RELEASE_OUT/shreks-release-$SOURCE_SHA.tar.gz"
CHECKSUM="$ARCHIVE.sha256"
MANIFEST="$RELEASE_OUT/RELEASE_MANIFEST.json"
python deploy/release/release_bundle.py verify \
  --archive "$ARCHIVE" \
  --checksum "$CHECKSUM" \
  --manifest "$MANIFEST"

rm -rf "$STAGING"
echo "$ARCHIVE"
