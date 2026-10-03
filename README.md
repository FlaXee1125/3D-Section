# 3D Section – Saluran & Jalan (Skenario 1 vs 2)

Viewer 3D berbasis Three.js untuk membandingkan **Skenario 1 (kiri)** dan **Skenario 2 (kanan)**
pada zona saluran **O1, O4–O10**, dibangun dari gambar potongan melintang `data/source/3d-Modeling.dxf`
(228 potongan: 38 bagian saluran × 2 skenario × AWAL/TENGAH/AKHIR).

## Menjalankan
```bash
python3 -m http.server 8000      # lalu buka http://localhost:8000
```
(Harus lewat server HTTP; membuka `index.html` langsung dari file tidak bisa memuat modul/JSON.)
Pilih zona (O1…O10) di atas; URL `#O5` membuka zona O5 langsung.

## Fitur
- Dua jendela berdampingan, kamera disinkronkan (tombol **Sinkron**; bisa dipisah).
- Potongan **melintang (STA)**, **memanjang (offset)**, **datar (elevasi)**, atau tanpa potongan.
  Bidang potong diberi penutup (cap) berwarna sesuai material.
- Slider STA mengikuti gambar teknis (bar biru = STA yang ada gambarnya; celah = tidak ada gambar).
  Tombol ◀ ▶ lompat ke potongan gambar berikutnya; spasi = animasi; ←/→ geser 1 m (Shift = 10 m).
- Kartu info tiap jendela: tipe saluran, elevasi Top/Dasar/Tanah/As jalan, catatan galian;
  kartu Skenario 2 menampilkan **selisih terhadap Skenario 1** (hijau = naik, merah = turun).
- Eksagerasi vertikal 1–4×, filter material, preset kamera.

## Cara data dibentuk (`tools/dxf_to_model.py`)
```bash
pip install ezdxf shapely numpy
python3 tools/dxf_to_model.py data/source/3d-Modeling.dxf data/model.json
```
- Satu bingkai `POT_ALL_BORDER` = satu potongan; x lokal = offset dari as jalan (− UTARA, + SELATAN),
  elevasi dikalibrasi dari label sumbu elevasi.
- Dikelompokkan per zona **O**; tiap segmen (Saluran n / Bagian m) di-loft antar AWAL → TENGAH → AKHIR
  pada posisi STA sebenarnya. Celah STA antar-saluran dibiarkan kosong.
- Elemen: tanah asli (`GROUND`), timbunan/galian (garis `ROAD`), perkerasan/jalan existing
  (blok `JALAN_ASLI_TIPIKAL_2OKT_METER`: pavement, beton ramping, LFA, median barrier, guardrail),
  saluran (`CHANNEL1/2`: U-ditch & trapesium), bangunan (`BUILDING`: siphon, box culvert, talang),
  dan patok RUMIJA (`APJ`).

## Asumsi / batasan
- Alinyemen dianggap **lurus** (gambar tidak memuat koordinat peta); antar potongan **interpolasi linear**.
- Siphon & talang hanya digambar sebagai persegi dimensi bersih → diberi dinding beton **asumsi 0,20 m**.
- Guardrail digambar menerus; patok RUMIJA digambar tiap 20 m (kelipatan 20 m STA).
- **O1**: banjir kawasan di selatan jalan, muka air (MAB) = satu elevasi datar = dasar saluran selatan di hilir (STA terendah, Skenario 1),
  sama untuk kedua skenario; sisi utara kering; air berada di luar timbunan (tidak mengisi saluran).
- Air di dalam saluran tidak dimodelkan.
- Jangkauan offset dimodelkan ±36 m dari as jalan.
