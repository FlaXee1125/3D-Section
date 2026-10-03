import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';
import { buildGeometry } from './geometry.js';

// ---------- konstanta tampilan
const MATS = {
  ground:  { c: 0x8a6c4a, n: 'Tanah dasar' },
  fill:    { c: 0xcfa86f, n: 'Timbunan / galian' },
  pav:     { c: 0x3b3f45, n: 'Perkerasan' },
  base:    { c: 0x7b8797, n: 'Beton ramping' },
  lfa:     { c: 0xd0c296, n: 'LFA' },
  barrier: { c: 0xc3c9d0, n: 'Median barrier' },
  steel:   { c: 0x9ec3d6, n: 'Guardrail (balok menerus + tiang tiap 2 m)' },
  channel: { c: 0x5fc2f0, n: 'Saluran (U-ditch / trapesium)' },
  culvert: { c: 0xf0883e, n: 'Siphon / box culvert / talang' },
  post:    { c: 0xe5484d, n: 'Patok RUMIJA (tiap 20 m)' },
  water:   { c: 0x2f7fd6, n: 'Air (banjir O1 / saluran irigasi)' },
  sawah:   { c: 0x74b04c, n: 'Sawah' },
  pematang:{ c: 0xc9ab70, n: 'Pematang sawah' },
  bore:    { c: 0x0b0f14, n: 'Rongga siphon / gorong-gorong' },
  marka:   { c: 0xf4f4f0, n: 'Marka jalan (zebra, stop, chevron, garis)' },
  island:  { c: 0xc3c8cd, n: 'Pulau berkerb' },
  cdrain:  { c: 0x2b3038, n: 'Catch drain (selokan pulau simpang)' },
  cb:      { c: 0xd9372f, n: 'Catch basin 60×60 cm' },
  bk:      { c: 0xb98bd9, n: 'Bak kontrol 110×110 cm' },
  mh:      { c: 0x2f78e6, n: 'Manhole' },
  pipa:    { c: 0xf2cf2e, n: 'Pipa drainase Ø300 (tanah)' },
};
const ORDER = Object.keys(MATS);
const $ = id => document.getElementById(id);
const fmtSTA = v => { const k = Math.floor(v / 1000); return `${k}+${(v - k * 1000).toFixed(2).padStart(6, '0')}`; };
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

// ---------- renderer
const canvas = $('gl'), stage = $('stage');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, stencil: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.localClippingEnabled = true;
renderer.setClearColor(0x0e1620);

const camL = new THREE.PerspectiveCamera(40, 1, 0.1, 6000);
const camR = new THREE.PerspectiveCamera(40, 1, 0.1, 6000);
let link = true, half = 0;
const setHalf = e => { const r = canvas.getBoundingClientRect(); half = (e.clientX - r.left) < r.width / 2 ? 0 : 1; applyEnable(); };
const applyEnable = () => { ctlL.enabled = link || half === 0; ctlR.enabled = !link && half === 1; };
['pointerdown', 'pointermove', 'wheel'].forEach(t => canvas.addEventListener(t, setHalf, { passive: true }));
const ctlL = new OrbitControls(camL, canvas), ctlR = new OrbitControls(camR, canvas);
for (const c of [ctlL, ctlR]) { c.enableDamping = true; c.dampingFactor = 0.08; c.maxPolarAngle = Math.PI * 0.98; }
applyEnable();

// ---------- state
const S = { zone: null, mode: 'sta', s: 0, win: 150, off: 0, lv: 0, ve: 1, flip: false, vis: {}, playing: false };
let MODEL, Z, views = [null, null], sta0 = 0, planes = [], lastDeck = 50;
ORDER.forEach(k => S.vis[k] = true);

