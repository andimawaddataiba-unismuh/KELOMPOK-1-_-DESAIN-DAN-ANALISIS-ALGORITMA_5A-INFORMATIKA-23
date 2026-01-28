# 🧠 Pendeteksi Duplikasi Kalimat Akademik (String Matching)

Aplikasi web berbasis **Flask (Python)** untuk mendeteksi **duplikasi kalimat** pada teks akademik menggunakan algoritma **String Matching**, yaitu:

- ✅ Naive String Matching  
- ✅ Knuth–Morris–Pratt (KMP)  
- ✅ Boyer–Moore (Bad Character Rule)

Aplikasi ini membandingkan setiap pasangan kalimat secara **pairwise** (1 baris = 1 kalimat), menampilkan status **DUPLIKAT / TIDAK DUPLIKAT**, highlight bukti substring, serta penjelasan proses detail (trace) agar hasil bisa dipaparkan secara ilmiah.

---

## 🎯 Tujuan Project
Project ini dibuat untuk membantu proses pengecekan duplikasi kalimat pada dokumen/tugas akademik dengan pendekatan **pencocokan substring**.

Aplikasi ini cocok untuk:
- tugas kuliah (String Matching / Design & Analysis of Algorithm)
- demo presentasi + video penjelasan algoritma
- pembelajaran perbedaan Naive vs KMP vs Boyer–Moore

---

## ✅ Aturan Duplikasi
Sebuah pasangan kalimat dinyatakan **DUPLIKAT** apabila:

> kalimat yang lebih pendek (**PATTERN**) ditemukan sebagai **substring** di kalimat yang lebih panjang (**TEXT**)  
> setelah proses **normalisasi teks**.

### 🔎 Normalisasi Teks
Normalisasi dilakukan agar pencocokan lebih konsisten:
- huruf besar → kecil semua (lowercase)
- tanda baca dihapus
- karakter “–”, “—”, “-” dianggap spasi
- spasi ganda dirapikan

📌 Catatan: aplikasi ini mendeteksi duplikasi berdasarkan substring (teks), bukan kemiripan makna.

---

## ✨ Fitur Utama
- ✅ Input multi-kalimat (1 baris = 1 kalimat)
- ✅ Pilih metode: Naive / KMP / Boyer–Moore
- ✅ Mode:
  - **Cepat (Fast)**
  - **Analisis (Trace)** → menampilkan langkah algoritma
- ✅ Highlight bukti duplikasi pada teks asli
- ✅ Output tabel hasil pairwise:
  - status duplikasi
  - indeks ditemukan (`idx`)
  - waktu proses (ms)
  - jumlah perbandingan karakter (`comparisons`)
- ✅ Panel **Proses (Detail)** untuk tiap pasangan kalimat:
  - TEXT & PATTERN yang dipilih sistem
  - normalisasi A & B
  - LPS table (KMP)
  - last occurrence table (BM)
  - trace langkah-langkah algoritma

---

## 🧩 Teknologi
- Python 3.x
- Flask
- HTML + CSS Modern UI
- JavaScript (Fetch API)

---

## 📂 Struktur File
├── app.py # program utama Flask + algoritma string matching
├── README.md # dokumentasi project
