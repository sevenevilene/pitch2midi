# Raspberry Pi (Patchbox OS) – compiled build

This folder turns `pitch2midi~` into a native **JACK app** with Heavy (hvcc)
and [DPF](https://github.com/DISTRHO/DPF). It uses less CPU than running the
patch in Pd, and it runs without Pd. There is also an optional **LV2 plugin**.

> Status: the build flow has been tested end to end on macOS, where the JACK app
> builds. It has **not been run on a Pi yet**. If something fails on the Pi,
> the error output from `build.sh` tells you which step broke.

## Build (on the Pi)

```bash
git clone https://github.com/sevenevilene/pitch2midi.git
```
```bash
cd pitch2midi && ./pi/build.sh
```

The script:
1. installs the build tools with `apt` (`git build-essential pkg-config python3-venv libjack-jackd2-dev`).
   Set `SKIP_APT=1` to skip this step.
2. installs hvcc 0.17.2 into `pi/.venv`. This needs **Python 3.9+**, so use a
   Bullseye-based or newer Patchbox / Raspberry Pi OS image.
3. downloads DPF into `pi/dpf`, pinned to the commit that was tested.
4. compiles `pi/pitch2midi_app.pd` (`adc~ 1` → `pitch2midi~ 1 -50`) to C++ and builds:
   - `pi/build/bin/pitch2midi`: the JACK app
   - `pi/build/bin/pitch2midi.lv2/`: the LV2 plugin (optional; copy it to `~/.lv2/`)

Expect the first build to take a few minutes on a Pi 4.

For bass guitar, build the bass-tuned variant (`pitch2midi-bass~`, low B at
31 Hz up to about 950 Hz) instead:

```bash
VARIANT=bass ./pi/build.sh
```

## Run

JACK must be running. Patchbox OS starts it with your Pisound / sound card.

```bash
./pi/run.sh
```

This starts the app and connects `system:capture_1` to `pitch2midi:audio_in_1`.
Notes come out on the JACK MIDI port **`pitch2midi:midi-out`**. Connect that
port to your synth or MIDI interface:

```bash
MIDI_OUT="<port from jack_lsp>" AUDIO_IN=system:capture_1 ./pi/run.sh
```

Run `jack_lsp` to list the ports. Hardware MIDI (USB MIDI, Pisound MIDI out) shows up
in JACK when the ALSA-to-JACK MIDI bridge is running (`a2jmidid -e &`), as ports
named `a2j:...`.

## Settings

The app has no UI and starts with threshold -50 dBFS and stable = 2.
To change the defaults, edit the `pitch2midi~` arguments in
`pi/pitch2midi_app.pd`, or the default values of the `@hv_param` receives in the
same file, then rebuild. In the LV2 plugin, `thresh` and `stable` are plugin
parameters you can change from the host.

## Notes

- hvcc warns about every `rzero~`. That's expected and harmless.
- The LV2 target doesn't link on macOS because of a symbol-export rule that
  only applies there. On the Pi it should build; if it doesn't, the JACK app
  is unaffected.
