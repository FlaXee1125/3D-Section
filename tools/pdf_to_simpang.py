#!/usr/bin/env python3
"""Ekstrak tipikal simpang dari PDF -> data/simpang.json (meter, kerangka simpang).

Kerangka: u = searah jalan utama (timur = STA bertambah), v = tegak lurus (selatan positif). Gambar diputar ~7,2 derajat.
Skala 8,27 pt/m (bak kontrol 1,1 m = 9,1 pt; lebar ruas jalan simpang 5,05 m).
Diambil: lengkung sudut (kerb), pulau berkerb + catch drain, marka (semua bidang hitam), catch basin, bak kontrol, manhole, pipa.
"""
import sys, json, math, collections
import numpy as np, pymupdf
from scipy import ndimage as ndi
from shapely.geometry import LineString, Polygon, Point
from shapely.ops import unary_union, polygonize
SRC = sys.argv[1]; OUT = sys.argv[2]
TH = math.radians(7.2); S = 8.27; CX, CY = 585.0, 433.0
def T(x, y):
    dx, dy = x - CX, y - CY
    return ((dx * math.cos(TH) + dy * math.sin(TH)) / S, (-dx * math.sin(TH) + dy * math.cos(TH)) / S)
def bez(p0, p1, p2, p3, n=10):
    t = np.linspace(0, 1, n)[:, None]; a, b, c, d = map(np.array, (p0, p1, p2, p3))
    return [tuple(q) for q in (1-t)**3 * a + 3*(1-t)**2 * t * b + 3*(1-t) * t**2 * c + t**3 * d]
doc = pymupdf.open(SRC); page = doc[0]; dr = page.get_drawings()
def col(c): return tuple(round(v, 2) for v in c) if c else None
def path_pts(x):                     # urutan titik (pt) dengan pemisah sub-path
    subs, cur = [], []
    for it in x['items']:
        if it[0] == 'l': a, b = [(it[1].x, it[1].y), (it[2].x, it[2].y)]; seg = [a, b]
        elif it[0] == 'c': seg = bez((it[1].x, it[1].y), (it[2].x, it[2].y), (it[3].x, it[3].y), (it[4].x, it[4].y))
        elif it[0] == 're': r = it[1]; seg = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1), (r.x0, r.y0)]
        elif it[0] == 'qu': q = it[1]; seg = [(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y), (q.ul.x, q.ul.y)]
        else: continue
        if cur and math.dist(cur[-1], seg[0]) > 0.05: subs.append(cur); cur = []
        cur += seg
    if cur: subs.append(cur)
    return subs
def rnd(pts): return [[round(a, 3), round(b, 3)] for a, b in (T(*p) for p in pts)]

# ---- lengkung kerb sudut (hitam, panjang): barat laut dan barat daya (timur dicerminkan di pemakai)
arcs = {}
for i, x in enumerate(dr):
    if col(x['color']) != (0.0, 0.0, 0.0) or x['type'] != 's': continue
    for sp in path_pts(x):
        q = [T(*p) for p in sp]
        if len(q) < 8: continue
        us = [a for a, b in q]; vs = [b for a, b in q]
        L = sum(math.dist(q[k], q[k+1]) for k in range(len(q)-1))
        if 60 < L < 90 and -31 < min(us) < -29 and max(us) < -1 and (max(vs) < -4 or min(vs) > 6) and sum(1 for it in x['items'] if it[0] == 'c') == 0:
            key = 'NW' if max(vs) < 0 else 'SW'
            arcs[key] = [[round(a, 3), round(b, 3)] for a, b in q]

# ---- pulau (loop magenta = pinggir pulau, hijau = tepi catch drain)
def lines_of(color, typ='s'):
    out = []
    for x in dr:
        if col(x['color']) == color and x['type'] == typ:
            for sp in path_pts(x):
                if len(sp) >= 2: out.append(LineString([T(*p) for p in sp]))
    return out
mag = [f for f in polygonize(unary_union(lines_of((1.0, 0.0, 1.0)))) if f.area > 20]
gre = [f for f in polygonize(unary_union(lines_of((0.0, 0.72, 0.0)))) if f.area > 20]
islands = []
for m in mag:
    g = max(gre, key=lambda g: g.intersection(m).area) if gre else None
    islands.append({'inner': [[round(a, 3), round(b, 3)] for a, b in m.exterior.coords],
                    'outer': [[round(a, 3), round(b, 3)] for a, b in (g.exterior.coords if g else m.buffer(0.3).exterior.coords)]})

