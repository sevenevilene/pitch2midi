#!/usr/bin/env python3
"""Synthesises bass_high_test.wav + bass_high_truth.csv: long, ringing high bass
notes (E3..C5) with stretched overtones, different pickup positions and vibrato,
over mains hum (50 + 150 Hz, about -48 dBFS) and a -60 dBFS noise floor.
While these notes decay, the hum and subharmonics must not take over.
NZ= / HUM= set the noise and hum amplitude."""
import math, random, struct, wave, sys, os
SR=int(os.environ.get("SR", 44100)); HERE=os.path.dirname(os.path.abspath(__file__)); random.seed(3); out=[]; truth=[]
def mtof(m): return 440*2**((m-69)/12)
def gap(s): out.extend([0.0]*int(s*SR))
def note(m, sec, B, harm, decay, amp=0.4, vib=0, label=""):
    n=int(sec*SR); f0=mtof(m); start=len(out)
    parts=[(k*math.sqrt(1+B*k*k), a) for k,a in harm]
    parts=[(r,a) for r,a in parts if f0*r<SR*0.45]
    ph=[random.uniform(0,6.28) for _ in parts]
    for i in range(n):
        t=i/SR
        f=f0*2**((8*math.exp(-t/0.05)+vib*math.sin(2*math.pi*5*t))/1200)
        s=0
        for j,(r,a) in enumerate(parts):
            ph[j]+=2*math.pi*f*r/SR
            s+=a*math.exp(-t*(1+0.6*r)/decay)*math.sin(ph[j])
        out.append(amp*min(1,t/0.003,max(0,(sec-t)/0.03))*s)
    truth.append((start/SR,len(out)/SR,m,label))
# pickup near string middle-ish for short strings: odd harmonics emphasized
PU=lambda pos:[(k,abs(math.sin(math.pi*k*pos))/k**0.7) for k in range(1,16)]
for m in [52,55,57,59,60,62,64,65,67,69,71,72]:
    note(m,2.5,0.0006,PU(0.25),0.9,label="hi-bridge"); gap(0.2)
for m in [55,59,62,64,67,69,72]:
    note(m,2.5,0.0006,PU(0.4),0.9,label="hi-neck"); gap(0.2)
for m in [57,60,64,67]:
    note(m,2.5,0.001,PU(0.12),0.7,vib=15,label="hi-vib"); gap(0.2)
NZ=float(os.environ.get('NZ','0.001')); HUM=float(os.environ.get('HUM','0.003'))
out=[s+random.gauss(0,NZ)+HUM*(math.sin(2*math.pi*50*i/SR)+0.5*math.sin(2*math.pi*150*i/SR+1)) for i,s in enumerate(out)]
with wave.open(os.path.join(HERE,"bass_high_test.wav"),"w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(b"".join(struct.pack("<h",max(-32767,min(32767,int(s*32767)))) for s in out))
open(os.path.join(HERE,"bass_high_truth.csv"),"w").write("".join("%.4f,%.4f,%d,%s\n"%x for x in truth))
print("wrote bass_high_test.wav (%.1f s), %d notes" % (len(out) / SR, len(truth)))
