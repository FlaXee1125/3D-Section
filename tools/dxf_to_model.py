#!/usr/bin/env python3
"""Konversi DXF potongan melintang (SK1/SK2 x AWAL/TENGAH/AKHIR) -> data/model.json.

Satu bingkai (BORDER) = satu potongan melintang. Koordinat lokal: x = offset dari as jalan
(negatif = UTARA, positif = SELATAN), y = elevasi (m). Elevasi dikalibrasi dari label sumbu elevasi.
Dikelompokkan berdasarkan zona O (O1, O4, ... O10) dan skenario.
"""
import sys, re, json, collections, math
import numpy as np, ezdxf
from shapely.geometry import Polygon, box, MultiPolygon, LineString
from shapely.ops import unary_union
from shapely import affinity

XL = 36.0   # jangkauan offset yang dimodelkan (m, kiri-kanan as jalan)
SRC = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else 'data/model.json'
doc = ezdxf.readfile(SRC)
ms = doc.modelspace()

# ---------- 1. bingkai & entitas -> bingkai
frames = []
for e in ms:
    if e.dxftype() == 'LWPOLYLINE' and e.dxf.layer == 'POT_ALL_BORDER':
        p = [(a[0], a[1]) for a in e.get_points()]
        xs = [a for a, _ in p]; ys = [b for _, b in p]
        frames.append(dict(x0=min(xs), x1=max(xs), y0=min(ys), y1=max(ys),
                           poly=collections.defaultdict(list), text=[], ins=[]))
def find(x, y):
    for f in frames:
        if f['x0'] <= x <= f['x1'] and f['y0'] <= y <= f['y1']: return f
titles = []
for e in ms:
    t = e.dxftype()
    if t == 'LWPOLYLINE':
        pts = e.get_points(); f = find(pts[0][0], pts[0][1])
        if f and e.dxf.layer != 'POT_ALL_BORDER':
            f['poly'][e.dxf.layer].append([(float(a[0]), float(a[1])) for a in pts])
    elif t == 'TEXT':
        x, y = float(e.dxf.insert.x), float(e.dxf.insert.y)
        f = find(x, y)
        if f: f['text'].append((e.dxf.layer, x, y, e.dxf.text))
        if e.dxf.text.startswith('SALURAN'): titles.append((x, y, e.dxf.text))
    elif t == 'INSERT':
        f = find(e.dxf.insert.x, e.dxf.insert.y)
        if f: f['ins'].append((float(e.dxf.insert.x), float(e.dxf.insert.y)))

TITLE = re.compile(r'SALURAN (\d+) / BAGIAN (\d+) - (O\d+) - STA (\S+) s\.d\. (\S+) - SKENARIO (\d)')
def sta_val(s):
    a, b = s.split('+'); return int(a) * 1000 + float(b)

# ---------- 2. isi bingkai
def parse_frame(f):
    f['cx'] = (f['x0'] + f['x1']) / 2
    ticks = [(y, float(t)) for l, x, y, t in f['text'] if l == 'POT_ALL_DIM' and re.fullmatch(r'\d+', t)]
    y, v = min(ticks); f['base'] = y - 0.15 - v          # elev = y - base
    lab = [t for l, x, y, t in f['text'] if re.match(r'SK\d - ', t)][0]
    m = re.match(r'SK(\d) - (AWAL|TENGAH|AKHIR) - STA (\S+)', lab)
    f['sk'], f['pos'], f['sta'] = int(m[1]), m[2], sta_val(m[3])
    L = lambda pts: [(round(x - f['cx'], 3), round(y - f['base'], 3)) for x, y in pts]
    f['L'] = L
    g = f['poly']['POT_ALL_GROUND'][0]
    f['ground'] = sorted(L(g))
    asj = [t for l, x, y, t in f['text'] if t.startswith('As jalan')][0]
    f['deck'] = float(re.search(r'([\d.]+) m', asj)[1])
    # teks per sisi
    info = {'U': {}, 'S': {}}
    for l, x, y, t in f['text']:
        s = 'U' if x - f['cx'] < 0 else 'S'; d = info[s]
        if (m := re.match(r'(UTARA|SELATAN): (\S+)', t)): d['code'] = m[2]
        elif (m := re.match(r'(.+?) / (Timbunan|Muka Tanah Dasar|Ruang Bebas Jalan)$', t)): d['type'], d['ctx'] = m[1], m[2]
        elif (m := re.match(r'Top ([\d.]+) m; Bottom ([\d.]+) m', t)): d['top'], d['bottom'] = float(m[1]), float(m[2])
        elif (m := re.match(r'b ([\d.]+) m; H ([\d.]+) m; lebar luar ([\d.]+) m', t)): d['b'], d['H'], d['outer'] = map(float, m.groups())
        elif (m := re.match(r'Tanah ([\d.]+) m; offset ([\d.]+) m', t)): d['ground'], d['offset'] = float(m[1]), float(m[2])
        elif (m := re.match(r'APJ/RUMIJA: offset ([\d.]+) m; elv kaki ([\d.]+) m', t)): d['rumija'], d['kaki'] = float(m[1]), float(m[2])
        elif re.match(r'[US]: ', t): d.setdefault('note', []).append(t[3:])
        elif t.startswith('Top di atas') or t.startswith('t1='): d.setdefault('note', []).append(t)
    # catatan U:/S: ditentukan oleh awalan, bukan posisi
    for l, x, y, t in f['text']:
        if (m := re.match(r'([US]): (.+)', t)):
            for s in 'US':
                if t[3:] in info[s].get('note', []) and s != m[1]: info[s]['note'].remove(t[3:])
            info[m[1]].setdefault('note', [])
            if m[2] not in info[m[1]]['note']: info[m[1]]['note'].append(m[2])
    f['info'] = info
