import json
import os
import time
import zipfile
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
import app as app_module
from schemas import Fact, Claim, Slide, Report, Review, QualityRepair
from pipeline import chunks, validate_facts, validate_report, render_pptx, summary_markdown, write_json, run_job

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, 'DATA', tmp_path)
    # Worker is tested separately: control scheduling in endpoint tests.
    with patch.object(app_module, 'worker', lambda: None):
        with TestClient(app_module.app) as c:
            yield c
    while not app_module.TASKS.empty():
        app_module.TASKS.get_nowait()
        app_module.TASKS.task_done()

@pytest.fixture
def headers():
    return {'X-Local-Token': app_module.LOCAL_TOKEN}

def test_upload_security_limits_and_no_source_filename_traversal(client, headers, tmp_path, monkeypatch):
    assert client.post('/api/jobs', files={'file': ('a.txt', b'ok')}).status_code == 403
    assert client.post('/api/jobs', headers=headers, files={'file': ('a.exe', b'ok')}).status_code == 415
    assert client.post('/api/jobs', headers=headers, files={'file': ('a.txt', b'')}).status_code == 422
    assert client.post('/api/jobs', headers=headers, files={'file': ('a.txt', b'\xff\xfe')}).status_code == 422
    assert client.post('/api/jobs', headers=headers, files={'file': ('a.txt', b'text')}, data={'slide_count':30}).status_code == 422
    r = client.post('/api/jobs', headers=headers, files={'file': ('../../source.txt', b'Rapat membahas biaya.')})
    assert r.status_code == 202
    assert (tmp_path / r.json()['id'] / 'input.txt').is_file()
    assert not (tmp_path / 'source.txt').exists()
    assert client.get('/api/jobs/not-a-uuid').status_code == 404
    monkeypatch.setenv('MAX_UPLOAD_MB', '0')
    assert client.post('/api/jobs', headers=headers, files={'file':('b.txt', b'x')}).status_code == 413

def test_retry_download_and_bundle(client, headers, tmp_path):
    r = client.post('/api/jobs', headers=headers, files={'file': ('a.txt', b'Isi rapat.')})
    job_id = r.json()['id']
    assert client.post(f'/api/jobs/{job_id}/retry', headers=headers).status_code == 409
    target = tmp_path / job_id
    app_module.update_job(target, status='failed')
    assert client.post(f'/api/jobs/{job_id}/retry', headers=headers).status_code == 202
    (target/'transcript.txt').write_text('hasil',encoding='utf-8')
    (target/'input-secret.txt').write_text('private',encoding='utf-8')
    assert client.get(f'/api/jobs/{job_id}/files/transcript.txt').text == 'hasil'
    assert client.get(f'/api/jobs/{job_id}/files/input-secret.txt').status_code == 404
    import io
    archive=zipfile.ZipFile(io.BytesIO(client.get(f'/api/jobs/{job_id}/bundle').content))
    assert archive.namelist() == ['transcript.txt']

def test_queue_limit(client, headers):
    for i in range(5):
        assert client.post('/api/jobs',headers=headers,files={'file':('a.txt',b'text')}).status_code == 202
    assert client.post('/api/jobs',headers=headers,files={'file':('a.txt',b'text')}).status_code == 429

def test_fact_quotes_and_report_references():
    source=[{'id':'S00001','text':'Anggaran yang disepakati Rp2 juta.'}]
    validate_facts([Fact(text='Anggaran Rp2 juta',quote='Rp2 juta.',source_ids=['S00001'])],source)
    with pytest.raises(ValueError):
        validate_facts([Fact(text='Anggaran',quote='Rp9 juta',source_ids=['S00001'])],source)
    with pytest.raises(ValueError):
        validate_facts([Fact(text='Anggaran',quote='Rp2 juta',source_ids=['S00999'])],source)
    report=sample_report()
    validate_report(report,[{'id':'F0001'}])
    report.summary[0].fact_ids=['F9999']
    with pytest.raises(ValueError): validate_report(report,[{'id':'F0001'}])

def test_chunking_keeps_order_and_every_segment():
    source=[{'id':str(i),'text':'kata '*40} for i in range(25)]
    groups=chunks(source,limit=500)
    assert len(groups)>1
    assert [s for g in groups for s in g] == source

