"""Evidence-linked proposals, bounded AI audit, local PPT additions and Excel export."""
import hashlib,json,os,re,subprocess
from pathlib import Path
from planning_schemas import ActionPlan
from schemas import Review

PLAN_INSTRUCTION = '''Buat rekomendasi perbaikan dan Action Plan dalam bahasa Indonesia untuk pemilik proyek.
Ini USULAN AI, bukan keputusan atau janji dalam rapat. Fakta latar belakang wajib didukung fact_ids.
Jangan mengubah laporan faktual. Jangan mengarang anggaran, kapasitas tim, nama PIC yang ditunjuk,
tanggal mulai, baseline KPI, nilai penghematan atau persetujuan yang tidak ada.
Gunakan 2-6 rekomendasi berbeda dan 6-20 langkah kerja bila bahan memadai; sumber singkat boleh lebih sedikit.
Tidak boleh ada rekomendasi generik tanpa masalah sumber atau pekerjaan pengisi untuk memenuhi jumlah.
slide_summary adalah ringkasan singkat yang utuh untuk PPT; rincian panjang tetap di proposal/task.
Setiap rekomendasi: masalah, solusi konkret, manfaat yang diharapkan, alasan prioritas dan tradeoff.
Setiap tugas: keluaran, kriteria penerimaan terukur, usulan peran PIC, sumber daya, risiko, mitigasi,
KPI usulan, asumsi serta bukti. KPI menjelaskan indikator dan cara ukur; bila baseline/target belum diketahui,
nyatakan perlu ditetapkan setelah pengukuran, bukan mengarang angka seolah sudah terbukti. PIC adalah peran yang diusulkan, bukan orang yang sudah ditunjuk.
Gunakan ID R001 dst dan A001 dst. Semua rekomendasi harus mempunyai tugas implementasi.
Jadwal adalah estimasi MINGGU RELATIF sejak persetujuan rencana, bukan tanggal hasil rapat.
Mulai dari klarifikasi scope/kapasitas dan baseline, lalu perbaikan mendesak/pilot sebelum perluasan.
Gunakan fase sesuai masalah, durasi wajar, dan jangan menumpuk semua pekerjaan pada minggu pertama.
Dependensi harus eksplisit: tugas penerus mulai setelah minggu akhir seluruh pendahulu.
Jangan menjadikan tinjauan/blacklist massal/penggantian sistem/kontrak sebagai tindakan langsung
sebelum verifikasi bukti, dampak operasional, kewenangan, dan persetujuan yang diperlukan.
Effort adalah estimasi person-day keseluruhan tugas, bukan jumlah orang. Gunakan null jika tidak dapat
menaksir secara bertanggung jawab. Tidak ada klaim kapasitas memadai bila kapasitas belum diketahui.
Semua nilai target/durasi/effort baru adalah asumsi/usulan dan perlu dijelaskan sebagai demikian.
Horizon paling lama 52 minggu, termasuk akhir setiap tugas. Jangan membuat dependensi melingkar.
Bila sumber ambigu atau audit faktual belum lolos, utamakan klarifikasi sebelum tindakan berisiko.
Usulan harus relevan, proporsional terhadap masalah, dapat diuji, dan mempertahankan operasi berjalan.'''
PLAN_INSTRUCTION += '''
Gunakan topik, risiko, hasil dan keputusan terbuka dalam report untuk menilai kelengkapan cakupan.
Untuk setiap rekomendasi jelaskan masalah sumber yang ditangani dan hasil yang dapat diperiksa.
Hindari satu tugas besar yang menyembunyikan pekerjaan penting; pisahkan validasi, keputusan,
pelaksanaan, pengujian dan penerimaan bila memang diperlukan. Jangan memecah pekerjaan remeh
untuk menambah jumlah tugas. Durasi dan effort harus mempertimbangkan prasyarat dan kapasitas
yang belum diketahui. Persetujuan dan kriteria penerimaan harus muncul sebelum perluasan.
Sediakan roadmap yang dapat dipresentasikan, sementara task, deliverable, acceptance, owner_role,
dependencies, resources, risk, mitigation, KPI dan assumptions cukup rinci untuk dipakai di Excel.
Jangan menyalin nama vendor, angka atau tanggal dari contoh desain ke rekaman lain.'''
PLAN_AUDIT = '''Periksa USULAN rekomendasi dan Action Plan terhadap fakta, konteks dan keterbatasan sumber.
Usulan boleh berupa gagasan baru; jangan menolaknya hanya karena belum disebut dalam rapat.
Namun jangan biarkan asumsi, PIC usulan, durasi, KPI target atau manfaat seolah sudah disepakati/terbukti.
Periksa manfaat tanpa dasar, duplikasi, langkah terlalu generik, ruang lingkup berlebihan, tidak ada pilot,
risiko operasional/otorisasi, durasi terlalu cepat, effort tidak masuk akal, prasyarat, ketergantungan,
kriteria penerimaan, dan kesesuaian tugas dengan rekomendasi. Jika kapasitas/budget/baseline tidak ada,
harus diakui dan ada langkah validasi, bukan klaim rencana pasti layak. Periksa semua rekomendasi
mempunyai langkah implementasi dan tidak menutup risiko yang dinyatakan sumber.
passed=true hanya jika tidak ada masalah material dan issues kosong. Tiap issue sebut ID tugas/rekomendasi,
alasan konkret dan perbaikan. Anda menilai kewajaran rancangan, bukan menjamin kelayakan dunia nyata.'''


