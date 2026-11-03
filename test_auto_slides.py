"""Automatic-count contracts with in-memory uploads and simulated AI only."""
import io,json,tempfile
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from fastapi import UploadFile,HTTPException
import app as application
import pipeline
from schemas import Extraction,Fact,Report,Slide,Claim,Review

def upload(data, filename='x.txt'):
    stream=tempfile.SpooledTemporaryFile(max_size=1024*1024)
    stream.write(data);stream.seek(0)
    return UploadFile(filename=filename,file=stream)


def finish_immediate(coro):
    # In-memory UploadFile and all mocked async operations finish without a portal/socket.
    try:coro.send(None)
    except StopIteration as result:return result.value
    finally:coro.close()
    raise AssertionError('Unexpected asynchronous I/O in offline test')

def report(count):
    return Report(title='Contoh',summary=[Claim(text='Tim sepakat uji coba.',fact_ids=['F0001'])],decisions=[],actions=[],uncertainties=[],slides=[Slide(title=f'Topik {n+1}',bullets=[Claim(text='Tim sepakat uji coba.',fact_ids=['F0001'])],notes='Materi rekaan.') for n in range(count)])

def test_auto_upload_persists_zero_and_rejects_invalid_counts(tmp_path,monkeypatch):
    monkeypatch.setattr(application,'DATA',tmp_path)
    file=upload(b'Tim sepakat uji coba.','contoh.txt')
    result=finish_immediate(application.submit(file=file,title='Uji',slide_count=0,orchestrator='n8n'))
    saved=json.loads((tmp_path/result['id']/'job.json').read_text())
    assert saved['slide_count']==0 and saved['status']=='waiting'
    for count in [-1,1,17]:
        with pytest.raises(HTTPException) as e:
            finish_immediate(application.submit(file=upload(b'x'),title='Uji',slide_count=count,orchestrator='n8n'))
        assert e.value.status_code==422

def test_n8n_proxy_forwards_auto_sentinel_as_multipart_string(monkeypatch):
    import httpx
    captured=[]
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kwargs):
            captured.append(kwargs)
            return SimpleNamespace(status_code=202,json=lambda:{'id':'example'})
    monkeypatch.setattr(httpx,'AsyncClient',Client)
    result=finish_immediate(application.submit_through_n8n(file=upload(b'Uji'),title='Uji',slide_count=0))
    assert result['id']=='example' and captured[0]['data']['slide_count']=='0'

@pytest.mark.parametrize('count',[1,3,12])
def test_auto_generation_accepts_content_driven_counts_without_extra_call(count,tmp_path,monkeypatch):
    calls=[]
    class FakeAI:
        def __init__(self,output):self.journal=SimpleNamespace(data={'requests':[]})
        def ask(self,schema,instruction,payload,max_tokens=6000):
            calls.append((schema,instruction))
            if schema is Extraction:return Extraction(facts=[Fact(text='Tim sepakat uji coba.',quote='Tim sepakat uji coba.',source_ids=['S00001'])])
            if schema is Report:return report(count)
            return Review(passed=True,issues=[])
    monkeypatch.setattr(pipeline,'AI',FakeAI)
    monkeypatch.setattr(pipeline,'local_preflight',lambda output:None)
    events=[]
    result,review=pipeline.summarize({'segments':[{'id':'S00001','text':'Tim sepakat uji coba.'}]},tmp_path,0,'Uji',lambda **kw:events.append(kw))
    assert len(result.slides)==count and review.passed
    assert [c[0] for c in calls]==[Extraction,Report,Review]
    assert 'berdasarkan jumlah topik' in calls[1][1] and 'tepat 0 slide' not in calls[1][1]
    assert events[-1]['selected_slide_count']==count and events[-1]['slide_count_mode']=='auto'
    with pytest.raises(ValueError):pipeline.validate_slide_count(result,4 if count!=4 else 6)

def test_manual_count_instruction_still_demands_exact_count():
    assert 'tepat 6 slide' in pipeline.slide_count_instruction(6)
    pipeline.validate_slide_count(report(6),6)
