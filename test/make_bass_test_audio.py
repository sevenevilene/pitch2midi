#!/usr/bin/env python3
"""Synthesises bass_test.wav (44.1 kHz mono) + bass_truth.csv: bass-guitar-like
material from low B (5-string, 31 Hz) up to the high frets of the G string."""
import math, random, struct, wave, os

SR = int(os.environ.get("SR", 44100))
HERE = os.path.dirname(os.path.abspath(__file__))
random.seed(2)
out = []
truth = []


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def gap(sec):
    out.extend([0.0] * int(sec * SR))


def bass(m, sec, amp=0.5, harm=None, decay=1.2, sharp=12.0, label="bass"):
    """Plucked/fingered bass: harmonic stack, exponential decay, upper partials
    decaying faster, pitch starting `sharp` cents high and settling (string
    tension at the attack)."""
    harm = harm or [(1, 1.0), (2, 0.7), (3, 0.45), (4, 0.3), (5, 0.2),
                    (6, 0.12), (7, 0.08), (8, 0.05)]
    n = int(sec * SR)
    f0 = mtof(m)
    nh = [h for h in harm if f0 * h[0] < SR * 0.45]
    start = len(out)
    ph = 0.0
    for i in range(n):
        t = i / SR
        f = f0 * 2 ** (sharp * math.exp(-t / 0.05) / 1200.0)
        ph += 2 * math.pi * f / SR
        s = sum(a * math.exp(-t * k / decay) * math.sin(k * ph) for k, a in nh)
        e = min(1.0, t / 0.003, max(0.0, (sec - t) / 0.03))
        out.append(amp * e * s)
    truth.append((start / SR, len(out) / SR, m, label))


# low B string: the fundamental is weak, the 2nd harmonic dominates
WEAKF = [(1, 0.25), (2, 1.0), (3, 0.7), (4, 0.45), (5, 0.3), (6, 0.2), (7, 0.1)]
# slap/pop-ish: bright, strong upper partials
SLAP = [(k, 1.0 / k ** 0.6) for k in range(1, 30)]

gap(0.3)
for m in [23, 28, 33, 38, 43]:                       # open strings B0 E1 A1 D2 G2
    bass(m, 0.8, label="open"); gap(0.15)
for m in [23, 24, 26, 28, 29]:                       # weak-fundamental low notes
    bass(m, 0.7, 0.45, WEAKF, label="weakfund"); gap(0.15)
for m in [31, 36, 40, 45, 48, 52, 55, 60, 64, 67]:   # frets up the neck
    bass(m, 0.5, 0.4, label="fretted"); gap(0.12)
for m in [28, 28, 35, 28, 40, 28, 38, 35]:           # 8th notes at 120 bpm
    bass(m, 0.23, 0.45, label="eighths"); gap(0.02)
gap(0.2)
for m in [28, 30, 31, 33, 35, 36, 38, 40]:           # legato (hammer-on style)
    bass(m, 0.3, 0.4, sharp=0.0, label="legato")
gap(0.2)
for m in [28, 33, 40, 45]:
    bass(m, 0.5, 0.35, SLAP, decay=0.5, label="slap"); gap(0.15)
for m in [33, 33, 33, 33, 26, 26, 26, 26]:           # repeated notes, short mute
    bass(m, 0.3, 0.45, label="repeat"); gap(0.03)
gap(0.2)
for m in [28, 33]:                                   # quiet (about -30 dBFS)
    bass(m, 0.6, 0.02, label="quiet"); gap(0.15)
gap(0.5)

out = [s + random.gauss(0, 0.0003) for s in out]     # -70 dBFS noise floor

with wave.open(os.path.join(HERE, "bass_test.wav"), "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(b"".join(struct.pack("<h", max(-32767, min(32767, int(s * 32767)))) for s in out))
with open(os.path.join(HERE, "bass_truth.csv"), "w") as f:
    for s, e, m, l in truth:
        f.write("%.4f,%.4f,%d,%s\n" % (s, e, m, l))
print("wrote bass_test.wav (%.1f s), %d notes" % (len(out) / SR, len(truth)))
