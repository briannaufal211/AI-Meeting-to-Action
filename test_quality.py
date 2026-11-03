"""Quality gates tested with simulated models only; no external API access."""
import json
from types import SimpleNamespace
import pytest
import pipeline as p
from schemas import Review, Report, Claim, Slide, QualityRepair


def fixture(tmp_path):
    transcript = {'segments': [
        {'id': 'S00001', 'start': 10, 'end': 14, 'text': 'Dua hari saya mengajar, mohon dikecualikan.'},
        {'id': 'S00002', 'start': 14, 'end': 19, 'text': 'Jadwal konsultasi bisa kita atur lagi, mungkin Senin telepon.'}]}
    facts = [{'id':'F0001', 'text': 'Jadwal perlu diatur.', 'quote':'Jadwal konsultasi bisa kita atur lagi', 'source_ids':['S00002']}]
    report = Report(title='Diskusi', summary=[Claim(text='Jadwal perlu diatur.',fact_ids=['F0001'])], decisions=[], actions=[],
        uncertainties=[], slides=[Slide(title='Jadwal',bullets=[Claim(text='Jadwal perlu diatur.',fact_ids=['F0001'])],notes='Rencana tentatif.')])
    for name, data in [('transcript.json',transcript),('facts.json',facts),('report.json',report.model_dump())]:p.write_json(tmp_path/name,data)
    return transcript, facts, report

class Model:
    def __init__(self, answers, used=0):
        self.answers=iter(answers); self.calls=[]; self.journal=SimpleNamespace(data={'requests':[{} for _ in range(used)]})
    def ask(self,schema,instruction,payload,max_tokens=6000):
        self.calls.append((schema,instruction,payload));self.journal.data['requests'].append({})
        value = next(self.answers)
        if schema is QualityRepair and isinstance(value, Report):
            return QualityRepair(report=value, fact_updates=[], additional_facts=[])
        return value

def run(tmp_path,t,f,r,model):return p.check_and_repair(t,tmp_path,r,f,0,'Laporan',lambda **kw:None,model)

def test_full_context_and_single_repair_then_cached_resume(tmp_path,monkeypatch):
    monkeypatch.setenv('MAX_AI_REVISIONS','1')
    t,f,r=fixture(tmp_path)
    model=Model([Review(passed=False,issues=['Periksa jadwal S00001.']),r,Review(passed=True,issues=[])])
    result,review=run(tmp_path,t,f,r,model)
    assert review.passed and len(model.calls)==3
    assert all(c[2]['transcript']==t['segments'] for c in model.calls)
    assert 'komitmen lain' in model.calls[0][1]
    assert json.loads((tmp_path/'quality.json').read_text())['repair_rounds']==1
    run(tmp_path,t,f,r,model)
    assert len(model.calls)==3
    assert (tmp_path/'quality.md').exists() and (tmp_path/'transcript-checked.txt').exists()

def test_second_failure_stops_and_never_loops(tmp_path,monkeypatch):
    monkeypatch.setenv('MAX_AI_REVISIONS','99')
    t,f,r=fixture(tmp_path);m=Model([Review(passed=False,issues=['S00001 salah tafsir']),r,Review(passed=False,issues=['S00001 tetap belum pasti'])])
    _,review=run(tmp_path,t,f,r,m)
    assert not review.passed and len(m.calls)==3
    assert 'DRAF' in (tmp_path/'quality.md').read_text(encoding='utf-8')

def test_insufficient_budget_never_spends_on_unreviewed_repair(tmp_path,monkeypatch):
    monkeypatch.setenv('MAX_AI_REVISIONS','1');monkeypatch.setenv('MAX_PAID_CALLS_PER_JOB','3')
    t,f,r=fixture(tmp_path);m=Model([Review(passed=False,issues=['Periksa S00001'])],used=1)
    _,review=run(tmp_path,t,f,r,m)
    assert len(m.calls)==1 and not review.passed
    assert any('Batas biaya' in i for i in review.issues)

def test_conflicting_verdict_never_passes(tmp_path):
    t,f,r=fixture(tmp_path);m=Model([Review(passed=True,issues=['Masih ada kesalahan'])])
    _,review=run(tmp_path,t,f,r,m)
    assert not review.passed

def test_post_audit_change_blocks_render_before_node(tmp_path,monkeypatch):
    t,f,r=fixture(tmp_path);run(tmp_path,t,f,r,Model([Review(passed=True,issues=[])]))
    data=json.loads((tmp_path/'report.json').read_text());data['title']='Diubah setelah audit';p.write_json(tmp_path/'report.json',data)
    monkeypatch.setattr(p.subprocess,'run',lambda *a,**kw:pytest.fail('Node should not run'))
    with pytest.raises(ValueError,match='berubah setelah'):p.render_pptx(tmp_path)

def test_confidence_markers_preserve_words_numbers_and_original(tmp_path):
    t,f,r=fixture(tmp_path);t['segments'][0]['avg_logprob']=-1.5
    (tmp_path/'transcript.txt').write_text('Asli: 2 hari.',encoding='utf-8')
    p.write_transcript_quality(t,tmp_path)
    checked=(tmp_path/'transcript-checked.txt').read_text(encoding='utf-8')
    assert 'UCAPAN PERLU KONFIRMASI' in checked and t['segments'][0]['text'] in checked
    assert (tmp_path/'transcript.txt').read_text()=='Asli: 2 hari.'
    assert p.transcript_flags({'segments':[{'id':'S1','text':'Tidak ada skor'}]})==[]