// ---------- membangun scene satu skenario
function buildView(segs) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0e1620);
  scene.add(new THREE.HemisphereLight(0xdfeaff, 0x3a2f24, 1.05));
  const sun = new THREE.DirectionalLight(0xffffff, 1.5); sun.position.set(-40, 90, 60); scene.add(sun);
  const fill = new THREE.DirectionalLight(0x9ec8ff, 0.5); fill.position.set(50, 30, -60); scene.add(fill);
  const root = new THREE.Group(); scene.add(root);
  const geos = buildGeometry(segs, sta0, Z.floor, Z.irigasi);
  const v = { scene, root, segs, mats: {}, planes: [] };
  const cutQuad = new THREE.PlaneGeometry(6000, 6000);
  ORDER.forEach((m, mi) => {
    if (!geos[m] || !geos[m].length) return;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(geos[m], 3)); g.computeVertexNormals(); g.computeBoundingSphere();
    const col = new THREE.Color(MATS[m].c);
    const mat = new THREE.MeshStandardMaterial({ color: col, roughness: 0.88, metalness: 0.03, side: THREE.DoubleSide });
    if (m === 'water') { mat.transparent = true; mat.opacity = 0.5; mat.depthWrite = false; mat.roughness = 0.2; }
    const mesh = new THREE.Mesh(g, mat); mesh.renderOrder = m === 'water' ? 1100 : 1000; mesh.frustumCulled = false; root.add(mesh);
    const rec = { mesh, mat, slots: [] };
    for (let p = 0; p < 3; p++) {
      const mk = (side, op) => new THREE.MeshBasicMaterial({
        side, depthWrite: false, depthTest: false, colorWrite: false, stencilWrite: true,
        stencilFunc: THREE.AlwaysStencilFunc, stencilFail: op, stencilZFail: op, stencilZPass: op, clippingPlanes: [] });
      const back = new THREE.Mesh(g, mk(THREE.BackSide, THREE.IncrementWrapStencilOp));
      const front = new THREE.Mesh(g, mk(THREE.FrontSide, THREE.DecrementWrapStencilOp));
      back.frustumCulled = front.frustumCulled = false;
      const base = (p * 20 + mi) * 2;
      back.renderOrder = front.renderOrder = base;
      const capMat = new THREE.MeshStandardMaterial({
        color: col.clone().lerp(new THREE.Color(0xffffff), 0.18), roughness: 0.95, metalness: 0, side: THREE.DoubleSide,
        emissive: col, emissiveIntensity: 0.38,
        stencilWrite: true, stencilRef: 0, stencilFunc: THREE.NotEqualStencilFunc,
        stencilFail: THREE.ReplaceStencilOp, stencilZFail: THREE.ReplaceStencilOp, stencilZPass: THREE.ReplaceStencilOp,
        clippingPlanes: [] });
      const cap = new THREE.Mesh(cutQuad, capMat); cap.renderOrder = base + 1; cap.frustumCulled = false;
      cap.onAfterRender = r => r.clearStencil();
      root.add(back, front); scene.add(cap);
      rec.slots.push({ back, front, cap });
    }
    v.mats[m] = rec;
  });
  scene.fog = new THREE.Fog(0x0e1620, 100, 400); v.fog = scene.fog;
  // grid dasar
  return v;
}

// ---------- bidang potong
function computePlanes() {
  const x0 = S.s - sta0, fl = S.flip ? -1 : 1;
  const P = (nx, ny, nz, c) => new THREE.Plane(new THREE.Vector3(nx, ny, nz), c);
  if (S.mode === 'sta') return [P(fl, 0, 0, -fl * x0)];                  // simpan sisi STA lebih besar (atau lebih kecil bila dibalik)
  if (S.mode === 'long') return [P(0, 0, -fl, fl * S.off)];
  if (S.mode === 'level') return [P(0, -fl, 0, fl * S.lv * S.ve)];
  return [];
}
function applyPlanes() {
  planes = computePlanes();
  const p0 = new THREE.Vector3();
  for (const v of views) {
    if (!v) continue;
    v.root.scale.set(1, S.ve, 1);
    for (const m of ORDER) {
      const rec = v.mats[m]; if (!rec) continue;
      rec.mesh.visible = S.vis[m]; rec.mat.clippingPlanes = planes;
      rec.slots.forEach((sl, p) => {
        const on = S.vis[m] && p < planes.length;
        sl.back.visible = sl.front.visible = sl.cap.visible = on;
        if (!on) return;
        const pl = planes[p];
        sl.back.material.clippingPlanes = sl.front.material.clippingPlanes = [pl];
        sl.cap.material.clippingPlanes = planes.filter((_, q) => q !== p);
        pl.coplanarPoint(p0); sl.cap.position.copy(p0);
        sl.cap.lookAt(p0.x + pl.normal.x, p0.y + pl.normal.y, p0.z + pl.normal.z);
      });
    }
  }
}

