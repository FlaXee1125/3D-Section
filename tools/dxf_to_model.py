#!/usr/bin/env python3
"""Konversi DXF potongan melintang (SK1/SK2 x AWAL/TENGAH/AKHIR) -> data/model.json.

Satu bingkai (BORDER) = satu potongan melintang. Koordinat lokal: x = offset dari as jalan
(negatif = UTARA, positif = SELATAN), y = elevasi (m). Elevasi dikalibrasi dari label sumbu elevasi.
Dikelompokkan berdasarkan zona O (O1, O4, ... O10) dan skenario.
"""
import os, sys, re, json, collections, math
import numpy as np, ezdxf
from shapely.geometry import Polygon, box, MultiPolygon, LineString, Point
from shapely.ops import unary_union
from shapely import affinity

WALL = 0.20  # tebal dinding siphon / talang (m)
ZC = 12.8    # |offset| tempat saluran irigasi melintang mulai terbuka (di luar badan jalan; di dalamnya lewat gorong-gorong)
PEMATANG = False   # sawah rata (tanpa pematang)
TS = 0.25    # tebal lapisan sawah (m)
CH = 1.0     # tinggi bersih gorong-gorong irigasi (m)
WFR = 0.6    # tinggi muka air di saluran drainase jalan = 60 % tinggi bersih
D0 = 0.5     # dasar saluran irigasi = 0,5 m di bawah muka tanah (arahan)
# titik acuan STA bangunan (kolom 'STA titik acuan' di Data_Drainase_Rev19.xlsx, sheet Bangunan): lokasi saluran irigasi bagi siphon
REF_IRIGASI = {8339.85, 11625.23, 14064.93}
# simpang (STA titik tengah) + tata letak tipikal dari data/simpang.json
# gorong-gorong kawasan (cross drain) di bawah jalan: (STA, elevasi acuan) dari daftar user; hanya Skenario 1
CROSS_RAW = [(993.855487437481, 44.664121309295), (1247.185329020964, 44.857097712159), (1452.351195835671, 45.138209799677),
             (1683.097081721271, 45.447501153871), (1882.157475318112, 45.727211487666), (2181.029658763325, 46.27666604612),
             (2398.7632585363, 47.296375894733), (8735.260030671307, 53.353782183304), (8842.842822913131, 53.446191504784),
             (9532.745137508466, 52.936231096648), (9695.519556815103, 53.401994095743), (14538.439999999991, 51.808000000007),
             (10048.992516074684, 53.286808901653), (14256.99, 50.0), (9321.663612878881, 53.502616371214), (13609.830156282304, 54.5),
             (17883.9, 50.0), (7085.088802914647, 51.249643245526), (8553.84, 52.244171969779)]
CROSS = [(i + 1, st_, el_) for i, (st_, el_) in enumerate(sorted(CROSS_RAW))]       # CD-1 .. CD-19 menurut STA
SIP_PRE = 5.0; SIP_K = 1.0                                                              # transisi mulai 5 m sebelum siphon; ramp siphon curam 1 : 1
CD_CLEAR = 0.5; CD_T = 0.15; CD_LOWER = 0.2                                            # bersih 0,5 x 0,5 m; dinding 15 cm; diturunkan 20 cm dari elevasi acuan
SIMPANG = [('Simpang 1', 3648.12), ('Simpang 2', 8328.29), ('Simpang 3', 12538.61), ('Simpang 4', 15349.0)]
XL = 36.0   # jangkauan offset yang dimodelkan (m, kiri-kanan as jalan)
SIMP = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'simpang.json')))
_FR = SIMP['frame']; SP_UC = _FR['uc']; SP_SIDE = _FR['sisi']; SP_MAIN = _FR['tepi_utama']
SP_G = 0.04        # kelandaian jalan simpang menjauhi jalan utama
SP_E0 = 10.4       # tepi perkerasan jalan utama (offset)
SP_REACH = 38.0    # jangkauan pemodelan simpang searah jalan utama (m dari titik tengah)
MV_C = sum(SP_MAIN) / 2; MV_HW = (SP_MAIN[1] - SP_MAIN[0]) / 2
def map_v_arr(v):  # v tipikal (PDF) -> offset model; lebar jalan utama pada PDF (tepi -4,9 .. 7,2) disesuaikan ke jalan utama model (±10,4 m)
    v = np.asarray(v, dtype=float); dv = v - MV_C; ad = np.abs(dv)
    return np.sign(dv) * np.where(ad <= MV_HW, ad * (SP_E0 / MV_HW), ad + (SP_E0 - MV_HW))
def map_v(v): return float(map_v_arr(v))
def _mirror(pts): return [(2 * SP_UC - u, v) for u, v in pts]
def _flare(arc, edge_v, side_u):
    a = sorted(arc, key=lambda p: abs(p[1]))
    return Polygon(a + [(side_u, a[-1][1]), (side_u, edge_v), (a[0][0], edge_v)]).buffer(0)
_west = [_flare(SIMP['arcs']['NW'], SP_MAIN[0], SP_SIDE[0]), _flare(SIMP['arcs']['SW'], SP_MAIN[1], SP_SIDE[0])]
_pdf_fp = unary_union([Polygon([(SP_SIDE[0], -90), (SP_SIDE[1], -90), (SP_SIDE[1], 90), (SP_SIDE[0], 90)])] + _west +
                      [Polygon(_mirror(list(p.exterior.coords))).buffer(0) for p in _west])
def _to_model(geom):
    import shapely
    g = shapely.segmentize(geom, 0.4)
    from shapely.ops import transform
    return transform(lambda x, y: (np.asarray(x) - SP_UC, map_v_arr(y)), g)
SP_FP = _to_model(_pdf_fp).intersection(box(-70, -XL - 1.0, 70, XL + 1.0))     # (t, offset) model; luar badan jalan = |x| > 10,4

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
# guardrail W-beam: balok (rail) menerus + tiang tersendiri (lihat js/geometry.js: tiang tiap 2 m)
RAIL_R = Polygon([(11.397,.094),(11.575,.094),(11.575,.406),(11.397,.406)])
GPOST_R = unary_union([Polygon([(11.575,-1.394),(11.753,-1.394),(11.753,.406),(11.575,.406)]),
                       Polygon([(11.568,-1.394),(12.025,-1.394),(12.018,-.498),(11.568,-.453)])])
RAIL_L = affinity.scale(RAIL_R, xfact=-1, origin=(0, 0)); GPOST_L = affinity.scale(GPOST_R, xfact=-1, origin=(0, 0))
# garis atas timbunan di bawah perkerasan (relatif as jalan)
SUB_R = [(10.401, None), (10.54, -1.03), (8.27, -.916), (.4, -.68)]

# ---------- 4. bangun elemen per bingkai
def polys(g):
    if g.is_empty: return []
    if isinstance(g, Polygon): return [g]
    return [p for p in getattr(g, 'geoms', []) if isinstance(p, Polygon) and p.area > 1e-5]
def clean(g): return g.buffer(0) if not g.is_valid else g

def talang_geom(cx, ib, b=0.8, h=0.95):
    """talang (flume terbuka): dinding+dasar beton WALL, bak bersih b x h; kembalikan (beton, hull, kavitas air)"""
    W = WALL
    conc = Polygon([(cx - b/2 - W, ib - W), (cx + b/2 + W, ib - W), (cx + b/2 + W, ib + h), (cx + b/2, ib + h), (cx + b/2, ib),
                    (cx - b/2, ib), (cx - b/2, ib + h), (cx - b/2 - W, ib + h)])
    return conc, box(cx - b/2 - W, ib - W, cx + b/2 + W, ib + h), box(cx - b/2, ib, cx + b/2, ib + WFR * h)

def build_frame(f, floor, override=None):
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
                r = rects[0]; hull = r.buffer(WALL, join_style=2); conc = hull.difference(r); mat = 'culvert'
        else:
            conc = clean(Polygon(shapes[0][1])); hull = conc.convex_hull; mat = 'channel'
        chan[s] = (conc, hull, mat)
    centers = {s_: (h.bounds[0] + h.bounds[2]) / 2 for s_, (c, h, m) in chan.items()}
    cavs = {}
    if override == 'siphon': chan = {}                  # siphon tertanam: dibuat sebagai elemen khusus (tanpa takik)
    elif isinstance(override, dict):                    # talang lurus sejajar jalan
        chan = {}
        for s_, (cx_, ib_) in override.items():
            conc_, hull_, cav_ = talang_geom(cx_, ib_); chan[s_] = (conc_, hull_, 'culvert'); cavs[s_] = cav_; centers[s_] = cx_
    for s_, (c, h, m) in ([] if isinstance(override, dict) else chan.items()):
        inf_ = f['info'][s_]; typ_ = inf_.get('type', '')
        if typ_.startswith(('U-Ditch', 'Trapesium')) or typ_.startswith('Talang'):
            if typ_.startswith('Talang'):
                rr = sorted([Polygon(p).buffer(0) for lay_ in ('POT_ALL_BUILDING',) for pts_ in f['poly'].get(lay_, []) for p in [L(pts_)] if np.mean([q[0] for q in p]) * (-1 if s_ == 'U' else 1) > 0], key=lambda p: -p.area)
                cav = rr[0] if rr else None
            else:
                cav = h.difference(c)
                gs = polys(cav); cav = max(gs, key=lambda p: p.area) if gs else None
            if cav is not None and not cav.is_empty and inf_.get('top') is not None and inf_.get('bottom') is not None:
                yw = inf_['bottom'] + WFR * (inf_['top'] - inf_['bottom'])
                minx, miny, maxx, maxy = cav.bounds
                w_ = cav.intersection(box(minx - 1, miny - 1, maxx + 1, yw))
                gs = polys(w_)
                if gs: cavs[s_] = max(gs, key=lambda p: p.area)
    if override: chan = {}          # saluran diganti struktur khusus (mis. siphon berliku)
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
        sl = (y2 - y1) / (x2 - x1); y54 = y1 + (10.54 - x1) * sl          # garis bahu diteruskan ke tepi bawah badan jalan (10,54): tanpa lekukan antara tepi perkerasan dan lereng
        return [a, (10.401*sign, ye), (10.54*sign, y54), (8.27*sign, d-.916), (.4*sign, d-.68)]
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
    bp |= {round(v, 4) for v in (-ZC, ZC, -ZC + 1e-3, ZC - 1e-3, toeL, toeR)}
    bp = sorted(v for v in bp if -XL <= v <= XL)
    hxS = [h.bounds[2] for s_, (c, h, m) in chan.items() if s_ == 'S']
    F0 = lambda x: float(np.interp(x, xs, ys))
    earth = dict(bp=bp, F=F, F0=F0, G=Gf, hx1S=hxS[0] if hxS else None, toeL=toeL, toeR=toeR, centers=centers, hulls={s_: h for s_, (c, h, m) in chan.items()})
    els = []
    for k, mat in (('base', 'base'), ('lfa', 'lfa'), ('pav', 'pav')):
        els.append((k, mat, ROAD[k].translate(0, d) if hasattr(ROAD[k], 'translate') else affinity.translate(ROAD[k], 0, d)))
    els.append(('barrier', 'barrier', affinity.translate(BARRIER, 0, d)))
    for k, g in (('railU', RAIL_L), ('railS', RAIL_R), ('gpostU', GPOST_L), ('gpostS', GPOST_R)):
        els.append((k, 'steel', affinity.translate(g, 0, d)))
    for s, (c, h, m) in chan.items():
        for i, p in enumerate(sorted(polys(c), key=lambda p: p.centroid.x)): els.append((f'chan{s}{i}', m, p))
    for s_, cv in cavs.items(): els.append((f'cwater{s_}', 'water', cv))
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
FLOOD = {'O1'}   # zona dengan banjir kawasan di sisi selatan; MAB = dasar saluran selatan Skenario 1
mab = {}
for f in frames:
    if f['sk_t'] == 1: mab.setdefault((f['saluran'], f['bagian']), {})[f['pos']] = f['info']['S'].get('bottom')