for f in frames: parse_frame(f)

# bingkai -> judul (kolom sama, judul terdekat di atas)
for f in frames:
    best = None
    for tx, ty, tt in titles:
        m = TITLE.match(tt)
        if int(m[6]) != f['sk'] or ty < f['y1'] or abs(tx - (f['x0'] + 1.0)) > 5: continue
        if best is None or ty < best[0]: best = (ty, m)
    m = best[1]
    f['saluran'], f['bagian'], f['O'], f['sk_t'] = int(m[1]), int(m[2]), m[3], int(m[6])

# ---------- 3. geometri jalan existing (blok) relatif terhadap as jalan
def mirror(pts): return [(-x, y) for x, y in pts]
R = {
 'pav':  [(0,-.33),(0,0),(.4,0),(8.27,-.236),(10.27,-.336),(10.401,-.673),(10.27,-.666),(8.27,-.566),(.4,-.33)],
 'base': [(0,-.48),(0,-.33),(.4,-.33),(8.27,-.566),(10.401,-.666),(10.461,-.826),(8.27,-.716),(.4,-.48)],
 'lfa':  [(0,-.68),(0,-.48),(.4,-.48),(8.27,-.716),(10.461,-.826),(10.54,-1.03),(8.27,-.916),(.4,-.68)],
}
def sym(pts):
    a = Polygon(pts).buffer(0); b = affinity.scale(a, xfact=-1, origin=(0, 0))
    return unary_union([a, b])
ROAD = {k: sym(v) for k, v in R.items()}
BARRIER = sym([(0,1.11),(.075,1.11),(.125,.27),(.4,.03),(.4,-.05),(0,-.05)])
GUARD_R = Polygon([(11.575,-1.394),(11.753,-1.394),(11.753,.406),(11.397,.406),(11.397,.094),(11.575,.094)])
GUARD_L = affinity.scale(GUARD_R, xfact=-1, origin=(0, 0))
# garis atas timbunan di bawah perkerasan (relatif as jalan)
SUB_R = [(10.401, None), (10.54, -1.03), (8.27, -.916), (.4, -.68)]

# ---------- 4. bangun elemen per bingkai
def polys(g):
    if g.is_empty: return []
    if isinstance(g, Polygon): return [g]
    return [p for p in getattr(g, 'geoms', []) if isinstance(p, Polygon) and p.area > 1e-5]
def clean(g): return g.buffer(0) if not g.is_valid else g