// ---------- data pada STA tertentu
function segAt(segs, s) { return segs.find(g => s >= Math.min(g.sta[0], g.sta[2]) - 1e-6 && s <= Math.max(g.sta[0], g.sta[2]) + 1e-6); }
function sample(seg, s) {
  const [a, b, c] = seg.sta; let i = s <= b ? 0 : 1; const s0 = seg.sta[i], s1 = seg.sta[i+1];
  const t = s1 === s0 ? 0 : clamp((s - s0) / (s1 - s0), 0, 1), near = t < 0.5 ? i : i + 1;
  const lerp = (u, v) => (u == null || v == null) ? null : u + (v - u) * t;
  const side = k => {
    const A = seg.info[i][k], B = seg.info[i+1][k], N = seg.info[near][k];
    return { ...N, top: lerp(A.top, B.top), bottom: lerp(A.bottom, B.bottom), ground: lerp(A.ground, B.ground), offset: lerp(A.offset, B.offset), note: N.note };
  };
  return { U: side('U'), S: side('S'), deck: lerp(seg.deck[i], seg.deck[i+1]), water: seg.water ? lerp(seg.water.W[i], seg.water.W[i+1]) : null, near: ['AWAL', 'TENGAH', 'AKHIR'][near], seg };
}
const f3 = v => v == null ? '–' : v.toFixed(3);
function delta(a, b) {
  if (a == null || b == null) return '';
  const d = b - a, c = Math.abs(d) < 0.0005 ? 'eq' : d > 0 ? 'up' : 'dn';
  return ` <span class="delta ${c}">${Math.abs(d) < 0.0005 ? '±0' : (d > 0 ? '+' : '') + d.toFixed(3)}</span>`;
}
const cardOpen = { L: true, R: true };
const cx = id => `<button class="cx" data-c="${id}" title="Buka / tutup tabel (I)" aria-label="Buka atau tutup tabel">${cardOpen[id] ? '▾' : '▴'}</button>`;
function cardHTML(sm, ref, id) {
  if (!sm) return `<div class="ch"><h4>STA ${fmtSTA(S.s)}</h4>${cx(id)}</div><div class="cb"><div class="none">Tidak ada gambar teknis pada STA ini</div></div>`;
  const row = (lab, fn) => `<tr><th>${lab}</th><td>${fn('U')}</td><td>${fn('S')}</td></tr>`;
  const get = (x, k, f) => x ? x[k][f] : null;
  const typ = k => { const d = sm[k]; return d.type ? `${d.type}<br><span class="muted">${d.ctx || ''}</span>` : '–'; };
  const num = (f, k) => f3(sm[k][f]) + (ref ? delta(ref[k][f], sm[k][f]) : '');
  const notes = [...new Set(['U', 'S'].flatMap(k => sm[k].note || []))];
  return `<div class="ch"><h4>${sm.seg.id} · ${sm.near}</h4>${cx(id)}</div><div class="cb">
  <table><tr><th></th><th>UTARA</th><th>SELATAN</th></tr>
  ${row('Tipe', typ)}${row('Top (m)', k => num('top', k))}${row('Dasar (m)', k => num('bottom', k))}
  ${row('Tanah (m)', k => num('ground', k))}
  <tr><th>As jalan</th><td colspan="2">${f3(sm.deck)} m${ref ? delta(ref.deck, sm.deck) : ''}</td></tr>
  ${sm.seg.simpang ? `<tr><th>Simpang</th><td colspan="2" style="color:#f2cf2e">${sm.seg.simpang.join(', ')} (tipikal dari PDF)</td></tr>` : ''}
  ${sm.seg.irig ? `<tr><th>Irigasi</th><td colspan="2" style="color:#6db3ff">saluran melintang jalan: dasar ${f3(sm.seg.irig.zb)} m, lebar dasar ${sm.seg.irig.bw.toFixed(1)} m (asumsi)</td></tr>` : ''}
  ${sm.water != null ? `<tr><th>MAB banjir</th><td colspan="2" style="color:#6db3ff">${f3(sm.water)} m (selatan jalan)</td></tr>` : ''}</table>
  ${notes.length ? `<div class="muted note">${notes.join(' · ')}</div>` : ''}</div>`;
}
document.querySelectorAll('.card').forEach(el => el.addEventListener('click', e => {
  const b = e.target.closest('.cx'); if (!b) return;
  cardOpen[b.dataset.c] = !cardOpen[b.dataset.c]; updateCards();
}));
function toggleCards() { const on = !(cardOpen.L || cardOpen.R); cardOpen.L = cardOpen.R = on; updateCards(); }
function updateCards() {
  const a = views[0] && segAt(views[0].segs, S.s), b = views[1] && segAt(views[1].segs, S.s);
  const sa = a && sample(a, S.s), sb = b && sample(b, S.s);
  $('cardL').innerHTML = cardHTML(sa, null, 'L');
  $('cardR').innerHTML = cardHTML(sb, sa && sb ? sa : null, 'R');
  $('cardL').classList.toggle('closed', !cardOpen.L); $('cardR').classList.toggle('closed', !cardOpen.R);
  const lab = sa || sb;
  $('segLabel').textContent = lab ? `· ${lab.seg.id}` : '· (tidak ada gambar teknis)';
  if (lab) lastDeck = lab.deck;
}

