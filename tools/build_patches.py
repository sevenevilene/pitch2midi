#!/usr/bin/env python3
"""
Generates the Pure Data abstractions for pitch2midi~.

The patches are plain Pd vanilla and use only objects that the Heavy compiler
(hvcc / plugdata "Compiled Mode") supports: no expr, fft, sigmund~, fiddle~,
list, value, change, etc.

Run:  python3 tools/build_patches.py
"""
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Filter-bank layout: half-octave spaced low-pass bands.
# A band "owns" fundamentals in (fc/sqrt2, fc]; there its 2nd harmonic is
# attenuated by >= 12 dB relative to the fundamental.
BAND_BASE_HZ = 55.0
BAND_COUNT = 12          # 55 Hz ... 2489 Hz  -> detects roughly 40 Hz .. 2.5 kHz


class Patch:
    def __init__(self, w=1000, h=800):
        self.head = "#N canvas 40 60 %d %d 12;" % (w, h)
        self.items = []
        self.conns = []

    def _add(self, kind, x, y, text):
        self.items.append("#X %s %d %d %s;" % (kind, x, y, text) if text
                          else "#X %s %d %d;" % (kind, x, y))
        return len(self.items) - 1

    def obj(self, x, y, text):
        return self._add("obj", x, y, text)

    def msg(self, x, y, text):
        return self._add("msg", x, y, text)

    def atom(self, x, y, width, label):
        return self._add("floatatom", x, y, "%d 0 0 0 %s - - 0" % (width, label))

    def text(self, x, y, text):
        # commas / semicolons must be escaped in Pd files
        return self._add("text", x, y,
                         text.replace(",", " \\,").replace(";", " \\;"))

    def c(self, a, b, ao=0, bi=0):
        self.conns.append("#X connect %d %d %d %d;" % (a, ao, b, bi))

    def write(self, path):
        with open(path, "w") as f:
            f.write("\n".join([self.head] + self.items + self.conns) + "\n")


