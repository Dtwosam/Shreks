#!/usr/bin/env bash
set -euo pipefail

SOURCE_SHA="${1:-${SOURCE_SHA:-}}"
PLATFORM="${PLATFORM:-x86_64-unknown-linux-gnu}"
RELEASE_OUT="${RELEASE_OUT:-dist/release}"
WHEEL_OUT="dist/release-wheel"
PYTHON_BUILD_ROOT="${RELEASE_OUT}-python-source"
STAGING="$RELEASE_OUT/staging"
CONTROL_PACKAGE="$PYTHON_BUILD_ROOT/src/shreks_brain/_sealed_deploy_control"\nFAST_TOOLS_PACKAGE="$PYTHON_BUILD_ROOT/src/shreks_brain/_sealed_fast_tools"

if [[ ! "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "SOURCE_SHA must be exactly 40 lowercase hex characters" >&2
  exit 2
fi

case "$PLATFORM" in
  x86_64-unknown-linux-gnu|aarch64-unknown-linux-gnu)
    ;;
  *)
    echo "unsupported release platform: $PLATFORM" >&2
    exit 2
    ;;
esac

ACTUAL_SHA="$(git rev-parse HEAD)"
if [[ "$ACTUAL_SHA" != "$SOURCE_SHA" ]]; then
  echo "checked-out source SHA does not match requested release SHA" >&2
  exit 2
fi

RUST_HOST="$(rustc -vV | sed -n 's/^host: //p')"
if [[ -z "$RUST_HOST" ]]; then
  echo "unable to determine native Rust host" >&2
  exit 2
fi
if [[ "$RUST_HOST" != "$PLATFORM" ]]; then
  echo "requested release platform does not match native Rust host: requested=$PLATFORM native=$RUST_HOST" >&2
  exit 2
fi

rm -rf "$RELEASE_OUT"
rm -rf "$WHEEL_OUT"
rm -rf "$PYTHON_BUILD_ROOT"
mkdir -p \
  "$STAGING/target/release" \
  "$STAGING/deploy/systemd" \
  "$STAGING/wheelhouse" \
  "$WHEEL_OUT"

cargo build --release --bin shreks-observe --bin shreks-paper-evidence \\\n  --bin export_fast_training_features \\\n  --bin shreks-fast-entry-authority \\\n  --bin shreks-fast-campaign-decision

# Keep the top-level release bundle compatible with the already-installed G2
# verifier. The sealed deployment-control scripts ride inside the already-
# allowlisted, manifest-hashed Shreks wheel for the one-time control-plane
# bootstrap after this release is staged.
cp -a python "$PYTHON_BUILD_ROOT"
mkdir -p "$CONTROL_PACKAGE"
printf '%s\n' '"""Sealed deployment-control payload; not a runtime API."""' \
  > "$CONTROL_PACKAGE/__init__.py"
cp deploy/release/release_manager.py "$CONTROL_PACKAGE/release_manager.py"
cp deploy/release/release_bundle.py "$CONTROL_PACKAGE/release_bundle.py"

python -m pip wheel "$PYTHON_BUILD_ROOT" --no-deps -w "$WHEEL_OUT"

mapfile -t WHEELS < <(find "$WHEEL_OUT" -maxdepth 1 -type f -name 'shreks_brain-*.whl' -print | sort)
if [[ "${#WHEELS[@]}" -ne 1 ]]; then
  echo "expected exactly one shreks_brain wheel" >&2
  exit 2
fi

python - "${WHEELS[0]}" <<'PY'
from pathlib import Path
import sys
import zipfile

wheel = Path(sys.argv[1])
expected = {
    "shreks_brain/_sealed_deploy_control/release_manager.py": Path(
        "deploy/release/release_manager.py"
    ).read_bytes(),
    "shreks_brain/_sealed_deploy_control/release_bundle.py": Path(
        "deploy/release/release_bundle.py"
    ).read_bytes(),
}
with zipfile.ZipFile(wheel) as archive:
    for member, payload in expected.items():
        try:
            actual = archive.read(member)
        except KeyError as exc:
            raise SystemExit(f"sealed deployment-control wheel member missing: {member}") from exc
        if actual != payload:
            raise SystemExit(f"sealed deployment-control wheel member mismatch: {member}")
PY

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
rm -rf "$PYTHON_BUILD_ROOT"
echo "$ARCHIVE"
