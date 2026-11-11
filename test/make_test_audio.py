#!/usr/bin/env python3
"""Synthesises test.wav (44.1 kHz mono) + truth.csv for the pitch2midi~ tests."""
import math, random, struct, wave, os

SR = int(os.environ.get("SR", 44100))
HERE = os.path.dirname(os.path.abspath(__file__))
random.seed(1)
out = []
truth = []


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def gap(sec):
    out.extend([0.0] * int(sec * SR))


def env(i, n, a=0.005, r=0.02):
    t, T = i / SR, n / SR
    return min(1.0, t / a, max(0.0, (T - t) / r))


def tone(m, sec, harm, amp=0.5, vib=0.0, label=""):
    n = int(sec * SR)
    f0 = mtof(m)
    nh = [h for h in harm if f0 * h[0] < SR * 0.45]
    start = len(out)
    ph = 0.0
    for i in range(n):
        f = f0 * (2 ** (vib * math.sin(2 * math.pi * 5.5 * i / SR) / 1200.0))
        ph += 2 * math.pi * f / SR
        s = sum(a * math.sin(k * ph) for k, a in nh)
        out.append(amp * env(i, n) * s)
    truth.append((start / SR, len(out) / SR, m, label))


def karplus(m, sec, amp=0.6):
    n = int(sec * SR)
    p = SR / mtof(m)
    L = int(p)
    frac = p - L
    buf = [random.uniform(-1, 1) for _ in range(L + 2)]
    start = len(out)
    idx = 0
    prev = 0.0
    hist = []
    for i in range(n):
        # fractional delay via linear interp, lowpass averaging, slight decay
        a = buf[idx % len(buf)]
        b = buf[(idx + 1) % len(buf)]
        v = 0.996 * 0.5 * (a + b)
        buf[idx % len(buf)] = v
        idx += 1
        out.append(amp * a * min(1.0, (n - i) / (0.02 * SR)))
    truth.append((start / SR, len(out) / SR, m, "pluck"))


SAW = [(k, 1.0 / k) for k in range(1, 60)]
SQUARE = [(k, 1.0 / k) for k in range(1, 60, 2)]
# voice-ish: weak fundamental, strong 2nd-4th harmonics
VOICE = [(1, 0.35), (2, 0.9), (3, 0.8), (4, 0.6), (5, 0.3), (6, 0.25), (7, 0.15), (8, 0.1)]

gap(0.3)
for m in [40, 45, 52, 57, 64, 69, 76, 81, 88, 93]:
    tone(m, 0.4, [(1, 1.0)], 0.5, label="sine"); gap(0.15)
for m in [36, 43, 50, 60, 67, 74, 84]:
    tone(m, 0.4, SAW, 0.3, label="saw"); gap(0.15)
for m in [38, 47, 55, 62, 71, 79]:
    tone(m, 0.4, SQUARE, 0.3, label="square"); gap(0.15)
for m in [48, 55, 60, 65, 72]:
    tone(m, 0.6, VOICE, 0.25, vib=30, label="voice"); gap(0.15)
for m in [60, 62, 64, 65, 67, 69, 71, 72]:        # legato, no gaps
    tone(m, 0.25, SAW, 0.3, label="legato")
gap(0.2)
for m in [40, 45, 50, 55, 59, 64, 69, 76]:
    karplus(m, 0.7); gap(0.1)
for m in [64, 64, 64]:                             # quiet notes (-30 dBFS)
    tone(m, 0.3, SAW, 0.02, label="quiet"); gap(0.15)
gap(0.5)

# noise floor ~ -70 dBFS
out = [s + random.gauss(0, 0.0003) for s in out]

with wave.open(os.path.join(HERE, "test.wav"), "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(b"".join(struct.pack("<h", max(-32767, min(32767, int(s * 32767)))) for s in out))
with open(os.path.join(HERE, "truth.csv"), "w") as f:
    for s, e, m, l in truth:
        f.write("%.4f,%.4f,%d,%s\n" % (s, e, m, l))
print("wrote test.wav (%.1f s), %d notes" % (len(out) / SR, len(truth)))