def test_context_includes_adjacent_deadline_even_if_quote_omits_it():
    segments=[{'id':f'S{i}', 'text':text} for i,text in enumerate(['Awal','Pekerjaan GA','Selesai akhir tahun','Lanjutan'])]
    result=p.evidence_context(['S1'],segments)
    assert any('akhir tahun' in x['text'] for x in result)

def test_explicit_quality_workflow_graph_and_no_automatic_network_retries():
    from pathlib import Path
    root=Path(p.__file__).parent
    w=json.loads((root/'n8n-workflow.json').read_text(encoding='utf-8'));n={x['id']:x for x in w['nodes']}
    for stage in p.STAGES:
        assert '/stages/'+stage in n[stage+'-start']['parameters']['url']
    assert w['connections'][n['summarize-done']['name']]['main'][0][0]['node']==n['quality-start']['name']
    assert w['connections'][n['quality-done']['name']]['main'][0][0]['node']==n['output-choice']['name']
    assert not any(node.get('retryOnFail') for node in w['nodes'])


def test_four_stages_persist_quality_and_resume_without_repeating_paid_work(tmp_path,monkeypatch):
    from schemas import Extraction, Fact
    meta={'input_kind':'text','title':'Test','slide_count':1,'extension':'.txt','quality_version':2,'completed_stages':[]}
    p.write_json(tmp_path/'job.json',meta)
    (tmp_path/'input.txt').write_text('Jadwal konsultasi bisa kita atur lagi.',encoding='utf-8')
    t,f,report=fixture(tmp_path)
    # Let the text preparation create the actual one-segment transcript.
    (tmp_path/'transcript.json').unlink()
    (tmp_path/'report.json').unlink()
    (tmp_path/'facts.json').unlink()
    calls=[]
    class FakeAI:
        def __init__(self,output):self.journal=SimpleNamespace(data={'requests':[]})
        def ask(self,schema,instruction,payload,max_tokens=6000):
            calls.append(schema)
            if schema is Extraction:return Extraction(facts=[Fact(text='Jadwal perlu diatur.',quote='Jadwal konsultasi bisa kita atur lagi.',source_ids=['S00001'])])
            if schema is Report:return report
            return Review(passed=True,issues=[])
    monkeypatch.setattr(p,'AI',FakeAI)
    def update(**values):
        meta.update(values);p.write_json(tmp_path/'job.json',meta)
    for stage in ['transcribe','summarize']:p.run_stage(tmp_path,stage,update)
    assert calls==[Extraction,Report] and not (tmp_path/'review.json').exists()
    p.run_stage(tmp_path,'quality',update)
    assert calls==[Extraction,Report,Review]
    p.run_stage(tmp_path,'quality',update)
    assert calls==[Extraction,Report,Review]
    p.run_stage(tmp_path,'render',update)
    assert meta['status']=='completed' and meta['completed_stages']==['transcribe','summarize','quality','render']
    assert (tmp_path/'quality.md').exists() and (tmp_path/'presentation.pptx').exists()
    import zipfile
    with zipfile.ZipFile(tmp_path/'presentation.pptx') as z:
        assert b'DIPERIKSA TERHADAP TRANSKRIP' in z.read('ppt/slides/slide1.xml')


def test_rendered_failed_review_is_visibly_draft(tmp_path):
    import zipfile
    t,f,r=fixture(tmp_path)
    run(tmp_path,t,f,r,Model([Review(passed=False,issues=['S00001 belum jelas'])]))
    p.render_pptx(tmp_path)
    with zipfile.ZipFile(tmp_path/'presentation.pptx') as z:
        assert b'DRAF / PERLU KONFIRMASI' in z.read('ppt/slides/slide1.xml')


def test_quality_endpoint_requires_previous_phase_and_reuses_done_result(tmp_path,monkeypatch):
    import app, queue, uuid
    from fastapi import HTTPException
    monkeypatch.setattr(app,'DATA',tmp_path);monkeypatch.setattr(app,'TASKS',queue.Queue())
    jobid=str(uuid.uuid4());d=tmp_path/jobid;d.mkdir()
    job={'id':jobid,'orchestrator':'n8n','status':'waiting','completed_stages':[]}
    p.write_json(d/'job.json',job)
    with pytest.raises(HTTPException) as e:app.start_stage(jobid,'quality')
    assert e.value.status_code==409 and app.TASKS.empty()
    job['completed_stages']=['transcribe','summarize'];p.write_json(d/'job.json',job)
    (d/'summary.md').write_text('Draf',encoding='utf-8')
    assert app.start_stage(jobid,'quality')['requested_stage']=='quality'
    assert app.TASKS.get_nowait()==(jobid,'quality')
    job.update(status='waiting',completed_stages=['transcribe','summarize','quality'])
    p.write_json(d/'job.json',job);p.write_json(d/'quality-manifest.json',{'version':2})
    app.start_stage(jobid,'quality')
    assert app.TASKS.empty()
