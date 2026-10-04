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
- Eksagerasi vertikal 1–4×, preset kamera.
- Menu **Lompat ke bangunan…** (kanan atas) langsung membawa ke Simpang, siphon/talang di saluran irigasi, atau box culvert drainase; zona dan STA berpindah otomatis.
- Legenda diringkas jadi 8 bagian (Badan Jalan, Timbunan & Tanah, Saluran Drainase, Air, Ruang Bebas Jalan, Sawah, Gorong-gorong Kawasan, Simpang); tombol **Rincian** menampilkan centang per material.
- Tabel info di tiap jendela bisa dilipat dengan tombol ▾ (atau tekan **I**); panel bawah dengan ▾ di tengah (atau **H**).

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

## Saluran irigasi melintang, siphon revisi, sawah
- Di setiap lokasi **Siphon / Talang** (O5, O6, O7, O8, O9) ditambahkan **saluran irigasi melintang jalan**: terbuka di luar badan jalan
  (|offset| > 12,8 m, memotong timbunan dan berm) dan lewat **gorong-gorong box di bawah jalan**. Talang melintas di atas, siphon di bawahnya.
  Dimensi (asumsi): kedalaman 1,2 m dari muka tanah (lebih dangkal bila siphon dangkal), lebar atas ≈ 0,7 × panjang talang/siphon (2,5–8 m), talud 1:1,
  gorong-gorong bersih 1,0 m; air setinggi 70 % kedalaman.
- **Revisi Saluran 17 / Bagian 2 – Skenario 2** (STA 9+942,90 – 9+949,90): saluran U-ditch/trapesium diganti **siphon box 0,8 × 0,95 m (dinding 20 cm)**
  yang turun di bawah dasar saluran irigasi (kemiringan kaki ±37°) lalu naik lagi; rongga digambar gelap.
- **Sawah** (hijau) di kanan-kiri jalan di luar kaki timbunan, dengan **pematang** sejajar jalan (tiap 9 m offset) dan pematang melintang tiap 25 m STA.

## Simpang dan lokasi irigasi
- **Simpang** (STA tengah): Simpang 1 3+648,12 · Simpang 2 8+328,29 · Simpang 3 12+538,61 · Simpang 4 15+349. Hanya yang jatuh di STA yang punya gambar potongan
  yang dimodelkan (Simpang 2 di O5 dan Simpang 4 di O9; Simpang 1 dan 3 berada di celah STA tanpa gambar).
- Bentuk simpang **dibaca langsung dari vektor PDF tipikal** (`tools/pdf_to_simpang.py` → `data/simpang.json`): lengkung kerb sudut, tepi jalan simpang (5,05 m),
  pulau berkerb dan catch drain, **seluruh marka** (zebra cross, stop bar, garis tengah putus-putus, chevron, panah), catch basin (20), bak kontrol (6), manhole (6), pipa Ø300.
  Skala 8,27 pt/m; lebar jalan utama pada PDF (±6 m) diregangkan ke jalan utama model (±10,4 m), selebihnya digeser. Median jalan utama dan guardrail terputus di mulut simpang
  (bukaan median mengikuti stop bar zebra di PDF).
- Hanya garis lajur jalan utama yang jauh dari simpang dan teks "STOP" yang tidak dibawa (jalan utama memakai penampang DXF).
- Pipa Ø300 digambar sebagai balok persegi 0,3 m di bawah tanah; matikan Tanah/Timbunan/Perkerasan di legenda (atau tombol **Tembus tanah**) untuk melihatnya.
- Panel kontrol di bawah bisa dilipat dengan tombol ▾ (atau tekan **H**).
- **Saluran irigasi**: di setiap siphon/talang. Titik pusat = *STA titik acuan* siphon pada `Data_Drainase_Rev19.xlsx` (sheet Bangunan: 8+339,85 · 11+625,23 · 14+064,93)
  bila ada, selain itu tengah rentang bangunan. Lokasi pasti belum terkonfirmasi (kemungkinan bergeser ±3 m); ubah `REF_IRIGASI` di `tools/dxf_to_model.py`.

