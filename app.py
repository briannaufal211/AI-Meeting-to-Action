"""Local-only API and upload page. Run exactly one server process."""
from typing import Annotated
import asyncio
import io
import json
import os
import queue
import secrets
import threading
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pipeline import ROOT, run_job, run_stage, STAGES, write_json, export_saved_word_summary

DATA = ROOT / 'data' / 'jobs'
DATA.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()
TASKS = queue.Queue()
ALLOWED = {'.mp3', '.wav', '.m4a', '.mp4', '.webm', '.ogg', '.flac', '.txt'}
DOWNLOADS = {'transcript-client.txt','transcript-client.html','transcript-client-map.json','transcript.txt', 'transcript.json', 'summary.docx', 'presentation.pptx', 'action-plan.xlsx', 'plan.json', 'plan-review.json', 'plan-notes.md',
             'transcription-manifest.json', 'transcription-alignment.json', 'primary-response.json', 'voice-evidence.json', 'quality.md', 'quality.json', 'transcript-checked.txt', 'transcript-quality.json',
             'report.json', 'facts.json', 'review.json', 'usage.json', 'cost-control.json', 'preflight.json'}
TOKEN_PATH = ROOT / 'data' / 'local-token.txt'
if not TOKEN_PATH.exists():
    TOKEN_PATH.write_text(secrets.token_urlsafe(32), encoding='utf-8')
LOCAL_TOKEN = TOKEN_PATH.read_text(encoding='utf-8').strip()


def now():
    return datetime.now(timezone.utc).isoformat()


def directory(job_id):
    try:
        if str(uuid.UUID(job_id)) != job_id:
            raise ValueError()
    except ValueError:
        raise HTTPException(404, 'Pekerjaan tidak ditemukan.')
    target = DATA / job_id
    if not (target / 'job.json').exists():
        raise HTTPException(404, 'Pekerjaan tidak ditemukan.')
    return target


def read_job(target):
    with LOCK:
        return json.loads((target / 'job.json').read_text(encoding='utf-8'))


def update_job(target, **values):
    with LOCK:
        job = read_job(target)
        job.update(values, updated_at=now())
        write_json(target / 'job.json', job)


def worker():
    while True:
        job_id = TASKS.get()
        if job_id is None:
            TASKS.task_done()
            return
        job_id, phase = job_id if isinstance(job_id, tuple) else (job_id, None)
        target = DATA / job_id
        try:
            update_job(target, status='running', started_at=now(), message='Pekerjaan dimulai')
            if phase:
                run_stage(target, phase, lambda **kw: update_job(target, **kw))
            else:
                run_job(target, lambda **kw: update_job(target, **kw))
        except Exception as error:
            # Do not return provider error strings, credentials or stack traces to browsers.
            name = type(error).__name__
            messages = {
                'AuthenticationError': 'API key OpenAI tidak valid. Periksa .env dan mulai ulang aplikasi.',
                'RateLimitError': 'Kuota, saldo, atau batas pemakaian API tercapai. Periksa akun API Anda.',
                'APIConnectionError': 'Koneksi OpenAI gagal. Status pemrosesan bisa belum pasti; sistem memblokir pengulangan permintaan yang sama sampai diperiksa.',
                'APITimeoutError': 'Respons OpenAI belum pasti. Permintaan tidak diulang otomatis. Periksa OpenAI Usage sebelum percobaan baru.',
            }
            message = messages.get(name, str(error) if isinstance(error, (ValueError, RuntimeError)) else
                                   f'Proses gagal ({name}). Periksa audio, model, dan panduan pemecahan masalah.')
            key = os.getenv('OPENAI_API_KEY', '')
            if key:
                message = message.replace(key, '[rahasia]')
            update_job(target, status='failed', message=message[:600])
        finally:
            TASKS.task_done()


