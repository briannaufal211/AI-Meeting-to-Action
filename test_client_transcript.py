import json,re,zipfile,io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import client_transcript as ct
import pipeline as p

def fixture(tmp_path):
    t={'duration_seconds':310,'segments':[
        {'id':'S00001','speaker':'Pembicara 1','start':0,'end':8,'text':'Kita belum menyetujui anggaran Rp800.000. Targetnya mungkin 10%, bukan keputusan.'},
        {'id':'S00002','speaker':'Pembicara 1','start':8,'end':12,'text':'Perlu konfirmasi dahulu.'},
        {'id':'S00003','speaker':'Pembicara 2','start':13,'end':19,'text':'Apakah Senin depan bisa dibahas?'},
        {'id':'S00004','speaker':'Pembicara belum dipastikan','text':'Barangkali, belum pasti.'},
        {'id':'S00005','speaker':'Pembicara 2','start':20,'end':22,'speaker_assignment_inferred':True,'text':'Nama [Dinar?] belum jelas.'},
        {'id':'S00006','speaker':'Pembicara 1','start':300,'end':310,'text':'Pilot perlu ditinjau sebelum diperluas.'}]}
    p.write_json(tmp_path/'transcript.json',t);p.write_json(tmp_path/'job.json',{'title':'CONTOH Diskusi inventaris','filename':'CONTOH-rekaman.mp3'})
    p.write_json(tmp_path/'facts-001.json',{'facts':[],'transcript_sections':[{'title':'Anggaran dan rencana pembahasan','start_source_id':'S00001'},{'title':'Peninjauan pilot','start_source_id':'S00006'}]})
    return t

def test_turns_preserve_every_utterance_and_do_not_guess_unknown_people(tmp_path):
    t=fixture(tmp_path);d=ct.export_client_transcript(tmp_path)
    turns=[x for s in d['sections'] for x in s['turns']]
    assert len(turns)==5 and turns[0]['source_ids']==['S00001','S00002']
    assert turns[2]['speaker']=='PEMBICARA BELUM DIPASTIKAN' and turns[3]['inferred']
    assert ''.join(ct.compact(x['text']) for x in turns)==''.join(ct.compact(x['text']) for x in t['segments'])
    text=(tmp_path/'transcript-client.txt').read_text(encoding='utf-8')
    assert 'DAFTAR ISI' in text and 'Rp800.000' in text and 'bukan keputusan' in text and 'PEMBICARA 2 [?]:' in text
    assert 'PEMBICARA BELUM DIPASTIKAN: Barangkali, belum pasti.' in text
    mapping=json.loads((tmp_path/'transcript-client-map.json').read_text())
    assert mapping['wording_unchanged'] and not mapping['speaker_guesses_added']
    assert [i for turn in mapping['turns'] for i in turn['source_ids']]==[s['id'] for s in t['segments']]

def test_part_timestamps_are_never_presented_as_exact_speech_times(tmp_path):
    t=fixture(tmp_path)
    for s in t['segments']:s['timestamp_precision']='audio_part_range'
    ct.export_client_transcript(tmp_path,t)
    assert '[00:00–00:12 · rentang bagian audio]' in (tmp_path/'transcript-client.txt').read_text(encoding='utf-8')

@pytest.mark.parametrize('passed',[False,True])
def test_summaries_separate_from_speech_and_only_after_review(tmp_path,passed):
    fixture(tmp_path);p.write_json(tmp_path/'review.json',{'passed':passed})
    p.write_json(tmp_path/'facts.json',[{'id':'F1','text':'Anggaran belum disetujui.','source_ids':['S00001']}])
    ct.export_client_transcript(tmp_path)
    text=(tmp_path/'transcript-client.txt').read_text(encoding='utf-8')
    assert ('RINGKASAN BAGIAN — Rangkuman AI, bukan ucapan:' in text)==passed

def test_html_escapes_source_and_preserves_raw_files(tmp_path):
    t=fixture(tmp_path);t['segments'][0]['text']='<script>alert("x")</script> tidak boleh diubah.'
    for name in ['transcript.txt','transcript-checked.txt']: (tmp_path/name).write_bytes(b'original')
    ct.export_client_transcript(tmp_path,t)
    html=(tmp_path/'transcript-client.html').read_text(encoding='utf-8')
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert all((tmp_path/n).read_bytes()==b'original' for n in ['transcript.txt','transcript-checked.txt'])

def test_invalid_section_references_do_not_drop_or_reorder_speech(tmp_path):
    t=fixture(tmp_path);p.write_json(tmp_path/'facts-002.json',{'transcript_sections':[{'title':'Bad','start_source_id':'S99999'},{'title':'Later','start_source_id':'S00006'}]})
    d=ct.export_client_transcript(tmp_path)
    assert len(d['sections'])==2 and 'Bad' not in (tmp_path/'transcript-client.txt').read_text()

def test_long_single_speech_has_readable_paragraphs_without_losing_words(tmp_path):
    t=fixture(tmp_path);t['segments']=t['segments'][:1];t['segments'][0]['text']=' '.join(['Tidak boleh mengubah 10% menjadi 100%.']*90)
    d=ct.export_client_transcript(tmp_path,t);paras=ct.paragraphs(d['sections'][0]['turns'][0]['text'])
    assert len(paras)>5 and max(len(x.split()) for x in paras)<=85
    assert ct.compact(' '.join(paras))==ct.compact(t['segments'][0]['text'])

def test_client_files_download_preview_and_zip_without_running_jobs(tmp_path,monkeypatch):
    import app
    t=fixture(tmp_path);ct.export_client_transcript(tmp_path)
    monkeypatch.setattr(app,'directory',lambda _:tmp_path)
    response=app.download('fixture','transcript-client.html')
    assert response.media_type=='text/html' and 'inline' in response.headers['content-disposition']
    assert "default-src 'none'" in response.headers['content-security-policy']
    with zipfile.ZipFile(io.BytesIO(app.bundle('fixture').body)) as z:
        assert {'transcript-client.txt','transcript-client.html'}.issubset(z.namelist())
    assert 'transcript-client.html' in app.public_job(tmp_path)['files']

def test_preparation_uses_saved_transcript_and_never_calls_ai(tmp_path,monkeypatch):
    fixture(tmp_path);monkeypatch.setattr(p,'AI',lambda *a:pytest.fail('No paid call'))
    p.prepare_transcript(tmp_path,lambda **kw:None)
    assert (tmp_path/'transcript-client.txt').exists()

def test_app_and_n8n_status_both_link_the_new_formats():
    root=Path(p.__file__).parent
    for n in ['index.html','form-status-code.js','n8n-form-workflow.json']:
        s=(root/n).read_text(encoding='utf-8')
        assert 'transcript-client.html' in s and 'transcript-client.txt' in s