# ---------------------------------------------------------------------------
# p2m.band~  : one analysis band.  arg $1 = low-pass cutoff (Hz)
#   inlet~ 1 : audio
#   inlet  2 : float = input power -> evaluates the band
#   outlet 1 : frequency (Hz) if this band holds a valid, stable fundamental
# ---------------------------------------------------------------------------
def build_band():
    p = Patch(1100, 900)
    p.text(20, 10, "p2m.band~ <cutoff Hz> : one band of pitch2midi~. "
                   "Low-pass -> zero-crossing period with sub-sample "
                   "interpolation -> validity checks")
    ain = p.obj(20, 50, "inlet~")
    tin = p.obj(700, 50, "inlet")
    # Heavy ignores rzero~ creation args, so the coefficient comes in as a signal
    one_sig = p.obj(420, 50, "sig~ 1")

    def rz(x, yy):
        o = p.obj(x, yy, "rzero~")
        p.c(one_sig, o, 0, 1)
        return o

    out = p.obj(700, 820, "outlet")

    # --- 4th order low pass (2x Butterworth biquad) -----------------------
    bq1 = p.obj(20, 90, "biquad~")
    bq2 = p.obj(20, 120, "biquad~")
    p.c(ain, bq1); p.c(bq1, bq2)
    y = bq2

    # --- upward zero crossing impulse ------------------------------------
    g = p.obj(20, 170, "*~ 1e+20")
    s = p.obj(20, 200, "clip~ 0 1")
    e = rz(20, 230)
    imp = p.obj(20, 260, "clip~ 0 1")
    p.c(y, g); p.c(g, s); p.c(s, e); p.c(e, imp)

    # --- fractional crossing position t = y[n-1] / (y[n-1] - y[n]) -------
    d = rz(180, 170)            # d = y[n] - y[n-1]
    y1 = p.obj(180, 200, "-~")                 # y[n-1]
    p.c(y, d); p.c(y, y1); p.c(d, y1, 0, 1)
    num = p.obj(180, 230, "*~ -1")
    p.c(y1, num)
    ad = p.obj(300, 200, "abs~")
    eps = p.obj(300, 230, "+~ 1e-20")
    p.c(d, ad); p.c(ad, eps)
    div = p.obj(180, 270, "/~")
    p.c(num, div); p.c(eps, div, 0, 1)
    t = p.obj(180, 300, "clip~ 0 1")
    p.c(div, t)

    # --- sample counter that restarts at each crossing --------------------
    # c[n] = (1 - imp*t) + (1 - imp) * c[n-1]   -> rpole~ with signal coef
    it = p.obj(20, 340, "*~")
    p.c(imp, it); p.c(t, it, 0, 1)
    it_n = p.obj(20, 370, "*~ -1")
    xin = p.obj(20, 400, "+~ 1")
    p.c(it, it_n); p.c(it_n, xin)
    imp_n = p.obj(120, 370, "*~ -1")
    coef = p.obj(120, 400, "+~ 1")
    p.c(imp, imp_n); p.c(imp_n, coef)
    cnt = p.obj(20, 440, "rpole~")
    p.c(xin, cnt); p.c(coef, cnt, 0, 1)

    # period at crossing = c[n-1] + t
    dc = rz(120, 480)
    c1 = p.obj(20, 510, "-~")
    p.c(cnt, dc); p.c(cnt, c1); p.c(dc, c1, 0, 1)
    z = p.obj(20, 540, "+~")
    p.c(c1, z); p.c(t, z, 0, 1)
    per = p.obj(20, 580, "samphold~")         # latest period (samples)
    p.c(z, per); p.c(cnt, per, 0, 1)
    # last four crossing intervals P1 (newest) .. P4, all updated at a crossing
    ivals = [per]
    for k in range(3):
        src_ = ivals[-1]
        dk = rz(120 + 60 * k, 620 + 90 * k)
        pk_ = p.obj(20 + 60 * k, 650 + 90 * k, "-~")       # value before this crossing
        p.c(src_, dk); p.c(src_, pk_); p.c(dk, pk_, 0, 1)
        hk = p.obj(20 + 60 * k, 680 + 90 * k, "samphold~")
        p.c(pk_, hk); p.c(cnt, hk, 0, 1)
        ivals.append(hk)

    # band power
    sq = p.obj(320, 120, "*~")
    p.c(y, sq); p.c(y, sq, 0, 1)
    pw = p.obj(320, 150, "lop~ 20")
    p.c(sq, pw)

    def close(x, yy):
        """a -> inlet 0 of returned 'a' object, b -> inlet 1 of 'b' object.
        result = |a-b| < 0.04*a"""
        ta = p.obj(x, yy, "t f f")
        tol = p.obj(x + 70, yy + 30, "* 0.04")
        sb = p.obj(x, yy + 30, "-")
        ab = p.obj(x, yy + 60, "abs")
        lt = p.obj(x, yy + 90, "<")
        p.c(ta, tol, 1); p.c(tol, lt, 0, 1); p.c(ta, sb, 0); p.c(sb, ab); p.c(ab, lt)
        return ta, sb, lt

    # --- evaluation (control rate) ---------------------------------------
    # Hypothesis A: one crossing per cycle   -> P1 ~ P2, period = P1
    # Hypothesis B: two crossings per cycle  -> P1 ~ P3 and P2 ~ P4, period = P1+P2
    tbf = p.obj(700, 90, "t b f")
    p.c(tin, tbf)
    ratio = p.obj(780, 120, "* 0.001")         # band must hold >= -30 dB of input power
    gtp = p.obj(900, 180, ">")
    p.c(tbf, ratio, 1); p.c(ratio, gtp, 0, 1)
    tb = p.obj(700, 150, "t b b b b b b")
    p.c(tbf, tb, 0)
    snpw = p.obj(900, 150, "snapshot~")
    p.c(pw, snpw); p.c(tb, snpw, 5); p.c(snpw, gtp)
    spA = p.obj(560, 760, "spigot")
    p.c(gtp, spA, 0, 1)

    s4 = p.obj(1000, 210, "snapshot~"); p.c(ivals[3], s4); p.c(tb, s4, 4)
    s3 = p.obj(900, 240, "snapshot~"); p.c(ivals[2], s3); p.c(tb, s3, 3)
    s2 = p.obj(800, 270, "snapshot~"); p.c(ivals[1], s2); p.c(tb, s2, 2)
    s1 = p.obj(700, 300, "snapshot~"); p.c(ivals[0], s1); p.c(tb, s1, 1)
    c12 = close(560, 400)                     # P1 ~ P2           (hyp. A)
    c13 = close(700, 400)                     # P1 ~ P3  \
    c24 = close(860, 400)                     # P2 ~ P4  / alternating (hyp. B)
    p.c(s4, c24[1], 0, 1)
    p.c(s3, c13[1], 0, 1)
    sum1 = p.obj(800, 330, "+")               # P1 + P2
    t2 = p.obj(800, 300, "t f f f")
    p.c(s2, t2); p.c(t2, c12[1], 2, 1); p.c(t2, sum1, 1, 1); p.c(t2, c24[0], 0)
    andB = p.obj(700, 530, "&&")
    p.c(c24[2], andB, 0, 1)
    t1 = p.obj(700, 340, "t f f f f")
    p.c(s1, t1)
    fP1 = p.obj(560, 560, "f")
    fS1 = p.obj(860, 560, "f")
    p.c(t1, fP1, 3, 1)
    p.c(t1, sum1, 2, 0); p.c(sum1, fS1, 0, 1)
    p.c(t1, c13[0], 1); p.c(c13[2], andB, 0, 0)
    p.c(t1, c12[0], 0)
    fA = p.obj(640, 560, "f")
    fB = p.obj(720, 560, "f")
    p.c(c12[2], fA, 0, 1); p.c(andB, fB, 0, 1)
    # decide
    sA = p.obj(640, 590, "sel 1 0")
    p.c(tb, fA, 0); p.c(fA, sA)
    p.c(sA, fP1, 0)
    sB = p.obj(720, 620, "sel 1")
    p.c(sA, fB, 1); p.c(fB, sB); p.c(sB, fS1, 0)
    p.c(fP1, spA); p.c(fS1, spA)

    mos = p.obj(560, 790, "moses 2")
    p.c(spA, mos)
    tbf2 = p.obj(620, 820, "t b f")
    p.c(mos, tbf2, 1)
    fsr = p.obj(620, 850, "f 44100")
    hz = p.obj(620, 880, "/")
    p.c(tbf2, hz, 1, 1); p.c(tbf2, fsr, 0); p.c(fsr, hz)
    mlo = p.obj(620, 910, "moses")
    mhi = p.obj(680, 940, "moses")
    p.c(hz, mlo); p.c(mlo, mhi, 1); p.c(mhi, out, 0)

    # --- init: sample rate, frequency window, filter coefficients --------
    lb = p.obj(400, 520, "loadbang")
    srt = p.obj(400, 550, "samplerate~")
    p.c(lb, srt)
    tsr = p.obj(400, 580, "t b f")
    p.c(srt, tsr)
    p.c(tsr, fsr, 1, 1)
    fc = p.obj(400, 610, "f \\$1")
    p.c(tsr, fc, 0)
    tfc = p.obj(400, 640, "t f f")
    p.c(fc, tfc)
    lo = p.obj(480, 680, "/ 1.7")
    hi = p.obj(560, 680, "* 1.15")
    p.c(tfc, lo, 1); p.c(tfc, hi, 1)
    p.c(lo, mlo, 0, 1); p.c(hi, mhi, 0, 1)

    w = p.obj(260, 680, "* 6.283185")
    p.c(tfc, w, 0)
    w0 = p.obj(260, 710, "/ 44100")
    p.c(tsr, w0, 1, 1); p.c(w, w0)
    tw = p.obj(260, 740, "t f f")
    p.c(w0, tw)
    sn = p.obj(360, 770, "sin")
    al = p.obj(360, 800, "* 0.707107")         # alpha = sin(w0)/(2Q), Q = 1/sqrt2
    tal = p.obj(360, 830, "t f f")
    p.c(tw, sn, 1); p.c(sn, al); p.c(al, tal)
    a0 = p.obj(460, 860, "+ 1")
    ta0 = p.obj(460, 890, "t b f")
    one = p.msg(460, 920, "1")
    inv = p.obj(460, 950, "/")                 # 1/a0
    p.c(tal, a0, 1); p.c(a0, ta0); p.c(ta0, inv, 1, 1); p.c(ta0, one, 0); p.c(one, inv)
    am1 = p.obj(360, 890, "- 1")
    fb2 = p.obj(360, 980, "*")
    p.c(tal, am1, 0); p.c(am1, fb2); p.c(inv, fb2, 0, 1)

    cs = p.obj(160, 770, "cos")
    tcs = p.obj(160, 800, "t f f")
    p.c(tw, cs, 0); p.c(cs, tcs)
    ng = p.obj(240, 830, "* -1")
    p1 = p.obj(240, 860, "+ 1")
    ff2 = p.obj(240, 980, "*")
    p.c(tcs, ng, 1); p.c(ng, p1); p.c(p1, ff2); p.c(inv, ff2, 0, 1)
    tff = p.obj(240, 1010, "t f f")
    p.c(ff2, tff)
    half = p.obj(240, 1040, "* 0.5")
    th = p.obj(240, 1070, "t f f")
    p.c(tff, half, 0); p.c(half, th)
    x2 = p.obj(160, 830, "* 2")
    fb1 = p.obj(160, 980, "*")
    p.c(tcs, x2, 0); p.c(x2, fb1); p.c(inv, fb1, 0, 1)
    pk = p.obj(160, 1110, "pack f f f f f")
    p.c(fb2, pk, 0, 1); p.c(tff, pk, 1, 3); p.c(th, pk, 1, 4); p.c(th, pk, 0, 2)
    p.c(fb1, pk, 0, 0)
    p.c(pk, bq1); p.c(pk, bq2)

    p.write(os.path.join(ROOT, "p2m.band~.pd"))


