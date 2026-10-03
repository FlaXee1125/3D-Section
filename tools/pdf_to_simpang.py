#!/usr/bin/env python3
"""Ekstrak tata letak tipikal drainase simpang dari PDF -> data/simpang.json (meter, kerangka simpang).

Kerangka: u = searah jalan utama (STA bertambah ke timur), v = tegak lurus (selatan positif), gambar diputar ~7 derajat.
Skala 8,27 pt/m (bak kontrol 1,1 m = 9,1 pt). Catch basin / bak kontrol / manhole dibaca dari warna simbol.
"""
import sys, json, math, collections
import numpy as np, pymupdf
from scipy import ndimage as ndi
SRC = sys.argv[1]; OUT = sys.argv[2]
th = math.radians(7.0); S = 8.27; CX, CY = 585.0, 433.0
def T(x, y):
    dx, dy = x - CX, y - CY
    return ((dx * math.cos(th) + dy * math.sin(th)) / S, (-dx * math.sin(th) + dy * math.cos(th)) / S)
doc = pymupdf.open(SRC); page = doc[0]
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
# garis tengah pipa/catch drain = ruas kuning putus-putus
seg = []
for x in page.get_drawings():
    c = tuple(round(v, 2) for v in (x['color'] or ()))
    if c == (1.0, 1.0, 0.0):
        for it in x['items']:
            if it[0] == 'l': seg.append((T(it[1].x, it[1].y), T(it[2].x, it[2].y)))
pts = [p for s in seg for p in s]
# gabungkan titik -> rantai per pulau (kuadran) dengan tetangga terdekat
def quad(p): return (p[0] > 0.75, p[1] > 1.2)
chains = []
for q in [(False, False), (True, False), (False, True), (True, True)]:
    P = [p for p in pts if quad(p) == q and abs(p[1] - 1.2) > 9]
    if not P: continue
    P = list(dict.fromkeys((round(a, 2), round(b, 2)) for a, b in P))
    # mulai dari titik paling jauh dari pusat, rantai greedy
    cur = max(P, key=lambda p: math.hypot(p[0], p[1] - 1.2)); order = [cur]; rest = set(P) - {cur}
    while rest:
        nxt = min(rest, key=lambda p: math.dist(p, cur))
        if math.dist(nxt, cur) > 6: break
        order.append(nxt); rest.discard(nxt); cur = nxt
    chains.append(order)
def pr(b): return [round(v, 2) for v in T(b[0], b[1])]
out = {'skala_pt_per_m': S, 'cb': [pr(b) for b in cb], 'mh': [pr(b) for b in mh], 'bk': [pr(b) + [round(b[2] / S, 2)] for b in bk],
       'pipa': [[[round(a, 2), round(b, 2)] for a, b in c] for c in chains]}
json.dump(out, open(OUT, 'w'))
print({k: (len(v) if isinstance(v, list) else v) for k, v in out.items()}, [len(c) for c in chains])