// ---------- kamera
const yc0 = () => ((lastDeck + 1) / 2 + Z.floor / 2) * S.ve;
function preset(name, keepDist) {
  const x0 = S.s - sta0, y = lastDeck * S.ve, fl = S.flip ? -1 : 1;
  const span = Math.min(S.win, 60);
  const t = new THREE.Vector3(x0 + fl * (S.mode === 'sta' && name !== 'sect' ? span * 0.2 : 0), name === 'sect' ? yc0() : y - 3 * S.ve, S.mode === 'long' ? S.off : 0);
  const d = 60, yc = ((lastDeck + 1) / 2 + Z.floor / 2) * S.ve;
  const pos = {
    sect: [x0 - fl * 95, yc, 0.001],
    iso:  [x0 - fl * d * 0.85, y + 20 * S.ve, 40],
    side: [x0 + fl * span * 0.25, y, d * 1.3],
    top:  [x0 + fl * span * 0.25, y + d * 1.6, 0.01],
  }[name];
  camL.fov = camR.fov = name === 'sect' ? 24 : 40;
  for (const [cam, ctl] of [[camL, ctlL], [camR, ctlR]]) { ctl.target.copy(t); cam.position.set(...pos); ctl.update(); }
}

// ---------- UI
function buildUI() {
  const zs = $('zones'); zs.innerHTML = '';
  Object.keys(MODEL.zona).forEach(k => {
    const b = document.createElement('button'); b.textContent = k; b.dataset.z = k;
    const z = MODEL.zona[k]; b.title = `STA ${fmtSTA(z.sta[0])} – ${fmtSTA(z.sta[1])}`;
    b.onclick = () => loadZone(k); zs.appendChild(b);
  });
  buildLegend();
}
// kelompok bagian (satu tombol = beberapa material)
const GROUPS = [
  { n: 'Badan Jalan', mats: ['pav', 'base', 'lfa', 'barrier', 'steel'] },
  { n: 'Timbunan & Tanah', mats: ['fill', 'ground'] },
  { n: 'Saluran Drainase', mats: ['channel', 'culvert', 'bore'] },
  { n: 'Air', mats: ['water'] },
  { n: 'Ruang Bebas Jalan (RUMIJA)', mats: ['post'] },
  { n: 'Sawah', mats: ['sawah', 'pematang'] },
  { n: 'Simpang', mats: ['marka', 'island', 'cdrain', 'cb', 'bk', 'mh', 'pipa'] },
];
const hex = c => '#' + c.toString(16).padStart(6, '0');
function buildLegend() {
  const lg = $('legend'); lg.innerHTML = '';
  const row = document.createElement('div'); row.className = 'chips'; lg.appendChild(row);
  GROUPS.forEach((g, gi) => {
    const b = document.createElement('button'); b.className = 'chip'; b.dataset.g = gi;
    b.title = g.mats.map(m => MATS[m].n).join(' · ');
    b.innerHTML = `<span class="sw">${g.mats.slice(0, 3).map(m => `<i style="background:${hex(MATS[m].c)}"></i>`).join('')}</span>${g.n}`;
    b.onclick = () => { const on = !g.mats.some(m => S.vis[m]); g.mats.forEach(m => S.vis[m] = on); syncLegend(); applyPlanes(); };
    row.appendChild(b);
  });
  const d = document.createElement('button'); d.className = 'chip more'; d.textContent = 'Rincian ▸'; row.appendChild(d);
  const det = document.createElement('div'); det.className = 'detail'; det.hidden = true; lg.appendChild(det);
  ORDER.forEach(m => {
    const l = document.createElement('label');
    l.innerHTML = `<input type="checkbox" data-m="${m}"><i style="background:${hex(MATS[m].c)}"></i>${MATS[m].n}`;
    l.querySelector('input').onchange = e => { S.vis[m] = e.target.checked; syncLegend(); applyPlanes(); };
    det.appendChild(l);
  });
  d.onclick = () => { det.hidden = !det.hidden; d.textContent = det.hidden ? 'Rincian ▸' : 'Rincian ▾'; requestAnimationFrame(() => document.documentElement.style.setProperty('--panel-h', $('panel').offsetHeight + 'px')); };
  syncLegend();
}
function syncLegend() {
  document.querySelectorAll('.chip[data-g]').forEach(b => {
    const g = GROUPS[+b.dataset.g], n = g.mats.filter(m => S.vis[m]).length;
    b.classList.toggle('on', n === g.mats.length); b.classList.toggle('part', n > 0 && n < g.mats.length);
  });
  document.querySelectorAll('.detail input').forEach(i => { i.checked = !!S.vis[i.dataset.m]; });
}
function toast(t) { const e = $('toast'); e.textContent = t; e.classList.add('show'); clearTimeout(toast.h); toast.h = setTimeout(() => e.classList.remove('show'), 2200); }