# ---- marka: semua bidang terisi hitam dalam jangkauan simpang
mark = []
for x in dr:
    if x['type'] != 'fs' or col(x.get('fill')) != (0.0, 0.0, 0.0): continue
    for sp in path_pts(x):
        q = [T(*p) for p in sp]
        if len(q) < 3: continue
        us = [a for a, b in q]; vs = [b for a, b in q]
        if min(us) < -37 or max(us) > 37 or abs(min(vs)) > 36 and abs(max(vs)) > 36: continue
        if max(us) - min(us) < 0.05 and max(vs) - min(vs) < 0.05: continue
        # garis lajur jalan utama (jauh dari simpang) tidak dipakai: model jalan utama berasal dari DXF
        if abs(min(us)) > 19.5 and abs(max(us)) > 19.5 and max(vs) - min(vs) < 10 and -9 < min(vs) and max(vs) < 11 and abs(min(us)) > 19.5 and abs(max(us)) > 19.5: continue
        mark.append([[round(a, 3), round(b, 3)] for a, b in q])
# bar STOP & garis pelengkap berupa goresan hitam pendek tebal (garis ganda)
for x in dr:
    if col(x['color']) != (0.0, 0.0, 0.0) or x['type'] != 's': continue
    for sp in path_pts(x):
        q = [T(*p) for p in sp]
        if len(q) != 2 and not (len(q) == 3 and q[0] == q[2]): continue
        L = math.dist(q[0], q[1])
        if 3.0 < L < 9.0 and abs(q[0][0]) < 8 and 12.5 < abs(q[0][1]) < 21.5 and abs(q[1][0]) < 8 and abs(abs(q[1][1]) - abs(q[0][1])) < 0.4:
            mark.append(('stop', [[round(a, 3), round(b, 3)] for a, b in q[:2]]))
# ---- simbol: catch basin (merah), manhole (biru), bak kontrol (magenta persegi) dari raster
Z = 4
pix = page.get_pixmap(dpi=72 * Z)
img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].astype(int)
R, G, B = img[:, :, 0], img[:, :, 1], img[:, :, 2]
def blobs(mask, amin):
    lab, n = ndi.label(mask, structure=np.ones((3, 3))); out = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        a = int((lab[sl] == i).sum())
        if a >= amin:
            cy, cx = ndi.center_of_mass(lab == i)
            out.append((cx / Z, cy / Z, (sl[1].stop - sl[1].start) / Z, (sl[0].stop - sl[0].start) / Z))
    return out
cb = blobs(ndi.binary_closing((R > 230) & (G < 40) & (B < 40), iterations=2), 150)
mh = blobs(ndi.binary_closing((R < 40) & (abs(G - 128) < 40) & (B > 230), iterations=1), 100)
bk = [b for b in blobs((R > 230) & (G < 40) & (B > 230), 60) if 6 < b[2] < 11.5 and 6 < b[3] < 11.5]
# ---- pipa: ruas kuning, disambung bila ujungnya berdekatan
segs = []
for x in dr:
    if col(x['color']) == (1.0, 1.0, 0.0):
        for sp in path_pts(x):
            for a, b in zip(sp[:-1], sp[1:]): segs.append((T(*a), T(*b)))
parent = list(range(len(segs)))
def find(i):
    while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
    return i
ends = [(k, e) for k, sg in enumerate(segs) for e in (0, 1)]
for i in range(len(ends)):
    for j in range(i + 1, len(ends)):
        if ends[i][0] != ends[j][0] and math.dist(segs[ends[i][0]][ends[i][1]], segs[ends[j][0]][ends[j][1]]) < 0.9:
            parent[find(ends[i][0])] = find(ends[j][0])
groups = collections.defaultdict(list)
for k in range(len(segs)): groups[find(k)].append(k)
pipes = []
for g in groups.values():
    if len(g) < 3: continue
    pts = [p for k in g for p in segs[k]]
    # urut: mulai dari titik paling ujung, tetangga terdekat
    uniq = list(dict.fromkeys((round(a, 2), round(b, 2)) for a, b in pts))
    cur = max(uniq, key=lambda p: math.hypot(p[0], p[1])); order = [cur]; rest = set(uniq) - {cur}
    while rest:
        nxt = min(rest, key=lambda p: math.dist(p, cur))
        if math.dist(nxt, cur) > 1.5: break
        order.append(nxt); rest.discard(nxt); cur = nxt
    if len(order) >= 3: pipes.append([[round(a, 2), round(b, 2)] for a, b in order])
def pr(b): return [round(v, 3) for v in T(b[0], b[1])]
side_u = [-2.09, 2.96]
out = {'frame': {'theta_deg': 7.2, 'skala_pt_per_m': S, 'uc': round(sum(side_u) / 2, 3), 'sisi': side_u, 'tepi_utama': [-4.9, 7.2]},
       'arcs': arcs, 'islands': islands, 'marka': [m for m in mark if not (isinstance(m, tuple))], 'stop': [m[1] for m in mark if isinstance(m, tuple)],
       'cb': [pr(b) for b in cb], 'mh': [pr(b) for b in mh], 'bk': [pr(b) + [round(b[2] / S, 2)] for b in bk], 'pipa': pipes}
json.dump(out, open(OUT, 'w'))
print({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in out.items()}, [len(p) for p in pipes])
