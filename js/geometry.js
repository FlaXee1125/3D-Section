// Membangun mesh tertutup (watertight) dari potongan melintang yang di-loft sepanjang STA.
import * as THREE from 'three';

const { ShapeUtils, Vector2 } = THREE;

function pt(x, lx, el) { return [x, el, lx]; }       // (X=STA, Y=elevasi, Z=offset)
function sub(a, b) { return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]; }
function cross(a, b) { return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]; }
function dot(a, b) { return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]; }

function tri(out, a, b, c, n) {
  if (dot(cross(sub(b, a), sub(c, a)), n) < 0) [b, c] = [c, b];
  out.push(...a, ...b, ...c);
}

function walls(ra, rb, xa, xb, out) {
  for (let i = 0; i < ra.length; i++) {
    const A = ra[i], B = rb[i]; const n = A.length / 2;
    for (let k = 0; k < n; k++) {
      const k2 = (k + 1) % n;
      const a0 = pt(xa, A[2*k], A[2*k+1]), a1 = pt(xa, A[2*k2], A[2*k2+1]);
      const b0 = pt(xb, B[2*k], B[2*k+1]), b1 = pt(xb, B[2*k2], B[2*k2+1]);
      const dl = A[2*k2] - A[2*k], de = A[2*k2+1] - A[2*k+1];
      const nrm = [0, -dl, de];                     // normal keluar (cincin luar CCW, lubang CW)
      if (Math.hypot(dl, de) < 1e-9) continue;
      tri(out, a0, a1, b1, nrm); tri(out, a0, b1, b0, nrm);
    }
  }
}

function cap(rings, x, dir, out) {
  const v = r => { const a = []; for (let k = 0; k < r.length; k += 2) a.push(new Vector2(r[k], r[k+1])); return a; };
  const contour = v(rings[0]), holes = rings.slice(1).map(v);
  let faces;
  try { faces = ShapeUtils.triangulateShape(contour, holes); } catch (e) { return; }
  const all = contour.concat(...holes);
  for (const [a, b, c] of faces) {
    const P = i => pt(x, all[i].x, all[i].y);
    tri(out, P(a), P(b), P(c), [dir, 0, 0]);
  }
}

export function loftChain(rings, X, out) {              // rings[k] = [outer, ...holes] di X[k]
  for (let k = 0; k + 1 < rings.length; k++) walls(rings[k], rings[k+1], X[k], X[k+1], out);
  cap(rings[0], X[0], -1, out);
  cap(rings[rings.length - 1], X[X.length - 1], +1, out);
}

export function prism(r, xa, xb, out) { loftChain([r, r], [xa, xb], out); }

// Pekerjaan tanah: solid "strip" antara kurva atas dan bawah pada grid offset x yang sama di tiap potongan.
function strip(x, tops, bots, X, out) {
  const n = x.length, T = 1e-4;
  const thick = (k, i) => tops[k][i] - bots[k][i];
  for (let k = 0; k + 1 < tops.length; k++) {
    for (let i = 0; i + 1 < n; i++) {
      if (Math.max(thick(k, i), thick(k, i+1), thick(k+1, i), thick(k+1, i+1)) < T) continue;
      const dl = x[i+1] - x[i];
      const A = (arr, kk, ii) => [X[kk], arr[kk][ii], x[ii]];
      const de = (tops[k][i+1] - tops[k][i] + tops[k+1][i+1] - tops[k+1][i]) / 2;
      const db = (bots[k][i+1] - bots[k][i] + bots[k+1][i+1] - bots[k+1][i]) / 2;
      let a = A(tops, k, i), b = A(tops, k, i+1), c = A(tops, k+1, i+1), d = A(tops, k+1, i);
      tri(out, a, b, c, [0, dl, -de]); tri(out, a, c, d, [0, dl, -de]);
      a = A(bots, k, i); b = A(bots, k, i+1); c = A(bots, k+1, i+1); d = A(bots, k+1, i);
      tri(out, a, b, c, [0, -dl, db]); tri(out, a, c, d, [0, -dl, db]);
    }
    for (const [i, dir] of [[0, -1], [n - 1, 1]]) {          // dinding ujung samping (offset = -40 / +40)
      if (Math.max(thick(k, i), thick(k+1, i)) < T) continue;
      const a = [X[k], bots[k][i], x[i]], b = [X[k], tops[k][i], x[i]];
      const c = [X[k+1], tops[k+1][i], x[i]], d = [X[k+1], bots[k+1][i], x[i]];
      tri(out, a, b, c, [0, 0, dir]); tri(out, a, c, d, [0, 0, dir]);
    }
  }
  for (const [k, dir] of [[0, -1], [tops.length - 1, 1]]) {   // tutup ujung (bidang potongan)
    for (let i = 0; i + 1 < n; i++) {
      if (Math.max(thick(k, i), thick(k, i+1)) < T) continue;
      const a = [X[k], bots[k][i], x[i]], b = [X[k], bots[k][i+1], x[i+1]];
      const c = [X[k], tops[k][i+1], x[i+1]], d = [X[k], tops[k][i], x[i]];
      tri(out, a, b, c, [dir, 0, 0]); tri(out, a, c, d, [dir, 0, 0]);
    }
  }
}

