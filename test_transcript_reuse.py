from pathlib import Path
import json
from types import SimpleNamespace
import pytest
from transcript_reuse import reuse_speaker_transcript
import pipeline as p

def source(tmp_path):
    old=tmp_path/'old';new=tmp_path/'new';old.mkdir();new.mkdir();(old/'ai-cache').mkdir()
    for sig in ['primary','voice']:p.write_json(old/'ai-cache'/(sig+'.json'),{'text':'Teks','segments':[]})
    p.write_json(old/'transcript.json',{'segments':[{'id':'S1','text':'Belum disetujui.','speaker':'Pembicara 1'}]})
    (old/'transcript.txt').write_text('Belum disetujui.',encoding='utf-8')
    p.write_json(old/'transcription-alignment.json',{'word_sequence_preserved':True})
    p.write_json(old/'usage.json',{'estimated_usd':99});p.write_json(old/'cost-control.json',{'requests':[{'status':'completed'}]})
    return old,new

def test_identical_checkpoint_reuse_does_not_copy_spend_or_change_source(tmp_path):
    old,new=source(tmp_path);original=(old/'transcript.json').read_bytes()
    result=reuse_speaker_transcript(new,['primary','voice'],p.write_json)
    assert result['reused_from_job']=='old' and (new/'transcript.txt').read_text()=='Belum disetujui.'
    assert not (new/'usage.json').exists() and not (new/'cost-control.json').exists()
    assert (old/'transcript.json').read_bytes()==original

def test_changed_model_context_signature_does_not_reuse(tmp_path):
    old,new=source(tmp_path)
    assert reuse_speaker_transcript(new,['primary-changed','voice'],p.write_json) is None

def test_incomplete_alignment_or_existing_paid_attempt_is_not_called_free(tmp_path):
    old,new=source(tmp_path);p.write_json(old/'transcription-alignment.json',{'word_sequence_preserved':False})
    assert reuse_speaker_transcript(new,['primary','voice'],p.write_json) is None
    p.write_json(old/'transcription-alignment.json',{'word_sequence_preserved':True})
    p.write_json(new/'cost-control.json',{'requests':[{'status':'completed'}]})
    assert reuse_speaker_transcript(new,['primary','voice'],p.write_json) is None

def test_cache_only_recovery_blocks_before_network_or_billing(monkeypatch):
    monkeypatch.setenv('WORKFLOW_CACHE_ONLY','1')
    journal=SimpleNamespace(signature=lambda *a:'s',get=lambda *a:None,begin=lambda *a:pytest.fail('No paid attempt'))
    with pytest.raises(ValueError,match='tanpa biaya'):p.AI.ask(SimpleNamespace(journal=journal),object,'instruction',{})

def test_audio_entrypoint_reuses_exact_configuration_without_client_or_spend(tmp_path,monkeypatch):
    import audio_speakers as audio
    from cost_control import CallJournal
    old,new=source(tmp_path)
    monkeypatch.setenv('TRANSCRIPTION_CONTEXT','Sumber yang sama')
    monkeypatch.setenv('TRANSCRIPTION_LANGUAGES','id,en')
    monkeypatch.setenv('MAX_TRANSCRIPTION_USD_PER_JOB','0')
    monkeypatch.setenv('WORKFLOW_CACHE_ONLY','1')
    monkeypatch.setattr(audio,'compress_audio',lambda *a:1800)
    monkeypatch.setattr(audio,'hashfile',lambda *a:'identical-file-hash')
    monkeypatch.setattr(audio,'OpenAI',lambda *a,**k:pytest.fail('No API client should be created'))
    common={'source_sha256':'identical-file-hash','upload_sha256':'identical-file-hash','context':'Sumber yang sama','languages':['id','en']}
    for model in ['gpt-transcribe','gpt-4o-transcribe-diarize']:
        journal=CallJournal(old,model,p.write_json)
        signature=journal.signature(audio.AudioResult,'Sumber yang sama',common,0)
        journal.store(signature,audio.AudioResult(text='Belum disetujui.'))
    result=audio.transcribe_with_speakers(tmp_path/'input.mp3',new,lambda **kw:None)
    assert result['reused_from_job']=='old'
    assert json.loads((new/'usage.json').read_text())['audio_calls']==0
    assert not (new/'cost-control.json').exists()