function drawTimeline() {
  const [lo, hi] = Z.sta, span = hi - lo;
  const cover = $('cover'); cover.innerHTML = '';
  const segs = Z.skenario['1'];
  segs.forEach((g, i) => {
    const e = document.createElement('i'); if (i % 2) e.className = 'alt';
    e.style.left = ((g.sta[0] - lo) / span * 100) + '%'; e.style.width = Math.max(0.25, (g.sta[2] - g.sta[0]) / span * 100) + '%';
    cover.appendChild(e);
  });
  const ticks = $('ticks'); ticks.innerHTML = ''; let last = -99;
  const marks = [...new Set(segs.flatMap(g => [g.sta[0], g.sta[2]]))].sort((a, b) => a - b);
  marks.forEach(v => { const p = (v - lo) / span * 100; if (p - last < 7) return; last = p;
    const e = document.createElement('span'); e.style.left = p + '%'; e.textContent = fmtSTA(v).replace(/\.\d+$/, ''); ticks.appendChild(e); });
  const r = $('sta'); r.min = lo; r.max = hi; r.step = 0.01;
}

function loadZone(k) {
  S.zone = k; Z = MODEL.zona[k]; sta0 = Z.sta[0];
  document.querySelectorAll('#zones button').forEach(b => b.classList.toggle('on', b.dataset.z === k));
  for (const v of views) if (v) { v.scene.traverse(o => { if (o.geometry && o.geometry.dispose) o.geometry.dispose(); }); }
  views = [buildView(Z.skenario['1'] || []), buildView(Z.skenario['2'] || [])];
  drawTimeline();
  const first = Z.skenario['1'][0]; S.s = first.sta[1];
  const lv = $('lv'); lv.min = Z.floor; lv.max = Z.floor + 22; S.lv = first.deck[1] - 0.2; lv.value = S.lv;
  $('sta').value = S.s; lastDeck = first.deck[1];
  syncOutputs(); applyPlanes(); updateCards(); preset('iso');
  history.replaceState(null, '', '#' + k);
}
function syncOutputs() {
  $('staLabel').textContent = fmtSTA(S.s);
  $('winOut').textContent = S.win >= +$('win').max ? 'Semua' : S.win + ' m';
  $('offOut').textContent = S.off.toFixed(1) + ' m'; $('lvOut').textContent = S.lv.toFixed(2) + ' m'; $('veOut').textContent = S.ve + '×';
}
function setSTA(v, followCam = true) {
  v = clamp(v, Z.sta[0], Z.sta[1]);
  const dx = v - S.s; S.s = v;
  if (followCam) for (const [cam, ctl] of [[camL, ctlL], [camR, ctlR]]) { cam.position.x += dx; ctl.target.x += dx; }
  $('sta').value = v; syncOutputs(); applyPlanes(); updateCards();
}
const stations = () => [...new Set(Z.skenario['1'].flatMap(g => g.sta))].sort((a, b) => a - b);
function step(dir) { const st = stations(); const n = dir > 0 ? st.find(v => v > S.s + 0.05) : [...st].reverse().find(v => v < S.s - 0.05); if (n != null) setSTA(n); }