// Prisma yang diekstrusi sepanjang Z (offset): cincin dalam bidang (STA, elevasi) -> saluran irigasi melintang, pematang
export function prismZ(rings, z0, z1, sta0, out) {
  const pt3 = (r, k, z) => [r[2*k] - sta0, r[2*k+1], z];
  for (const r of rings) {
    const n = r.length / 2;
    for (let k = 0; k < n; k++) {
      const k2 = (k + 1) % n, dx = r[2*k2] - r[2*k], dy = r[2*k2+1] - r[2*k+1];
      if (Math.hypot(dx, dy) < 1e-9) continue;
      const nrm = [dy, -dx, 0];                        // keluar untuk cincin luar CCW (lubang CW)
      const a = pt3(r, k, z0), b = pt3(r, k2, z0), c = pt3(r, k2, z1), d = pt3(r, k, z1);
      tri(out, a, b, c, nrm); tri(out, a, c, d, nrm);
    }
  }
  const v = r => { const a = []; for (let k = 0; k < r.length; k += 2) a.push(new Vector2(r[k] - sta0, r[k+1])); return a; };
  const contour = v(rings[0]), holes = rings.slice(1).map(v);
  let faces; try { faces = ShapeUtils.triangulateShape(contour, holes); } catch (e) { return; }
  const all = contour.concat(...holes);
  for (const [a, b, c] of faces) for (const [z, dir] of [[z0, -1], [z1, 1]]) {
    const P = i => [all[i].x, all[i].y, z];
    tri(out, P(a), P(b), P(c), [0, 0, dir]);
  }
}

// Prisma tegak: cincin dalam bidang (STA, offset) diekstrusi dari elevasi y0 ke y1 (catch basin, bak kontrol, manhole, pipa)
export function prismY(ring, y0, y1, sta0, out) {
  const n = ring.length / 2, P = (k, y) => [ring[2*k] - sta0, y, ring[2*k+1]];
  let a2 = 0; for (let k = 0; k < n; k++) { const k2 = (k + 1) % n; a2 += ring[2*k] * ring[2*k2+1] - ring[2*k2] * ring[2*k+1]; }
  const sgn = a2 >= 0 ? 1 : -1;                       // cincin (X,Z) CCW -> normal samping keluar (dz, 0, -dx)
  for (let k = 0; k < n; k++) {
    const k2 = (k + 1) % n, dx = ring[2*k2] - ring[2*k], dz = ring[2*k2+1] - ring[2*k+1];
    if (Math.hypot(dx, dz) < 1e-9) continue;
    const nrm = [sgn * dz, 0, -sgn * dx];
    tri(out, P(k, y0), P(k2, y0), P(k2, y1), nrm); tri(out, P(k, y0), P(k2, y1), P(k, y1), nrm);
  }
  const contour = []; for (let k = 0; k < n; k++) contour.push(new Vector2(ring[2*k] - sta0, ring[2*k+1]));
  let faces; try { faces = ShapeUtils.triangulateShape(contour, []); } catch (e) { return; }
  for (const [a, b, c] of faces) for (const [y, dir] of [[y0, -1], [y1, 1]]) {
    const Q = i => [contour[i].x, y, contour[i].y];
    tri(out, Q(a), Q(b), Q(c), [0, dir, 0]);
  }
}