first = min((f for f in frames if f['sk_t'] == 1 and f['O'] in FLOOD), key=lambda f: f['sta'])
MAB0 = first['info']['S']['bottom']       # MAB tunggal = dasar saluran selatan di hilir (STA terendah), Skenario 1
print('MAB banjir O1 =', MAB0, 'm di STA', first['sta'])
byO = collections.defaultdict(list)
for f in frames: byO[f['O']].append(f)
model = {'sumber': SRC.split('/')[-1], 'zona': {}}

def rect(x0, y0, x1, y1, cw=False):
    r = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return r[::-1] if cw else r
def flat(r): return [round(v, 3) for p in r for v in p]

def find_sites(O, segs):
    """lokasi saluran irigasi melintang: rentang segmen bertipe Siphon / Talang (kedua skenario).
    Titik pusat = 'STA titik acuan' siphon (xlsx) bila ada, selain itu tengah rentang."""
    runs = []
    for (sk, sal, bag), ps in segs.items():
        ty = {f['info'][s_].get('type', '') for f in ps.values() for s_ in 'US'}
        if any(t.startswith(('Siphon', 'Talang')) for t in ty):
            st = [f['sta'] for f in ps.values()]; runs.append([min(st), max(st)])
    runs.sort(); merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < 5.0: merged[-1][1] = max(merged[-1][1], r[1])
        else: merged.append(r)
    def info_at(sk, sta):
        best = None
        for (k, sal, bag), ps in segs.items():
            if k != sk: continue
            sts = [f['sta'] for f in ps.values()]
            if min(sts) - 0.01 <= sta <= max(sts) + 0.01:
                f = min(ps.values(), key=lambda f: abs(f['sta'] - sta)); best = f['info']
        return best
    sites = []
    for sa, sb in merged:
        run = sb - sa
        refs = [r_ for r_ in REF_IRIGASI if sa - 0.5 <= r_ <= sb + 0.5]
        sc = refs[0] if refs else (sa + sb) / 2
        gv = [i_[s_]['ground'] for sk in (1, 2) for i_ in [info_at(sk, sc)] if i_ for s_ in 'US' if i_[s_].get('ground') is not None]
        gavg = float(np.mean(gv))
        zb = gavg - D0
        d = max(0.5, gavg - zb); zb = gavg - d
        Wt = float(np.clip(0.7 * min(run, 20.0), 2.5, 8.0)); bw = Wt            # saluran irigasi berdinding tegak
        zc = ZC
        for sn, ss in SIMPANG:                       # gorong-gorong lewat di bawah mulut simpang (sampai di luar kerb + lereng)
            if abs(sc - ss) < SP_REACH:
                it = SP_FP.intersection(box(sc - ss - bw / 2 - 1.0, -XL - 1, sc - ss + bw / 2 + 1.0, XL + 1))
                if not it.is_empty: zc = max(zc, min(XL - 1.0, max(abs(it.bounds[1]), abs(it.bounds[3])) + 2.5))
        sites.append(dict(sta=round(sc, 2), a=round(sa, 2), b=round(sb, 2), zb=round(zb, 3), d=round(d, 3), bw=round(bw, 3), ground=round(gavg, 3), zc=round(zc, 2),
                          ref=bool(refs)))
    return sites

def cd_parts(sc, base, zz):
    """gorong-gorong kawasan (cross drain) box CD_CLEAR x CD_CLEAR di atas tanah dasar: badan, bukaan, kepala di tiap ujung dan sayap 30 derajat.
    Tinggi atas sayap mengikuti lereng timbunan dan berakhir persis di ujung (kaki) timbunan; area di antara sayap bebas tanah (digali di pekerjaan tanah)."""
    w = h = CD_CLEAR; t = CD_T; sl_ = []
    outer = rect(sc - w/2 - t, base, sc + w/2 + t, base + h + 2*t); inner = rect(sc - w/2, base + t, sc + w/2, base + t + h)
    zl = [{'m': 'cross', 'k': 'gorong', 'rings': [flat(outer), flat(inner[::-1])], 'z0': -zz['xhU'], 'z1': zz['xhS']},
          {'m': 'bore', 'k': 'gorongbore', 'rings': [flat(inner)], 'z0': -zz['xhU'] - 0.3, 'z1': zz['xhS'] + 0.3}]
    hwh = w / 2 + t + 0.5
    for sg, key in ((1, 'S'), (-1, 'U')):
        xh, Fh, Ff, xt, Gt = zz['xh' + key], zz['Fh' + key], zz['Ff' + key], zz['xt' + key], zz['Gt' + key]
        z0_, z1_ = (xh - 0.05, xh + 0.25) if sg > 0 else (-xh - 0.25, -xh + 0.05)
        zl.append({'m': 'culvert', 'k': 'kepala', 'rings': [flat(rect(sc - hwh, Gt - 0.3, sc + hwh, Fh)), flat(inner[::-1])], 'z0': z0_, 'z1': z1_})
        xf = xh + 0.25; Lx = max(xt - xf, 0.3); slope = (Gt - Ff) / Lx
        for sd in (1, -1):
            p0 = (sc + sd * hwh, sg * xf); p1 = (p0[0] + sd * Lx * math.tan(math.radians(30)), sg * xt)
            rb = ribbon(p0, p1, 0.25)
            if rb: sl_.append({'m': 'culvert', 'k': 'sayap', 'rings': [flat(ccw(rb))], 'y0': round(Ff, 3), 'gx': round(slope * sg, 4), 'z0': round(sg * xf, 3), 'hb': round(Ff - (Gt - 0.4), 3), 'ht': 0.0})
    return zl, sl_

def lerp_cols(sta_list, arrs, t):
    """interpolasi linear antar potongan (arrs: list of np arrays) pada STA t"""
    if t <= sta_list[0]: return arrs[0]
    for i in range(len(sta_list) - 1):
        if t <= sta_list[i+1]:
            u = (t - sta_list[i]) / (sta_list[i+1] - sta_list[i]) if sta_list[i+1] > sta_list[i] else 0
            return arrs[i] + (arrs[i+1] - arrs[i]) * u
    return arrs[-1]

def ribbon(p0, p1, wd):
    """persegi panjang berarah (sta, z) selebar wd sepanjang p0->p1"""
    dx, dz = p1[0] - p0[0], p1[1] - p0[1]; L = math.hypot(dx, dz)
    if L < 1e-6: return None
    nx, nz = -dz / L * wd / 2, dx / L * wd / 2
    return [(p0[0] + nx, p0[1] + nz), (p1[0] + nx, p1[1] + nz), (p1[0] - nx, p1[1] - nz), (p0[0] - nx, p0[1] - nz)]
