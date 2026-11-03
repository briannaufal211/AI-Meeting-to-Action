import json
from types import SimpleNamespace
import numpy as np
import pytest
from gpt_transcription import transcribe_gpt,audio_parts

class Client:
 def __init__(self,error=None):self.calls=[];self.error=error;self.audio=SimpleNamespace(transcriptions=self)
 def create(self,**kw):
  self.calls.append({k:v for k,v in kw.items() if k!='file'})
  if self.error:raise self.error
  return SimpleNamespace(text='Keputusan masih perlu dikonfirmasi.',_request_id='mock-request')

def setup(tmp_path,monkeypatch):
 monkeypatch.setenv('TRANSCRIPTION_MODEL','gpt-transcribe');monkeypatch.setenv('TRANSCRIPTION_LANGUAGES','id');monkeypatch.setenv('MAX_TRANSCRIPTION_USD_PER_JOB','.60')
 audio=tmp_path/'source.wav';audio.write_bytes(b'fictional audio stub for mocked requests')
 return audio,np.ones(16000,dtype='float32')*.05

def test_gpt_request_cache_and_shared_ledger(tmp_path,monkeypatch):
 audio,samples=setup(tmp_path,monkeypatch);c=Client()
 result=transcribe_gpt(audio,tmp_path,lambda **k:None,c,samples)
 assert result['model']=='gpt-transcribe' and result['accuracy_measured'] is False
 assert c.calls[0]['extra_body']=={'languages':['id'],'keywords':[]}
 transcribe_gpt(audio,tmp_path,lambda **k:None,c,samples)
 assert len(c.calls)==1
 usage=json.loads((tmp_path/'usage.json').read_text());assert usage['audio_calls']==usage['calls']==1 and usage['audio_estimated_usd']>0
 # Resume repairs missing usage from durable checkpoint without another upload.
 (tmp_path/'usage.json').unlink();transcribe_gpt(audio,tmp_path,lambda **k:None,c,samples)
 assert len(c.calls)==1 and json.loads((tmp_path/'usage.json').read_text())['audio_calls']==1

def test_unknown_network_result_never_reuploads(tmp_path,monkeypatch):
 audio,samples=setup(tmp_path,monkeypatch);c=Client(TimeoutError('mock timeout'))
 with pytest.raises(TimeoutError):transcribe_gpt(audio,tmp_path,lambda **k:None,c,samples)
 with pytest.raises(ValueError,match='belum pasti'):transcribe_gpt(audio,tmp_path,lambda **k:None,c,samples)
 assert len(c.calls)==1

@pytest.mark.parametrize('case',['money','calls','context'])
def test_prechecks_prevent_any_paid_request(tmp_path,monkeypatch,case):
 audio,samples=setup(tmp_path,monkeypatch);c=Client()
 if case=='money':monkeypatch.setenv('MAX_TRANSCRIPTION_USD_PER_JOB','0')
 if case=='calls':monkeypatch.setenv('MAX_PAID_CALLS_PER_JOB','0')
 if case=='context':monkeypatch.setenv('TRANSCRIPTION_CONTEXT','x'*501)
 with pytest.raises(ValueError):transcribe_gpt(audio,tmp_path,lambda **k:None,c,samples)
 assert not c.calls

def test_changed_source_blocks_old_checkpoints(tmp_path,monkeypatch):
 audio,samples=setup(tmp_path,monkeypatch);c=Client();transcribe_gpt(audio,tmp_path,lambda **k:None,c,samples)
 audio.write_bytes(b'changed')
 with pytest.raises(ValueError,match='berubah'):transcribe_gpt(audio,tmp_path,lambda **k:None,c,samples)
 assert len(c.calls)==1

def test_splitting_never_gaps_or_duplicates_audio():
 values=np.ones(1420*16000,dtype='float32')*.1
 parts=list(audio_parts(values));assert parts[0][0]==0 and parts[-1][1]==len(values)
 assert all(a[1]==b[0] for a,b in zip(parts,parts[1:]))
 assert all(2*(end-start)+44<25_000_000 for start,end in parts)

def test_text_usage_adds_audio_cost(tmp_path,monkeypatch):
 import pipeline
 from schemas import Review
 audio,samples=setup(tmp_path,monkeypatch);transcribe_gpt(audio,tmp_path,lambda **k:None,Client(),samples)
 monkeypatch.setenv('OPENAI_API_KEY','mock-only')
 response=SimpleNamespace(id='mock-text',usage=SimpleNamespace(input_tokens=100,output_tokens=50),output_parsed=Review(passed=True,issues=[]))
 monkeypatch.setattr(pipeline,'OpenAI',lambda **kw:SimpleNamespace(responses=SimpleNamespace(parse=lambda **k:response)))
 ai=pipeline.AI(tmp_path);ai.ask(Review,'test',{})
 usage=json.loads((tmp_path/'usage.json').read_text())
 assert usage['calls']==2 and usage['estimated_usd']==round(usage['text_estimated_usd']+usage['audio_estimated_usd'],6)


def test_saved_response_recovers_interrupted_ledger_without_upload(tmp_path,monkeypatch):
 audio,samples=setup(tmp_path,monkeypatch);c=Client();transcribe_gpt(audio,tmp_path,lambda **k:None,c,samples)
 path=tmp_path/'cost-control.json';ledger=json.loads(path.read_text());ledger['requests'][0]['status']='in_flight';path.write_text(json.dumps(ledger))
 transcribe_gpt(audio,tmp_path,lambda **k:None,c,samples)
 assert len(c.calls)==1 and json.loads(path.read_text())['requests'][0]['status']=='completed'