$('sta').oninput = e => { setSTA(+e.target.value); };
$('win').oninput = e => { S.win = +e.target.value; syncOutputs(); applyPlanes(); };
$('off').oninput = e => { S.off = +e.target.value; syncOutputs(); applyPlanes(); };
$('lv').oninput = e => { S.lv = +e.target.value; syncOutputs(); applyPlanes(); };
$('ve').oninput = e => { const o = S.ve; S.ve = +e.target.value;
  for (const [cam, ctl] of [[camL, ctlL], [camR, ctlR]]) { const r = S.ve / o; ctl.target.y *= r; cam.position.y *= r; }
  syncOutputs(); applyPlanes(); };
$('flip').onchange = e => { S.flip = e.target.checked; applyPlanes(); preset('sect'); };
$('cutMode').onchange = e => { S.mode = e.target.value;
  $('offWrap').hidden = S.mode !== 'long'; $('lvWrap').hidden = S.mode !== 'level'; applyPlanes();
  preset(S.mode === 'long' ? 'side' : S.mode === 'level' ? 'top' : 'iso'); };
$('btnLink').onclick = e => { link = !link; e.target.classList.toggle('on', link); applyEnable();
  if (link) { camR.position.copy(camL.position); ctlR.target.copy(ctlL.target); } toast(link ? 'Kamera disinkronkan' : 'Kamera terpisah: geser tiap jendela sendiri'); };
let xray = false;
$('btnXray').onclick = e => {
  xray = !xray; e.target.classList.toggle('on', xray);
  const hide = ['ground', 'fill', 'sawah', 'pematang', 'pav'];
  hide.forEach(m => S.vis[m] = !xray); syncLegend();
  applyPlanes();
};
const panel = $('panel'), pbtn = $('btnPanel');
const setPanel = on => {
  document.body.classList.toggle('nopanel', !on); pbtn.textContent = on ? '▾' : '▴'; pbtn.setAttribute('aria-expanded', on);
  try { localStorage.setItem('panel', on ? '1' : '0'); } catch (e) {}
  requestAnimationFrame(() => document.documentElement.style.setProperty('--panel-h', (on ? panel.offsetHeight : 0) + 'px'));
};
pbtn.onclick = () => setPanel(document.body.classList.contains('nopanel'));
try { new ResizeObserver(() => { if (!document.body.classList.contains('nopanel')) document.documentElement.style.setProperty('--panel-h', panel.offsetHeight + 'px'); }).observe(panel); } catch (e) {}
try { setPanel(localStorage.getItem('panel') !== '0'); } catch (e) { setPanel(true); }
const goFull = () => { try { document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen().catch(() => toast('Layar penuh ditolak browser. Buka link di tab sendiri lalu tekan F11.')); } catch (e) { toast('Layar penuh tidak didukung. Tekan F11.'); } };
$('btnFull').onclick = goFull;
document.addEventListener('fullscreenchange', () => { $('btnFull').textContent = document.fullscreenElement ? '⛶ Keluar layar penuh' : '⛶ Layar penuh'; });
document.querySelectorAll('.views button').forEach(b => b.onclick = () => preset(b.dataset.v));
$('prev').onclick = () => step(-1); $('next').onclick = () => step(1);
$('play').onclick = () => { S.playing = !S.playing; $('play').textContent = S.playing ? '❚❚' : '▶'; };
addEventListener('keydown', e => {
  if (/INPUT|SELECT/.test(document.activeElement.tagName) && document.activeElement.type !== 'range') return;
  if (e.key === 'ArrowRight') setSTA(S.s + (e.shiftKey ? 10 : 1)); else if (e.key === 'ArrowLeft') setSTA(S.s - (e.shiftKey ? 10 : 1));
  else if (e.key === 'f' || e.key === 'F') goFull();
  else if (e.key === 'h' || e.key === 'H') pbtn.click();
  else if (e.key === 'i' || e.key === 'I') toggleCards();
  else if (e.key === ' ') { e.preventDefault(); $('play').click(); }
});