// Pelat (slab) berbidang miring: cincin (STA, offset) [luar CCW, lubang CW], permukaan y = y0 + gx*(z - z0); tebal dari y-hb s/d y+ht
export function slab(rings, y0, gx, z0, hb, ht, sta0, out) {
  const Y = z => y0 + gx * (z - z0);
  for (const r of rings) {
    const n = r.length / 2;
    for (let k = 0; k < n; k++) {
      const k2 = (k + 1) % n, x1 = r[2*k] - sta0, z1 = r[2*k+1], x2 = r[2*k2] - sta0, z2 = r[2*k2+1];
      const dx = x2 - x1, dz = z2 - z1; if (Math.hypot(dx, dz) < 1e-9) continue;
      const nrm = [dz, 0, -dx];
      tri(out, [x1, Y(z1) - hb, z1], [x2, Y(z2) - hb, z2], [x2, Y(z2) + ht, z2], nrm);
      tri(out, [x1, Y(z1) - hb, z1], [x2, Y(z2) + ht, z2], [x1, Y(z1) + ht, z1], nrm);
    }
  }
  const v = r => { const a = []; for (let k = 0; k < r.length; k += 2) a.push(new Vector2(r[k] - sta0, r[k+1])); return a; };
  const contour = v(rings[0]), holes = rings.slice(1).map(v);
  let faces; try { faces = ShapeUtils.triangulateShape(contour, holes); } catch (e) { return; }
  const all = contour.concat(...holes);
  for (const [a, b, c] of faces) for (const [d, dir] of [[ht, 1], [-hb, -1]]) {
    const Q = i => [all[i].x, Y(all[i].y) + d, all[i].y];
    tri(out, Q(a), Q(b), Q(c), [0, dir, 0]);
  }
}

// segs: daftar segmen satu skenario; kembalikan {mat: Float32Array posisi}
function decodeEarth(e, ts) {            // delta cm -> meter; P (lapisan sawah) dihitung dari S dan kaki timbunan
  if (e._d) return e; e._d = true;
  const dec = rows => rows.map(r => { const o = new Array(r.length); let a = 0; for (let i = 0; i < r.length; i++) { a += r[i]; o[i] = a / 100; } return o; });
  e.F = dec(e.F); e.S = dec(e.S); if (e.V) e.V = dec(e.V);
  e.P = e.S.map((row, k) => row.map((v, i) => { const x = e.x[i]; return (x <= e.toe[k][0] + 1e-6 || x >= e.toe[k][1] - 1e-6) ? v - 0.02 : v; }));
  return e;
}

export function buildGeometry(segs, sta0, floor, irig) {
  const buf = {};
  const get = m => buf[m] || (buf[m] = []);
  for (const seg of segs) {
    const X = seg.sta.map(v => v - sta0);
    const e = decodeEarth(seg.earth), XE = (e.sta || seg.sta).map(v => v - sta0);
    strip(e.x, e.P, e.S.map(r => r.map(() => floor)), XE, get('ground'));
    strip(e.x, e.S, e.P, XE, get('sawah'));            // lapisan sawah setebal 2 cm: permukaan rata dengan tanah, tanpa anak tangga di kaki timbunan
    if (e.V) strip(e.x, e.V, e.F, XE, get('pav'));
    strip(e.x, e.F, e.S, XE, get('fill'));
    if (seg.water) strip(e.x, seg.water.top, e.S, XE, get('water'));
    for (const z of seg.zel || []) prismZ(z.rings, z.z0, z.z1, sta0, get(z.m));
    for (const q of seg.sl || []) slab(q.rings, q.y0, q.gx, q.z0, q.hb, q.ht, sta0, get(q.m));
    for (const el of seg.els) {
      const out = get(el.m);
      const XS = el.xs ? el.xs.map(v => v - sta0) : X, N = el.r.length;
      if (el.k.startsWith('post') || el.k.startsWith('gpost')) {   // tiang tersendiri: patok RUMIJA tiap 20 m, tiang guardrail tiap 2 m (kelipatan STA)
        const gp = el.k.startsWith('gpost'), sp = gp ? 2 : 20, th = gp ? 0.1 : 0.15;
        const sa = Math.min(seg.sta[0], seg.sta[2]), sb = Math.max(seg.sta[0], seg.sta[2]);
        for (let st = Math.ceil(sa / sp) * sp; st <= sb; st += sp) {
          if (gp && (seg.gaps && seg.gaps.gpost || []).some(([a, b]) => st > a && st < b)) continue;
          const x = st - sta0, k = [0, 1, 2].reduce((b, q) => Math.abs(x - X[q]) < Math.abs(x - X[b]) ? q : b, 0);
          if (el.r[k]) prism(el.r[k], x - th, x + th, out);
        }
        continue;
      }
      let i = 0;
      while (i < N) {
        if (!el.r[i]) { i++; continue; }
        let j = i; while (j + 1 < N && el.r[j+1]) j++;
        if (j === i) {
          const a = i > 0 ? (XS[i-1] + XS[i]) / 2 : XS[i], b = i < N - 1 ? (XS[i] + XS[i+1]) / 2 : XS[i];
          if (b > a) prism(el.r[i], a, b, out);
        } else loftChain(el.r.slice(i, j + 1), XS.slice(i, j + 1), out);
        i = j + 1;
      }
    }
  }
  for (const z of (irig && irig.zel) || []) prismZ(z.rings, z.z0, z.z1, sta0, get(z.m));
  const res = {};
  for (const m in buf) res[m] = new Float32Array(buf[m]);
  return res;
}
