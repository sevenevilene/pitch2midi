#!/usr/bin/env bash
# Builds pitch2midi as a compiled JACK app (+ LV2 plugin) with the Heavy
# compiler. Run it ON the Raspberry Pi (Patchbox OS / Raspberry Pi OS):
#
#   ./pi/build.sh
#
# Result: pi/build/bin/pitch2midi        (JACK app, start with pi/run.sh)
#         pi/build/bin/pitch2midi.lv2/   (LV2 plugin, copy to ~/.lv2/)
set -euo pipefail

HVCC_VERSION="0.17.2"                                   # version this was tested with
DPF_COMMIT="4238e1c7f0351bbe488d79f0899c540543ac7583"    # DPF version this was tested with

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
BUILD="$HERE/build"
VENV="$HERE/.venv"
DPF="$HERE/dpf"

# 1. system packages (skip with SKIP_APT=1)
if [ "${SKIP_APT:-0}" != "1" ] && command -v apt-get >/dev/null; then
  echo "== installing build tools (sudo) =="
  sudo apt-get update
  sudo apt-get install -y git build-essential pkg-config python3-venv libjack-jackd2-dev
fi

# 2. hvcc needs Python >= 3.9
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "error: hvcc needs Python 3.9+, this system has $(python3 --version)." >&2
  echo "       Use a newer Patchbox / Raspberry Pi OS image (Bullseye or later)." >&2
  exit 1
fi
if [ ! -x "$VENV/bin/hvcc" ]; then
  echo "== installing hvcc $HVCC_VERSION into $VENV =="
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install "hvcc==$HVCC_VERSION"
fi

# 3. DPF (plugin framework that wraps the Heavy C code as JACK app / LV2)
if [ ! -d "$DPF/.git" ]; then
  echo "== fetching DPF =="
  git clone https://github.com/DISTRHO/DPF.git "$DPF"
  git -C "$DPF" checkout -q "$DPF_COMMIT"
  git -C "$DPF" submodule update --init --recursive
fi

# 4. Pd patch -> C++ -> binaries
echo "== compiling patch with hvcc =="
rm -rf "$BUILD"
APP="$HERE/pitch2midi_app.pd"
[ "${VARIANT:-}" = bass ] && APP="$HERE/pitch2midi_bass_app.pd"
echo "   patch: $APP"
"$VENV/bin/hvcc" "$APP" -o "$BUILD" -n pitch2midi \
  -p "$ROOT" -m "$HERE/meta.json" -g dpf 2>&1 | grep -v "rzero~\] accepts only signal" || true
[ -f "$BUILD/Makefile" ] || { echo "hvcc failed" >&2; exit 1; }
ln -s "$DPF" "$BUILD/dpf"

JOBS="$(nproc 2>/dev/null || sysctl -n hw.ncpu)"
echo "== building JACK app =="
make -C "$BUILD/plugin/source" -j"$JOBS" jack
echo "== building LV2 plugin (optional) =="
make -C "$BUILD" -j"$JOBS" || echo "warning: LV2 build failed - the JACK app is still fine"

echo
echo "done:"
ls -d "$BUILD"/bin/*
echo "start it with: $HERE/run.sh"