def validate_plan(plan,facts):
    known={f['id'] for f in facts}
    recs={r.id for r in plan.recommendations};tasks={t.id:t for t in plan.tasks}
    if len(recs)!=len(plan.recommendations) or len(tasks)!=len(plan.tasks):
        raise ValueError('ID rekomendasi atau tugas ganda.')
    if any(not re.fullmatch(r'R\d{3}',x) for x in recs) or any(not re.fullmatch(r'A\d{3}',x) for x in tasks):
        raise ValueError('Format ID rencana tidak valid.')
    for item in [*plan.recommendations,*plan.tasks]:
        if any(f not in known for f in item.fact_ids):raise ValueError('Rencana merujuk fakta yang tidak tersedia.')
    for task in plan.tasks:
        if task.recommendation_id not in recs:raise ValueError('Tugas merujuk rekomendasi yang tidak tersedia.')
        if task.start_week+task.duration_weeks-1>52:raise ValueError('Jadwal tugas melampaui 52 minggu.')
        if len(set(task.depends_on))!=len(task.depends_on):raise ValueError('Dependensi tugas ganda.')
        for previous in task.depends_on:
            if previous not in tasks or previous==task.id:raise ValueError('Dependensi tugas tidak valid.')
    visiting=set();visited=set()
    def visit(key):
        if key in visiting:raise ValueError('Dependensi Action Plan melingkar.')
        if key in visited:return
        visiting.add(key)
        for previous in tasks[key].depends_on:visit(previous)
        visiting.remove(key);visited.add(key)
    for key in tasks:visit(key)
    for task in plan.tasks:
        if any(task.start_week < tasks[p].start_week+tasks[p].duration_weeks for p in task.depends_on):
            raise ValueError('Jadwal tugas mendahului selesainya prasyarat.')
    if recs!={t.recommendation_id for t in plan.tasks}:raise ValueError('Ada rekomendasi tanpa langkah implementasi.')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_plan(directory):
    manifest=directory/'plan-manifest.json'
    if not manifest.exists():return False
    data=json.loads(manifest.read_text(encoding='utf-8'))
    for name,value in data['artifacts'].items():
        if not (directory/name).exists() or digest(directory/name)!=value:
            raise ValueError('Sumber atau Action Plan berubah setelah pemeriksaan. Rencana tidak digunakan sebagai hasil terperiksa.')
    return True