# ---------------------------------------------------------------------------
# pitch2midi~ : main abstraction
#   args     : [pitch2midi~ <midi channel (1)> <threshold dBFS (-50)>]
#   inlet~ 1 : audio (monophonic)
#   inlet  2 : control: thresh <dBFS>, stable <ticks>, midi <0|1>, channel <n>
#   outlet 1 : note number   (like notein left outlet)
#   outlet 2 : velocity      (0 = note off; sent BEFORE the note number)
#   outlet 3 : detected frequency in Hz (continuous, while a pitch is valid)
#   also sends note on/off to [noteout]
# ---------------------------------------------------------------------------
def build_main():
    p = Patch(1300, 1000)
    p.text(20, 10, "pitch2midi~ [channel] [threshold dBFS] : monophonic "
                   "audio -> MIDI notes. Heavy / plugdata Compiled Mode safe")
    ain = p.obj(20, 50, "inlet~")
    cin = p.obj(900, 50, "inlet")
    o_note = p.obj(700, 940, "outlet")
    o_vel = p.obj(800, 940, "outlet")
    o_hz = p.obj(900, 940, "outlet")

    hp = p.obj(20, 80, "hip~ 20")
    p.c(ain, hp)

    # filter bank
    bands = []
    for i in range(BAND_COUNT):
        fc = BAND_BASE_HZ * 2 ** (i / 2.0)
        x = 20 + (i % 6) * 120
        yy = 330 + (i // 6) * 30
        b = p.obj(x, yy, "p2m.band~ %g" % round(fc, 2))
        p.c(hp, b)
        bands.append(b)

    # input power
    sq = p.obj(20, 120, "*~")
    p.c(hp, sq); p.c(hp, sq, 0, 1)
    lp = p.obj(20, 150, "lop~ 30")
    p.c(sq, lp)

    # analysis clock
    lb = p.obj(500, 50, "loadbang")
    tinit = p.obj(500, 80, "t b b")
    p.c(lb, tinit)
    met = p.obj(500, 120, "metro 4")
    p.c(tinit, met, 0)
    snap = p.obj(20, 190, "snapshot~")
    p.c(lp, snap); p.c(met, snap)
    tpin = p.obj(20, 220, "t f f")
    p.c(snap, tpin)

    # level in dB (Pd scale: 100 = 0 dBFS)
    mx = p.obj(200, 250, "max 1e-20")
    lg = p.obj(200, 280, "log")
    k = p.obj(200, 310, "* 4.342945")
    db = p.obj(280, 310, "+ 100")
    p.c(tpin, mx, 1); p.c(mx, lg); p.c(lg, k); p.c(k, db)
    tdb = p.obj(280, 250, "t f f f")
    # (placed visually above, logic order: db -> tdb)
    p.c(db, tdb)
    fdb = p.obj(400, 700, "f")
    p.c(tdb, fdb, 2, 1)

    # release guard: no NEW notes while the level falls > 10 dB below a
    # slowly decaying peak (stops filter ringing / note tails from triggering)
    tga = p.obj(1000, 250, "t f f")
    p.c(tdb, tga, 1)
    pmx = p.obj(1080, 280, "max")
    tpk = p.obj(1080, 310, "t f f")
    pdec = p.obj(1160, 340, "- 0.5")
    p10 = p.obj(1080, 340, "- 4")
    gcmp = p.obj(1000, 370, ">")
    p.c(tga, pmx, 1); p.c(pmx, tpk); p.c(tpk, pdec, 1); p.c(pdec, pmx, 0, 1)
    p.c(tpk, p10, 0); p.c(p10, gcmp, 0, 1); p.c(tga, gcmp, 0)

    # gate with 6 dB hysteresis
    gt = p.obj(280, 200, ">")
    p.c(tdb, gt, 0)
    tst = p.obj(280, 170, "t f f f f")
    p.c(gt, tst)
    fstate = p.obj(470, 170, "f")
    p.c(tst, fstate, 3, 1)
    stm = p.obj(400, 140, "* -6")
    thrp = p.obj(400, 110, "+ 50")
    p.c(tst, stm, 2); p.c(stm, thrp); p.c(thrp, gt, 0, 1)
    spg = p.obj(20, 260, "spigot")
    p.c(tst, spg, 1, 1)
    p.c(tpin, spg, 0)
    sel0 = p.obj(560, 200, "sel 0")
    p.c(tst, sel0, 0)

    # evaluate bands (lowest valid band wins)
    tev = p.obj(20, 290, "t b f b")
    p.c(spg, tev)
    m1 = p.msg(260, 400, "1")
    m0 = p.msg(300, 400, "0")
    p.c(tev, m1, 2); p.c(tev, m0, 2)
    tb = p.obj(20, 300 - 10 + 20, "t " + " ".join(["f"] * BAND_COUNT))
    p.c(tev, tb, 1)
    for i, b in enumerate(bands):
        p.c(tb, b, BAND_COUNT - 1 - i, 1)     # band 0 fires first
    col = p.obj(20, 410, "spigot 1")
    for b in bands:
        p.c(b, col)
    p.c(m1, col, 0, 1)
    tcol = p.obj(20, 440, "t b f")
    p.c(col, tcol)
    m0b = p.msg(20, 470, "0")
    p.c(tcol, m0b, 0); p.c(m0b, col, 0, 1)
    cand = p.obj(140, 500, "f")
    p.c(tcol, cand, 1, 1); p.c(m0, cand, 0, 1); p.c(tev, cand, 0)
    cm = p.obj(140, 530, "moses 1")
    p.c(cand, cm)
    tc = p.obj(200, 560, "t f f")
    p.c(cm, tc, 1)
    p.c(tc, o_hz, 1)
    # required stable ticks = N + 1.5 periods (4 ms ticks) -> low notes wait longer
    treq = p.obj(300, 590, "t b f")
    m375 = p.msg(300, 620, "375")
    dreq = p.obj(300, 650, "/")
    areq = p.obj(300, 680, "+ 2")
    p.c(tc, treq, 1); p.c(treq, dreq, 1, 1); p.c(treq, m375, 0); p.c(m375, dreq); p.c(dreq, areq)
    # Hz -> fractional MIDI: 12*log2(f/440)+69
    flg = p.obj(140, 590, "log")
    fk = p.obj(140, 620, "* 17.31234")
    fo = p.obj(140, 650, "+ -36.37632")
    p.c(tc, flg, 0); p.c(flg, fk); p.c(fk, fo)

    # pitch hysteresis: stay on current note while within 0.8 semitone
    tm = p.obj(140, 680, "t f f")
    p.c(fo, tm)
    rcur1 = p.obj(260, 690, "r \\$0-cur")
    dcur = p.obj(220, 720, "-")
    p.c(tm, dcur, 1); p.c(rcur1, dcur, 0, 1)
    adc = p.obj(220, 750, "abs")
    near = p.obj(220, 780, "< 0.8")
    tnear = p.obj(220, 810, "t f f")
    p.c(dcur, adc); p.c(adc, near); p.c(near, tnear)
    eq0 = p.obj(220, 840, "== 0")
    p.c(tnear, eq0, 0)
    tm2 = p.obj(140, 860, "t f f")
    p.c(tm, tm2, 0)
    spX = p.obj(80, 890, "spigot")
    spY = p.obj(160, 890, "spigot")
    p.c(tnear, spX, 1, 1); p.c(eq0, spY, 0, 1)
    p.c(tm2, spX, 1); p.c(tm2, spY, 0)
    tbx = p.obj(80, 920, "t b")
    rcur2 = p.obj(30, 920, "r \\$0-cur")
    fcur = p.obj(80, 950, "f")
    p.c(spX, tbx); p.c(tbx, fcur); p.c(rcur2, fcur, 0, 1)
    rnd = p.obj(160, 920, "+ 0.5")
    itg = p.obj(160, 950, "i")
    p.c(spY, rnd); p.c(rnd, itg)

    # stability: same note for N consecutive ticks
    tn = p.obj(420, 500, "t f f f")
    p.c(fcur, tn); p.c(itg, tn)
    rln = p.obj(560, 500, "r \\$0-lastn")
    eqn = p.obj(520, 540, "==")
    p.c(tn, eqn, 2); p.c(rln, eqn, 0, 1)
    sl1 = p.obj(520, 570, "sel 1")
    p.c(eqn, sl1)
    fcnt = p.obj(520, 600, "f")
    inc = p.obj(520, 630, "+ 1")
    one = p.msg(580, 600, "1")
    p.c(sl1, fcnt, 0); p.c(fcnt, inc); p.c(sl1, one, 1)
    tcnt = p.obj(520, 660, "t f f")
    p.c(inc, tcnt); p.c(one, tcnt); p.c(tcnt, fcnt, 1, 1)
    ge = p.obj(520, 690, ">= 3")
    p.c(tcnt, ge, 0); p.c(areq, ge, 0, 1)
    sln = p.obj(470, 530, "s \\$0-lastn")
    p.c(tn, sln, 1)
    spS = p.obj(420, 720, "spigot")
    p.c(ge, spS, 0, 1); p.c(tn, spS, 0)
    tch = p.obj(420, 750, "t f f")
    p.c(spS, tch)
    rcur3 = p.obj(540, 750, "r \\$0-cur")
    neq = p.obj(500, 780, "!=")
    p.c(tch, neq, 1); p.c(rcur3, neq, 0, 1)
    spT = p.obj(420, 810, "spigot")
    p.c(neq, spT, 0, 1); p.c(tch, spT, 0)

    # new note: release old, then note on
    spD = p.obj(420, 830, "spigot")
    p.c(gcmp, spD, 0, 1); p.c(spT, spD)
    tnn = p.obj(420, 850, "t f b")
    p.c(spD, tnn)
    tnf = p.obj(420, 870, "t f f")
    p.c(tnn, tnf, 0)
    scur = p.obj(520, 900, "s \\$0-cur")
    p.c(tnf, scur, 1)
    ton = p.obj(420, 900, "t f b")
    p.c(tnf, ton, 0)
    p.c(ton, fdb, 1)
    vm = p.obj(400, 730, "- 40")
    vk = p.obj(400, 760, "* 2.1167")
    vc = p.obj(400, 790, "clip 1 127")
    vi = p.obj(400, 820, "i")
    p.c(fdb, vm); p.c(vm, vk); p.c(vk, vc); p.c(vc, vi)
    pk = p.obj(700, 820, "pack f f")
    p.c(vi, pk, 0, 1); p.c(ton, pk, 0, 0)

    # release (bang): note off for current note if any
    rel = p.obj(700, 600, "f")
    rcur4 = p.obj(760, 570, "r \\$0-cur")
    p.c(rcur4, rel, 0, 1)
    p.c(tnn, rel, 1)
    rm = p.obj(700, 630, "moses 0")
    p.c(rel, rm)
    trel = p.obj(760, 660, "t b f")
    p.c(rm, trel, 1)
    off = p.msg(820, 690, "\\$1 0")
    p.c(trel, off, 1); p.c(off, pk)
    mneg = p.msg(760, 720, "-1")
    scur2 = p.obj(760, 750, "s \\$0-cur")
    p.c(trel, mneg, 0); p.c(mneg, scur2)

    # gate closed -> release + forget last candidate
    tgo = p.obj(560, 230, "t b b")
    p.c(sel0, tgo, 0)
    p.c(tgo, rel, 1)
    mneg2 = p.msg(560, 260, "-1")
    sln2 = p.obj(560, 290, "s \\$0-lastn")
    p.c(tgo, mneg2, 0); p.c(mneg2, sln2)

    # output: outlets (always) + noteout (switchable)
    tout = p.obj(700, 850, "t a a")
    p.c(pk, tout)
    up = p.obj(700, 900, "unpack f f")
    p.c(tout, up, 0)
    p.c(up, o_vel, 1); p.c(up, o_note, 0)
    spm = p.obj(900, 850, "spigot 1")
    p.c(tout, spm, 1)
    up2 = p.obj(900, 880, "unpack f f")
    nout = p.obj(900, 910, "noteout")
    p.c(spm, up2); p.c(up2, nout, 1, 1); p.c(up2, nout, 0, 0)

    # control inlet
    rt = p.obj(900, 90, "route thresh stable midi channel")
    p.c(cin, rt)
    thr = p.obj(900, 130, "+ 100")
    p.c(rt, thr, 0)
    tthr = p.obj(900, 160, "t b f")
    p.c(thr, tthr); p.c(tthr, thrp, 1, 1); p.c(tthr, fstate, 0)
    p.c(fstate, stm)
    mst = p.obj(1000, 130, "max 1")
    p.c(rt, mst, 1); p.c(mst, areq, 0, 1)
    p.c(rt, spm, 2, 1)
    chn = p.obj(1100, 130, "clip 1 16")
    p.c(rt, chn, 3); p.c(chn, nout, 0, 2)

    # init from creation arguments
    tia = p.obj(620, 80, "t b b b")
    p.c(tinit, tia, 1)
    a1 = p.obj(620, 110, "f \\$1")
    p.c(tia, a1, 2)
    a1m = p.obj(620, 140, "max 1")
    p.c(a1, a1m); p.c(a1m, chn)
    a2 = p.obj(700, 110, "f \\$2")
    p.c(tia, a2, 1)
    s0 = p.obj(700, 140, "sel 0")
    p.c(a2, s0)
    m50 = p.msg(700, 170, "-50")
    p.c(s0, m50, 0); p.c(m50, thr); p.c(s0, thr, 1)
    mi = p.msg(780, 110, "-1")
    p.c(tia, mi, 0); p.c(mi, scur2); p.c(mi, sln2)

    p.write(os.path.join(ROOT, "pitch2midi~.pd"))


# ---------------------------------------------------------------------------
# help / example patch
# ---------------------------------------------------------------------------
def build_help():
    p = Patch(980, 720)
    p.text(20, 10, "pitch2midi~ - monophonic pitch detector: audio in -> MIDI notes out")
    p.text(20, 35, "Pure Pd vanilla - no externals. Runs in plugdata Compiled Mode / Heavy (hvcc).")
    adc = p.obj(20, 80, "adc~")
    tg = p.obj(120, 80, "tgl 18 0 empty empty test-tone 22 9 0 12 #fcfcfc #000000 #000000 0 1")
    tone = p.obj(120, 110, "osc~ 220")
    tsw = p.obj(120, 140, "*~")
    p.c(tone, tsw); p.c(tg, tsw, 0, 1)
    ctl = p.text(470, 80, "control messages (right inlet):")
    m1 = p.msg(470, 110, "thresh -40")
    p.text(570, 110, "gate threshold in dBFS (default -50)")
    m2 = p.msg(470, 140, "stable 2")
    p.text(570, 140, "extra 4 ms ticks a note must be stable (default 2)")
    m3 = p.msg(470, 170, "midi 0")
    m3b = p.msg(530, 170, "midi 1")
    p.text(600, 170, "MIDI port output off / on")
    m4 = p.msg(470, 200, "channel 2")
    p.text(570, 200, "MIDI channel 1-16")
    det = p.obj(20, 250, "pitch2midi~ 1 -50")
    p.c(adc, det); p.c(tsw, det)
    for m in (m1, m2, m3, m3b, m4):
        p.c(m, det, 0, 1)
    p.text(20, 225, "args: [pitch2midi~ <midi channel> <threshold dBFS>]")
    n = p.atom(20, 300, 5, "note")
    v = p.atom(110, 300, 5, "vel")
    hz = p.atom(200, 300, 7, "Hz")
    p.c(det, n, 0); p.c(det, v, 1); p.c(det, hz, 2)
    p.text(20, 335, "outlets work like [notein]: velocity arrives first then note (velocity 0 = note off). "
                    "Notes are also sent to [noteout] -> your MIDI out port.")
    pk = p.obj(20, 390, "pack f f")
    pr = p.obj(20, 420, "print pitch2midi")
    p.c(det, pk, 0); p.c(det, pk, 1, 1); p.c(pk, pr)
    # tiny mono synth driven by the outlets
    p.text(300, 390, "example: drive a synth exactly like you would from [notein]")
    ptk = p.obj(300, 420, "pack f f")
    p.c(det, ptk, 0); p.c(det, ptk, 1, 1)
    up = p.obj(300, 450, "unpack f f")
    p.c(ptk, up)
    mt = p.obj(300, 480, "mtof")
    ph = p.obj(300, 510, "phasor~")
    p.c(up, mt, 0); p.c(mt, ph)
    vd = p.obj(380, 480, "/ 127")
    vs = p.obj(380, 510, "pack f 10")
    ln = p.obj(380, 540, "line~")
    p.c(up, vd, 1); p.c(vd, vs); p.c(vs, ln)
    amp = p.obj(300, 570, "*~")
    p.c(ph, amp); p.c(ln, amp, 0, 1)
    vol = p.obj(300, 600, "*~ 0.1")
    dac = p.obj(300, 630, "dac~")
    p.c(amp, vol); p.c(vol, dac); p.c(vol, dac, 0, 1)
    p.text(620, 260, "To use it from ANOTHER patch or app with [notein]: "
                     "pick a virtual MIDI port as Pd's MIDI output (macOS: IAC Driver "
                     "in Audio MIDI Setup). Inside the same patch just use the outlets.")
    p.text(620, 400, "Tips: feed one monophonic source (voice / bass / guitar single notes). "
                     "Range ~40 Hz - 2.5 kHz (MIDI 28-99). Latency ~1.5-3 periods + 10 ms "
                     "(about 15 ms at A4 and 65 ms at low E2).")
    dsp = p.msg(20, 140, "\\; pd dsp 1")
    p.write(os.path.join(ROOT, "pitch2midi~-help.pd"))


if __name__ == "__main__":
    build_band()
    build_main()
    build_help()
    print("wrote p2m.band~.pd, pitch2midi~.pd, pitch2midi~-help.pd")
