"""Readable dialogue from saved transcript. No network and no rewriting of utterances."""
from pathlib import Path
import json,re,html,hashlib,math,textwrap

VERSION=1
def read(folder,name,default):
    path=folder/name
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default
def compact(text):return ''.join(str(text).split())
def seconds(value):
    try:
        result=float(value)
        return result if math.isfinite(result) and result>=0 else None
    except (ValueError,TypeError):return None
def stamp(value):
    if value is None:return 'waktu tidak tersedia'
    value=int(value)
    return f'{value//3600:02}:{value%3600//60:02}:{value%60:02}' if value>=3600 else f'{value//60:02}:{value%60:02}'
def timing(turn):
    start=stamp(turn['start'])
    if turn['precision']=='audio_part_range':return start+'–'+stamp(turn['end'])+' · rentang bagian audio'
    return start
def paragraphs(text,limit=85):
    # Keep every word, punctuation, number and qualification; only whitespace changes.
    parts=re.split(r'(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9“"(\[])',text.strip())
    output=[];buffer=[];size=0
    for part in parts:
        words=part.split()
        if size and size+len(words)>limit:output.append(' '.join(buffer));buffer=[];size=0
        while len(words)>limit:
            if buffer:output.append(' '.join(buffer));buffer=[];size=0
            output.append(' '.join(words[:limit]));words=words[limit:]
        if words:buffer.append(' '.join(words));size+=len(words)
    if buffer:output.append(' '.join(buffer))
    return output
def label(segment):
    original=str(segment.get('speaker') or '').strip()
    if not original or 'belum dipastikan' in original.casefold():return 'PEMBICARA BELUM DIPASTIKAN'
    return original.upper()
def make_turns(segments):
    turns=[]
    for s in segments:
        if not str(s.get('text','')).strip():continue
        name=label(s);inferred=bool(s.get('speaker_assignment_inferred'))
        start=seconds(s.get('start'));end=seconds(s.get('end'))
        precision=s.get('timestamp_precision','model_segment')
        previous=turns[-1] if turns else None
        gap=(start-previous['end']) if previous and start is not None and previous['end'] is not None else None
        can_merge=(previous and name==previous['speaker'] and name!='PEMBICARA BELUM DIPASTIKAN'
            and not inferred and not previous['inferred'] and precision==previous['precision']
            and (gap is None or ((previous['start'] is None or start>=previous['start']) and gap<=3))
            and len(previous['text'].split())+len(s['text'].split())<=350)
        if can_merge:
            previous['text']+=' '+s['text'];previous['source_ids'].append(s['id'])
            if end is not None:previous['end']=max(previous['end'] or end,end)
        else:turns.append({'speaker':name,'inferred':inferred,'start':start,'end':end,'precision':precision,'text':s['text'],'source_ids':[s['id']]})
    return turns
def section_starts(folder,segments):
    positions={s['id']:i for i,s in enumerate(segments)};starts={0:'Pembukaan dan pembahasan awal'}
    for cache in sorted(folder.glob('facts-[0-9][0-9][0-9].json')):
        for guide in read(folder,cache.name,{}).get('transcript_sections',[]):
            index=positions.get(guide.get('start_source_id'))
            title=' '.join(str(guide.get('title','')).split())
            if index is not None and title and len(title)<=110:starts.setdefault(index,title)
            if index==0 and title and len(title)<=110:starts[0]=title
    # Existing cached jobs still get navigation without calling an AI again.
    last=0;characters=0
    for i,s in enumerate(segments):
        if i in starts:last=i;characters=0
        age=None
        if seconds(s.get('start')) is not None and seconds(segments[last].get('start')) is not None:
            age=seconds(s.get('start'))-seconds(segments[last].get('start'))
        if i>last and (characters>=6000 or (age is not None and age>=240 and characters>=1000)):
            starts.setdefault(i,'Pembahasan lanjutan');last=i;characters=0
        characters+=len(s.get('text',''))
    return sorted(starts.items())