// ---------- label STA yang mengikuti bidang potong
const labelEls = [document.createElement('div'), document.createElement('div')];
labelEls.forEach(e => { e.className = 'lb'; $('labels').appendChild(e); });
const tmp = new THREE.Vector3();
function updateLabels(w, h) {
  [camL, camR].forEach((cam, i) => {
    tmp.set(S.s - sta0, (lastDeck + 2.2) * S.ve, S.mode === 'long' ? S.off : 0).project(cam);
    const e = labelEls[i], vis = S.mode !== 'none' && tmp.z < 1 && Math.abs(tmp.x) < 1.05;
    e.style.display = vis ? '' : 'none';
    e.textContent = 'STA ' + fmtSTA(S.s);
    e.style.left = ((tmp.x * 0.5 + 0.5) * (w / 2) + i * w / 2) + 'px'; e.style.top = ((-tmp.y * 0.5 + 0.5) * h) + 'px';
  });
}

// ---------- loop render
let last = performance.now();
function frame(now) {
  const dt = Math.min(0.1, (now - last) / 1000); last = now;
  if (S.playing && Z) { if (S.s >= Z.sta[1] - 0.01) setSTA(Z.sta[0]); else setSTA(S.s + 18 * dt); }
  const w = stage.clientWidth, h = stage.clientHeight;
  if (Z) { const all = S.win >= +$('win').max, dC = camL.position.distanceTo(ctlL.target);
    for (const v of views) if (v) { v.fog.near = all ? 1e5 : dC + S.win * 0.35; v.fog.far = all ? 2e5 : dC + S.win * 1.5; } }
  if (canvas.width !== Math.floor(w * renderer.getPixelRatio()) || canvas.height !== Math.floor(h * renderer.getPixelRatio())) renderer.setSize(w, h, false);
  camL.aspect = camR.aspect = (w / 2) / h; camL.updateProjectionMatrix(); camR.updateProjectionMatrix();
  ctlL.update(); if (link) { camR.position.copy(camL.position); camR.quaternion.copy(camL.quaternion); ctlR.target.copy(ctlL.target); } else ctlR.update();
  renderer.setScissorTest(true);
  [[0, camL], [1, camR]].forEach(([i, cam]) => {
    if (!views[i]) return;
    renderer.setViewport(i * w / 2, 0, w / 2, h); renderer.setScissor(i * w / 2, 0, w / 2, h);
    renderer.render(views[i].scene, cam);
  });
  updateLabels(w, h);
  requestAnimationFrame(frame);
}

// ---------- mulai
fetch('data/model.json').then(r => r.json()).then(m => {
  MODEL = m; buildUI();
  const z = location.hash.slice(1); loadZone(MODEL.zona[z] ? z : Object.keys(MODEL.zona)[0]);
  window.__app = { S, camL, ctlL, setSTA, loadZone, preset, views: () => views };
  requestAnimationFrame(frame);
}).catch(e => { document.body.insertAdjacentHTML('beforeend', `<pre style="position:fixed;top:60px;left:20px;color:#f88">Gagal memuat data/model.json: ${e}\nJalankan lewat server lokal: python3 -m http.server</pre>`); });