def sample_report():
    return Report(title='Contoh diskusi proyek',summary=[Claim(text='Tim menyepakati uji coba.',fact_ids=['F0001'])],
        decisions=[],actions=[],uncertainties=['Nama penanggung jawab belum disebutkan.'],
        slides=[Slide(title='Keputusan rapat',bullets=[Claim(text='Tim menyepakati uji coba.',fact_ids=['F0001'])],notes='Contoh sintetis untuk pengujian.')])

def test_real_pptx_render_and_long_text_pagination(tmp_path):
    report=sample_report()
    report.slides.append(Slide(title='Materi panjang',bullets=[Claim(text=('Penjelasan diskusi dengan rincian yang perlu dibaca. '*20)[:1100],fact_ids=['F0001']) for _ in range(6)],notes='Contoh panjang.'))
    write_json(tmp_path/'report.json',report.model_dump())
    render_pptx(tmp_path)
    with zipfile.ZipFile(tmp_path/'presentation.pptx') as z:
        slides=[n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
        assert len(slides)>2
        assert b'F0001' in z.read(slides[0])
        assert any(n.startswith('ppt/notesSlides/notesSlide') for n in z.namelist())

def test_review_failure_visible_in_summary():
    text=summary_markdown(sample_report(),[{'id':'F0001','source_ids':['S00001'],'quote':'Uji coba.'}],Review(passed=False,issues=['Periksa keputusan.']))
    assert 'belum lolos' in text and 'S00001' in text

def test_resume_render_without_api(tmp_path,monkeypatch):
    report=sample_report()
    write_json(tmp_path/'job.json',{'input_kind':'text','title':'Test','slide_count':4,'extension':'.txt'})
    write_json(tmp_path/'transcript.json',{'device':'text','duration_seconds':None,'segments':[{'id':'S00001','text':'Uji coba.'}]})
    write_json(tmp_path/'report.json',report.model_dump())
    write_json(tmp_path/'facts.json',[{'id':'F0001','source_ids':['S00001'],'quote':'Uji coba.'}])
    write_json(tmp_path/'review.json',{'passed':True,'issues':[]})
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    updates=[]
    run_job(tmp_path,lambda **kw: updates.append(kw))
    assert updates[-1]['status']=='completed'
    assert (tmp_path/'presentation.pptx').exists()

def test_full_text_pipeline_with_real_sdk_mock_transport(tmp_path,monkeypatch):
    import httpx
    import pipeline
    from openai import OpenAI as SDK
    from schemas import Extraction, Fact, QualityRepair
    calls=[]
    extraction=Extraction(facts=[Fact(text='Tim menyepakati uji coba.',quote='Tim menyepakati uji coba.',source_ids=['S00001'])])
    report=sample_report()
    # Minimal fixture requests one slide directly; UI has its own 4-16 input constraint.
    replies=[extraction,report,Review(passed=True,issues=[])]
    def handler(request):
        body=json.loads(request.content)
        calls.append(body)
        result=replies[len(calls)-1]
        return httpx.Response(200,json={
            'id':f'resp_{len(calls)}','object':'response','created_at':1,'status':'completed',
            'model':'gpt-4.1-mini','output':[{'type':'message','id':'msg_test','role':'assistant',
                'status':'completed','content':[{'type':'output_text','text':result.model_dump_json(),'annotations':[]}]}],
            'usage':{'input_tokens':100,'output_tokens':50,'total_tokens':150}})
    monkeypatch.setenv('OPENAI_API_KEY','test-only-no-real-key')
    monkeypatch.setattr(pipeline,'OpenAI',lambda **kw: SDK(api_key='test-only-no-real-key',http_client=httpx.Client(transport=httpx.MockTransport(handler))))
    write_json(tmp_path/'job.json',{'input_kind':'text','title':'Test','slide_count':1,'extension':'.txt'})
    (tmp_path/'input.txt').write_text('Tim menyepakati uji coba.',encoding='utf-8')
    updates=[]
    run_job(tmp_path,lambda **kw:updates.append(kw))
    assert updates[-1]['status']=='completed'
    assert len(calls)==3 and all(c['store'] is False for c in calls)
    assert all(c['text']['format']['type']=='json_schema' for c in calls)
    assert json.loads((tmp_path/'usage.json').read_text())['input_tokens']==300
    assert (tmp_path/'summary.md').is_file() and (tmp_path/'presentation.pptx').is_file()


def test_failed_ai_review_gets_one_revision_then_needs_review(tmp_path,monkeypatch):
    import pipeline
    from schemas import Extraction, Fact
    calls=[]
    monkeypatch.setenv('MAX_AI_REVISIONS','1')
    report=sample_report()
    answers=[Extraction(facts=[Fact(text='Tim menyepakati uji coba.',quote='Tim menyepakati uji coba.',source_ids=['S00001'])]),
        report,Review(passed=False,issues=['Periksa hasil.']),QualityRepair(report=report,fact_updates=[],additional_facts=[]),Review(passed=False,issues=['Masih perlu pemeriksaan.'])]
    def ask(self,schema,instruction,payload,max_tokens=6000):
        calls.append(schema)
        return answers[len(calls)-1]
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    monkeypatch.setattr(pipeline.AI,'ask',ask)
    write_json(tmp_path/'job.json',{'input_kind':'text','title':'Test','slide_count':1,'extension':'.txt'})
    (tmp_path/'input.txt').write_text('Tim menyepakati uji coba.',encoding='utf-8')
    updates=[]
    run_job(tmp_path,lambda **kw:updates.append(kw))
    assert len(calls)==5
    assert updates[-1]['status']=='needs_review'
    assert 'belum lolos' in (tmp_path/'summary.md').read_text(encoding='utf-8')

def test_audio_decoder_compatibility_without_model(tmp_path):
    import wave
    from faster_whisper.audio import decode_audio
    path=tmp_path/'silence.wav'
    with wave.open(str(path),'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b'\x00\x00'*16000)
    samples=decode_audio(str(path))
    assert len(samples)==16000

def test_n8n_proxy_forwarding_and_failure(client,headers,monkeypatch):
    import httpx
    captured=[]
    class FakeClient:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kw):
            captured.append((url,kw))
            return httpx.Response(202,json={'job_id':'test-id','status':'queued'})
    monkeypatch.setattr(httpx,'AsyncClient',FakeClient)
    response=client.post('/api/n8n-jobs',headers=headers,files={'file':('a.txt',b'Contoh diskusi')},data={'slide_count':6})
    assert response.status_code==202
    assert captured[0][1]['data']['slide_count']=='6'
    assert captured[0][1]['headers']['X-Local-Token']==app_module.LOCAL_TOKEN
    assert client.post('/api/n8n-jobs',files={'file':('a.txt',b'text')}).status_code==403
    class BrokenClient(FakeClient):
        async def post(self,url,**kw):raise httpx.ConnectError('not running')
    monkeypatch.setattr(httpx,'AsyncClient',BrokenClient)
    assert client.post('/api/n8n-jobs',headers=headers,files={'file':('a.txt',b'text')}).status_code==502

def test_reload_configuration_blocked_while_work_is_active(client,headers,monkeypatch):
    import dotenv
    calls=[]
    monkeypatch.setattr(dotenv,'load_dotenv',lambda *a,**kw:calls.append(kw))
    response=client.post('/api/reload-config',headers=headers)
    assert response.status_code==200 and calls[0]['override'] is True
    client.post('/api/jobs',headers=headers,files={'file':('a.txt',b'text')})
    assert client.post('/api/reload-config',headers=headers).status_code==409

def test_staged_n8n_flow_requires_each_phase_and_preserves_results(client,headers,tmp_path,monkeypatch):
    import pipeline
    from schemas import Extraction,Fact
    response=client.post('/api/jobs',headers=headers,files={'file':('a.txt',b'Tim menyepakati uji coba.')},data={'orchestrator':'n8n','slide_count':4})
    assert response.status_code==202
    job=response.json();job_id=job['id'];target=tmp_path/job_id
    assert job['status']=='waiting' and app_module.TASKS.empty()
    assert client.post(f'/api/jobs/{job_id}/stages/summarize',headers=headers).status_code==409
    assert client.post(f'/api/jobs/{job_id}/stages/unknown',headers=headers).status_code==404
    assert client.post(f'/api/jobs/{job_id}/stages/transcribe',headers=headers).status_code==202
    assert client.post(f'/api/jobs/{job_id}/stages/transcribe',headers=headers).status_code==202
    assert app_module.TASKS.qsize()==1
    def execute_expected(phase):
        task=app_module.TASKS.get_nowait();app_module.TASKS.task_done()
        assert task==(job_id,phase)
        pipeline.run_stage(target,phase,lambda **kw:app_module.update_job(target,**kw))
    execute_expected('transcribe')
    assert app_module.read_job(target)['completed_stages']==['transcribe']
    original=(target/'transcript.txt').read_bytes()
    calls=[]
    report=sample_report()
    report.slides=[report.slides[0].model_copy(deep=True) for _ in range(4)]
    def ask(self,schema,instruction,payload,max_tokens=6000):
        calls.append(schema.__name__)
        if schema is Extraction:
            return Extraction(facts=[Fact(text='Tim menyepakati uji coba.',quote='Tim menyepakati uji coba.',source_ids=['S00001'])])
        return report if schema is Report else Review(passed=True,issues=[])
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    monkeypatch.setattr(pipeline.AI,'ask',ask)
    assert client.post(f'/api/jobs/{job_id}/stages/summarize',headers=headers).status_code==202
    execute_expected('summarize')
    assert app_module.read_job(target)['status']=='waiting'
    assert client.post(f'/api/jobs/{job_id}/stages/summarize',headers=headers).status_code==202
    assert app_module.TASKS.empty()
    assert client.post(f'/api/jobs/{job_id}/stages/quality',headers=headers).status_code==202
    execute_expected('quality')
    assert client.post(f'/api/jobs/{job_id}/stages/render',headers=headers).status_code==202
    execute_expected('render')
    final=client.get(f'/api/jobs/{job_id}').json()
    assert final['status']=='completed'
    assert final['completed_stages']==['transcribe','summarize','quality','render']
    assert calls==['Extraction','Report','Review']
    assert (target/'presentation.pptx').is_file()
    assert (target/'transcript.txt').read_bytes()==original
    assert client.post(f'/api/jobs/{job_id}/retry',headers=headers).status_code==409


def test_adopt_old_job_and_resume_through_n8n(client,headers,tmp_path,monkeypatch):
    import httpx
    job=client.post('/api/jobs',headers=headers,files={'file':('a.txt',b'Isi diskusi.')}).json()
    job_id=job['id'];target=tmp_path/job_id
    app_module.update_job(target,status='failed')
    (target/'transcript.txt').write_text('hasil tersimpan',encoding='utf-8')
    captured=[]
    class FakeClient:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kw):
            captured.append((url,kw))
            return httpx.Response(202,json={'job_id':job_id,'status':'waiting'})
    monkeypatch.setattr(httpx,'Client',FakeClient)
    assert client.post('/api/n8n-resume/'+job_id,headers=headers).status_code==202
    assert app_module.read_job(target)['orchestrator']=='n8n'
    assert (target/'transcript.txt').read_text()=='hasil tersimpan'
    assert captured[0][1]['json']['job_id']==job_id