def build_plan(directory,update,ai=None):
    from pipeline import AI,write_json,check_quality_manifest
    if checked_plan(directory):
        return ActionPlan.model_validate_json((directory/'plan.json').read_text(encoding='utf-8')),Review.model_validate_json((directory/'plan-review.json').read_text(encoding='utf-8'))
    check_quality_manifest(directory)
    facts=json.loads((directory/'facts.json').read_text(encoding='utf-8'))
    report=json.loads((directory/'report.json').read_text(encoding='utf-8'))
    source_review=json.loads((directory/'review.json').read_text(encoding='utf-8'))
    ai=ai or AI(directory)
    payload={'facts':facts,'report':report,'source_review':source_review}
    cache=directory/'plan-initial.json';audit=directory/'plan-review-initial.json'
    needed=int(not cache.exists())+int(not audit.exists())
    if int(os.getenv('MAX_PAID_CALLS_PER_JOB','12'))-len(ai.journal.data['requests'])<needed:
        raise ValueError('Sisa batas API tidak cukup untuk rekomendasi dan pemeriksaannya. Hasil sebelumnya tetap tersimpan; tidak ada panggilan rencana baru.')
    update(stage='planning',progress=92,message='Menyusun rekomendasi dan Action Plan yang terkait bukti diskusi')
    if cache.exists():plan=ActionPlan.model_validate_json(cache.read_text(encoding='utf-8'))
    else:
        plan=ai.ask(ActionPlan,PLAN_INSTRUCTION,payload,max_tokens=16000)
        validate_plan(plan,facts);write_json(cache,plan.model_dump())
    validate_plan(plan,facts)
    def review_at(path,value):
        if path.exists():result=Review.model_validate_json(path.read_text(encoding='utf-8'))
        else:
            result=ai.ask(Review,PLAN_AUDIT,{**payload,'plan':value.model_dump()},max_tokens=4000)
            if result.issues:result.passed=False
            elif not result.passed:result.issues=['Pemeriksa rencana belum meloloskan usulan tanpa rincian temuan.']
            write_json(path,result.model_dump())
        return result
    review=review_at(audit,plan)
    revisions=0
    if not review.passed and int(os.getenv('MAX_AI_REVISIONS','1'))>0:
        revised=directory/'plan-repaired.json';final=directory/'plan-review-final.json'
        needed=int(not revised.exists())+int(not final.exists())
        if int(os.getenv('MAX_PAID_CALLS_PER_JOB','12'))-len(ai.journal.data['requests'])>=needed:
            if revised.exists():candidate=ActionPlan.model_validate_json(revised.read_text(encoding='utf-8'))
            else:
                candidate=ai.ask(ActionPlan,PLAN_INSTRUCTION+'\nPerbaiki temuan pemeriksa secara menyeluruh.',{**payload,'plan':plan.model_dump(),'issues':review.issues},max_tokens=16000)
                validate_plan(candidate,facts);write_json(revised,candidate.model_dump())
            validate_plan(candidate,facts);review=review_at(final,candidate);plan=candidate;revisions=1
        else:review=Review(passed=False,issues=review.issues+['Sisa batas API tidak cukup untuk revisi rencana dan pemeriksaan ulang.'])
    write_json(directory/'plan.json',plan.model_dump());write_json(directory/'plan-review.json',review.model_dump())
    (directory/'plan-notes.md').write_text('# Catatan Rekomendasi dan Action Plan\n\nStatus: '+('Lolos pemeriksaan otomatis usulan' if review.passed else 'DRAF - masih ada temuan')+'\n\nSemua rekomendasi, peran PIC, target dan jadwal adalah usulan yang memerlukan persetujuan.\n\n'+'\n'.join('- '+x for x in review.issues)+'\n\n## Asumsi\n'+'\n'.join('- '+x for x in plan.assumptions)+'\n',encoding='utf-8')
    names=['plan.json','plan-review.json','report.json','facts.json','review.json']
    write_json(directory/'plan-manifest.json',{'version':1,'repair_rounds':revisions,'artifacts':{n:digest(directory/n) for n in names}})
    return plan,review