def ccw(pts):
    a = sum(pts[i][0] * pts[(i+1) % len(pts)][1] - pts[(i+1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    return pts if a > 0 else pts[::-1]

DECK_TOP = [(0.0, 0.0), (0.4, 0.0), (8.27, -0.236), (10.27, -0.336), (10.54, -0.5)]
def deck_top(ax):    # tinggi permukaan perkerasan jalan utama relatif as jalan pada |offset| = ax
    return float(np.interp(ax, [p[0] for p in DECK_TOP], [p[1] for p in DECK_TOP]))

def ring8(o, i):
    """cincin U (bak terbuka di atas) dari 4 titik luar [BL,BR,TR,TL] dan 4 titik dalam: urutan titik tetap sehingga transisi antar bentuk selalu berbentuk U (tidak melebar / terpilin)"""
    r = [o[0], o[1], o[2], i[2], i[1], i[0], i[3], o[3]]
    a = sum(r[k][0] * r[(k + 1) % 8][1] - r[(k + 1) % 8][0] * r[k][1] for k in range(8))
    return r if a > 0 else r[::-1]
def u_params(conc):
    """4 titik luar & 4 titik dalam dari poligon beton saluran U / trapesium (hull cembung dan rongga); None bila bentuknya tidak sederhana"""
    try:
        hull = conc.convex_hull; gs = polys(hull.difference(conc))
        if not gs: return None
        cav = max(gs, key=lambda p: p.area)
        def four(p):
            c = list(p.simplify(0.002).exterior.coords)[:-1]
            if len(c) != 4: return None
            c.sort(key=lambda a: a[1]); bot = sorted(c[:2], key=lambda a: a[0]); top = sorted(c[2:], key=lambda a: a[0])
            return [bot[0], bot[1], top[1], top[0]]
        o, i = four(hull), four(cav)
        return (o, i) if o and i else None
    except Exception: return None

def sip_zones(st, c_):
    """zona siphon sepanjang STA: [tetangga ext] | transisi (trapesium -> kotak) | kotak terbuka | SIPHON (turun curam - datar - naik) | kotak terbuka | transisi | [ext].
    Transisi dimulai SIP_PRE m sebelum siphon; panjangnya 2-5 m menurut lebar saluran tetangga (trapesium lebar = transisi lebih panjang)."""
    a_, b_, sc = st['a'], st['b'], st['sta']; hw = st['bw'] / 2 + WALL; Lr = st['Lr']
    def lrule(h): return 2.0 if h is None else float(np.clip(2.5 * ((h.bounds[2] - h.bounds[0]) - 1.0), 2.0, 5.0))
    LA, LB = lrule(c_['nb']['A'][0]), lrule(c_['nb']['B'][0])
    if st['simp']: S0 = a_; S1 = b_                              # siphon panjang di bawah mulut simpang: seluruh rentang
    else: S0 = max(a_ + 0.1, sc - hw - Lr); S1 = min(b_ - 0.1, sc + hw + Lr)      # siphon pendek tepat di sekitar saluran irigasi
    T0 = S0 - SIP_PRE; T1 = T0 + min(LA, SIP_PRE)                 # transisi mulai SIP_PRE m sebelum siphon: ruas saluran trapesium di gambar dimundurkan
    T3 = S1 + SIP_PRE; T2 = T3 - min(LB, SIP_PRE)
    return dict(a=a_, b=b_, T0=T0, T1=T1, S0=S0, S1=S1, T2=T2, T3=T3, Lr=min(Lr, (S1 - S0) / 2), LA=LA, LB=LB)

for O in sorted(byO, key=lambda s: int(s[1:])):
    fr = byO[O]
    floor = math.floor(min(min(p[1] for p in f['ground']) for f in fr) - 2)
    z = {'floor': floor, 'skenario': {}}
    segs = collections.defaultdict(dict)
    for f in fr: segs[(f['sk_t'], f['saluran'], f['bagian'])][f['pos']] = f
    sites = find_sites(O, segs)
    if os.environ.get('DEBUG_SEGS'):
        for (k_, a_, b_), ps in sorted(segs.items(), key=lambda kv: min(f_['sta'] for f_ in kv[1].values())):
            sts_ = [f_['sta'] for f_ in ps.values()]
            print('SEG', O, 'S%d' % k_, a_, b_, round(min(sts_), 2), round(max(sts_), 2), sorted({f_['info'][s__].get('type', '') + '/' + str(f_['info'][s__].get('place', '')) for f_ in ps.values() for s__ in 'US'}))
    zsta = [f['sta'] for f in fr]; zlo, zhi = min(zsta), max(zsta)
    simps = [dict(name=n, sta=v) for n, v in SIMPANG if zlo <= v <= zhi and any(
        min(f_['sta'] for f_ in ps.values()) <= v <= max(f_['sta'] for f_ in ps.values()) for (k_, a_, b_), ps in segs.items() if k_ == 1)]
    # struktur penyeberang saluran irigasi diseragamkan (lurus, sejajar jalan): S1 = talang di atas, S2 = siphon di bawah saluran
    ovr_map = {}
    def seg_types(ps): return {f['info'][s_].get('type', '') for f in ps.values() for s_ in 'US'}
    for st in sites:                                   # talang hanya ada di Skenario 1 bila gambar memuat tipe Talang di rentang itu
        st['tal1'] = any(k_ == 1 and any(t.startswith('Talang') for t in seg_types(ps_)) and st['a'] - 0.5 <= min(f_['sta'] for f_ in ps_.values()) and max(f_['sta'] for f_ in ps_.values()) <= st['b'] + 0.5
                         for (k_, a_, b_), ps_ in segs.items())
    for st in sites:
        for (sk, sal, bag), ps in segs.items():
            sts = [f['sta'] for f in ps.values()]
            if not (st['a'] - 0.5 <= min(sts) and max(sts) <= st['b'] + 0.5): continue
            ty = seg_types(ps)
            if any(t.startswith('Box') for t in ty): continue
            if sk == 2: ovr_map[(sk, sal, bag)] = ('siphon', st)
            elif st['tal1'] and not any(t.startswith('Talang') for t in ty): ovr_map[(sk, sal, bag)] = ('talang', st)
    def neigh_bottom(sk, sta_t, s_):
        best = None
        for f in fr:
            if f['sk_t'] != sk: continue
            ty = f['info'][s_].get('type', '')
            if ty.startswith(('Siphon', 'Talang', 'Box')) or f['info'][s_].get('bottom') is None: continue
            dd = abs(f['sta'] - sta_t)
            if best is None or dd < best[0]: best = (dd, f['info'][s_]['bottom'])
        return best[1] if best else None
    NB = {}
    for st in sites:
        for sk_ in (1, 2):
            for key, tgt in (('A', st['a']), ('B', st['b'])):
                best = None
                for f in fr:
                    if f['sk_t'] != sk_ or any(f['info'][s_].get('type', '').startswith(('Siphon', 'Talang', 'Box')) for s_ in 'US'): continue
                    dd = abs(f['sta'] - tgt)
                    if best is None or dd < best[0]: best = (dd, f)
                NB[(st['sta'], sk_, key)] = best[1] if best and best[0] < 80 else None
    for st in sites:
        cands = [f for f in fr if st['a'] - 1 <= f['sta'] <= st['b'] + 1] or fr
        f0 = min(cands, key=lambda f: abs(f['sta'] - st['sta']))
        ea0 = build_frame(f0, floor)[1]
        st['cx'] = {s_: round(ea0['centers'].get(s_, (-17.0 if s_ == 'U' else 17.0)), 3) for s_ in 'US'}
        st['bt'] = {sk_: {s_: [neigh_bottom(sk_, st['a'], s_), neigh_bottom(sk_, st['b'], s_)] for s_ in 'US'} for sk_ in (1, 2)}
        st['cx2'] = {}                                   # pusat saluran Skenario 2 = pusat saluran tetangga (trapesium/U di gambar): siphon lurus sejajar jalan, tanpa belok
        for s_ in 'US':
            cs_ = []
            for key in 'AB':
                fnb = NB.get((st['sta'], 2, key))
                if fnb is not None:
                    h_ = build_frame(fnb, floor)[1]['hulls'].get(s_)
                    if h_ is not None: cs_.append((h_.bounds[0] + h_.bounds[2]) / 2)
            st['cx2'][s_] = round(float(np.mean(cs_)), 3) if cs_ else st['cx'][s_]
        run = st['b'] - st['a']
        st['dip'] = round(st['zb'] - 0.3 - WALL - 0.95, 3)
        st['simp'] = any(abs(st['sta'] - ss_) < SP_REACH for _, ss_ in SIMPANG)
        st['zcs'] = {}
        for sk_ in (1, 2):
            cands_ = [f for f in fr if f['sk_t'] == sk_] or fr
            f_ = min(cands_, key=lambda f: abs(f['sta'] - st['sta']))
            ea_ = build_frame(f_, floor)[1]; zz = {}
            for s_, sg in (('U', -1), ('S', 1)):
                # kepala gorong-gorong ditarik ke dalam (dekat jalan) agar talang / siphon berada di luar kepala, di atas saluran terbuka
                if sk_ == 1 and not st['tal1']: xh = abs(st['cx'][s_]) + 1.2          # tanpa talang: saluran drainase menerus di atas timbunan, kepala di luar saluran
                else: xh = max(ZC, abs((st['cx2'] if sk_ == 2 else st['cx'])[s_]) - 1.6)               # kepala tepat di dalam saluran drainase: sayap pendek, selesai di kaki timbunan
                for _, ss_ in SIMPANG:                              # di simpang: gorong-gorong lewat di bawah seluruh mulut simpang
                    if abs(st['sta'] - ss_) < SP_REACH:
                        it = SP_FP.intersection(box(st['sta'] - ss_ - st['bw'] / 2 - 1.0, -XL - 1, st['sta'] - ss_ + st['bw'] / 2 + 1.0, XL + 1))
                        if not it.is_empty: xh = max(xh, max(abs(it.bounds[1]), abs(it.bounds[3])) + 2.5)
                xh = round(min(xh, XL - 4.0), 2)
                xt = abs(ea_['toeR'] if sg > 0 else ea_['toeL'])           # ujung (kaki) timbunan menurut rencana
                zz[s_] = xh; zz['Fh' + s_] = round(float(ea_['F0'](sg * xh)), 3); zz['xt' + s_] = round(max(xt, xh + 0.5), 2)
                zz['Ff' + s_] = round(float(ea_['F0'](sg * (xh + 0.3))), 3); zz['Gt' + s_] = round(float(ea_['G'](sg * zz['xt' + s_])), 3)
            st['zcs'][str(sk_)] = zz
    SC = {}
    def sipctx(st_, s_):
        k_ = (st_['sta'], s_)
        if k_ not in SC:
            nbs = {}
            for key in 'AB':
                fnb = NB.get((st_['sta'], 2, key))
                if fnb is not None:
                    eb = build_frame(fnb, floor); dd_ = {n_: p_ for n_, m_, p_ in eb[0]}; nbs[key] = (eb[1]['hulls'].get(s_), dd_.get(f'chan{s_}0'), dd_.get(f'cwater{s_}'))
                else: nbs[key] = (None, None, None)
            ba, bb = st_['bt'][2][s_]
            if ba is None or bb is None:
                fn_ = min([f for f in fr if f['sk_t'] == 2] or fr, key=lambda f: abs(f['sta'] - st_['sta'])); ba = bb = fn_['info'][s_].get('bottom') or 53.0
            SC[k_] = dict(nb=nbs, cx=st_['cx2'][s_], ba=ba, bb=bb); SC[k_]['g'] = sip_zones(st_, SC[k_])
            if os.environ.get('DEBUG_SIP'): print('SIP', O, st_['sta'], s_, 'cx', st_['cx'][s_], 'A', None if nbs['A'][0] is None else round(sum(nbs['A'][0].bounds[0::2]) / 2, 2), 'B', None if nbs['B'][0] is None else round(sum(nbs['B'][0].bounds[0::2]) / 2, 2), 'widthA', None if nbs['A'][0] is None else round(nbs['A'][0].bounds[2] - nbs['A'][0].bounds[0], 2), 'widthB', None if nbs['B'][0] is None else round(nbs['B'][0].bounds[2] - nbs['B'][0].bounds[0], 2))
        return SC[k_]
    for st in sites:                                    # ramp siphon curam dekat saluran irigasi; lebar saluran irigasi menyesuaikan panjang rentang siphon
        a_, b_, sc = st['a'], st['b'], st['sta']; bts = st['bt'][2]
        drops = [max(bts[s_][0], bts[s_][1]) - st['dip'] for s_ in 'US' if bts[s_][0] is not None and bts[s_][1] is not None] or [1.2]
        drop = max(0.4, max(drops)); Lr = drop * SIP_K
        if not st['simp']:
            avail = min(sc - a_, b_ - sc) - 0.2; bw0 = st['bw']
            bw = float(np.clip(min(bw0, 2 * (avail - Lr) - 2 * WALL), 1.2, bw0)); space = avail - (bw / 2 + WALL)
            if space < Lr: Lr = max(0.3, space)
            st['bw'] = round(bw, 3)
        st['Lr'] = round(Lr, 3); st['drop'] = round(drop, 3)
    if os.environ.get('DEBUG_SIP'):
        for st in sites:
            for sk_ in (1, 2):
                r_ = []
                for key in 'AB':
                    fnb = NB.get((st['sta'], sk_, key))
                    if fnb is None: r_.append(None); continue
                    eb = build_frame(fnb, floor)[1]; r_.append({s_: (round(sum(eb['hulls'][s_].bounds[0::2]) / 2, 2) if s_ in eb['hulls'] else None) for s_ in 'US'})
                print('NBC', O, st['sta'], 'S%d' % sk_, 'cx', st['cx'], 'A', r_[0], 'B', r_[1])
    irig = {'sites': sites, 'simpang': [x['name'] + f" @ {x['sta']}" for x in simps], 'zel': []}
    z['irigasi'] = irig
    # --- gorong-gorong kawasan (cross drain): hanya Skenario 1; diturunkan sedikit dari elevasi acuan dan dijaga di bawah dasar saluran tepi jalan
    cds = []
    for num, sta_, el_ in CROSS:
        cand = [ps_ for (k_, a_, b_), ps_ in segs.items() if k_ == 1 and min(f_['sta'] for f_ in ps_.values()) <= sta_ <= max(f_['sta'] for f_ in ps_.values())]
        if not cand: continue
        f_ = min(cand[0].values(), key=lambda f: abs(f['sta'] - sta_)); inf_ = f_['info']
        chb = min([inf_[s_]['bottom'] for s_ in 'US' if inf_[s_].get('bottom') is not None] or [99.0])
        ea_ = build_frame(f_, floor)[1]; zz = {}; Gts = []
        for s_, sg in (('U', -1), ('S', 1)):
            xt = XL - 1.0
            for xx in np.arange(SP_E0, XL, 0.1):                       # ujung (kaki) timbunan
                if ea_['F0'](sg * xx) <= ea_['G'](sg * xx) + 0.2: xt = float(xx); break
            zz['xt' + s_] = round(xt, 2); zz['Gt' + s_] = round(float(ea_['G'](sg * xt)), 3); Gts.append(zz['Gt' + s_])
        base = max(Gts)                                                  # box di atas tanah dasar (tanpa galian): dasar = tanah tertinggi di kaki timbunan
        top = base + CD_CLEAR + 2 * CD_T
        if top > chb - 0.3: base -= top - (chb - 0.3); top = chb - 0.3   # dijaga di bawah dasar saluran tepi jalan
        for s_, sg in (('U', -1), ('S', 1)):
            xh = zz['xt' + s_] - 0.5
            for xx in np.arange(SP_E0, XL, 0.05):                        # kepala: titik lereng yang tingginya sedikit di atas atap box
                if ea_['F0'](sg * xx) <= top + 0.15: xh = float(xx); break
            zz['xh' + s_] = round(xh, 2); zz['Fh' + s_] = round(float(ea_['F0'](sg * xh)), 3); zz['Ff' + s_] = round(float(ea_['F0'](sg * (xh + 0.25))), 3)
        gv_ = [inf_[s__]['ground'] for s__ in 'US' if inf_[s__].get('ground') is not None]
        if os.environ.get('DEBUG_CD'): print('CD', num, round(sta_, 1), 'elev', round(el_, 2), 'base', round(base, 2), 'ground', [round(g_, 2) for g_ in gv_], 'chbot', round(chb, 2), zz)
        cds.append(dict(num=num, sta=round(sta_, 2), elev=round(el_, 3), inv=round(base, 3), top=round(top, 3), zz=zz, deck=f_['deck'], koreksi=False))
    z['crossdrain'] = [{k: v for k, v in c.items() if k != 'zz'} for c in cds]
    tags = []
    tg30 = math.tan(math.radians(30))
    for c in cds:
        zz = c['zz']; hwh = CD_CLEAR / 2 + CD_T + 0.5
        tags.append({'sk': 1, 'sta': c['sta'], 'z': 0, 'y': round(c['deck'] + 0.3, 2), 'kind': 'cd', 'text': f"CD-{c['num']} Gorong-gorong kawasan", 'r': 190})
        tags.append({'sk': 1, 'sta': c['sta'], 'z': round(zz['xhS'] + 0.1, 2), 'y': round(zz['FhS'], 2), 'kind': 'conc', 'text': 'Kepala gorong-gorong', 'r': 45})
        lx_ = max(zz['xtS'] - zz['xhS'] - 0.25, 0.3)
        tags.append({'sk': 1, 'sta': round(c['sta'] + hwh + 0.5 * lx_ * tg30, 2), 'z': round(zz['xhS'] + 0.25 + 0.5 * lx_, 2), 'y': round(zz['GtS'] + 0.5 * (zz['FfS'] - zz['GtS']), 2), 'kind': 'conc', 'text': 'Wing', 'r': 45})
    for st_ in sites:
        dk_ = next((f_['deck'] for f_ in fr if abs(f_['sta'] - st_['sta']) < 30), 55.0)
        tags.append({'sk': 0, 'sta': st_['sta'], 'z': 0, 'y': round(dk_ + 0.3, 2), 'kind': 'irig', 'text': 'Gorong-gorong irigasi', 'r': 190})
        for sk_ in (1, 2):
            zz = st_['zcs'][str(sk_)]; xr = st_['bw'] / 2 + 0.3
            tags.append({'sk': sk_, 'sta': st_['sta'], 'z': round(zz['S'], 2), 'y': round(zz['FhS'], 2), 'kind': 'conc', 'text': 'Kepala gorong-gorong', 'r': 50})
            lw_ = max(zz['xtS'] - zz['S'] - 0.3, 0.5)
            tags.append({'sk': sk_, 'sta': round(st_['sta'] + st_['bw'] / 2 + 0.1, 2), 'z': round(zz['S'] + 0.3 + 0.5 * lw_, 2), 'y': round(zz['FhS'] - 0.25 * lw_ - 0.0, 2), 'kind': 'conc', 'text': 'Wing', 'r': 50})
            tags.append({'sk': sk_, 'sta': st_['sta'], 'z': round(min(zz['xtS'] + 3.0, XL - 1.0), 2), 'y': round(st_['zb'] + 0.3, 2), 'kind': 'canal', 'text': 'Saluran irigasi', 'r': 70})
        if st_['tal1']: tags.append({'sk': 1, 'sta': st_['sta'], 'z': round(st_['cx']['S'], 2), 'y': round(st_['bt'][1]['S'][0] + 1.1 if st_['bt'][1]['S'][0] else st_['zb'] + 2.0, 2), 'kind': 'talang', 'text': 'Talang', 'r': 90})
        tags.append({'sk': 2, 'sta': st_['sta'], 'z': round(st_['cx2']['S'], 2), 'y': round(st_['dip'] + 0.5, 2), 'kind': 'siphon', 'text': 'Siphon', 'r': 90})
    for sp_ in simps:
        dk_ = next((f_['deck'] for f_ in fr if abs(f_['sta'] - sp_['sta']) < 30), 55.0)
        tags.append({'sk': 0, 'sta': sp_['sta'], 'z': 0, 'y': round(dk_ + 0.3, 2), 'kind': 'simpang', 'text': sp_['name'], 'r': 190})
    z['tags'] = tags
    done_sites = set()
    for (sk, sal, bag), ps in sorted(segs.items(), key=lambda kv: (kv[0][0], kv[1]['AWAL']['sta'])):
        secs = [ps[p] for p in POS]
        ovr_ = ovr_map.get((sk, sal, bag)); ovr = ovr_[1] if ovr_ else None; okind = ovr_[0] if ovr_ else None
        def ov_arg(f):
            if okind == 'siphon': return 'siphon'
            if okind == 'talang':
                st_ = ovr; spec = {}
                for s_ in 'US':
                    ba, bb = st_['bt'][1][s_]
                    if ba is None or bb is None: ba = bb = f['info'][s_].get('bottom') or 53.0
                    ib_ = float(np.interp(f['sta'], [st_['a'], st_['b']], [ba, bb]))
                    spec[s_] = (st_['cx'][s_], ib_)
                return spec
            return None
        bf = [build_frame(f, floor, override=ov_arg(f)) for f in secs]
        built = [{k: (mat, poly) for k, mat, poly in els} for els, _ in bf]
        stas = [s_['sta'] for s_ in secs]; sa_, sb_ = stas[0], stas[2]
        sp_here = [sp for sp in simps if sp['sta'] - SP_REACH < sb_ and sp['sta'] + SP_REACH > sa_]
        # saluran yang bergeser (belok/melipir) -> stasiun tambahan tiap 40 m agar takik timbunan mengikuti saluran
        def hb_of(ea, s_):
            h = ea['hulls'].get(s_); return None if h is None else h.bounds
        moving = False
        for s_ in 'US':
            bb = [hb_of(ea, s_) for _, ea in bf]
            if all(b_ is not None for b_ in bb):
                if max(abs(bb[i][j] - bb[0][j]) for i in range(1, 3) for j in (0, 1, 2)) > 0.03: moving = True
        T = list(stas); trench = []
        cds_here = [c for c in cds if sk == 1 and sa_ - 1e-6 <= c['sta'] < sb_ + 1e-6]
        for c in cds_here:                                  # area antar sayap: stasiun rapat (diagonal sayap 30 derajat tampak halus)
            R_ = CD_CLEAR / 2 + CD_T + 0.5 + max(c['zz']['xtU'] - c['zz']['xhU'], c['zz']['xtS'] - c['zz']['xhS']) * math.tan(math.radians(30)) + 0.3
            for t in np.arange(c['sta'] - R_, c['sta'] + R_ + 1e-6, 0.125):
                if sa_ + 0.01 < t < sb_ - 0.01: T.append(round(float(t), 3))
        for st in sites:
            ext = st['bw'] / 2 + 1.5
            if st['sta'] + ext > sa_ and st['sta'] - ext < sb_:
                trench.append((st, ext))
                zq_ = st['zcs'][str(sk)]; R_ = st['bw'] / 2 + WALL + 0.4 + max(zq_['xtU'] - zq_['U'], zq_['xtS'] - zq_['S']) * math.tan(math.radians(30)) + 0.3
                for t in np.arange(st['sta'] - R_, st['sta'] + R_ + 1e-6, 0.125):          # area antar sayap (diagonal 30 derajat) halus
                    if sa_ + 0.01 < t < sb_ - 0.01: T.append(round(float(t), 3))
                for t in (st['sta'] - st['bw'] / 2 - 0.002, st['sta'] - st['bw'] / 2 + 0.002, st['sta'], st['sta'] + st['bw'] / 2 - 0.002, st['sta'] + st['bw'] / 2 + 0.002):
                    if sa_ + 0.01 < t < sb_ - 0.01: T.append(round(float(t), 3))
        for sp in sp_here:
            for t in np.arange(sp['sta'] - SP_REACH, sp['sta'] + SP_REACH + 1e-6, 0.25):
                if sa_ + 0.01 < t < sb_ - 0.01: T.append(round(float(t), 3))
        if moving:
            for t in np.arange(sa_ + 40.0, sb_ - 20.0, 40.0): T.append(round(float(t), 3))
        zones_here = []                                   # situs siphon yang zonanya (transisi ... siphon ... transisi) menjangkau segmen ini; Skenario 2 saja
        if sk == 2:
            for st_ in sites:
                cs_ = {s_: sipctx(st_, s_) for s_ in 'US'}
                z0_ = min(cs_[s_]['g']['T0'] for s_ in 'US'); z1_ = max(cs_[s_]['g']['T3'] for s_ in 'US')
                if z1_ > sa_ + 0.01 and z0_ < sb_ - 0.01 and (okind == 'siphon' and ovr is st_ or not okind): zones_here.append((st_, cs_))
        tr_ctx = {}
        for st_, cs_ in zones_here:
            for s_ in 'US':
                g = cs_[s_]['g']
                for p_ in (g['T0'], g['T1'], g['S0'], g['S1'], g['T2'], g['T3']):
                    for dd in (-0.02, 0.02):
                        if sa_ + 0.01 < p_ + dd < sb_ - 0.01: T.append(round(float(p_ + dd), 3))
                for lo_, hi_ in ((g['T0'], g['T1']), (g['T2'], g['T3'])):
                    for t in np.arange(lo_, hi_, 0.0625):
                        if sa_ + 0.01 < t < sb_ - 0.01: T.append(round(float(t), 3))
        T = sorted(set(T))
        refined = len(T) > 3
        def hull_at(t, s_):
            """takik terbuka pada STA t: saluran tetangga -> transisi -> kotak terbuka; siphon tertanam tanpa takik. None bila di luar zona siphon."""
            for st_, cs_ in zones_here:
                c_ = cs_[s_]; g = c_['g']; cx = c_['cx']
                snap = lambda b_: (b_[0] + 0.03, b_[1], b_[2] - 0.03, b_[3])        # takik sedikit lebih sempit dari beton: tepi galian tersembunyi di dalam dinding beton
                bu = lambda e0: snap((cx - 0.4 - WALL, e0 - WALL, cx + 0.4 + WALL, e0 + 0.95))
                if t < g['T0'] or t > g['T3']:
                    continue
                if t < g['S0']:
                    hnb = c_['nb']['A'][0]; bn = hnb.bounds if hnb is not None else bu(c_['ba'])
                    if t < g['T1']:
                        u = (t - g['T0']) / max(g['T1'] - g['T0'], 1e-6); b0 = bu(c_['ba']); return box(*snap([bn[i] + (b0[i] - bn[i]) * u for i in range(4)]))
                    return box(*bu(c_['ba']))
                if t <= g['S1']: return 'siphon'
                hnb = c_['nb']['B'][0]; bn = hnb.bounds if hnb is not None else bu(c_['bb'])
                if t < g['T2']: return box(*bu(c_['bb']))
                u = (g['T3'] - t) / max(g['T3'] - g['T2'], 1e-6); b0 = bu(c_['bb']); return box(*snap([bn[i] + (b0[i] - bn[i]) * u for i in range(4)]))
            return None
        def hull_at_orig(t, s_):
            """hull saluran pada STA t: bergeser linear antar potongan (geser hull potongan terdekat)"""
            hs_ = [ea['hulls'].get(s_) for _, ea in bf]
            if all(h_ is None for h_ in hs_): return None
            if any(h_ is None for h_ in hs_):
                j = int(np.argmin([abs(t - v) for v in stas])); return hs_[j]
            bb = [h_.bounds for h_ in hs_]
            j = int(np.argmin([abs(t - v) for v in stas]))
            dx = float(np.interp(t, stas, [b_[0] for b_ in bb])) - bb[j][0]; dy = float(np.interp(t, stas, [b_[1] for b_ in bb])) - bb[j][1]
            return affinity.translate(hs_[j], dx, dy)
        def hull_all(t, s_):
            z_ = hull_at(t, s_)
            if isinstance(z_, str): return None               # siphon tertanam
            if z_ is not None: return z_
            if okind == 'siphon':                             # bagian rentang di luar zona siphon: saluran tetangga (trapesium) dilanjutkan
                for st_, cs_ in zones_here:
                    c_ = cs_[s_]; g = c_['g']; hnb = c_['nb']['A' if t < g['T0'] else 'B'][0]
                    if hnb is not None: return hnb
                return None
            return hull_at_orig(t, s_)
        def hb(h, x):
            ln = LineString([(x, -1e3), (x, 1e3)]).intersection(h)
            return None if ln.is_empty else ln.bounds[1]
        hullT = {t: {s_: hull_all(t, s_) for s_ in 'US'} for t in T}
        # grid x bersama
        grid = set()
        for _, ea in bf:
            xsb = ea['bp']; Fv = [ea['F'](x) for x in xsb]; Gv = [ea['G'](x) for x in xsb]
            grid |= set(xsb)
            for i in range(len(xsb) - 1):
                d0, d1 = Gv[i] - Fv[i], Gv[i+1] - Fv[i+1]
                if d0 * d1 < 0: grid.add(round(xsb[i] + (xsb[i+1]-xsb[i]) * d0 / (d0 - d1), 4))
        if moving or okind == 'siphon' or zones_here:          # kolom tepat di sisi takik (hull) tiap stasiun, agar dinding galian tegak dan bersih
            for t in T:
                for s_, h in hullT[t].items():
                    if h is None: continue
                    hx0, hy0, hx1, hy1 = h.bounds
                    grid |= {round(hx0, 4), round(hx0 + 1e-3, 4), round(hx1 - 1e-3, 4), round(hx1, 4)} | {round(p[0], 4) for p in h.exterior.coords}
        if sp_here:
            for k_ in range(0, 106):
                for sg in (1, -1): grid.add(round(sg * (SP_E0 + 0.25 * k_), 4))
        for c in cds_here:
            for key, sg in (('U', -1), ('S', 1)):
                xh_, xt_ = c['zz']['xh' + key], c['zz']['xt' + key]
                for v_ in np.arange(xh_ - 0.25, xt_ + 0.5, 0.125): grid.add(round(sg * float(v_), 4))
                grid |= {round(sg * xh_, 4), round(sg * xh_ - sg * 1e-3, 4)}
        for st_, _e in trench:
            zz_ = st_['zcs'][str(sk)]
            for key_, sg_ in (('U', -1), ('S', 1)):
                for v_ in np.arange(zz_[key_] - 0.25, zz_['xt' + key_] + 0.5, 0.125): grid.add(round(sg_ * float(v_), 4))
            for v_ in (zz_['S'], -zz_['U']): grid |= {round(v_, 4), round(v_ - 1e-3 * (1 if v_ > 0 else -1), 4)}
        grid = {v for v in grid if -XL <= v <= XL}
        grid = sorted(grid); ug = []
        for v in grid:
            if not ug or v - ug[-1] >= 1e-4: ug.append(v)
        xa = np.array(ug)
        F0k, Gk, toes = [], [], []
        for _, ea in bf:
            F0k.append(np.array([ea['F0'](x) for x in ug])); Gk.append(np.array([ea['G'](x) for x in ug])); toes.append((ea['toeL'], ea['toeR']))
        decks = [s_['deck'] for s_ in secs]
        FT, ST, PT, VT = [], [], [], []
        for t in T:
            Fv = np.array(lerp_cols(stas, F0k, t)); Gv_t = np.array(lerp_cols(stas, Gk, t))
            for s_, h in hullT[t].items():
                if h is None: continue
                hx0, hy0, hx1, hy1 = h.bounds
                for ci in np.where((xa > hx0 + 1e-6) & (xa < hx1 - 1e-6))[0]:
                    lo = hb(h, float(xa[ci]))
                    if lo is not None and lo < Fv[ci]: Fv[ci] = lo
            Sv = np.minimum(Gv_t, Fv)
            tl = float(np.interp(t, stas, [x[0] for x in toes])); tr_ = float(np.interp(t, stas, [x[1] for x in toes]))
            Vv = Fv.copy()
            dk = float(np.interp(t, stas, decks))
            for sp in sp_here:                      # jalan simpang: timbunan + perkerasan (bentuk dari PDF tipikal)
                import shapely
                tt = t - sp['sta']
                pts_ = shapely.points(np.full(len(xa), tt), xa)
                on = np.abs(xa) >= SP_E0 - 1e-9
                inside = on & shapely.contains_xy(SP_FP, np.full(len(xa), tt), xa)
                dist = np.where(inside, 0.0, shapely.distance(SP_FP, pts_))
                dd = np.maximum(np.abs(xa) - SP_E0, 0.0)
                Hs = (dk + deck_top(SP_E0)) - SP_G * dd
                Fsub = Hs - 0.4 - 0.5 * dist
                prot = np.zeros(len(xa), dtype=bool)               # takik saluran terbuka tidak boleh tertimbun lereng simpang
                for s_, h in hullT[t].items():
                    if h is None: continue
                    hx0, hy0, hx1, hy1 = h.bounds; prot |= (xa > hx0 - 0.3) & (xa < hx1 + 0.3)
                Fn = np.where(on & (inside | ~prot), np.maximum(Fv, Fsub), Fv)
                Vv = np.where(inside, np.maximum(Hs, Fn), np.where(on, np.maximum(Vv, Fn), Vv))
                Fv = Fn
            for st, ext in trench:          # gorong-gorong irigasi: lereng timbunan tetap utuh, saluran terbuka baru mulai di kepala gorong-gorong
                zz = st['zcs'][str(sk)]; zarr = np.where(xa >= 0, zz['S'], zz['U'])
                if st['simp']:
                    cover = st['zb'] + CH + WALL + 0.25 - 0.5 * max(0.0, abs(t - st['sta']) - (st['bw'] / 2 + WALL))
                    m2 = (np.abs(xa) >= SP_E0) & (np.abs(xa) < zarr)
                    Fv = np.where(m2, np.maximum(Fv, cover), Fv); Vv = np.where(m2, np.maximum(Vv, np.minimum(cover, Fv)), Vv)
            for st, ext in trench:          # area di antara sayap kepala gorong-gorong bebas tanah (muka tanah dasar), seperti gorong-gorong kawasan
                zz = st['zcs'][str(sk)]; hwh_ = st['bw'] / 2 + WALL + 0.4; tg_ = math.tan(math.radians(30)); ax_ = np.abs(xa)
                for key_, sg_ in (('U', -1), ('S', 1)):
                    mp_ = (np.sign(xa) == sg_) & (ax_ >= zz[key_] - 1e-9) & (np.abs(t - st['sta']) <= hwh_ + np.maximum(0.0, ax_ - (zz[key_] + 0.3)) * tg_ + 1e-9)
                    Fv = np.where(mp_, np.minimum(Fv, Gv_t), Fv); Vv = np.where(mp_, np.minimum(Vv, Fv), Vv)
            for st, ext in trench:          # alur saluran irigasi dipotong tegak, mulai dari kepala gorong-gorong ke luar
                zz = st['zcs'][str(sk)]; zarr = np.where(xa >= 0, zz['S'], zz['U'])
                hf = np.where(abs(t - st['sta']) <= st['bw'] / 2, st['zb'], 1e6)
                m = np.abs(xa) >= zarr - 1e-9
                Fv = np.where(m, np.minimum(Fv, hf), Fv); Sv = np.where(m, np.minimum(Sv, hf), Sv); Vv = np.where(m, np.minimum(Vv, hf), Vv)
            for c in cds_here:              # area di antara sayap bebas tanah: muka tanah = tanah dasar
                zz_ = c['zz']; hwh = CD_CLEAR / 2 + CD_T + 0.5; tg = math.tan(math.radians(30))
                for key, sg in (('U', -1), ('S', 1)):
                    xh_, xt_ = zz_['xh' + key], zz_['xt' + key]; ax = np.abs(xa)
                    m = (np.sign(xa) == sg) & (ax >= xh_ - 1e-9) & (np.abs(t - c['sta']) <= hwh + np.maximum(0.0, ax - (xh_ + 0.25)) * tg + 1e-9)
                    Fv = np.where(m, np.minimum(Fv, np.minimum(Gv_t, c['inv'])), Fv); Vv = np.where(m, np.minimum(Vv, Fv), Vv)
            Sv = np.minimum(Sv, Fv)
            outside_t = (xa <= tl + 1e-6) | (xa >= tr_ - 1e-6)
            Pv = Sv - TS * outside_t
            FT.append(np.round(Fv, 2).tolist()); ST.append(np.round(Sv, 2).tolist()); PT.append(np.round(Pv, 2).tolist()); VT.append(np.round(Vv, 2).tolist())
        def enc(rows):          # cm bulat, delta antar kolom (jauh lebih pendek di JSON)
            out_ = []
            for r_ in rows:
                iv = [int(round(v * 100)) for v in r_]
                out_.append([iv[0]] + [iv[i] - iv[i-1] for i in range(1, len(iv))])
            return out_
        earth_out = {'x': ug, 'F': enc(FT), 'S': enc(ST), 'toe': [[round(float(np.interp(t_, stas, [x_[0] for x_ in toes])), 2), round(float(np.interp(t_, stas, [x_[1] for x_ in toes])), 2)] for t_ in T], 'enc': 1}
        if sp_here: earth_out['V'] = enc(VT)
        if refined: earth_out['sta'] = T
        i3 = [T.index(v) for v in stas] if refined else [0, 1, 2]
        def surf(sta_, x_):
            j = int(np.clip(np.searchsorted(T, sta_) - 1, 0, len(T) - 2)) if len(T) > 1 else 0
            a_, b_ = T[j], T[min(j + 1, len(T) - 1)]
            u_ = 0 if b_ <= a_ else float(np.clip((sta_ - a_) / (b_ - a_), 0, 1))
            va = float(np.interp(x_, ug, VT[j])); vb = float(np.interp(x_, ug, VT[min(j + 1, len(T) - 1)]))
            return va + (vb - va) * u_
        keys = []
        for b in built:
            for k in b:
                if k not in keys: keys.append(k)
        elements = []
        # jendela bukaan (median / pagar pengaman terputus di mulut simpang)
        def rail_gap(sp):
            iv = []
            for xr in (SP_E0 + 1.35, -(SP_E0 + 1.35)):               # garis guardrail (offset ±11,75)
                it = SP_FP.intersection(LineString([(-70, xr), (70, xr)]).buffer(0.05))
                if not it.is_empty: iv.append((it.bounds[0], it.bounds[2]))
            if not iv: return None
            return [sp['sta'] + min(a_ for a_, b_ in iv) - 1.0, sp['sta'] + max(b_ for a_, b_ in iv) + 1.0]
        gaps_med = [[sp['sta'] + (-18.6), sp['sta'] + 17.8] for sp in sp_here]          # bukaan median: dari stop-bar zebra barat ke timur (PDF)
        gaps_rail = [g_ for g_ in (rail_gap(sp) for sp in sp_here) if g_]
        def pieces(a, b, gaps):
            out = [(a, b)]
            for g0, g1 in gaps:
                nxt = []
                for p0, p1 in out:
                    if g1 <= p0 or g0 >= p1: nxt.append((p0, p1)); continue
                    if g0 > p0: nxt.append((p0, g0))
                    if g1 < p1: nxt.append((g1, p1))
                out = nxt
            return [(p0, p1) for p0, p1 in out if p1 - p0 > 0.05]
        for k in keys:
            if sp_here and k in ('barrier', 'railU', 'railS') and k in built[0]:
                mat, poly0 = built[0][k]
                base = affinity.translate(poly0, 0, -secs[0]['deck'])
                for pi, (p0, p1) in enumerate(pieces(sa_, sb_, gaps_med if k == 'barrier' else gaps_rail)):
                    d0 = float(np.interp(p0, stas, decks)); d1 = float(np.interp(p1, stas, decks))
                    r0 = poly_rings(affinity.translate(base, 0, d0)); r1 = poly_rings(affinity.translate(base, 0, d1))
                    elements.append({'k': f'{k}_{pi}', 'm': mat, 'xs': [round(p0, 3), round(p1, 3)],
                                     'r': [[[round(v, 3) for pt in rg for v in pt] for rg in r0], [[round(v, 3) for pt in rg for v in pt] for rg in r1]]})
                continue
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
        # --- siphon lurus di bawah saluran irigasi: [transisi trapesium -> kotak] -> siphon (turun - datar - naik) -> [transisi kotak -> trapesium]
        def add_piece(k, m, p0, p1, ring_fn, bps=()):
            lo, hi = max(p0, sa_), min(p1, sb_)
            if hi - lo < 0.02: return
            xs_ = sorted({lo, hi} | {p for p in bps if lo < p < hi})
            elements.append({'k': k, 'm': m, 'xs': [round(v, 3) for v in xs_], 'r': [ring_fn(x_) for x_ in xs_]})
        def ring_interp(rs, x):
            j = int(np.clip(np.searchsorted(stas, x) - 1, 0, len(stas) - 2)); A, B = rs[j], rs[j + 1]
            if A is None and B is None: return None
            if A is None: return B
            if B is None: return A
            u = 0.0 if stas[j + 1] <= stas[j] else float(np.clip((x - stas[j]) / (stas[j + 1] - stas[j]), 0, 1))
            return [[round(a_ + (b_ - a_) * u, 3) for a_, b_ in zip(ra, rb)] for ra, rb in zip(A, B)]
        if okind != 'siphon' and zones_here:              # saluran tetangga (trapesium / U-ditch) dimundurkan: ruas yang dipakai transisi dan siphon dipangkas
            new_el = []
            for el in elements:
                k_ = el['k']; side = next((s_ for s_ in 'US' if k_.startswith('chan' + s_) or k_ == 'cwater' + s_), None)
                if side is None or 'xs' in el or 'r' not in el: new_el.append(el); continue
                keep = [(sa_, sb_)]
                for st_z, cs_z in zones_here:
                    g = cs_z[side]['g']; nk = []
                    for lo, hi in keep:
                        if g['T3'] <= lo or g['T0'] >= hi: nk.append((lo, hi)); continue
                        if g['T0'] > lo: nk.append((lo, g['T0']))
                        if g['T3'] < hi: nk.append((g['T3'], hi))
                    keep = nk
                if keep == [(sa_, sb_)]: new_el.append(el); continue
                for n_, (lo, hi) in enumerate(keep):
                    if hi - lo < 0.02: continue
                    xs_ = sorted({lo, hi} | {v for v in stas if lo < v < hi}); rr = [ring_interp(el['r'], x_) for x_ in xs_]
                    if any(r_ is None for r_ in rr): continue
                    new_el.append({'k': k_ + (f'_{n_}' if n_ else ''), 'm': el['m'], 'xs': [round(v, 3) for v in xs_], 'r': rr})
            elements[:] = new_el
        for st, cs_z in zones_here:
            if ('trans', st['sta']) not in done_sites:
                done_sites.add(('trans', st['sta'])); g0 = cs_z['S']['g']
                tags.append({'sk': 2, 'sta': round((g0['T0'] + g0['T1']) / 2, 2), 'z': round(cs_z['S']['cx'], 2), 'y': round(cs_z['S']['ba'] + 1.1, 2), 'kind': 'trans', 'text': 'Transisi', 'r': 70})
            for s_ in 'US':
                c_ = cs_z[s_]; g = c_['g']; cx, ba, bb = c_['cx'], c_['ba'], c_['bb']; bw_ = 0.8; h_ = 0.95
                prof_x = [g['S0'], g['S0'] + g['Lr'], g['S1'] - g['Lr'], g['S1']]; prof_y = [ba, st['dip'], st['dip'], bb]
                def sph(x_): return float(np.interp(x_, prof_x, prof_y))
                def ring_sip(x_):
                    e0 = sph(x_); return [flat(rect(cx - bw_/2 - WALL, e0 - WALL, cx + bw_/2 + WALL, e0 + h_ + WALL)), flat(rect(cx - bw_/2, e0, cx + bw_/2, e0 + h_, cw=True))]
                def ring_bore(x_):
                    e0 = sph(x_); return [flat(rect(cx - bw_/2, e0, cx + bw_/2, e0 + h_))]
                add_piece(f'siphon{s_}', 'culvert', g['S0'], g['S1'], ring_sip, prof_x)
                add_piece(f'siphonbore{s_}', 'bore', g['S0'], g['S1'], ring_bore, prof_x)
                u_a = poly_rings(talang_geom(cx, ba)[0])[0]; u_b = poly_rings(talang_geom(cx, bb)[0])[0]
                wA = box(cx - bw_/2, ba, cx + bw_/2, ba + WFR * h_); wB = box(cx - bw_/2, bb, cx + bw_/2, bb + WFR * h_)
                for key, (zo0, zo1), (zt0, zt1), (ze0, ze1), e0, ur, wcav in (('A', (g['T1'], g['S0']), (g['T0'], g['T1']), (g['a'], g['T0']), ba, u_a, wA), ('B', (g['S1'], g['T2']), (g['T2'], g['T3']), (g['T3'], g['b']), bb, u_b, wB)):
                    add_piece(f'open{key}{s_}', 'culvert', zo0, zo1, lambda x_, ur=ur: [flat(ur)])                # saluran kotak terbuka (talang) tertanam
                    add_piece(f'openw{key}{s_}', 'water', zo0, zo1, lambda x_, wcav=wcav: [flat(list(wcav.exterior.coords)[:-1])])
                    nb = c_['nb'][key]; npoly = nb[1]; pn = u_params(npoly) if npoly is not None else None
                    if pn is not None:                                                  # transisi parametrik: tetangga (trapesium / U) -> U kotak, selalu berbentuk U
                        ou = [(cx - bw_/2 - WALL, e0 - WALL), (cx + bw_/2 + WALL, e0 - WALL), (cx + bw_/2 + WALL, e0 + h_), (cx - bw_/2 - WALL, e0 + h_)]
                        iu = [(cx - bw_/2, e0), (cx + bw_/2, e0), (cx + bw_/2, e0 + h_), (cx - bw_/2, e0 + h_)]
                        R0, R1 = ring8(*pn), ring8(ou, iu)
                        def ring_tr(x_, key=key, p0=zt0, p1=zt1, R0=R0, R1=R1):
                            wn = 1 - (x_ - p0) / (p1 - p0) if key == 'A' else (x_ - p0) / (p1 - p0)               # bobot saluran tetangga
                            return [flat([(R0[i][0] * wn + R1[i][0] * (1 - wn), R0[i][1] * wn + R1[i][1] * (1 - wn)) for i in range(8)])]
                        r0 = ring8(*pn)
                        if ze1 - ze0 > 0.02: add_piece(f'ext{key}{s_}', 'channel', ze0, ze1, lambda x_, r0=r0: [flat(r0)])
                        if nb[2] is not None and ze1 - ze0 > 0.02: add_piece(f'extw{key}{s_}', 'water', ze0, ze1, lambda x_, rw=poly_rings(nb[2])[0]: [flat(rw)])
                    elif npoly is not None:
                        r0 = poly_rings(npoly)[0]; R0, R1 = align_rings([r0, ur])
                        def ring_tr(x_, key=key, p0=zt0, p1=zt1, R0=R0, R1=R1):
                            wn = 1 - (x_ - p0) / (p1 - p0) if key == 'A' else (x_ - p0) / (p1 - p0)
                            return [flat([(R0[i][0] * wn + R1[i][0] * (1 - wn), R0[i][1] * wn + R1[i][1] * (1 - wn)) for i in range(len(R0))])]
                        if ze1 - ze0 > 0.02: add_piece(f'ext{key}{s_}', 'channel', ze0, ze1, lambda x_, r0=r0: [flat(r0)])
                    else:
                        def ring_tr(x_, ur=ur): return [flat(ur)]
                    add_piece(f'trans{key}{s_}', 'culvert', zt0, zt1, ring_tr)
                    add_piece(f'transw{key}{s_}', 'water', zt0, zt1, lambda x_, wcav=wcav: [flat(list(wcav.exterior.coords)[:-1])])
        # --- pematang sawah (di luar kaki timbunan)
        zel = []
        toeabs = {'U': max(abs(t[0]) for t in toes), 'S': max(abs(t[1]) for t in toes)}
        xbs = {s_: [toeabs[s_] + 0.4 + 9.0 * i for i in range(6) if toeabs[s_] + 0.4 + 9.0 * i < XL - 0.8] for s_ in 'US'}
        if PEMATANG and not trench and not sp_here:
            for s_ in 'US':
                sign = -1 if s_ == 'U' else 1
                for n_, xb in enumerate(xbs[s_]):
                    rg = []
                    for kk in range(3):
                        sv = float(np.interp(sign * xb, ug, ST[i3[kk]]))
                        rg.append([flat(rect(sign * xb - 0.25, sv - 0.15, sign * xb + 0.25, sv + 0.3))])
                    elements.append({'k': f'pem{s_}{n_}', 'm': 'pematang', 'r': rg})
        for stn in range(int(math.ceil(sa_ / 25.0)), int(math.floor(sb_ / 25.0)) + 1):
            stv = stn * 25.0
            if not PEMATANG or not (sa_ <= stv < sb_) or any(abs(stv - st_['sta']) < ext_ + 1.5 for st_, ext_ in trench) or any(abs(stv - sp['sta']) < SP_REACH for sp in sp_here): continue
            ti = int(np.argmin([abs(stv - t) for t in T]))
            for s_ in 'US':
                sign = -1 if s_ == 'U' else 1
                xl = xbs[s_] + [XL - 0.8]
                for j in range(len(xl) - 1):
                    x0_, x1_ = xl[j], xl[j + 1]
                    sv = float(np.interp(sign * (x0_ + x1_) / 2, ug, ST[ti]))
                    zel.append({'m': 'pematang', 'k': 'pemx', 'rings': [flat(rect(stv - 0.2, sv - 0.6, stv + 0.2, sv + 0.3))],
                                'z0': round(min(sign * x0_, sign * x1_), 3), 'z1': round(max(sign * x0_, sign * x1_), 3)})
        # --- perlengkapan simpang (semua dari PDF tipikal): marka, pulau berkerb, catch drain, catch basin, bak kontrol, manhole, pipa
        sl = []
        def plane_at(sta_, x_):
            dk_ = float(np.interp(sta_, stas, decks)); ax = abs(x_); sg = 1.0 if x_ >= 0 else -1.0
            if ax <= SP_E0:
                return dk_ + deck_top(ax), sg * (deck_top(min(ax + 0.1, SP_E0)) - deck_top(max(ax - 0.1, 0.0))) / (min(ax + 0.1, SP_E0) - max(ax - 0.1, 0.0))
            return dk_ + deck_top(SP_E0) - SP_G * (ax - SP_E0), -SP_G * sg
        def orient_rings(pg):
            from shapely.geometry.polygon import orient
            pg = orient(pg, 1.0)
            return [flat(list(pg.exterior.coords)[:-1])] + [flat(list(h.coords)[:-1]) for h in pg.interiors]
        def add_slab(m, k, geom, hb, ht, split_bands=False, y_from_surface=False, dy=0.0):
            geom = geom.intersection(box(sa_, -XL - 1, sb_, XL + 1))
            bands = [(-1e3, -SP_E0), (-SP_E0, 0.0), (0.0, SP_E0), (SP_E0, 1e3)] if split_bands else [(-1e3, 1e3)]
            for x0_, x1_ in bands:
                part = geom.intersection(box(-1e7, x0_, 1e7, x1_)) if split_bands else geom
                for pg in polys(part):
                    if pg.area < 2e-4: continue
                    c = pg.centroid; yy, gx = plane_at(c.x, c.y)
                    if y_from_surface: yy = surf(c.x, c.y)
                    sl.append({'m': m, 'k': k, 'rings': orient_rings(pg), 'y0': round(yy + dy, 3), 'gx': round(gx, 4), 'z0': round(c.y, 3), 'hb': hb, 'ht': ht})
        for sp in sp_here:
            ss = sp['sta']
            def M(geom_uv):                          # (u,v) PDF -> (sta, offset) model
                g = _to_model(geom_uv); from shapely import affinity as af
                return af.translate(g, ss, 0)
            for ring_ in SIMP['marka']:
                try: pg = Polygon(ring_).buffer(0)
                except Exception: continue
                if pg.is_empty or pg.area < 1e-4: continue
                add_slab('marka', 'marka', M(pg), 0.04, 0.012, split_bands=True)
            for (p0, p1) in SIMP['stop']:
                add_slab('marka', 'stop', M(LineString([tuple(p0), tuple(p1)]).buffer(0.2, cap_style=2)), 0.04, 0.012, split_bands=True)
            for isl in SIMP['islands']:
                inner = Polygon(isl['inner']).buffer(0); outer = Polygon(isl['outer']).buffer(0)
                add_slab('island', 'pulau', M(inner), 0.35, 0.15)
                add_slab('cdrain', 'cd', M(outer.difference(inner)), 0.4, 0.015)
            for (u, v) in SIMP['cb']:
                add_slab('cb', 'cb', M(box(u - 0.3, v - 0.3, u + 0.3, v + 0.3)), 0.8, 0.03, y_from_surface=True)
            for b_ in SIMP['bk']:
                add_slab('bk', 'bk', M(box(b_[0] - 0.55, b_[1] - 0.55, b_[0] + 0.55, b_[1] + 0.55)), 1.2, 0.04, y_from_surface=True)
            for (u, v) in SIMP['mh']:
                add_slab('mh', 'mh', M(Point(u, v).buffer(0.45, 8)), 1.5, 0.04, y_from_surface=True)
            for chn in SIMP['pipa']:
                add_slab('pipa', 'pp', M(LineString([tuple(q) for q in chn]).buffer(0.15, cap_style=2, join_style=2)), 0.15, 0.15, y_from_surface=True, dy=-0.8)
        # --- gorong-gorong kawasan (Skenario 1): box 0,5 x 0,5 m menembus timbunan sampai kaki lereng, kepala + sayap 30 derajat, manhole besi cor
        if sk == 1:
            for c in cds:
                if not (sa_ - 1e-6 <= c['sta'] < sb_ + 1e-6): continue
                zl_, sl_ = cd_parts(c['sta'], c['inv'], c['zz'])
                zel += zl_; sl += sl_
                for xm in (-2.2, 2.2):
                    yy, gx = plane_at(c['sta'], xm)
                    sl.append({'m': 'castiron', 'k': 'manholecd', 'rings': orient_rings(Point(c['sta'], xm).buffer(0.32, 8)), 'y0': round(yy, 3), 'gx': round(gx, 4), 'z0': xm, 'hb': 0.5, 'ht': 0.03})
        # --- gorong-gorong irigasi di bawah timbunan: kepala gorong-gorong + sayap penahan timbunan; saluran terbuka berair di luar kaki timbunan
        for st in sites:
            if not (sa_ - 1e-6 <= st['sta'] < sb_ + 1e-6) or (sk, st['sta']) in done_sites: continue
            done_sites.add((sk, st['sta']))
            zz = st['zcs'][str(sk)]; zb, bw, d, sc = st['zb'], st['bw'], st['d'], st['sta']
            outer = rect(sc - bw/2 - WALL, zb - WALL, sc + bw/2 + WALL, zb + CH + WALL); inner = rect(sc - bw/2, zb, sc + bw/2, zb + CH)
            zel.append({'m': 'culvert', 'k': 'gorong', 'rings': [flat(outer), flat(inner[::-1])], 'z0': -zz['U'], 'z1': zz['S']})
            zel.append({'m': 'bore', 'k': 'gorongbore', 'rings': [flat(inner)], 'z0': -zz['U'] - 0.3, 'z1': zz['S'] + 0.3})
            wr = [(sc - bw/2, zb), (sc + bw/2, zb), (sc + bw/2, zb + 0.7 * d), (sc - bw/2, zb + 0.7 * d)]
            for sg, key in ((1, 'S'), (-1, 'U')):
                xh, Fh, xt = zz[key], zz['Fh' + key], zz['xt' + key]
                z0_, z1_ = (xh - 0.05, xh + 0.3) if sg > 0 else (-xh - 0.3, -xh + 0.05)
                hw_out = rect(sc - bw/2 - WALL - 0.4, zb - WALL - 0.3, sc + bw/2 + WALL + 0.4, Fh)
                zel.append({'m': 'culvert', 'k': 'kepala', 'rings': [flat(hw_out), flat(inner[::-1])], 'z0': z0_, 'z1': z1_})
                zel.append({'m': 'water', 'k': 'airirigasi', 'rings': [flat(wr)], 'z0': (xh + 0.3) if sg > 0 else -XL, 'z1': XL if sg > 0 else -(xh + 0.3)})
                Ff, Gt = zz['Ff' + key], zz['Gt' + key]; xf = xh + 0.3; Lx = max(xt - xf, 0.3); slope = (Gt - Ff) / Lx; hwh = bw / 2 + WALL + 0.4
                for sd in (1, -1):                                  # sayap 30 derajat: tinggi atas mengikuti lereng timbunan, berakhir persis di ujung timbunan
                    p0 = (sc + sd * hwh, sg * xf); p1 = (p0[0] + sd * Lx * math.tan(math.radians(30)), sg * xt)
                    rb = ribbon(p0, p1, 0.25)
                    if rb: sl.append({'m': 'culvert', 'k': 'sayap', 'rings': [flat(ccw(rb))], 'y0': round(Ff, 3), 'gx': round(slope * sg, 4), 'z0': round(sg * xf, 3), 'hb': round(Ff - (zb - 0.3), 3), 'ht': 0.0})

        water = None
        if O in FLOOD and all(hullT[t_]['S'] is not None for t_ in T):
            W = [MAB0] * 3
            tops = []
            for k_, t_ in enumerate(T):                       # MAB datar; air hanya di luar saluran selatan (di luar timbunan)
                hx1 = hullT[t_]['S'].bounds[2]
                tops.append([round(max(sv, MAB0), 3) if x >= hx1 - 1e-6 else sv for x, sv in zip(ug, ST[k_])])
            water = {'W': W, 'top': tops}
        infos = [s_['info'] for s_ in secs]
        if ovr:
            for inf in infos:
                for s_ in 'US':
                    inf[s_]['type'] = 'Siphon (standar)' if okind == 'siphon' else 'Talang (standar)'
                    inf[s_]['note'] = ['siphon di bawah saluran irigasi (lurus, sejajar jalan)' if okind == 'siphon' else 'talang di atas saluran irigasi (lurus, sejajar jalan)']
        ov_st = [st_ for st_ in sites if st_['a'] - 0.5 <= (sa_ + sb_) / 2 <= st_['b'] + 0.5]
        z['skenario'].setdefault(str(sk), []).append({
            'id': f'Saluran {sal} / Bagian {bag}', 'saluran': sal, 'bagian': bag,
            'sta': stas, 'deck': decks, 'irig': ov_st[0] if ov_st else None,
            'simpang': [sp['name'] for sp in sp_here] or None,
            'gaps': {'gpost': gaps_rail} if sp_here else None,
            'info': infos, 'earth': earth_out, 'water': water, 'zel': zel, 'sl': sl, 'els': elements,
            **({'revisi': okind} if ovr else {})})
    allsta = [s for sk in z['skenario'].values() for sg in sk for s in sg['sta']]
    z['sta'] = [min(allsta), max(allsta)]
    model['zona'][O] = z
with open(OUT, 'w') as fh: json.dump(model, fh, separators=(',', ':'))
print(OUT, os.path.getsize(OUT) // 1024, 'KB')
for O, z in model['zona'].items():
    print(O, z['sta'], 'irigasi', [(x['sta'], x['zb'], x['bw'], x['zc']) for x in z['irigasi']['sites']], 'simpang', z['irigasi']['simpang'])
