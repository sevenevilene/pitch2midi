#!/usr/bin/env bash
# Starts the compiled pitch2midi JACK app and wires it up.
#
#   ./pi/run.sh                       # audio from system:capture_1
#   AUDIO_IN=system:capture_2 ./pi/run.sh
#   MIDI_OUT="a2j:..." ./pi/run.sh    # also connect MIDI out to this JACK port
#
# JACK must already be running (Patchbox OS starts it for you).
# List available ports with: jack_lsp
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$HERE/build/bin/pitch2midi"
AUDIO_IN="${AUDIO_IN:-system:capture_1}"
MIDI_OUT="${MIDI_OUT:-}"

[ -x "$APP" ] || { echo "not built yet - run $HERE/build.sh first" >&2; exit 1; }

"$APP" &
PID=$!
trap 'kill $PID 2>/dev/null' INT TERM EXIT

# wait for the JACK client to appear
for _ in $(seq 50); do
  jack_lsp 2>/dev/null | grep -q '^pitch2midi:audio_in_1$' && break
  sleep 0.1
done

jack_connect "$AUDIO_IN" pitch2midi:audio_in_1 && echo "audio: $AUDIO_IN -> pitch2midi"
if [ -n "$MIDI_OUT" ]; then
  jack_connect pitch2midi:midi-out "$MIDI_OUT" && echo "midi:  pitch2midi -> $MIDI_OUT"
else
  echo "MIDI out port is pitch2midi:midi-out - connect it to a destination, e.g.:"
  jack_lsp -t 2>/dev/null | grep -B1 midi | grep -v '^\s' | grep -iv pitch2midi | sed 's/^/  /' || true
fi

echo "running (Ctrl+C to stop)"
wait $PID