def test_workflow_graph_has_ordered_phase_polling():
    root=Path(__file__).resolve().parent
    data=json.loads((root/'n8n-workflow.json').read_text(encoding='utf-8'))
    byid={n['id']:n for n in data['nodes']}
    names={n['name'] for n in data['nodes']}
    for value in data['connections'].values():
        for group in value['main']:
            assert all(edge['node'] in names for edge in group)
    for stage in ['transcribe','summarize','quality','render']:
        assert '/stages/'+stage in byid[stage+'-start']['parameters']['url']
        assert stage in byid[stage+'-done']['parameters']['conditions']['conditions'][0]['leftValue']
        assert data['connections'][byid[stage+'-wait']['name']]['main'][0][0]['node']==byid[stage+'-status']['name']
    register=byid['register']['parameters']['bodyParameters']['parameters']
    assert {'name':'orchestrator','value':'n8n'} in register

def test_generated_pptx_has_no_orphan_content_type_declarations(tmp_path):
    import xml.etree.ElementTree as ET
    write_json(tmp_path/'report.json',sample_report().model_dump())
    render_pptx(tmp_path)
    with zipfile.ZipFile(tmp_path/'presentation.pptx') as archive:
        parts=set(archive.namelist())
        root=ET.fromstring(archive.read('[Content_Types].xml'))
        for node in root:
            if node.tag.endswith('Override'):
                assert node.attrib['PartName'].lstrip('/') in parts
