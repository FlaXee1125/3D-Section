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

// segs: daftar segmen satu skenario; kembalikan {mat: Float32Array posisi}
export function buildGeometry(segs, sta0, floor) {
  const buf = {};
  const get = m => buf[m] || (buf[m] = []);
  for (const seg of segs) {
    const X = seg.sta.map(v => v - sta0);
    const e = seg.earth;
    strip(e.x, e.S, e.S.map(r => r.map(() => floor)), X, get('ground'));
    strip(e.x, e.F, e.S, X, get('fill'));
    if (seg.water) strip(e.x, seg.water.top, e.S, X, get('water'));
    for (const el of seg.els) {
      const out = get(el.m);
      if (el.m === 'post') {                              // patok RUMIJA: satu tiang tiap 20 m (kelipatan 20 m STA)
        const sa = Math.min(seg.sta[0], seg.sta[2]), sb = Math.max(seg.sta[0], seg.sta[2]);
        for (let st = Math.ceil(sa / 20) * 20; st <= sb; st += 20) {
          const x = st - sta0, k = [0, 1, 2].reduce((b, q) => Math.abs(x - X[q]) < Math.abs(x - X[b]) ? q : b, 0);
          if (el.r[k]) prism(el.r[k], x - 0.15, x + 0.15, out);
        }
        continue;
      }
      let i = 0;
      while (i < 3) {
        if (!el.r[i]) { i++; continue; }
        let j = i; while (j + 1 < 3 && el.r[j+1]) j++;
        if (j === i) {
          const a = i > 0 ? (X[i-1] + X[i]) / 2 : X[i], b = i < 2 ? (X[i] + X[i+1]) / 2 : X[i];
          if (b > a) prism(el.r[i], a, b, out);
        } else loftChain(el.r.slice(i, j + 1), X.slice(i, j + 1), out);
        i = j + 1;
      }
    }
  }
  const res = {};
  for (const m in buf) res[m] = new Float32Array(buf[m]);
  return res;
}