@asynccontextmanager
async def lifespan(app):
    # A stopped process cannot safely resume in-flight model calls automatically.
    for path in DATA.glob('*/job.json'):
        if read_job(path.parent).get('status') in {'running', 'queued', 'uploading'}:
            update_job(path.parent, status='interrupted', message='Aplikasi sebelumnya berhenti. Klik Lanjutkan untuk memakai hasil tersimpan.')
    # Add the new document format to completed older jobs without AI calls.
    for path in DATA.glob('*/job.json'):
        if read_job(path.parent).get('status') in {'completed', 'needs_review'}:
            try:
                export_saved_word_summary(path.parent)
            except (ValueError, RuntimeError, OSError):
                update_job(path.parent, summary_export_error='Ringkasan Word belum tersedia. Periksa pemasangan pustaka dan hasil tersimpan.')
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    yield
    TASKS.put(None)


app = FastAPI(title='Otomasi Diskusi Lokal', lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'host.docker.internal', 'testserver'])


@app.middleware('http')
async def local_only(request: Request, call_next):
    # Token on mutations prevents cross-site form submissions. No CORS is enabled.
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        token = request.headers.get('x-local-token', '')
        if not secrets.compare_digest(token, LOCAL_TOKEN):
            return Response('Token lokal tidak sesuai.', status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@app.get('/', response_class=HTMLResponse)
def home():
    return (ROOT / 'index.html').read_text(encoding='utf-8').replace('__LOCAL_TOKEN__', LOCAL_TOKEN)


@app.get('/api/health')
def health():
    return {'ok': True, 'presentation_design_version': 5, 'client_template_version': 5, 'detailed_summary_supported': True, 'adaptive_slide_layouts': True, 'auto_slide_count_supported': True, 'quality_pipeline_version': 3, 'summary_standard_version': 5, 'evidence_repair_supported': True, 'summary_docx_supported': True, 'planning_supported': True, 'api_key_configured': bool(os.getenv('OPENAI_API_KEY', '').strip()),
            'model': os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'),
            'client_transcript_version':1, 'client_transcript_supported':True,
            'quote_recovery_version':2, 'identical_audio_reuse_supported':True, 'cache_only_recovery_supported':True,
            'n8n_upload_route_version':2, 'output_modes_supported':True, 'speaker_audio_supported': True, 'speaker_audio_enabled': os.getenv('SPEAKER_AUDIO_ENABLED','1')!='0', 'speaker_text_import_supported': True, 'transcription_languages': os.getenv('TRANSCRIPTION_LANGUAGES','id'), 'transcription_api_version': 1, 'transcription_provider': os.getenv('TRANSCRIPTION_PROVIDER','openai'),
            'transcription_model': os.getenv('TRANSCRIPTION_MODEL','gpt-transcribe'),
            'whisper_model': os.getenv('WHISPER_MODEL', 'small'),
            'device_setting': os.getenv('WHISPER_DEVICE', 'auto'), 'queue_size': TASKS.qsize(),
            'cost_controls': {'automatic_network_retries': 0, 'max_calls_per_job': int(os.getenv('MAX_PAID_CALLS_PER_JOB','12')),
                              'automatic_ai_revisions': min(1, max(0, int(os.getenv('MAX_AI_REVISIONS','1'))))}}


@app.get('/api/jobs')
def jobs():
    records = [public_job(p.parent) for p in DATA.glob('*/job.json')]
    return sorted(records, key=lambda j: j['created_at'], reverse=True)


def public_job(target):
    job = read_job(target)
    job['files'] = sorted(name for name in DOWNLOADS if (target / name).exists())
    usage_path = target / 'usage.json'
    if usage_path.exists():
        job['usage'] = json.loads(usage_path.read_text(encoding='utf-8'))
    return job


@app.get('/api/jobs/{job_id}')
def status(job_id: str):
    return public_job(directory(job_id))


@app.post('/api/jobs', status_code=202)
async def submit(file: UploadFile = File(...), title: str = Form('Ringkasan diskusi'), slide_count: int = Form(0), orchestrator: str = Form('app'), output_mode: Annotated[str, Form()] = 'summary_ppt'):
    if output_mode not in {'summary_only','summary_ppt'}:raise HTTPException(422,'Pilihan keluaran tidak valid.')
    if orchestrator not in {'app', 'n8n'}:
        raise HTTPException(422, 'Pengatur alur harus app atau n8n.')
    if slide_count != 0 and not 4 <= slide_count <= 16:
        raise HTTPException(422, 'Pilih Otomatis atau jumlah slide 4 sampai 16.')
    extension = Path(file.filename or '').suffix.lower()
    if extension not in ALLOWED:
        raise HTTPException(415, 'Gunakan MP3, WAV, M4A, MP4, WEBM, OGG, FLAC, atau TXT UTF-8.')
    with LOCK:
        active = sum(read_job(p.parent).get('status') in {'uploading', 'queued', 'running'} for p in DATA.glob('*/job.json'))
        if active >= 5:
            raise HTTPException(429, 'Antrean penuh. Tunggu salah satu pekerjaan selesai.')
        job_id = str(uuid.uuid4())
        target = DATA / job_id
        target.mkdir()
        write_json(target / 'job.json', {
            'id': job_id, 'title': title.strip()[:180] or 'Ringkasan diskusi', 'slide_count': -1 if output_mode=='summary_only' else slide_count, 'output_mode':output_mode,
            'filename': Path(file.filename or 'rekaman').name, 'extension': extension,
            'input_kind': 'text' if extension == '.txt' else 'audio', 'orchestrator': orchestrator,
            'transcription_speakers': extension!='.txt' and os.getenv('SPEAKER_AUDIO_ENABLED','1')!='0', 'transcription_provider': os.getenv('TRANSCRIPTION_PROVIDER','openai'), 'transcription_model': os.getenv('TRANSCRIPTION_MODEL','gpt-transcribe'),
            'quality_version': 2, 'summary_standard_version': 5, 'client_template_version': 5, 'planning_version': 1 if output_mode=='summary_ppt' and os.getenv('ENABLE_ACTION_PLAN','1') != '0' else 0, 'completed_stages': [], 'status': 'uploading',
            'stage': 'uploading', 'progress': 0, 'message': 'Mengunggah file', 'created_at': now()})
    size = 0
    try:
        with (target / ('input' + extension)).open('wb') as stream:
            while data := await file.read(1024 * 1024):
                size += len(data)
                if size > int(os.getenv('MAX_UPLOAD_MB', '300')) * 1024 * 1024:
                    raise HTTPException(413, 'Ukuran file melebihi MAX_UPLOAD_MB di .env.')
                stream.write(data)
        if not size:
            raise HTTPException(422, 'File kosong.')
        if extension == '.txt':
            try:
                text = (target / 'input.txt').read_text(encoding='utf-8-sig')
                if not text.strip() or len(text) > 250000:
                    raise ValueError()
            except (UnicodeError, ValueError):
                raise HTTPException(422, 'TXT harus UTF-8, berisi teks, dan maksimal 250.000 karakter.')
    except BaseException:
        (target / ('input' + extension)).unlink(missing_ok=True)
        update_job(target, status='failed', message='Unggah gagal. Buat pekerjaan baru dengan file yang sesuai.')
        raise
    finally:
        await file.close()
    if orchestrator == 'n8n':
        update_job(target, status='waiting', stage='registered', message='File diterima. Menunggu perintah tahap dari n8n.', uploaded_bytes=size)
    else:
        update_job(target, status='queued', stage='queued', message='Menunggu giliran', uploaded_bytes=size)
        TASKS.put(job_id)
    return public_job(target)


@app.post('/api/jobs/{job_id}/retry', status_code=202)
def retry(job_id: str):
    target = directory(job_id)
    if read_job(target).get('orchestrator') == 'n8n':
        raise HTTPException(409, 'Lanjutkan melalui n8n agar urutan tahap tetap dikelola n8n.')
    with LOCK:
        if read_job(target)['status'] not in {'failed', 'interrupted'}:
            raise HTTPException(409, 'Hanya pekerjaan gagal atau terhenti yang bisa dilanjutkan.')
        meta = read_job(target)
        if not (target / ('input' + meta['extension'])).exists():
            raise HTTPException(409, 'File sumber tidak tersedia. Unggah ulang sebagai pekerjaan baru.')
        active = sum(read_job(p.parent).get('status') in {'uploading', 'queued', 'running'} for p in DATA.glob('*/job.json'))
        if active >= 5:
            raise HTTPException(429, 'Antrean penuh.')
        update_job(target, status='queued', stage='queued', message='Melanjutkan dari hasil yang tersimpan')
        TASKS.put(job_id)
    return public_job(target)


@app.get('/api/jobs/{job_id}/files/{name}')
def download(job_id: str, name: str):
    target = directory(job_id)
    if name not in DOWNLOADS | {'summary.md'} or not (target / name).is_file():
        raise HTTPException(404, 'File belum tersedia.')
    if name=='transcript-client.html':
        return FileResponse(target/name,filename=name,media_type='text/html',content_disposition_type='inline',
            headers={'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",'X-Content-Type-Options':'nosniff'})
    return FileResponse(target / name, filename=name)


@app.get('/api/jobs/{job_id}/bundle')
def bundle(job_id: str):
    target = directory(job_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(DOWNLOADS):
            if (target / name).is_file():
                archive.write(target / name, name)
    return Response(buffer.getvalue(), media_type='application/zip',
                    headers={'Content-Disposition': f'attachment; filename="hasil-{job_id[:8]}.zip"'})

@app.post('/api/n8n-jobs', status_code=202)
async def submit_through_n8n(file: UploadFile = File(...), title: str = Form('Ringkasan diskusi'), slide_count: int = Form(0), output_mode: Annotated[str, Form()] = 'summary_ppt'):
    """Same upload page can send work through the imported localhost n8n webhook."""
    import httpx
    if output_mode not in {'summary_only','summary_ppt'}:raise HTTPException(422,'Pilihan keluaran tidak valid.')
    if Path(file.filename or '').suffix.lower() not in ALLOWED or (slide_count != 0 and not 4 <= slide_count <= 16):
        raise HTTPException(422, 'Format file atau jumlah slide tidak sesuai.')
    size = 0
    while data := await file.read(1024 * 1024):
        size += len(data)
        if size > int(os.getenv('MAX_UPLOAD_MB', '300')) * 1024 * 1024:
            await file.close()
            raise HTTPException(413, 'Ukuran file melebihi batas upload.')
    if not size:
        await file.close()
        raise HTTPException(422, 'File kosong.')
    await file.seek(0)
    url = n8n_upload_url()
    try:
        async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
            response = await client.post(url, headers={'X-Local-Token': LOCAL_TOKEN}, files={'file':(file.filename, file.file, file.content_type)},
                data={'title':title[:180], 'slide_count':str(slide_count),'output_mode':output_mode})
        if response.status_code != 202:
            raise HTTPException(502, f'n8n belum menerima pekerjaan (HTTP {response.status_code}). Periksa alamat webhook, workflow aktif, dan credential token. Tidak ada pengiriman ulang otomatis.')
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, 'n8n lokal belum terhubung. Nyalakan n8n dan aktifkan workflow, atau gunakan proses langsung.')
    finally:
        await file.close()

@app.post('/api/reload-config')
def reload_configuration():
    from dotenv import load_dotenv
    with LOCK:
        if any(read_job(p.parent).get('status') in {'uploading','queued','running'} for p in DATA.glob('*/job.json')):
            raise HTTPException(409,'Tunggu antrean selesai sebelum memuat konfigurasi baru.')
        load_dotenv(ROOT / '.env', override=True)
    return health()


@app.post('/api/jobs/{job_id}/stages/{phase}', status_code=202)
def start_stage(job_id: str, phase: str):
    target = directory(job_id)
    if phase not in STAGES:
        raise HTTPException(404, 'Tahap tidak ditemukan.')
    required = {'transcribe': None, 'summarize': 'transcribe', 'quality': 'summarize', 'plan': 'quality', 'render': 'summarize'}[phase]
    artifacts = {'transcribe': 'transcript.json', 'summarize': 'summary.md', 'quality': 'quality-manifest.json', 'plan': 'plan-manifest.json', 'render': 'summary.docx' if job_mode_summary(target) else 'presentation.pptx'}
    with LOCK:
        job = read_job(target)
        if job.get('orchestrator') != 'n8n':
            raise HTTPException(409, 'Pekerjaan ini belum dikelola n8n.')
        if job['status'] in {'running', 'queued'}:
            if job.get('requested_stage') == phase:
                return public_job(target)
            raise HTTPException(409, 'Tahap lain masih berjalan.')
        if phase in job.get('completed_stages', []) and ((target / artifacts[phase]).exists() or (phase == 'plan' and (target/'plan-skipped.json').exists())):
            if job['status'] in {'failed', 'interrupted'}:
                update_job(target, status='waiting', message='Tahap tersimpan tersedia. n8n melanjutkan ke tahap berikutnya.')
            return public_job(target)
        if required and required not in job.get('completed_stages', []):
            raise HTTPException(409, 'Tahap sebelumnya belum selesai.')
        if phase != 'transcribe' and not (target / artifacts[required]).exists():
            raise HTTPException(409, 'File hasil tahap sebelumnya tidak tersedia.')
        if TASKS.qsize() >= 5:
            raise HTTPException(429, 'Antrean pemrosesan penuh.')
        update_job(target, status='queued', requested_stage=phase, stage=phase + '_queued', message='n8n menjadwalkan tahap ' + phase)
        TASKS.put((job_id, phase))
    return public_job(target)


@app.post('/api/n8n-resume/{job_id}', status_code=202)
def resume_with_n8n(job_id: str):
    import httpx
    target = directory(job_id)
    with LOCK:
        job = read_job(target)
        if job['status'] not in {'failed', 'interrupted', 'waiting'}:
            raise HTTPException(409, 'Pekerjaan masih berjalan atau sudah selesai.')
        update_job(target, orchestrator='n8n')
    url = os.getenv('N8N_RESUME_URL', 'http://127.0.0.1:5678/webhook/diskusi-lanjut')
    try:
        with httpx.Client(timeout=30, trust_env=False) as client:
            response = client.post(url, headers={'X-Local-Token': LOCAL_TOKEN}, json={'job_id':job_id})
        if response.status_code != 202:
            raise HTTPException(502, 'Workflow lanjut n8n belum siap. Aktifkan workflow dan periksa credential token.')
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, 'n8n belum terhubung. Jalankan n8n dan aktifkan workflow terlebih dahulu.')


def job_mode_summary(target):
    return read_job(target).get('output_mode')=='summary_only'

@app.post('/api/jobs/{job_id}/output-mode')
def set_output_mode(job_id: str, output_mode: str = Form(...), slide_count: Annotated[int, Form()] = 0):
    if output_mode not in {'summary_only','summary_ppt'}:raise HTTPException(422,'Pilihan keluaran tidak valid.')
    if slide_count!=0 and not 4<=slide_count<=16:raise HTTPException(422,'Jumlah slide tidak valid.')
    target=directory(job_id)
    with LOCK:
        job=read_job(target)
        if job.get('status') in {'running','queued','uploading'}:raise HTTPException(409,'Pekerjaan masih aktif.')
        if job.get('output_mode','summary_ppt')==output_mode and (output_mode=='summary_only' or job.get('slide_count',0)==slide_count):return public_job(target)
        if (target/'report.json').exists() or any(s!='transcribe' for s in job.get('completed_stages',[])):raise HTTPException(409,'Keluaran sudah diproses. Jangan mengubah mode setelah AI berjalan.')
        update_job(target,output_mode=output_mode,slide_count=-1 if output_mode=='summary_only' else slide_count,planning_version=0 if output_mode=='summary_only' else 1)
    return public_job(target)


def n8n_upload_url():
    # n8n-common sets N8N_WEBHOOK_URL to the public base URL. The backend
    # must target the upload webhook, not POST to that base URL.
    from urllib.parse import urlsplit
    explicit=os.getenv('APP_N8N_JOB_URL','').strip()
    if explicit:return explicit
    legacy=os.getenv('N8N_WEBHOOK_URL','http://127.0.0.1:5678').strip().rstrip('/')
    path=urlsplit(legacy).path.rstrip('/')
    if not path:return legacy+'/webhook/diskusi'
    if path=='/webhook':return legacy+'/diskusi'
    return legacy