def build_frame(f, floor):
    d = f['deck']; G = f['ground']; gx = np.array([p[0] for p in G]); gy = np.array([p[1] for p in G])
    Gf = lambda x: float(np.interp(x, gx, gy))
    L = f['L']
    # --- saluran per sisi
    chan = {}
    for s in 'US':
        sign = -1 if s == 'U' else 1
        shapes = []
        for lay in ('POT_ALL_CHANNEL1', 'POT_ALL_CHANNEL2', 'POT_ALL_BUILDING'):
            for pts in f['poly'].get(lay, []):
                pl = L(pts)
                if np.mean([p[0] for p in pl]) * sign > 0: shapes.append((lay, pl))
        if not shapes: continue
        typ = f['info'][s].get('type', '')
        if shapes[0][0] == 'POT_ALL_BUILDING':
            rects = sorted([Polygon(p).buffer(0) for _, p in shapes], key=lambda p: -p.area)
            if len(rects) >= 2: conc = rects[0].difference(rects[1]); hull = rects[0]; mat = 'culvert'
            else:
                r = rects[0]; hull = r.buffer(0.15, join_style=2); conc = hull.difference(r); mat = 'culvert'
        else:
            conc = clean(Polygon(shapes[0][1])); hull = conc.convex_hull; mat = 'channel'
        chan[s] = (conc, hull, mat)
    # --- rantai permukaan rencana per sisi (dari tengah ke luar)
    chains = {}
    for s in 'US':
        sign = -1 if s == 'U' else 1
        segs = []
        for pts in f['poly'].get('POT_ALL_ROAD', []):
            pl = L(pts)
            if np.mean([p[0] for p in pl]) * sign > 0:
                pl.sort(key=lambda p: abs(p[0])); segs.append(pl)
        segs.sort(key=lambda pl: abs(pl[0][0]))
        ch = []
        for pl in segs:
            for p in pl:
                if not ch or abs(ch[-1][0]-p[0]) > 1e-6 or abs(ch[-1][1]-p[1]) > 1e-6: ch.append(p)
        chains[s] = ch
    # titik awal bahu (x=±12.353) dan sub-struktur jalan
    def sub(sign):
        a = (12.353*sign, d-0.533)
        # garis bahu s/d tepi perkerasan
        x1, y1, x2, y2 = 12.353, d-0.533, 10.27, d-0.336
        ye = y1 + (10.401-x1)*(y2-y1)/(x2-x1)
        return [a, (10.401*sign, ye), (10.54*sign, d-1.03), (8.27*sign, d-.916), (.4*sign, d-.68)]
    left = list(reversed(chains['U'])) if chains['U'] else []   # luar -> tengah
    right = chains['S']                                          # tengah -> luar
    toeL = left[0][0] if left else -12.353
    toeR = right[-1][0] if right else 12.353
    mid = sorted(sub(-1) + sub(1), key=lambda p: p[0])
    def add(A, pts):
        for p in pts:
            if not A or abs(A[-1][0]-p[0]) > 1e-6 or abs(A[-1][1]-p[1]) > 1e-6: A.append(p)
    A = [(-40, floor)]
    add(A, [(x, y) for x, y in G if -40 < x < toeL - 1e-6])
    add(A, left)
    add(A, [p for p in mid if abs(p[0]) <= 12.353 + 1e-6 and not (left and abs(p[0] + 12.353) < 1e-3)])
    add(A, right)
    add(A, [(x, y) for x, y in G if toeR + 1e-6 < x < 40]); A.append((40, floor))
    # --- fungsi permukaan tanah: F(x) = permukaan atas pekerjaan tanah (rencana / galian / takik saluran), G(x) = tanah asli
    P = A[1:-1]
    xs, ys = [], []
    for x, y in sorted(P, key=lambda p: p[0]):
        if xs and x <= xs[-1] + 1e-4: x = xs[-1] + 1e-4
        xs.append(x); ys.append(y)
    xs, ys = np.array(xs), np.array(ys)
    hulls = []
    for s_, (c, h, m) in chan.items():
        hx0, hy0, hx1, hy1 = h.bounds
        hulls.append((hx0, hx1, h))
    def hb(h, x):
        ln = LineString([(x, -1e3), (x, 1e3)]).intersection(h)
        return None if ln.is_empty else ln.bounds[1]
    def F(x):
        v = float(np.interp(x, xs, ys))
        for hx0, hx1, h in hulls:
            if hx0 + 1e-6 < x < hx1 - 1e-6:
                lo = hb(h, x)
                if lo is not None: v = min(v, lo)
        return v
    bp = set(round(float(v), 4) for v in xs) | set(round(float(v), 4) for v in gx) | {-XL, XL}
    for hx0, hx1, h in hulls:
        bp |= {round(hx0, 4), round(hx0 + 1e-3, 4), round(hx1 - 1e-3, 4), round(hx1, 4)}
        bp |= {round(p[0], 4) for p in h.exterior.coords}
    bp = sorted(v for v in bp if -XL <= v <= XL)
    earth = dict(bp=bp, F=F, G=Gf)
    els = []
    for k, mat in (('base', 'base'), ('lfa', 'lfa'), ('pav', 'pav')):
        els.append((k, mat, ROAD[k].translate(0, d) if hasattr(ROAD[k], 'translate') else affinity.translate(ROAD[k], 0, d)))
    els.append(('barrier', 'barrier', affinity.translate(BARRIER, 0, d)))
    els.append(('guardU', 'steel', affinity.translate(GUARD_L, 0, d)))
    els.append(('guardS', 'steel', affinity.translate(GUARD_R, 0, d)))
    for s, (c, h, m) in chan.items():
        for i, p in enumerate(sorted(polys(c), key=lambda p: p.centroid.x)): els.append((f'chan{s}{i}', m, p))
    for lay in f['poly'].get('POT_ALL_APJ', []):
        pl = L(lay)
        if len(pl) >= 8:
            p = clean(Polygon(pl))
            minx, miny, maxx, maxy = p.bounds
            gl = min(Gf(minx), Gf(maxx)) - 0.3          # patok ditanam sampai tanah
            p = unary_union([p, box(minx, gl, maxx, miny + 0.01)]).simplify(0.001)
            els.append(('post' + ('U' if np.mean([a for a, _ in pl]) < 0 else 'S'), 'post', p))
    return els, earth

