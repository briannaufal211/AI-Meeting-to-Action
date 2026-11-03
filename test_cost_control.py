import json
from pathlib import Path
from types import SimpleNamespace
import pytest
import httpx
from openai import OpenAI as SDK, APITimeoutError
import pipeline
from schemas import Extraction, Fact, Report, Review


def attach_mock(monkeypatch, handler):
    settings=[]
    def factory(**kw):
        settings.append(kw)
        return SDK(api_key='test-only',max_retries=kw['max_retries'],http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    monkeypatch.setattr(pipeline,'OpenAI',factory)
    return settings


def reply(parsed):
    return httpx.Response(200,json={'id':'resp_mock','object':'response','created_at':1,'status':'completed',
        'model':'gpt-4.1-mini','output':[{'type':'message','id':'msg_mock','role':'assistant','status':'completed',
        'content':[{'type':'output_text','text':parsed.model_dump_json(),'annotations':[]}]}],
        'usage':{'input_tokens':100,'output_tokens':50,'total_tokens':150}})


def extraction():
    return Extraction(facts=[Fact(text='Uji coba disepakati.',quote='Uji coba disepakati.',source_ids=['S00001'])])


def test_cache_persisted_and_call_cap_enforced(tmp_path,monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request)
        return reply(extraction())
    settings=attach_mock(monkeypatch,handler)
    monkeypatch.setenv('MAX_PAID_CALLS_PER_JOB','1')
    ai=pipeline.AI(tmp_path)
    first=ai.ask(Extraction,'ambil fakta',{'text':'Uji coba disepakati.'})
    second=pipeline.AI(tmp_path).ask(Extraction,'ambil fakta',{'text':'Uji coba disepakati.'})
    assert first==second and len(calls)==1
    assert settings[0]['max_retries']==0
    with pytest.raises(ValueError,match='Batas jumlah'):
        pipeline.AI(tmp_path).ask(Extraction,'permintaan lain',{'text':'Materi berbeda.'})
    assert len(calls)==1


def test_uncertain_timeout_never_retried_automatically(tmp_path,monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('simulasi respons hilang',request=request)
    attach_mock(monkeypatch,handler)
    with pytest.raises(APITimeoutError):
        pipeline.AI(tmp_path).ask(Extraction,'ambil',{'text':'contoh'})
    assert len(calls)==1
    with pytest.raises(ValueError,match='Tidak dikirim ulang'):
        pipeline.AI(tmp_path).ask(Extraction,'ambil',{'text':'contoh'})
    assert len(calls)==1
    ledger=json.loads((tmp_path/'cost-control.json').read_text())
    assert ledger['requests'][0]['status']=='uncertain'


def test_ppt_preflight_failure_prevents_ai_calls(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    calls=[]
    monkeypatch.setattr(pipeline.AI,'ask',lambda *a,**kw:calls.append(1))
    def broken(output):raise ValueError('Node tidak siap')
    monkeypatch.setattr(pipeline,'render_pptx',broken)
    with pytest.raises(ValueError,match='Node tidak siap'):
        pipeline.summarize({'segments':[{'id':'S00001','text':'contoh'}]},tmp_path,4,'Test',lambda **kw:None)
    assert calls==[]


def test_preflight_call_plan_blocks_before_any_ai(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    monkeypatch.setenv('MAX_PAID_CALLS_PER_JOB','2')
    calls=[]
    monkeypatch.setattr(pipeline.AI,'ask',lambda *a,**kw:calls.append(1))
    with pytest.raises(ValueError,match='melebihi sisa batas'):
        pipeline.summarize({'segments':[{'id':'S00001','text':'contoh'}]},tmp_path,4,'Test',lambda **kw:None)
    assert calls==[] and (tmp_path/'preflight.json').exists()


def test_ai_review_failure_does_not_trigger_paid_revision_by_default(tmp_path,monkeypatch):
    from test_project import sample_report
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    monkeypatch.setenv('MAX_AI_REVISIONS','0')
    calls=[]
    def ask(self,schema,*args,**kw):
        calls.append(schema)
        if schema is Extraction:return extraction()
        if schema is Report:return sample_report()
        return Review(passed=False,issues=['Perlu pemeriksaan manual.'])
    monkeypatch.setattr(pipeline.AI,'ask',ask)
    result,review=pipeline.summarize({'segments':[{'id':'S00001','text':'Uji coba disepakati.'}]},tmp_path,1,'Test',lambda **kw:None)
    assert len(calls)==3 and not review.passed

def test_luna_request_uses_low_reasoning_without_changing_other_models(tmp_path,monkeypatch):
    bodies=[]
    def handler(request):
        bodies.append(json.loads(request.content))
        return reply(extraction())
    attach_mock(monkeypatch,handler)
    monkeypatch.setenv('OPENAI_MODEL','gpt-6-luna')
    pipeline.AI(tmp_path).ask(Extraction,'ambil',{'text':'contoh'})
    assert bodies[0]['reasoning']['effort']=='low'
    assert bodies[0]['model']=='gpt-6-luna'
