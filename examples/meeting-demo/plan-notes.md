# Tinjauan rencana final

Status: selesai ditinjau editorial. Bukan kelulusan audit AI baru.

Rancangan bersyarat belum dapat dijadwalkan dan bukan persetujuan implementasi. Audit AI terakhir belum meloloskan versi sebelumnya; seluruh revisi berikutnya ditinjau editorial tanpa panggilan API tambahan.

## Temuan yang ditutup
- Lingkup evaluasi eksplisit hanya kelengkapan/konsistensi dokumen; keputusan verifikasi stok terpisah di A004.
- Protokol, validasi kasus sintetis, konflik, stop-rule dan go/no-go menjadi prasyarat minimum sebelum pilot paralel.
- Mulai, durasi dan effort null; rancangan belum dapat dijadwalkan sampai kapasitas/estimasi/kalender disepakati A002.
- Kriteria daftar persiapan terpisah dari verifikasi; bukti yang tidak tersedia tidak dibuat-buat.
- Tugas Sari/Budi dan tenggat sumber independen; Rina mengoordinasikan pertemuan tanpa diasumsikan sebagai pemberi persetujuan.
- Empat paket kerja minimum; kebutuhan fungsi dan beban divalidasi sebelum kegiatan tambahan, fungsi boleh dirangkap.
- A004 meminta keputusan konkret kebutuhan stok fisik oleh pihak berwenang A002 saat evaluasi/penutupan.
- Semua keputusan bisnis yang belum ada tetap dilabeli bersyarat. Review editorial tidak mengaku sebagai kelulusan audit AI.

## Protokol operasional usulan
### mandat dan peran
Ini usulan prosedur, belum keputusan rapat. Pemilik proses sesuai mandat organisasi diminta menunjuk pemberi keputusan dan penanggung jawab data. Sari/Budi tetap memegang tugas sumber; data kapasitas disediakan pemilik proses/petugas yang relevan. Fungsi penyusun, pengamat dan pelaksana dapat dirangkap bila layak, ditunjuk hanya bila diperlukan menurut protokol. Tidak diasumsikan telah ada penunjukan atau persetujuan. Tugas rapat dan penerimaan hasil Sari/Budi tidak bergantung pada A001; hanya aktivitas pilot tambahan memerlukan mandat tersebut.

### minimum daftar
Untuk kesiapan pilot, daftar perlu identitas yang membedakan barang (kode bila ada, nama/deskripsi bila belum), status verifikasi dan cara menandai item tidak dikenal. Pemberi keputusan mengesahkan minimum sebelum go. Daftar persiapan tetap diterima sebagai penyelesaian tugas sumber; jika minimum pilot belum terpenuhi, catat pengecualian dan tunda go. Jangan membuat kode, jumlah atau bukti fiktif.

### jenis evaluasi
Sebelum pilot pilih dan sahkan: deskriptif (tanpa baseline/target, hanya hasil teramati) atau evaluasi perbaikan (hanya jika baseline pembanding dan target tervalidasi tersedia). Baseline berarti observasi awal, bukan target sukses. Deskriptif tidak mensyaratkan baseline dan tidak menyimpulkan perbaikan/keberhasilan. Pilihan, denominator dan batas simpulan disahkan sebelum mulai.

### populasi dan sampel
Tetapkan periode, populasi transaksi yang boleh diakses, cakupan Gudang A, ukuran sampel dan metode pemilihan menurut volume aktual. Jika volume belum diketahui, kumpulkan terlebih dahulu; jangan menetapkan angka sampel rekaan. Catat periode, populasi, metode, sampel terpilih dan pengecualian. Tanpa cakupan dan metode yang disahkan, no-go.

### indikator
Kelengkapan = isian wajib terisi dibagi seluruh isian wajib pada sampel. Kolom wajib disahkan dari format sumber sebelum pilot. Konsistensi aritmetis = catatan dengan saldo sebelumnya+masuk-keluar sama dengan saldo berikutnya dibagi catatan yang dapat diuji. Catatan tak dapat diuji dilaporkan terpisah. Saldo awal belum terverifikasi; indikator ini bukan kecocokan atau akurasi stok fisik.