def ring(coords):
    c = [(round(x, 3), round(y, 3)) for x, y in coords]
    if c[0] == c[-1]: c = c[:-1]
    a = 0.5 * sum(c[i][0]*c[(i+1) % len(c)][1] - c[(i+1) % len(c)][0]*c[i][1] for i in range(len(c)))
    return c if a > 0 else c[::-1]
def canon(c, outer=True):
    i = min(range(len(c)), key=lambda k: (c[k][0], c[k][1])); c = c[i:] + c[:i]
    return c
def poly_rings(p):
    p = clean(p) if not p.is_valid else p
    from shapely.geometry.polygon import orient
    p = orient(p, 1.0)
    rs = [canon(ring(p.exterior.coords))]
    for h in p.interiors:
        rs.append(canon(ring(h.coords)[::-1][::-1]))
    # lubang: orientasi CW
    rs = [rs[0]] + [canon(list(reversed(ring(h.coords)))) for h in p.interiors]
    return rs
def _cum(c):
    L = [0.0]
    for i in range(len(c)):
        L.append(L[-1] + math.dist(c[i], c[(i+1) % len(c)]))
    return L
def _at(c, L, t):
    """titik pada parameter keliling t in [0,1)"""
    d = (t % 1.0) * L[-1]
    lo, hi = 0, len(c)
    while hi - lo > 1:
        m = (lo + hi) // 2
        if L[m] <= d: lo = m
        else: hi = m
    seg = L[lo+1] - L[lo]; u = 0 if seg < 1e-12 else (d - L[lo]) / seg
    a, b = c[lo], c[(lo+1) % len(c)]
    return (a[0] + (b[0]-a[0])*u, a[1] + (b[1]-a[1])*u)
def _samples(c, m=240):
    L = _cum(c); return np.array([_at(c, L, i/m) for i in range(m)])
def _rebase(c, shift_t):
    """putar cincin agar parameter 0 berada di shift_t (sisipkan titik bila perlu); kembalikan titik+param baru"""
    L = _cum(c); tot = L[-1]
    pts = [(L[i]/tot, c[i]) for i in range(len(c))]
    out = [((t - shift_t) % 1.0, p) for t, p in pts]
    out.append((0.0, _at(c, L, shift_t)))
    out.sort(key=lambda q: q[0])
    return out                               # [(param, titik)]
def align_rings(rings_list):
    """rings_list: daftar cincin (satu per potongan) -> cincin dengan jumlah & urutan titik sama."""
    base = rings_list[0]
    if all(len(r) == len(base) for r in rings_list):
        # coba cocokkan per-vertex dengan geser bilangan bulat
        res = [base]; okay = True
        for r in rings_list[1:]:
            n = len(r); best = None
            ref = res[-1]
            for sft in range(n):
                rr = r[sft:] + r[:sft]
                ca = np.mean(ref, axis=0); cb = np.mean(rr, axis=0)
                dsum = sum(math.dist((a[0]-ca[0], a[1]-ca[1]), (b[0]-cb[0], b[1]-cb[1])) for a, b in zip(ref, rr)) / n
                if best is None or dsum < best[0]: best = (dsum, rr)
            if best[0] > 1.5: okay = False; break
            res.append(best[1])
        if okay: return res
    # umum: selaraskan lewat parameter keliling lalu satukan semua parameter
    M = 240; ref_s = _samples(base, M); based = [(base, 0.0)]; prev = ref_s
    for r in rings_list[1:]:
        sm = _samples(r, M)
        pc = prev - prev.mean(axis=0); sc = sm - sm.mean(axis=0)
        best = min(range(M), key=lambda s: float(((pc - np.roll(sc, -s, axis=0))**2).sum()))
        based.append((r, best / M)); prev = np.roll(sm, -best, axis=0)
    reb = [_rebase(c, st) for c, st in based]
    params = sorted({round(t, 5) for rb in reb for t, _ in rb})
    uni = []
    for t in params:
        if not uni or t - uni[-1] > 2e-4: uni.append(t)
    out = []
    for c, st in based:
        L = _cum(c)
        out.append([_at(c, L, (t + st) % 1.0) for t in uni])
    return [[(round(x, 3), round(y, 3)) for x, y in r] for r in out]