## Penyeberang saluran irigasi (talang / siphon)
- Di tiap lokasi irigasi, saluran drainase jalan diseragamkan agar konsepnya jelas: **Skenario 1 = talang** (flume terbuka, di atas saluran irigasi, berisi air),
  **Skenario 2 = siphon** (turun – datar – naik, simetris di bawah saluran irigasi). Keduanya lurus dan sejajar jalan (offset tetap).
- Dasar saluran irigasi = 0,5 m di bawah muka tanah (arahan); tombol **Tembus tanah** menyembunyikan tanah/timbunan agar siphon dan pipa terlihat.
- Saluran drainase jalan (U-ditch, trapesium, talang) kini berisi air setinggi 60 % tinggi bersih; takik timbunan mengikuti saluran yang bergeser (belok/melipir).

## Gorong-gorong irigasi, transisi siphon
- Gorong-gorong irigasi (box 1,0 m, dinding 20 cm) menembus **timbunan yang utuh**; kepala gorong-gorong (headwall) ada di tempat lereng timbunan jatuh ke puncak gorong-gorong,
  dengan **sayap (wingwall) 30°** penahan timbunan; saluran irigasi terbuka (berair) baru mulai di luar kepala gorong-gorong. Sudut 30° mengikuti praktik umum box culvert
  cast-in-place; gambar standar Bina Marga tidak tersedia, jadi dimensi sayap (panjang 3,5 m, tebal 0,25 m) adalah asumsi.
- Siphon Skenario 2: saluran (trapesium/U-ditch) → **transisi 3 m menjadi kotak terbuka** → siphon tertutup (turun – datar – naik) → transisi → saluran. Lokasi berdekatan (<5 m) digabung jadi satu siphon.

## Asumsi / batasan
- Alinyemen dianggap **lurus** (gambar tidak memuat koordinat peta); antar potongan **interpolasi linear**.
- Siphon & talang hanya digambar sebagai persegi dimensi bersih → diberi dinding beton **asumsi 0,20 m**.
- Guardrail W-beam: balok menerus, **tiang tersendiri tiap 2 m** (acuan: jarak tiang maks. 2 m untuk pagar pengaman W-beam; tinggi atas 65–80 cm dari perkerasan, tiang tertanam 1,0–1,15 m). Patok RUMIJA tiap 20 m (kelipatan STA).
- Skala gambar DXF 1:1 (1 satuan = 1 m, horizontal dan vertikal sama); arah memanjang hanya diketahui dari label STA.
- **O1**: banjir kawasan di selatan jalan, muka air (MAB) = satu elevasi datar = dasar saluran selatan di hilir (STA terendah, Skenario 1),
  sama untuk kedua skenario; sisi utara kering; air berada di luar timbunan (tidak mengisi saluran).
- Air di dalam saluran tidak dimodelkan.
- Jangkauan offset dimodelkan ±36 m dari as jalan.

## Gorong-gorong kawasan (cross drain) dan label 3D
- 19 titik (CD-1…CD-19, daftar STA/elevasi dari pengguna), **hanya Skenario 1**, box 0,5×0,5 m (dinding 15 cm) melintang di bawah jalan, bentuk mengacu `data/source/TIPIKAL_GORONG_GORONG.dxf`
  (kepala di kaki timbunan, sayap 30°, manhole besi cor). Elevasi diperlakukan sebagai acuan dasar dan diturunkan 0,2 m; dasar dijaga ≥ 0,3 m di bawah dasar saluran tepi
  supaya saluran tidak terpengaruh, dan maks. 1,2 m di bawah tanah. CD di luar cakupan DXF (STA 17883,9) dan di celah STA tanpa gambar tidak digambar.
- Gorong-gorong irigasi: kepala ditarik ke dalam (dekat jalan) dengan dinding penahan, talang/siphon berada di luar kepala di atas saluran terbuka.
- Tombol **🏷 Label** menampilkan nama bangunan (cross drain, gorong-gorong irigasi, talang/siphon, simpang) sebagai label 3D di tiap jendela.
