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
| `pitch2midi-bass~.pd` | the same detector tuned for bass guitar (see below) |
| `bass-example.pd` | ready-to-use bass patch: input 1 → MIDI notes, with a threshold box, a pitch-bend on/off toggle (off at start) and a built-in "listen" synth |
| `p2m.band~.pd` | internal sub-abstraction (keep it next to `pitch2midi~.pd`) |
| `pitch2midi~-help.pd` | help / example patch |
| `tools/build_patches.py` | generator: the patches are generated from this script. Edit it and re-run it to change them |
| `test/` | synthetic test suite (Pd batch run + Heavy-compiled C run) |
| `pi/` | Raspberry Pi / Patchbox OS: builds a compiled JACK app with MIDI out (see [pi/README.md](pi/README.md)) |

To reuse it, copy `pitch2midi~.pd` and `p2m.band~.pd` into your project folder
(or into a folder on Pd's search path) and create `[pitch2midi~ 1 -50]`.
An optional third argument sets the pitch bend range: `[pitch2midi~ 1 -50 2]`.

## Interface

```
[pitch2midi~ <midi channel=1> <threshold dBFS=-50> <bend range=2>]
 inlet~ 1 : audio (one monophonic source)
 inlet  2 : thresh <dBFS> | stable <ticks> | midi <0|1> | channel <1-16>
            | bend <0|1> | bendrange <semitones>
 outlet 1 : note number   ┐ same order as [notein]: velocity is sent first,
 outlet 2 : velocity      ┘ then the note (velocity 0 = note off)
 outlet 3 : detected frequency in Hz (continuous)
 outlet 4 : pitch bend, -8192..8191 (0 = centre, same scale as [bendout])
 + note on/off is sent to [noteout] and pitch bend to [bendout] (the MIDI out
   port); turn both off with "midi 0", or only the bend with "bend 0"
```

**Using it with `[notein]`:** in the same patch, use the outlets the way you would
use `[notein]`'s outlets. For another patch or app, set Pd's MIDI output to a
virtual port (on macOS, the IAC Driver in Audio MIDI Setup) and listen on that
port with `[notein]`.

**Pitch bend:** notes snap to the nearest semitone, so the leftover distance
between the detected pitch and the held note is sent as pitch bend
(`(pitch − note) / bendrange × 8192`). This carries vibrato, slides and
out-of-tune playing. A new note's bend is sent just before its note-on. A value
is only sent when it changes. Set your synth's bend range to the same number of
semitones as `bendrange` (default 2). The bend keeps its last value after a
note-off, so a release tail doesn't jump in pitch.

## Bass guitar: `pitch2midi-bass~`

Same interface and messages as `pitch2midi~`, tuned for bass:

- **Range B0–~950 Hz** (5-string low B at 31 Hz up to the top frets of the G
  string, plus harmonics/tapping). 10 bands from 36.7 Hz instead of 12 from 55 Hz.
  The standard version can't go below about 32 Hz, so it misses low B.
- **No high bands**: pick, slap and fret-noise transients can't produce
  spurious high notes at the attack (the standard version sometimes does,
  e.g. a short MIDI 93 blip before a low E). It also uses ~20 % less CPU.
- **Octave-error guard**: a low band that holds a lot of energy but hasn't
  settled into a steady period yet vetoes the higher bands for that tick. On a
  low B string, where the 2nd harmonic is often much louder than the
  fundamental, this stops it from playing the octave above first.
- **Shorter stability wait** (1 period instead of 1.5), so low notes speak a
  little sooner. Raise it with `stable <ticks>` if you get wrong notes at the attack.
- `hip~ 15` instead of `hip~ 20`, so low B isn't attenuated.

Both versions also have a **leap guard**: while a note rings and there has
been no new attack, the detector ignores jumps of more than 7 semitones. As
a high note decays, mains hum (50/60 Hz) and subharmonics can get strong enough
in the low bands to win. Without the guard, the output flips between the real
note and the hum or the octave below. A new pluck unlocks the guard. Hammer-ons,
pull-offs and slides move in small steps, so they still work.

Both versions now also detect a **re-attack of the same note** (e.g. repeated
8th notes on one string): if the level jumps by more than 6 dB, the same note
can start again once it is stable.

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
   and a stability requirement of 2 ticks plus 1.5 periods. An onset detector
   (a fast-decaying peak of the level rising 6 dB above a slow floor, 80 ms
   refractory time) lets the same note retrigger. Without such an attack, a
   held note can only move by up to 7 semitones (leap guard). A release guard blocks
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

The bass test (`test/make_bass_test_audio.py`) is 50 bass-like notes from B0 to
G4: open strings, low notes with a weak fundamental, fretted notes, 8th notes
and repeated notes on one string, legato, slap-like tones and quiet notes. Each
note starts slightly sharp, like a plucked string.

| run | correct | spurious | median onset latency | CPU |
|---|---|---|---|---|
| `pitch2midi~` (standard), Pd 44.1 kHz | 44/50 | 0 | 94 ms | |
| **`pitch2midi-bass~`**, Pd 44.1 kHz | **50/50** | 0 | 92 ms | |
| `pitch2midi-bass~`, Pd 48 kHz | 50/50 | 0 | 92 ms | |
| `pitch2midi-bass~`, Heavy compiled C, 44.1 kHz | 50/50 | 0 | 98 ms | 0.4 % of one core |

`test/make_bass_high_test_audio.py` adds 23 long, ringing high notes (E3–C5)
over loud mains hum (about −48 dBFS) and noise. Before the leap guard, the bass
version got **0/23**: every note flipped to the hum or a lower octave while it
decayed. It now gets **23/23** (Pd and Heavy).

Bass latency is mostly physics: a low E (41 Hz) has a 24 ms period and the
detector needs a few of them, so expect ~100–130 ms on the E string and up to
~250 ms on a low B with a weak fundamental; notes from A2 up take 30–60 ms.

Latency depends on pitch (about 12–20 ms above A4, 60–80 ms at E2/C2), because a
detector has to see a couple of periods before it can trust a note.

Re-run the tests (`test/run.sh` runs Pd in batch mode and scores the result;
set `PD=` if Pd is somewhere else, and `SR=48000` for both scripts to test 48 kHz):

```bash
python3 test/make_test_audio.py && test/run.sh
```
```bash
python3 test/make_bass_test_audio.py && test/run.sh bass_test.wav bass_truth.csv "pitch2midi-bass~ 1 -50"
```
```bash
python3 test/make_bass_high_test_audio.py && test/run.sh bass_high_test.wav bass_high_truth.csv "pitch2midi-bass~ 1 -50"
```

Heavy version (needs `pip install hvcc`):

```bash
hvcc test/heavy_main.pd -o build -n p2m -p . -g c && clang++ -O2 -std=c++14 -Ibuild/c build/c/*.c build/c/*.cpp test/heavy_harness.cpp -o build/harness && build/harness test/test.wav 44100 > test/out.txt && python3 test/evaluate.py
```

hvcc prints a warning for every `rzero~`. You can ignore it: the coefficient is
fed in as a signal (`sig~ 1`), which is the form Heavy supports.

## Limits

- Monophonic only. Chords give unpredictable results.
- Range is about 40 Hz – 2.5 kHz (MIDI ~28–99), or 31 Hz – ~950 Hz for the bass
  version. To change it, edit `BAND_BASE_HZ` / `BAND_COUNT` or the `BASS`
  settings in the generator.
- A re-attack of the *same* note is only detected when the level jumps by more
  than 6 dB. A very soft re-pluck over a loud ringing note is missed.
- Because of the leap guard, a jump of more than 7 semitones *without* a new
  attack (e.g. a wide hammer-on or tapped note) is ignored until the next
  attack. Change `max_leap` in the generator if you play like that.

## License

MIT, see [LICENSE](LICENSE).