def presentation_with_plan(directory):
    from pipeline import write_json
    report=json.loads((directory/'report.json').read_text(encoding='utf-8'))
    if not (directory/'plan.json').exists():return directory/'report.json'
    checked_plan(directory)
    plan=ActionPlan.model_validate_json((directory/'plan.json').read_text(encoding='utf-8'))
    review=Review.model_validate_json((directory/'plan-review.json').read_text(encoding='utf-8'))
    report['client_plan']=plan.model_dump()
    report['client_plan_review_passed']=review.passed
    def slide(title,bullets,refs,notes='',**visual):
        return {'title':title,'bullets':[{'text':text,'fact_ids':refs} for text in bullets],
                'notes':notes,'proposal':True,'plan_review_passed':review.passed,**visual}
    for rec in sorted(plan.recommendations,key=lambda r:r.priority):
        report['slides'].append(slide(rec.priority+' '+rec.title,
            [rec.slide_summary,'Manfaat yang diharapkan: '+rec.benefit],rec.fact_ids,
            'USULAN AI. Rincian solusi: '+rec.proposal+'\nDasar masalah: '+rec.problem+'\nAlasan prioritas: '+rec.rationale+'\nTradeoff: '+rec.tradeoff,
            layout='recommendation',recommendation=rec.model_dump()))
    phases={}
    for task in plan.tasks:phases.setdefault(task.phase,[]).append(task)
    for phase,tasks in phases.items():
        first=min(t.start_week for t in tasks);last=max(t.start_week+t.duration_weeks-1 for t in tasks)
        report['slides'].append(slide(f'Timeline {phase}',
            [f'Usulan Minggu {first} sampai {last} sejak persetujuan rencana.']+[t.slide_summary for t in tasks],
            sorted({f for t in tasks for f in t.fact_ids}),
            '\n'.join(f'{t.id}: {t.task}; peran PIC usulan {t.owner_role}; mulai M{t.start_week}, durasi {t.duration_weeks} minggu; keluaran {t.deliverable}.' for t in tasks)+'\nRincian seluruh tugas tersedia pada action-plan.xlsx.',
            layout='timeline',tasks=[t.model_dump() for t in tasks]))
        report['slides'].append(slide(f'Action plan {phase}',[t.slide_summary for t in tasks],
            sorted({f for t in tasks for f in t.fact_ids}),
            'Usulan peran dan estimasi jadwal memerlukan persetujuan. Kriteria penerimaan, dependensi, effort, risiko dan KPI lengkap tersedia pada Excel dan catatan slide.',
            layout='action_table',tasks=[t.model_dump() for t in tasks]))
    refs=sorted({f for r in plan.recommendations for f in r.fact_ids})
    report['slides'].append(slide('Persetujuan dan asumsi rencana',plan.approvals_required,refs,
        '\n'.join(plan.assumptions)+'\nKapasitas: '+plan.capacity_assumption+'\nPPT merupakan snapshot rencana saat dibuat; perubahan Excel berikutnya tidak otomatis mengubah PPT.',layout='decisions'))
    target=directory/'presentation-report.json';write_json(target,report);return target


def render_action_plan(directory,preview=False):
    from pipeline import ROOT
    if (directory/'plan-manifest.json').exists():checked_plan(directory)
    node=os.getenv('NODE_EXE','node')
    args=[node,str(ROOT/'render-action-plan.mjs'),str(directory),str(directory/'action-plan.xlsx')]
    if preview:args.append('--preview')
    result=subprocess.run(args,env={**os.environ,'WORKFLOW_PYTHON':__import__('sys').executable},cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
    if result.returncode or not (directory/'action-plan.xlsx').exists():
        raise RuntimeError('Pembuatan Excel gagal. Periksa runtime Excel lokal dan hasil tersimpan. Permintaan AI tidak diulang untuk memperbaiki format file.')


def planning_preflight(directory):
    from pipeline import write_json
    plan={'title':'Uji Action Plan Lokal','assumptions':['Data rekaan untuk uji tanpa API.'],
          'capacity_assumption':'Belum dikonfirmasi.','approvals_required':['Persetujuan uji.'],
          'recommendations':[{'id':'R001','title':'Konfirmasi kebutuhan','problem':'Uji lokal',
          'slide_summary':'Konfirmasi ruang lingkup sebelum mulai.','proposal':'Konfirmasi ruang lingkup sebelum mulai.','benefit':'Scope jelas.','priority':'P1',
          'rationale':'Prasyarat kerja.','tradeoff':'Memerlukan waktu.','fact_ids':['TEST']}],
          'tasks':[{'id':'A001','recommendation_id':'R001','phase':'Persiapan','priority':'P1',
          'task':'Konfirmasi ruang lingkup.','slide_summary':'Konfirmasi ruang lingkup.','deliverable':'Ruang lingkup uji.','acceptance':'Disetujui pemilik proses.',
          'owner_role':'Pemilik proses usulan','start_week':1,'duration_weeks':1,'effort_person_days':None,
          'depends_on':[],'resources':'Waktu diskusi','risk':'Kapasitas belum jelas','mitigation':'Konfirmasi kapasitas',
          'kpi':'Scope disepakati','assumptions':'Estimasi awal','fact_ids':['TEST']}]}
    write_json(directory/'plan.json',plan);write_json(directory/'facts.json',[{'id':'TEST','source_ids':['S1'],'quote':'Data rekaan.'}])
    write_json(directory/'plan-review.json',{'passed':True,'issues':[]});render_action_plan(directory)