def build(folder,transcript=None):
    folder=Path(folder);transcript=transcript or read(folder,'transcript.json',{})
    segments=transcript.get('segments',[])
    if not segments:return None
    meta=read(folder,'job.json',{});review=read(folder,'review.json',{});facts=read(folder,'facts.json',[])
    flags={f['source_id']:f.get('reasons',[]) for f in read(folder,'transcript-quality.json',{}).get('flags',[])}
    starts=section_starts(folder,segments);sections=[]
    for n,(start,title) in enumerate(starts):
        stop=starts[n+1][0] if n+1<len(starts) else len(segments);source=segments[start:stop]
        turns=make_turns(source);ids={s['id'] for s in source}
        for turn in turns:turn['warnings']=sorted({reason for sid in turn['source_ids'] for reason in flags.get(sid,[]) if 'atribusi pembicara' not in reason})
        summaries=[f for f in facts if f.get('text') and f.get('source_ids') and set(f['source_ids']).issubset(ids)][:3] if review.get('passed') is True else []
        if not turns:continue
        sections.append({'title':title,'turns':turns,'summaries':summaries,'source_ids':[s['id'] for s in source]})
    utterances=''.join(compact(t['text']) for section in sections for t in section['turns'])
    original=''.join(compact(s.get('text','')) for s in segments)
    if utterances!=original:raise ValueError('Versi baca mengubah urutan/isi ucapan; ekspor dihentikan.')
    return {'version':VERSION,'title':meta.get('title','Transkrip diskusi'),'source':meta.get('filename','transcript.json'),
        'duration':seconds(transcript.get('duration_seconds')),'sections':sections,
        'wording_unchanged':True,'speaker_guesses_added':False,
        'dialogue_sha256':hashlib.sha256(original.encode()).hexdigest(),
        'source_sha256':hashlib.sha256(json.dumps(segments,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
def export_client_transcript(folder,transcript=None):
    folder=Path(folder);data=build(folder,transcript)
    if data is None:return None
    rule='='*78
    guide=[
        'Setiap giliran bicara memiliki label pembicara dan satu penanda waktu bila tersedia.',
        'Ucapan yang berurutan dari pembicara sama digabung bila atribusinya tidak ditandai sebagai dugaan.',
        'Nama pembicara hanya ditampilkan bila tersedia pada sumber. Label suara bukan identitas nyata.',
        '[?] menandai atribusi pembicara yang masih perlu dikonfirmasi; pembicara tidak ditebak dari konteks.',
        '[*] menandai indikator ucapan yang perlu konfirmasi; alasannya ada setelah giliran terkait.',
        'Waktu mengikuti segmen sumber. Rentang bagian audio bukan waktu presisi kalimat.',
        'Kata, angka, negasi, syarat dan urutan ucapan dipertahankan. Paragraf dan tata letak dirapikan.',
        'Judul bagian merupakan panduan penyusun. RINGKASAN BAGIAN adalah rangkuman AI, bukan ucapan.',
        'Ringkasan bagian hanya ditampilkan setelah audit laporan lolos. Teks sumber tetap menjadi acuan.',
        'Penanda ketidakjelasan yang sudah ada pada sumber dipertahankan; akurasi terhadap audio tidak dijamin oleh perapian format.']
    lines=[rule,'TRANSKRIP RAPAT VERSI MUDAH DIBACA',rule,data['title'],
        'Sumber : '+data['source'],'Durasi : '+stamp(data['duration']),
        'Status : Versi baca dari transkripsi otomatis. Identitas dan ucapan yang belum pasti perlu konfirmasi.',
        '', 'CARA MEMBACA',*['- '+v for v in guide],'','DAFTAR ISI']
    esc=lambda x:html.escape(str(x),quote=True)
    fragments=['<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Transkrip mudah dibaca</title><style>body{font:18px/1.75 Georgia,serif;color:#24343b;background:#fff;max-width:850px;margin:40px auto;padding:0 24px}h1,h2,h3,nav,header,small{font-family:Arial,sans-serif}h1{font-size:30px;line-height:1.25}h2{font-size:23px;color:#0f3b4c;margin-top:44px;line-height:1.4}h3{font-size:15px;color:#1b6570;margin:22px 0 8px}p{margin:8px 0 16px}small{font-size:13px;color:#60717a}a{color:#176579}header p,li{font-size:15px}aside{border-top:1px solid #d3dde0;margin-top:24px;font-size:16px}article{break-inside:auto}article h3{break-after:avoid}p{orphans:3;widows:3}@media print{body{font-size:11pt;margin:0;max-width:none}nav{break-after:page}h2{break-after:avoid}}</style></head><body>',
        '<header><h1>Transkrip rapat versi mudah dibaca</h1><p>'+esc(data['title'])+'</p><p>Sumber: '+esc(data['source'])+'<br>Durasi: '+esc(stamp(data['duration']))+'</p><p>Versi baca dari transkripsi otomatis. Identitas dan ucapan yang belum pasti perlu konfirmasi.</p><details><summary>Cara membaca dan arti penanda</summary><ul>'+''.join('<li>'+esc(v)+'</li>' for v in guide)+'</ul></details></header><nav><h2>Daftar isi</h2><ol>']
    mapping=[]
    for i,section in enumerate(data['sections'],1):
        first=section['turns'][0];when=timing(first)
        lines.append(f"{i:2}. {section['title']} — {when}")
        fragments.append(f'<li><a href="#bagian-{i}">{esc(section["title"])} — {esc(when)}</a></li>')
    fragments.append('</ol></nav>')
    for i,section in enumerate(data['sections'],1):
        lines+=['',rule,f"{i}. {section['title'].upper()} ({timing(section['turns'][0])})",rule,'']
        fragments.append(f'<section id="bagian-{i}"><h2>{i}. {esc(section["title"])}</h2>')
        for turn in section['turns']:
            # A tiny unassigned fragment remains separate, without a large heading
            # that visually interrupts the exchange or attributes it to a neighbour.
            if turn['speaker']=='PEMBICARA BELUM DIPASTIKAN' and len(turn['text'].split())<=16 and not turn['warnings']:
                prefix=(f'[{timing(turn)}] ' if turn['start'] is not None else '')+'PEMBICARA BELUM DIPASTIKAN: '
                lines+=[prefix+' '.join(turn['text'].split()),'']
                fragments.append('<p><small>'+esc(prefix)+'</small>'+esc(' '.join(turn['text'].split()))+'</p>')
                mapping.append({k:v for k,v in turn.items() if k!='text'})
                continue
            marker=(' [?]' if turn['inferred'] else '')+(' [*]' if turn['warnings'] else '')
            heading=(f"[{timing(turn)}] " if turn['start'] is not None else '')+f"{turn['speaker']}{marker}:"
            lines.append(heading);fragments.append('<article><h3>'+esc(heading)+'</h3>')
            for paragraph in paragraphs(turn['text']):
                lines += [textwrap.fill(paragraph,width=88,break_long_words=False,break_on_hyphens=False),'']
                fragments.append('<p>'+esc(paragraph)+'</p>')
            if turn['warnings']:
                note='Catatan sumber [*]: '+'; '.join(turn['warnings'])
                lines+=[note,''];fragments.append('<p><small>'+esc(note)+'</small></p>')
            fragments.append('</article>')
            mapping.append({k:v for k,v in turn.items() if k!='text'})
        if section['summaries']:
            lines+=['RINGKASAN BAGIAN — Rangkuman AI, bukan ucapan:']
            fragments.append('<aside><strong>Ringkasan bagian</strong><p><small>Rangkuman AI, bukan ucapan.</small></p><ul>')
            for f in section['summaries']:
                lines+=['- '+f['text']];fragments.append('<li>'+esc(f['text'])+'</li>')
            lines.append('');fragments.append('</ul></aside>')
        fragments.append('</section>')
    fragments.append('</body></html>')
    for name,value in [('transcript-client.txt','\n'.join(lines)+'\n'),('transcript-client.html',''.join(fragments)),
        ('transcript-client-map.json',json.dumps({k:v for k,v in data.items() if k!='sections'}|{'turns':mapping,'sections':[{'title':s['title'],'source_ids':s['source_ids'],'summary_fact_ids':[f['id'] for f in s['summaries']]} for s in data['sections']]},ensure_ascii=False,indent=2))]:
        target=folder/name;temp=target.with_suffix(target.suffix+'.tmp');temp.write_text(value,encoding='utf-8');temp.replace(target)
    return data
