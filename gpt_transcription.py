"""GPT-Transcribe audio uploads, per-part checkpoints and shared paid-call budget."""
import hashlib,json,os,wave
from pathlib import Path
from pydantic import BaseModel,Field
from openai import OpenAI
from cost_control import CallJournal

class AudioText(BaseModel):
    text: str = Field(min_length=1)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def audio_parts(samples,sample_rate=16000):
    """Prefer a quiet boundary near 700s; no overlap or invented word timestamps."""
    import numpy as np
    start=0;maximum=700*sample_rate
    while start<len(samples):
        end=min(start+maximum,len(samples))
        if end<len(samples):
            # A quarter-second quiet window in the final 15 seconds of a part.
            for point in range(end,end-15*sample_rate,-sample_rate//4):
                frame=samples[point-sample_rate//4:point]
                if len(frame) and float(np.sqrt(np.mean(frame.astype('float64')**2)))<.008:
                    end=point;break
        yield start,end
        start=end

def transcribe_gpt(audio,output,update,client=None,samples=None):
    from pipeline import write_json,stamp
    import numpy as np
    output=Path(output);output.mkdir(exist_ok=True,parents=True)
    key=os.getenv('OPENAI_API_KEY','').strip()
    if client is None and not key:raise ValueError('OPENAI_API_KEY belum diisi; audio belum dikirim.')
    model=os.getenv('TRANSCRIPTION_MODEL','gpt-transcribe')
    if model!='gpt-transcribe':raise ValueError('Mode ini memerlukan TRANSCRIPTION_MODEL=gpt-transcribe; tidak mengganti model otomatis.')
    if samples is None:
        from faster_whisper.audio import decode_audio
        samples=decode_audio(str(audio))
    duration=len(samples)/16000
    if duration<.1 or duration>float(os.getenv('MAX_AUDIO_MINUTES','120'))*60:raise ValueError('Durasi audio kosong atau melebihi batas MAX_AUDIO_MINUTES.')
    prompt=os.getenv('TRANSCRIPTION_CONTEXT','Diskusi berbahasa Indonesia. Transkripsikan ucapan sebagaimana terdengar; jangan merangkum atau menambahkan isi.').strip()
    keywords=[v.strip() for v in os.getenv('TRANSCRIPTION_KEYWORDS','').split(',') if v.strip()]
    if len(prompt)>500 or len(keywords)>30 or any(len(k)>100 or any(c in k for c in '<>\r\n') for k in keywords):raise ValueError('Konteks transkripsi maksimal 500 karakter; maksimal 30 istilah pendek tanpa tanda khusus.')
    languages=[v.strip() for v in os.getenv('TRANSCRIPTION_LANGUAGES','id').split(',') if v.strip()]
    if not languages or any(not __import__('re').fullmatch('[a-z]{2,3}',v) for v in languages):raise ValueError('TRANSCRIPTION_LANGUAGES harus kode bahasa, misalnya id atau id,en.')
    config={'version':1,'model':model,'audio_sha256':sha(audio),'prompt':prompt,'keywords':keywords,'languages':languages,'sample_rate':16000}
    manifest=output/'transcription-manifest.json'
    if manifest.exists() and json.loads(manifest.read_text(encoding='utf-8'))['config']!=config:raise ValueError('Sumber atau pengaturan transkripsi berubah. Checkpoint lama tidak digunakan dan tidak ada audio dikirim ulang.')
    parts=list(audio_parts(samples));signatures=[]
    journal=CallJournal(output,model,write_json)
    for i,(start,end) in enumerate(parts):
        signatures.append(journal.signature(AudioText,prompt,{**config,'start_sample':start,'end_sample':end},0))
    for signature in signatures:
        if journal.get(signature,AudioText) is not None:
            for record in journal.data['requests']:
                if record.get('signature')==signature and record.get('status')=='in_flight':journal.finish(record,'completed')
    pending=[i for i,sig in enumerate(signatures) if journal.get(sig,AudioText) is None]
    estimated=duration/60*.0045
    for i in pending:
        if any(r.get('signature')==signatures[i] and r.get('status') in ('in_flight','uncertain','invalid','completed') for r in journal.data['requests']):raise ValueError('Transkripsi sebelumnya belum pasti. Audio tidak dikirim ulang; periksa OpenAI Usage dan cost-control.json.')
    reserve=0
    meta=output/'job.json'
    if meta.exists() and json.loads(meta.read_text(encoding='utf-8')).get('planning_version')==1:reserve=5
    if len(journal.data['requests'])+len(pending)+reserve>int(os.getenv('MAX_PAID_CALLS_PER_JOB','12')):raise ValueError('Batas panggilan API tidak cukup untuk bagian audio dan tahapan berikutnya. Belum ada bagian baru dikirim; gunakan rekaman lebih pendek.')
    if pending and estimated>float(os.getenv('MAX_TRANSCRIPTION_USD_PER_JOB','.60')):raise ValueError('Estimasi transkripsi melebihi MAX_TRANSCRIPTION_USD_PER_JOB. Audio belum dikirim.')
    write_json(manifest,{'config':config,'duration_seconds':duration,'parts':len(parts),'estimated_usd':round(estimated,6),'timestamp_precision':'audio_part_range','accuracy_measured':False})
    client=client or OpenAI(api_key=key,timeout=float(os.getenv('TRANSCRIPTION_TIMEOUT_SECONDS','600')),max_retries=0)
    records=[]
    for i,(start,end) in enumerate(parts):
        parsed=journal.get(signatures[i],AudioText)
        if parsed is None:
            path=output/f'audio-part-{i+1:03}.wav'
            pcm=(np.clip(samples[start:end],-1,1)*32767).astype('<i2')
            with wave.open(str(path),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(pcm.tobytes())
            if path.stat().st_size>=25_000_000:raise ValueError('Bagian audio melebihi batas unggahan API; belum dikirim.')
            update(stage='transcribing',progress=8+int(48*i/len(parts)),message=f'GPT-Transcribe: bagian {i+1}/{len(parts)}. Audio dikirim ke OpenAI.')
            record=journal.begin(signatures[i],AudioText,0)
            record.update(audio_seconds=round((end-start)/16000,3),estimated_usd=round((end-start)/16000/60*.0045,6));write_json(journal.path,journal.data)
            try:
                with path.open('rb') as f:response=client.audio.transcriptions.create(model=model,file=f,prompt=prompt,extra_body={'languages':languages,'keywords':keywords})
            except Exception as error:
                journal.finish(record,'rejected' if getattr(error,'status_code',None) in (400,401,403,404,429) else 'uncertain');raise
            raw=getattr(response,'text',None)
            if not isinstance(raw,str) or not raw.strip():journal.finish(record,'invalid');raise ValueError('API tidak memberikan transkrip lengkap. Tidak diulang otomatis.')
            parsed=AudioText(text=raw.strip());journal.store(signatures[i],parsed);journal.finish(record,'completed',getattr(response,'_request_id',None))
            # Usage is derived from the durable ledger, so a resumed part is never billed twice in the estimate.
        # Range identifies the uploaded part, NOT the exact time of each sentence.
        for paragraph in __import__('re').split(r'\n\s*\n',parsed.text):
            if paragraph.strip():records.append({'id':f'S{len(records)+1:05}','start':round(start/16000,2),'end':round(end/16000,2),'text':paragraph.strip(),'timestamp_precision':'audio_part_range'})
    usage_path=output/'usage.json';usage=json.loads(usage_path.read_text(encoding='utf-8')) if usage_path.exists() else {'input_tokens':0,'output_tokens':0,'calls':0}
    audio_records=[r for r in journal.data['requests'] if r.get('schema')=='AudioText' and r.get('status')=='completed']
    old=usage.get('audio_calls',0);usage['audio_calls']=len(audio_records);usage['calls']+=len(audio_records)-old
    usage['audio_estimated_usd']=round(sum(r['estimated_usd'] for r in audio_records),6);usage['audio_seconds']=round(sum(r['audio_seconds'] for r in audio_records),3)
    usage['estimated_usd']=round(usage.get('text_estimated_usd',0)+usage['audio_estimated_usd'],6)
    usage['estimated_idr']=round(usage['estimated_usd']*float(os.getenv('USD_IDR','17000')))
    usage['estimate_note']='Estimasi durasi audio dan tarif teks; respons hilang dapat menimbulkan biaya belum tercatat. Periksa OpenAI Usage.';write_json(usage_path,usage)
    result={'duration_seconds':duration,'device':'openai-api','model':model,'language':','.join(languages),'provider':'openai','warning':'Rentang waktu menunjukkan bagian audio yang dikirim, bukan waktu presisi tiap ucapan. Akurasi belum diukur terhadap transkrip acuan.','accuracy_measured':False,'segments':records}
    write_json(output/'transcript.json',result)
    (output/'transcript.txt').write_text('GPT-Transcribe. Rentang waktu adalah bagian audio, bukan timestamp presisi ucapan.\n\n'+'\n'.join(f"[{s['id']} {stamp(s['start'])} - {stamp(s['end'])}] {s['text']}" for s in records),encoding='utf-8')
    return result
