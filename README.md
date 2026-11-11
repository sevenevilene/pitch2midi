# pitch2midi~

A monophonic pitch detector for Pure Data. Audio goes in, MIDI notes come out.
It's built from scratch out of **Pd vanilla objects only**, with no externals, no
`expr`, `fft~`, `sigmund~` or `fiddle~`. Every object is one that the
**Heavy compiler (hvcc)** supports, so it runs in **plugdata Compiled Mode**
and can be exported to C++/Daisy/DPF/Web.

## Files

| file | what |
|---|---|
| `pitch2midi~.pd` | the abstraction you use |
| `p2m.band~.pd` | internal sub-abstraction (keep it next to `pitch2midi~.pd`) |
| `pitch2midi~-help.pd` | help / example patch |
| `tools/build_patches.py` | generator: the patches are generated from this script. Edit it and re-run it to change them |
| `test/` | synthetic test suite (Pd batch run + Heavy-compiled C run) |

To reuse it, copy `pitch2midi~.pd` and `p2m.band~.pd` into your project folder
(or into a folder on Pd's search path) and create `[pitch2midi~ 1 -50]`.

## Interface

```
[pitch2midi~ <midi channel=1> <threshold dBFS=-50>]
 inlet~ 1 : audio (one monophonic source)
 inlet  2 : thresh <dBFS> | stable <ticks> | midi <0|1> | channel <1-16>
 outlet 1 : note number   ┐ same order as [notein]: velocity is sent first,
 outlet 2 : velocity      ┘ then the note (velocity 0 = note off)
 outlet 3 : detected frequency in Hz (continuous)
 + note on/off is sent to [noteout] (the MIDI out port); turn it off with "midi 0"
```

**Using it with `[notein]`:** in the same patch, use the outlets the way you would
use `[notein]`'s outlets. For another patch or app, set Pd's MIDI output to a
virtual port (on macOS, the IAC Driver in Audio MIDI Setup) and listen on that
port with `[notein]`.

## How it works

1. A `hip~ 20` removes DC, then the signal feeds **12 half-octave low-pass bands**
   (55 Hz to 2.5 kHz, each a 4th-order Butterworth built from 2× `biquad~`).
2. In each band, a sign detector plus `rzero~` finds upward zero crossings. A
   `rpole~` with a *signal* coefficient makes a sample counter that resets at each
   crossing, starting from the **sub-sample (interpolated) crossing point**. A
   chain of `samphold~` keeps the last 4 crossing intervals, so periods are
   accurate to a fraction of a sample.
3. Every 4 ms, each band is checked. It needs enough power, and either
   *P1≈P2* (one crossing per cycle) or *P1≈P3 and P2≈P4* (two crossings per
   cycle). The resulting frequency also has to fall inside that band's own range,
   which rejects octave errors. **The lowest valid band wins.**
4. Note logic: a level gate with 6 dB hysteresis, ±0.8 semitone pitch hysteresis,
   and a stability requirement of 2 ticks plus 1.5 periods. A release guard blocks
   new notes while the level is falling fast, so note tails and filter ringing
   don't trigger anything. Velocity comes from the level at the onset.

## Measured results (`test/`)

The test signal is 47 notes: sine, saw, square, a voice-like tone with a weak
fundamental and vibrato, legato runs, Karplus-Strong plucks, and quiet notes at
-30 dBFS, all over a -70 dB noise floor.

| run | correct | spurious | median onset latency | CPU |
|---|---|---|---|---|
| Pd 0.57 vanilla, 44.1 kHz | 47/47 | 0 | 24 ms | ~1.5 % of one core |
| Pd 0.57 vanilla, 48 kHz | 47/47 | 0 | 24 ms | |
| **Heavy/hvcc compiled C**, 44.1 kHz | 47/47 | 0 | 33 ms | **0.5 % of one core** |

Latency depends on pitch (about 12–20 ms above A4, 60–80 ms at E2/C2), because a
detector has to see a couple of periods before it can trust a note.

Re-run the tests:

```bash
python3 test/make_test_audio.py
cd test && /Applications/Pd-0.57-0.app/Contents/Resources/bin/pd -nogui -batch -nomidi -r 44100 -stderr -path .. run_test.pd > out.txt 2>&1; python3 evaluate.py
```

Heavy version (needs `pip install hvcc`):

```bash
hvcc test/heavy_main.pd -o build -n p2m -p . -g c && clang++ -O2 -std=c++14 -Ibuild/c build/c/*.c build/c/*.cpp test/heavy_harness.cpp -o build/harness && build/harness test/test.wav 44100 > test/out.txt && python3 test/evaluate.py
```

hvcc prints a warning for every `rzero~`. You can ignore it: the coefficient is
fed in as a signal (`sig~ 1`), which is the form Heavy supports.

## Limits

- Monophonic only. Chords give unpredictable results.
- Range is about 40 Hz – 2.5 kHz (MIDI ~28–99). To change it, edit
  `BAND_BASE_HZ` / `BAND_COUNT` in the generator.
- It doesn't detect a re-attack of the *same* note while the sound keeps ringing.
  The gate has to close in between.
