"""Source-checked repair of evidence and report. No network or paid calls."""
from copy import deepcopy
from schemas import Extraction, Fact
from quote_grounding import complete_references

SUMMARY_STANDARD = (
    'executive_slide_summary berisi 2-3 poin singkat untuk slide, maksimal 110 karakter per poin; '
    'tetap lengkap maknanya, fact_ids valid, tidak mengubah status usulan/keputusan atau angka. '
    'STANDAR KELUARAN KLIEN V5. '
    'Susun ringkasan informatif yang bisa dipahami klien tanpa mendengar rekaman: '
    'awali dengan pokok persoalan dan hasil utama, lalu cakup perkembangan, alasan penting, '
    'hasil terukur, risiko, keputusan, tindak lanjut, dan persoalan terbuka yang memang dibahas. '
    'Jangan hanya membuat daftar topik. Sesuaikan panjang dengan kekayaan informasi; '
    '3-12 poin ringkasan boleh digunakan, tanpa pengulangan atau mengisi jumlah poin. '
    'Periksa setiap topik dan setiap penugasan eksplisit di seluruh transkrip. '
    'actions tidak boleh kosong bila ada penugasan yang jelas. '
    'Bedakan penugasan, ajakan bantuan bersyarat, usulan, hasil lampau dan keputusan; '
    'sebutkan kategorinya di task jika perlu. Pertanyaan apakah daftar sudah tersedia '
    'bukan perintah membuat daftar dan bukan bukti daftar sudah tersedia. '
    'Jika PIC atau tenggat tidak disebut, tulis Tidak disebutkan; jangan menebak identitas dari label suara. '
    'Urgensi secepatnya bukan tanggal kalender. Angka historis bukan target baru. '
    'Ringkasan harus netral, jelas, spesifik dan bersumber; rekomendasi tambahan bukan keputusan rapat. '
    'Isi context dengan latar dan tujuan yang didukung sumber; bila tujuan tidak dinyatakan, akui batasnya. '
    'topics mengelompokkan pembahasan secara utuh dengan judul spesifik, points detail dan status bersumber. '
    'outcomes memuat hasil/perkembangan konkret, conclusions memuat sintesis berhati-hati, '
    'open_decisions memuat keputusan yang masih dibutuhkan. Hindari mengulang kalimat yang sama pada semua bagian. '
    'risk_items mengaitkan masalah, dampak, tingkat dan mitigasi. Bila tingkat/dampak/mitigasi adalah '
    'penilaian baru, assessment_basis wajib Analisis usulan; jangan menyajikannya sebagai keputusan rapat. '
    'highlights hanya angka, nilai atau periode yang benar-benar ada dalam sumber beserta konteks dan fact_ids; '
    'jika tidak ada angka yang cukup pasti gunakan [] dan jangan mengisi dengan angka contoh. '
    'Setiap bagian boleh kosong bila tidak didukung sumber. Jangan menulis bagian umum sekadar mengisi template. '
    'meeting_date hanya tanggal pertemuan yang disebut eksplisit, bukan tenggat atau tanggal panggilan berikutnya; '
    'gunakan null jika tidak pasti. participants hanya pihak/peran yang dapat ditelusuri, '
    'dengan identitas dan keanggotaan yang meragukan dinyatakan belum pasti. '
    'slide_summary tiap topic adalah ringkasan singkat yang utuh untuk PPT; rincian lengkap tetap di points Word. '
    'slide_impact dan slide_mitigation pada risk_items merangkum dampak dan mitigasi untuk tabel PPT, '
    'dengan makna dan status usulan yang sama dengan uraian lengkap Word. '
    'Tindak lanjut faktual di actions harus terpisah dari rekomendasi baru yang dibuat pada tahap rencana. '
)

REPAIR_STANDARD = (
    'Kembalikan QualityRepair berisi report yang lengkap, fact_updates dan additional_facts. '
    'Jangan hanya memperbaiki report bila kesalahan ada dalam facts. '
    'fact_updates berisi pengganti lengkap untuk ID fakta lama yang salah makna atau tidak lengkap rujukannya; '
    'ID lama tidak boleh diganti/dihapus. additional_facts hanya fakta penting yang benar-benar terlewat, '
    'dengan ID F berikutnya secara berurutan setelah ID terbesar. '
    'Bila tidak diperlukan gunakan []. Setiap fakta wajib memiliki quote yang PERSIS ada di '
    'gabungan source_ids sesuai urutan transkrip. Kutipan pendek bukan satu-satunya dasar klaim: '
    'source_ids harus mencakup semua segmen yang mendukung seluruh isi fakta. '
    'Gunakan fakta lama yang relevan bila sudah cukup; jangan membuat fakta duplikat. '
    'report dapat merujuk ID lama maupun ID additional_facts yang valid. '
    'Periksa kembali seluruh actions agar penugasan eksplisit tidak hilang saat merevisi. '
)


def apply_evidence_repair(bundle, facts, segments, validate_facts, validate_report, validate_slides, slide_count):
    """Reject unsupported quotes/IDs before a corrected report reaches audit/export."""
    result = deepcopy(facts)
    positions = {f['id']: i for i, f in enumerate(result)}
    order = {s['id']: i for i, s in enumerate(segments)}
    if len(positions) != len(result):
        raise ValueError('ID fakta sumber duplikat.')
    next_id = max((int(fid[1:]) for fid in positions), default=0) + 1
    seen = set()
    changes = []
    for is_new, corrections in [(False, bundle.fact_updates), (True, bundle.additional_facts)]:
        for corrected in corrections:
            fid = corrected.id
            if fid in seen:
                raise ValueError('ID perbaikan fakta duplikat.')
            seen.add(fid)
            if is_new:
                if fid != f'F{next_id:04}':
                    raise ValueError('ID fakta tambahan harus berurutan setelah fakta lama.')
                next_id += 1
            elif fid not in positions:
                raise ValueError('Perbaikan merujuk ID fakta yang tidak tersedia.')
            fact = Fact(text=corrected.text, quote=corrected.quote, source_ids=corrected.source_ids)
            if any(sid not in order for sid in fact.source_ids):
                raise ValueError('Rujukan transkrip perbaikan tidak ditemukan.')
            fact.source_ids = sorted(set(fact.source_ids), key=order.__getitem__)
            extraction, _ = complete_references(Extraction(facts=[fact]), segments)
            fact = extraction.facts[0]
            validate_facts([fact], segments)
            indices = sorted({j for sid in fact.source_ids for j in range(max(0, order[sid]-3), min(len(segments), order[sid]+4))})
            record = {'id': fid, **fact.model_dump(), 'context': [segments[j] for j in indices]}
            if is_new:
                result.append(record)
            else:
                result[positions[fid]] = record
            changes.append({'id': fid, 'kind': 'added' if is_new else 'corrected', 'source_ids': fact.source_ids})
    validate_report(bundle.report, result)
    validate_slides(bundle.report, slide_count)
    return bundle.report, result, changes