# ---------- 5. susun per zona / skenario / segmen
POS = ['AWAL', 'TENGAH', 'AKHIR']
byO = collections.defaultdict(list)
for f in frames: byO[f['O']].append(f)
model = {'sumber': SRC.split('/')[-1], 'zona': {}}
for O in sorted(byO, key=lambda s: int(s[1:])):
    fr = byO[O]
    floor = math.floor(min(min(p[1] for p in f['ground']) for f in fr) - 2)
    z = {'floor': floor, 'skenario': {}}
    segs = collections.defaultdict(dict)
    for f in fr: segs[(f['sk_t'], f['saluran'], f['bagian'])][f['pos']] = f
    for (sk, sal, bag), ps in sorted(segs.items(), key=lambda kv: (kv[0][0], kv[1]['AWAL']['sta'])):
        secs = [ps[p] for p in POS]
        bf = [build_frame(f, floor) for f in secs]
        built = [{k: (mat, poly) for k, mat, poly in els} for els, _ in bf]
        # grid x bersama untuk tiga potongan
        grid = set()
        for _, ea in bf:
            xsb = ea['bp']; Fv = [ea['F'](x) for x in xsb]; Gv = [ea['G'](x) for x in xsb]
            grid |= set(xsb)
            for i in range(len(xsb) - 1):
                d0, d1 = Gv[i] - Fv[i], Gv[i+1] - Fv[i+1]
                if d0 * d1 < 0: grid.add(round(xsb[i] + (xsb[i+1]-xsb[i]) * d0 / (d0 - d1), 4))
        grid = sorted(grid); ug = []
        for v in grid:
            if not ug or v - ug[-1] >= 1e-4: ug.append(v)
        earth_out = {'x': ug, 'F': [], 'S': []}
        for _, ea in bf:
            Fv = [round(ea['F'](x), 3) for x in ug]
            Sv = [round(min(ea['G'](x), f), 3) for x, f in zip(ug, Fv)]
            earth_out['F'].append(Fv); earth_out['S'].append(Sv)
        keys = []
        for b in built:
            for k in b:
                if k not in keys: keys.append(k)
        elements = []
        for k in keys:
            mats = [b[k][0] for b in built if k in b]
            per = []
            for b in built:
                per.append(poly_rings(b[k][1]) if k in b else None)
            ref = next(r for r in per if r)
            nh = len(ref) - 1
            ok = [r if (r and len(r) - 1 == nh) else None for r in per]
            idx = [i for i, r in enumerate(ok) if r]
            if not idx: continue
            aligned = [None] * 3
            slots = []
            for ri in range(nh + 1):
                slots.append(align_rings([ok[i][ri] for i in idx]))
            for n, i in enumerate(idx):
                aligned[i] = [slots[ri][n] for ri in range(nh + 1)]
            elements.append({'k': k, 'm': mats[0], 'r': [None if o is None else [[round(v, 3) for pt in rg for v in pt] for rg in o] for o in aligned]})
        z['skenario'].setdefault(str(sk), []).append({
            'id': f'Saluran {sal} / Bagian {bag}', 'saluran': sal, 'bagian': bag,
            'sta': [s['sta'] for s in secs], 'deck': [s['deck'] for s in secs],
            'info': [s['info'] for s in secs], 'earth': earth_out, 'els': elements})
    allsta = [s for sk in z['skenario'].values() for sg in sk for s in sg['sta']]
    z['sta'] = [min(allsta), max(allsta)]
    model['zona'][O] = z
with open(OUT, 'w') as fh: json.dump(model, fh, separators=(',', ':'))
import os; print(OUT, os.path.getsize(OUT) // 1024, 'KB')
for O, z in model['zona'].items():
    print(O, z['sta'], {k: len(v) for k, v in z['skenario'].items()}, 'floor', z['floor'])
