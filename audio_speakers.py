"""Audio-only transcription plus voice evidence. Text alignment never rewrites primary words."""
from pathlib import Path
import os,json,re,hashlib,difflib,wave
from pydantic import BaseModel,Field
from openai import OpenAI
from cost_control import CallJournal

class AudioResult(BaseModel):
 text:str
 segments:list[dict]=Field(default_factory=list)

def hashfile(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

def compress_audio(source,target):
 import av,numpy as np
 from fractions import Fraction
 from faster_whisper.audio import decode_audio
 proof=target.with_suffix('.source.json');source_hash=hashfile(source)
 if proof.exists() and json.loads(proof.read_text(encoding='utf-8'))['source_sha256']!=source_hash:raise ValueError('Sumber berubah; audio kompresi lama tidak digunakan.')
 if target.exists() and not proof.exists():raise ValueError('Bukti sumber audio kompresi tidak ada; tidak mengirim berkas yang belum terverifikasi.')
 samples=decode_audio(str(source));duration=len(samples)/16000
 if not target.exists():
  with av.open(str(target),'w',format='mp3') as container:
   stream=container.add_stream('libmp3lame',rate=16000);stream.bit_rate=64000;stream.layout='mono'
   for offset in range(0,len(samples),1152):
    frame=av.AudioFrame.from_ndarray(samples[offset:offset+1152].reshape(1,-1).astype('float32'),format='fltp',layout='mono');frame.sample_rate=16000;frame.pts=offset;frame.time_base=Fraction(1,16000)
    for packet in stream.encode(frame):container.mux(packet)
   for packet in stream.encode(None):container.mux(packet)
 proof.write_text(json.dumps({'source_sha256':source_hash,'duration_seconds':duration}),encoding='utf-8')
 if target.stat().st_size>=25_000_000:raise ValueError('Audio versi dua proses melebihi 25 MB. Tidak ada panggilan API; perlu pembagian dengan referensi suara lintas bagian.')
 return duration

def align_speakers(primary,segments):
 words=re.findall(r'\S+',primary);other=[];owners=[]
 for index,seg in enumerate(segments):
  for word in re.findall(r'\S+',seg.get('text','')):other.append(word);owners.append(index)
 if not other:raise ValueError('Tidak ada bukti pembicara dari audio.')
 norm=lambda w:re.sub(r'[^\w]','',w.casefold())
 matcher=difflib.SequenceMatcher(None,[norm(w) for w in words],[norm(w) for w in other],autojunk=False)
 mapping={};differences=[]
 for tag,a,b,c,d in matcher.get_opcodes():
  if tag=='equal':
   for x,y in zip(range(a,b),range(c,d)):mapping[x]=owners[y]
  else:differences.append({'type':tag,'primary_start_word':a,'primary_end_word':b,'primary':' '.join(words[a:b]),'voice_engine':' '.join(other[c:d]),'voice_segment_ids':sorted(set(owners[c:d]))})
 if not mapping:raise ValueError('Teks dan bukti suara tidak cukup selaras. Tidak menebak pembicara.')
 assignments={};inferred=set()
 anchors=sorted(mapping)
 import bisect
 for i in range(len(words)):
  if i in mapping:assignments[i]=mapping[i];continue
  n=bisect.bisect_left(anchors,i);left=mapping[anchors[n-1]] if n else None;right=mapping[anchors[n]] if n<len(anchors) else None
  # Fill only within the same source voice segment, or a small edge attached to it.
  if left is not None and right is not None and (left==right or segments[left].get('speaker')==segments[right].get('speaker')):assignments[i]=left
  elif left is None and n<len(anchors) and anchors[n]-i<=5:assignments[i]=right
  elif right is None and i-anchors[n-1]<=5:assignments[i]=left
  else:assignments[i]=None
  inferred.add(i)
 labels={};result=[];current=[];indexes=[];current_owner=object()
 def flush():
  if not current:return
  owner=indexes[0][1];seg=segments[owner] if owner is not None else None
  raw=seg.get('speaker') if seg else None
  if raw is not None and raw not in labels:labels[raw]='Pembicara '+str(len(labels)+1)
  item={'id':f'S{len(result)+1:05}','speaker':labels.get(raw,'Pembicara belum dipastikan'),'text':' '.join(current),'speaker_assignment_inferred':any(i in inferred for i,_ in indexes),'timestamp_precision':'speaker_segment_range'}
  if seg:item.update(start=float(seg['start']),end=float(seg['end']))
  result.append(item)
 for i,word in enumerate(words):
  owner=assignments[i]
  if current and (owner!=current_owner or (len(current)>=70 and re.search(r'[.!?][\"\u201d\)]?$',current[-1])) or len(current)>=130):flush();current=[];indexes=[]
  current.append(word);indexes.append((i,owner));current_owner=owner
 flush()
 assert re.findall(r'\S+',' '.join(s['text'] for s in result))==words
 return result,{'word_sequence_preserved':True,'primary_words':len(words),'aligned_words':len(mapping),'speaker_inferred_words':len(inferred),'speaker_unknown_words':sum(assignments[i] is None for i in assignments),'labels_not_person_identity':True,'accuracy_measured':False,'differences_not_ground_truth':differences}


def merge_turns(records):
 merged=[]
 for record in records:
  if merged and merged[-1]['speaker']==record['speaker'] and len(merged[-1]['text'].split())+len(record['text'].split())<=100:
   last=merged[-1];last['text']+=' '+record['text'];last['speaker_assignment_inferred']|=record['speaker_assignment_inferred'];last['source_turn_ids'].append(record['id'])
   if 'end' in last and 'end' in record:last['end']=max(last['end'],record['end'])
  else:merged.append({**record,'source_turn_ids':[record['id']]})
 for i,record in enumerate(merged):record['id']=f'S{i+1:05}'
 assert ' '.join(r['text'] for r in merged)==' '.join(r['text'] for r in records)
 return merged


def transcribe_with_speakers(audio,output,update,client=None):
 from pipeline import write_json,stamp
 output=Path(output);output.mkdir(parents=True,exist_ok=True)
 duration=compress_audio(audio,output/'audio-upload.mp3')
 if duration<.1 or duration>float(os.getenv('MAX_AUDIO_MINUTES','120'))*60:raise ValueError('Durasi audio tidak sesuai batas.')
 context=os.getenv('TRANSCRIPTION_CONTEXT','Diskusi bisnis berbahasa Indonesia bercampur istilah Inggris. Pertahankan istilah sebagaimana diucapkan, gunakan tanda baca, jangan merangkum.')
 languages=[x.strip() for x in os.getenv('TRANSCRIPTION_LANGUAGES','id,en').split(',') if x.strip()]
 common={'source_sha256':hashfile(audio),'upload_sha256':hashfile(output/'audio-upload.mp3'),'context':context,'languages':languages}
 models=[('gpt-transcribe','primary',.0045),('gpt-4o-transcribe-diarize','voice',.006)]
 journals=[CallJournal(output,m,write_json) for m,_,_ in models]
 sigs=[j.signature(AudioResult,context,common,0) for j in journals]
 from transcript_reuse import reuse_speaker_transcript
 reused=reuse_speaker_transcript(output,sigs,write_json)
 if reused is not None:
  update(stage='transcribing',progress=58,message='Memakai transkrip tersimpan dari audio identik; tidak mengirim audio atau memakai API transkripsi lagi.')
  if not (output/'usage.json').exists():
   write_json(output/'usage.json',{'model':os.getenv('OPENAI_MODEL','gpt-6-luna'),'calls':0,'audio_calls':0,'input_tokens':0,'output_tokens':0,'audio_estimated_usd':0,'estimated_usd':0,'estimated_idr':0,'transcription_reused':True})
  return reused
 if duration/60*.0105>float(os.getenv('MAX_TRANSCRIPTION_USD_PER_JOB','.60')):raise ValueError('Estimasi dua proses audio melebihi batas biaya; belum dikirim.')
 pending=sum(j.get(sig,AudioResult) is None for j,sig in zip(journals,sigs))
 if journals[1].get(sigs[1],AudioResult) is None:pending+=max(0,__import__('math').ceil(duration/1000)-1)
 meta=json.loads((output/'job.json').read_text(encoding='utf-8')) if (output/'job.json').exists() else {}
 reserve=5 if meta.get('planning_version')==1 else 0
 if len(journals[0].data['requests'])+pending+reserve>int(os.getenv('MAX_PAID_CALLS_PER_JOB','12')):raise ValueError('Batas panggilan tidak cukup untuk dua proses audio dan tahapan berikutnya.')
 if os.getenv('WORKFLOW_CACHE_ONLY')=='1':raise ValueError('Pemulihan tanpa biaya: audio tidak dikirim ke API.')
 client=client or OpenAI(api_key=os.getenv('OPENAI_API_KEY'),max_retries=0,timeout=600)
 responses=[]
 for i,((model,name,rate),signature) in enumerate(zip(models,sigs)):
  journal=CallJournal(output,model,write_json);cached=journal.get(signature,AudioResult)
  if cached is None:
   # A completed request whose cached file was removed is not automatically repeated.
   if any(r.get('signature')==signature and r.get('status')!='rejected' for r in journal.data['requests']):raise ValueError('Hasil permintaan audio sebelumnya belum tersedia dengan pasti. Tidak diulang otomatis.')
   update(stage='transcribing',progress=10+25*i,message=('Mentranskripsi kata dan tanda baca' if i==0 else 'Mengenali suara pembicara dari audio'))
   if i==1:
    cached=diarize_parts(audio,output,client,update,duration)
    journal=CallJournal(output,model,write_json);journal.store(signature,cached)
    responses.append(cached)
    continue
   record=journal.begin(signature,AudioResult,0);record.update(audio_seconds=duration,estimated_usd=round(duration/60*rate,6));write_json(journal.path,journal.data)
   params={'model':model,'prompt':context,'extra_body':{'languages':languages}} if i==0 else {'model':model,'response_format':'diarized_json','chunking_strategy':'auto'}
   try:
    with (output/'audio-upload.mp3').open('rb') as f:r=client.audio.transcriptions.create(file=f,**params)
   except Exception as error:
    journal.finish(record,'rejected' if getattr(error,'status_code',None) in [400,401,403,404,429] else 'uncertain');raise
   data=r.model_dump(mode='json');write_json(output/(name+'-response.json'),data)
   if not data.get('text') or (i==1 and not data.get('segments')):journal.finish(record,'invalid');raise ValueError('Respons audio belum lengkap. Tidak diulang otomatis.')
   cached=AudioResult.model_validate(data);journal.store(signature,cached);journal.finish(record,'completed')
  responses.append(cached)
  # Durable combined estimate includes successful audio requests only; unknown charges stay in ledger.
  ledger=CallJournal(output,model,write_json).data
  usage_path=output/'usage.json';usage=json.loads(usage_path.read_text(encoding='utf-8')) if usage_path.exists() else {'input_tokens':0,'output_tokens':0,'calls':0}
  audio_records=[r for r in ledger['requests'] if r.get('schema') in ('AudioResult','AudioText') and r.get('status')=='completed']
  before=usage.get('audio_calls',0);usage['audio_calls']=len(audio_records);usage['calls']+=len(audio_records)-before
  usage['audio_estimated_usd']=round(sum(r['estimated_usd'] for r in audio_records),6);usage['estimated_usd']=round(usage.get('text_estimated_usd',0)+usage['audio_estimated_usd'],6);usage['estimated_idr']=round(usage['estimated_usd']*float(os.getenv('USD_IDR','17000')));write_json(usage_path,usage)
 ledger=CallJournal(output,'gpt-transcribe',write_json).data
 usage=json.loads((output/'usage.json').read_text(encoding='utf-8'))
 paid=[r for r in ledger['requests'] if r.get('schema')=='AudioResult' and r.get('status')=='completed']
 usage.update(audio_calls=len(paid),calls=len(paid),audio_estimated_usd=round(sum(r['estimated_usd'] for r in paid),6))
 usage['estimated_usd']=round(usage.get('text_estimated_usd',0)+usage['audio_estimated_usd'],6);usage['estimated_idr']=round(usage['estimated_usd']*float(os.getenv('USD_IDR','17000')));write_json(output/'usage.json',usage)
 voice=responses[1].segments;write_json(output/'voice-evidence.json',responses[1].model_dump())
 if max(float(s['end']) for s in voice)<duration-max(30,duration*.02):raise ValueError('Bukti pembicara belum mencakup akhir rekaman; hasil sementara disimpan, tidak disebut transkrip lengkap.')
 records,audit=align_speakers(responses[0].text,voice);audit['raw_turn_count']=len(records);records=merge_turns(records);write_json(output/'transcription-alignment.json',audit)
 result={'duration_seconds':duration,'device':'openai-api','provider':'openai','model':'gpt-transcribe','speaker_model':'gpt-4o-transcribe-diarize','language':','.join(languages),'accuracy_measured':False,'timestamp_precision':'speaker_segment_range','warning':'Label suara bukan identitas nyata. Waktu menunjukkan rentang segmen suara. Perbedaan antarmesin tersedia dalam catatan; akurasi kata belum diukur terhadap acuan.','segments':records}
 write_json(output/'transcript.json',result)
 lines=['TRANSKRIP DENGAN LABEL SUARA','Kata: GPT-Transcribe. Suara: model diarization. Atribusi dan kata tetap perlu validasi; bukan jaminan akurasi 100%.','']
 for s in records:
  timing=f"[{stamp(s['start'])}–{stamp(s['end'])}]" if 'start' in s else '[waktu belum dipastikan]'
  lines += [f"{s['speaker']} {timing} | {s['id']}"+(' [atribusi perlu diperiksa]' if s['speaker_assignment_inferred'] else ''),s['text'],'']
 (output/'transcript.txt').write_text('\n'.join(lines),encoding='utf-8')
 return result


def diarize_parts(audio,output,client,update,duration):
 from pipeline import write_json
 from faster_whisper.audio import decode_audio
 import numpy as np,base64,io
 samples=decode_audio(str(audio));all_segments=[];refs={};total_parts=(len(samples)+16000000-1)//16000000
 for part,start in enumerate(range(0,len(samples),16000000)):
  stop=min(start+16000000,len(samples));offset=start/16000
  wav=output/f'voice-{part+1:03}.wav'
  if not wav.exists():
   with wave.open(str(wav),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes((np.clip(samples[start:stop],-1,1)*32767).astype('<i2').tobytes())
  mp3=wav.with_suffix('.mp3');compress_audio(wav,mp3)
  journal=CallJournal(output,'gpt-4o-transcribe-diarize',write_json)
  signature=journal.signature(AudioResult,'voice-parts-v1',{'sha':hashfile(mp3),'references':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in refs.items()}},0)
  cached=journal.get(signature,AudioResult)
  if cached is None:
   if any(r.get('signature')==signature and r.get('status')!='rejected' for r in journal.data['requests']):raise ValueError('Bagian suara sebelumnya belum pasti; tidak diulang.')
   record=journal.begin(signature,AudioResult,0);record.update(audio_seconds=(stop-start)/16000,estimated_usd=round((stop-start)/16000/60*.006,6));write_json(journal.path,journal.data)
   update(message=f'Mengenali pembicara: bagian {part+1}/{total_parts}')
   params={'model':'gpt-4o-transcribe-diarize','response_format':'diarized_json','chunking_strategy':'auto'}
   if refs:params['extra_body']={'known_speaker_names':list(refs),'known_speaker_references':list(refs.values())}
   try:
    with mp3.open('rb') as f:r=client.audio.transcriptions.create(file=f,**params)
   except Exception as error:
    journal.finish(record,'rejected' if getattr(error,'status_code',None) in [400,401,403,404,429] else 'uncertain')
    write_json(output/f'voice-error-{part+1}.json',{'http':getattr(error,'status_code',None),'body':getattr(error,'body',None)})
    raise
   data=r.model_dump(mode='json');write_json(output/f'voice-response-{part+1}.json',data)
   if not data.get('segments'):journal.finish(record,'invalid');raise ValueError('Respons pembicara kosong.')
   cached=AudioResult.model_validate(data);journal.store(signature,cached);journal.finish(record,'completed')
  if max(float(x['end']) for x in cached.segments)<(stop-start)/16000-30:raise ValueError('Bagian pembicara terpotong; tidak disebut lengkap.')
  local={}
  if part==0:
   candidates={}
   for seg in cached.segments:
    speaker=seg.get('speaker');length=float(seg['end'])-float(seg['start'])
    if speaker is not None and 2<=length and (speaker not in candidates or length>float(candidates[speaker]['end'])-float(candidates[speaker]['start'])):candidates[speaker]=seg
   for speaker,seg in list(candidates.items())[:4]:
    label=f'voice_{len(refs)+1}';local[speaker]=label
    a=int((float(seg['start'])+.2)*16000);b=min(int(float(seg['end'])*16000),a+5*16000)
    memory=io.BytesIO()
    with wave.open(memory,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes((np.clip(samples[a:b],-1,1)*32767).astype('<i2').tobytes())
    refs[label]='data:audio/wav;base64,'+base64.b64encode(memory.getvalue()).decode()
  for seg in cached.segments:
   speaker=seg.get('speaker');label=local.get(speaker,speaker if speaker in refs else f'part{part+1}_{speaker}')
   all_segments.append({**seg,'speaker':label,'start':float(seg['start'])+offset,'end':float(seg['end'])+offset})
 return AudioResult(text=' '.join(s['text'] for s in all_segments),segments=all_segments)
