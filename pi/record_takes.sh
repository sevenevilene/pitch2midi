#!/usr/bin/env bash
# Records a set of test takes from the Pisound input, for tuning pitch2midi
# on a real instrument. Each take is saved as its own WAV file, with a short
# description of what you played, so it can be replayed through the detector
# on another computer and used as a regression test.
#
#   ./pi/record_takes.sh bass            # or: guitar
#   AUDIO_IN=system:capture_2 ./pi/record_takes.sh guitar
#
# Output: pi/recordings/<instrument>-<date>/NN_<take>.wav + notes.txt + info.txt
# Needs JACK running (Patchbox OS starts it) and jack_capture:
#   sudo apt install jack-capture
set -euo pipefail

INSTR="${1:-bass}"
case "$INSTR" in bass|guitar) ;; *) echo "usage: $0 bass|guitar" >&2; exit 1 ;; esac
AUDIO_IN="${AUDIO_IN:-system:capture_1}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/recordings/$INSTR-$(date +%Y%m%d-%H%M)"

command -v jack_capture >/dev/null || { echo "jack_capture is missing: sudo apt install jack-capture" >&2; exit 1; }
jack_lsp 2>/dev/null | grep -qx "$AUDIO_IN" || { echo "JACK port $AUDIO_IN not found (is JACK running? list ports with jack_lsp)" >&2; exit 1; }
mkdir -p "$OUT"

{
  echo "instrument: $INSTR"
  echo "date: $(date -Iseconds)"
  echo "input port: $AUDIO_IN"
  echo "jack sample rate: $(jack_samplerate 2>/dev/null || echo ?)"
  echo "jack buffer size: $(jack_bufsize 2>/dev/null | head -1 || echo ?)"
  echo "system: $(uname -a)"
  grep -m1 Model /proc/cpuinfo 2>/dev/null || true
} > "$OUT/info.txt"

if [ "$INSTR" = bass ]; then
  STRINGS="the lowest string (B or E) and the G string"
  HIGH="12th-24th fret on the D and G strings"
else
  STRINGS="the low E string and the high e string"
  HIGH="12th fret and up on the B and high e strings"
fi

TAKES=(
  "silence|Plugged in, volume up, hands OFF the strings (10 s). Measures hum and noise."
  "open_strings|Each open string once, low to high. Let every note ring until it dies away."
  "chromatic|Chromatic run, open to 12th fret and back, on $STRINGS. One note per beat, ~80 bpm."
  "repeats|Same note repeated: 8 slow notes, then 8 fast 8th notes. Do it on a low and a high note."
  "legato|Hammer-ons, pull-offs and a couple of slides. Pick only the first note of each phrase."
  "high_ring|High notes, $HIGH. Hold each one long, until it fades out."
  "soft_loud|The same few notes very softly, then hard."
  "free|About a minute of your normal playing: a real line or riff."
)

peak_report() {  # prints peak and RMS of a WAV file (PCM 16/24/32 or float)
  python3 - "$1" <<'PY'
import struct, sys, math
d = open(sys.argv[1], 'rb').read()
i, fmt, data = 12, None, None
while i + 8 <= len(d):
    cid, size = d[i:i+4], struct.unpack('<I', d[i+4:i+8])[0]
    body = d[i+8:i+8+size]
    if cid == b'fmt ':
        fmt = list(struct.unpack('<HHIIHH', body[:16]))
        if fmt[0] == 0xFFFE and len(body) >= 26:   # WAVE_FORMAT_EXTENSIBLE: real type in the subformat
            fmt[0] = struct.unpack('<H', body[24:26])[0]
    if cid == b'data': data = body
    i += 8 + size + (size & 1)
tag, ch, sr, _, _, bits = fmt
n = len(data) // (bits // 8)
if tag == 3 and bits == 32:
    x = struct.unpack('<%df' % n, data[:n*4])
elif bits == 16:
    x = [v / 32768 for v in struct.unpack('<%dh' % n, data[:n*2])]
elif bits == 24:
    x = [int.from_bytes(data[k:k+3], 'little', signed=True) / 8388608 for k in range(0, n*3, 3)]
elif bits == 32:
    x = [v / 2147483648 for v in struct.unpack('<%di' % n, data[:n*4])]
else:
    print("  (can't read %d-bit audio)" % bits); sys.exit()
x = x[::ch]
pk = max(abs(v) for v in x) or 1e-9
rms = math.sqrt(sum(v*v for v in x) / max(1, len(x))) or 1e-9
db = lambda v: 20 * math.log10(v)
print("  %.1f s, %d Hz, peak %.1f dBFS, rms %.1f dBFS" % (len(x) / sr, sr, db(pk), db(rms)))
if pk > 0.98: print("  WARNING: clipping - turn the Pisound input gain down a bit and redo this take")
elif pk < 0.05: print("  note: quite quiet - turn the Pisound input gain up if you can")
PY
}

echo "Recording to $OUT"
echo "Input: $AUDIO_IN. Press Return to start a take, Return again to stop."
echo
n=0
for t in "${TAKES[@]}"; do
  n=$((n + 1))
  name="${t%%|*}"; what="${t#*|}"
  file="$OUT/$(printf '%02d' $n)_$name.wav"
  echo "== take $n/${#TAKES[@]}: $name"
  echo "   $what"
  read -r -p "   Return = record, s = skip, q = quit: " a
  [ "$a" = q ] && break
  [ "$a" = s ] && { echo; continue; }
  rm -f "$file"
  echo "   recording... (Return to stop)"
  jack_capture --channels 1 --port "$AUDIO_IN" --format wav "$file" >/dev/null 2>&1 &
  pid=$!
  read -r _
  kill -INT $pid 2>/dev/null || true
  wait $pid 2>/dev/null || true
  [ -f "$file" ] || { echo "   recording failed (no file)"; continue; }
  peak_report "$file"
  read -r -p "   what did you play? (e.g. 'E string open to 12th fret', Return to skip): " desc
  echo "$(basename "$file"): $what | played: ${desc:--}" >> "$OUT/notes.txt"
  echo
done
echo "Done: $OUT"
ls -1 "$OUT"
