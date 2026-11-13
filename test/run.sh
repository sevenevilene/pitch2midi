#!/bin/sh
# Runs one test file through a detector in Pd (batch mode) and scores it.
#   test/run.sh                                   -> test.wav with [pitch2midi~ 1 -50]
#   test/run.sh bass_test.wav bass_truth.csv "pitch2midi-bass~ 1 -50"
# PD=/path/to/pd overrides the Pd binary, SR=48000 the sample rate.
set -e
cd "$(dirname "$0")"
WAV=${1:-test.wav}; TRUTH=${2:-truth.csv}; OBJ=${3:-pitch2midi~ 1 -50}
PD=${PD:-/Applications/Pd-0.57-0.app/Contents/Resources/bin/pd}
TMP=.run_tmp.pd
sed -e "s|read -resize test.wav|read -resize $WAV|" -e "s|obj 20 240 pitch2midi~ 1 -50|obj 20 240 $OBJ|" run_test.pd > $TMP
"$PD" -nogui -batch -nomidi -r "${SR:-44100}" -stderr -path .. $TMP > out_run.txt 2>&1 || true
rm -f $TMP
python3 evaluate.py out_run.txt "$TRUTH"
