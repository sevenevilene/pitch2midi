#!/usr/bin/env python3
"""Compares Pd output (out.txt, 'EV: note ms vel') with truth.csv.
usage: evaluate.py [out.txt] [truth.csv]"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))

truth = []
for line in open(os.path.join(HERE, sys.argv[2] if len(sys.argv) > 2 else "truth.csv")):
    s, e, m, l = line.strip().split(",")
    truth.append((float(s) * 1000, float(e) * 1000, int(m), l))

ons = []
for line in open(os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else "out.txt")):
    if line.startswith("EV:"):
        n, t, v = line.split()[1:4]
        if float(v) > 0:
            ons.append((float(t), int(float(n)), int(float(v))))

ok = 0
lat = []
used = set()
for s, e, m, l in truth:
    inside = [(t, n, v) for (t, n, v) in ons if s - 5 <= t < e]
    for o in inside:
        used.add(o)
    first = inside[0] if inside else None
    good = first is not None and first[1] == m and len(inside) == 1
    ok += good
    if first:
        lat.append(first[0] - s)
    status = "OK " if good else "BAD"
    got = " ".join("%d@%+.0fms" % (n, t - s) for t, n, v in inside) or "-"
    print("%s %-7s truth %3d (%7.1f Hz)  got %s" % (status, l, m, 440 * 2 ** ((m - 69) / 12), got))
extra = [o for o in ons if o not in used]
print("\n%d/%d notes exactly right, %d spurious note-ons outside notes" % (ok, len(truth), len(extra)))
if lat:
    lat.sort()
    print("onset latency ms: min %.0f  median %.0f  max %.0f" % (lat[0], lat[len(lat) // 2], lat[-1]))