### checklist latihan
Sebelum latihan sahkan checklist: identifikasi item; masukkan kolom wajib; catat masuk/keluar; uji saldo aritmetis; tandai kolom kosong/item tak dikenal/saldo tak dapat diuji; log pengecualian; lakukan eskalasi. Gunakan data sintetis yang mewakili semua kasus. Lulus bila langkah dan hasil tiap kasus sesuai harapan yang disahkan, bukti dicatat, dan kesalahan kritis ditutup. Kritis = data hilang, angka salah lolos sebagai benar, konflik/akses tak sah tidak ditandai. Ini validasi prosedur, bukan pembuktian operasi nyata.

### paralel dan konflik
Pilot hanya salinan paralel, catatan resmi berjalan tetap otoritatif dan tidak ditimpa/diganti. Sebelum mulai, sahkan aturan perbandingan dan penanganan konflik: beda catatan dilog, diperiksa terhadap dokumen sumber yang diizinkan, dan diputuskan pemberi keputusan. Tidak memperbaiki catatan resmi tanpa kewenangan dan jejak perubahan; konflik yang tak terselesaikan tetap ditandai.

### stop dan eskalasi
Pertemuan A002 menetapkan penanggung jawab penghentian dan pemberi keputusan eskalasi; fungsi ini boleh dirangkap jika disahkan. Stop jika akses tak sah, data hilang, angka salah diterima benar, konflik sumber tak dapat diselesaikan, atau kapasitas/prosedur tak terpenuhi. Hentikan input pilot, simpan bukti/log tanpa mengubah sumber, beri tahu pemberi keputusan. Hanya lanjut setelah penyebab diselesaikan dan go baru dicatat.

### penutupan
A002/A003 menetapkan aturan: tutup evaluasi setelah periode/sampel disepakati tercapai dan pengecualian diklasifikasikan. Koreksi hanya berdasar sumber, diotorisasi dan dicatat. Jika data minimum tak cukup atau masalah kritis terbuka, laporan tidak konklusif; pemberi keputusan memilih perbaiki/ulang atau tutup tanpa kesimpulan. Pengulangan/perluasan bukan otomatis dan perlu keputusan terpisah. Deskriptif tidak menghasilkan klaim berhasil.

### keputusan terbuka
Register opsional sejak awal memuat tanggal mulai, sampel/target atau mode deskriptif, pertemuan berikutnya, barcode, anggaran dan kebutuhan verifikasi stok. Catat belum diputuskan serta pihak yang diminta mengonfirmasi sesuai mandat, tanpa penugasan baru tersirat. Rina hanya disebut sebagai koordinator pertemuan sesuai sumber, bukan otomatis pemberi seluruh persetujuan. Register boleh ditutup tanpa kajian/pengadaan. Setelah evaluasi, bila ada kebutuhan stok fisik, mintakan gerbang terpisah: otorisasi, metode hitung, saldo awal, kapasitas dan kriteria. Tanpa itu tidak dilakukan; risiko stok belum tertangani.

### proporsionalitas
Empat paket kerja, bukan tujuh lapis persetujuan. Rincian protokol merupakan checklist minimum sesuai risiko, bukan jabatan/tahap tambahan yang wajib. Pada A002, pemilik proses menilai kebutuhan setiap fungsi dan beban, boleh merangkap peran atau menyederhanakan prosedur tanpa menghilangkan kontrol data. Jika kapasitas tidak memadai, no-go atau lingkup dikurangi dengan keputusan tercatat.

### keputusan stok
Pada evaluasi/penutupan A004, fungsi evaluasi meminta pemberi keputusan yang ditetapkan A002 menentukan: tidak perlu verifikasi stok, perlu gerbang terpisah, atau belum dapat diputuskan. Jika perlu, belum boleh hitung fisik sebelum mandat/izin, metode, saldo awal, kapasitas dan kriteria disetujui. Pilot dokumen tidak menangani risiko akurasi stok fisik.